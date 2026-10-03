#!/usr/bin/env python3
"""Download verified MusicBrainz metadata and stream it into the public catalog."""

import argparse
import codecs
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.catalog.importer import import_canonical
from backend.catalog.store import CatalogStore
from tools.catalog_download import archive_info, download_archive, _write_json


ROOT = Path(__file__).resolve().parents[1]
CSV_MEMBER = 'canonical_musicbrainz_data.csv'


def official_url(url, *, checksum=False):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'data.metabrainz.org'
            or parsed.query or parsed.fragment
            or not re.fullmatch(r'/pub/musicbrainz/canonical_data/'
                                r'musicbrainz-canonical-dump-[0-9-]+/'
                                r'musicbrainz-canonical-dump-[0-9-]+\.tar\.zst'
                                + (r'(?:\.sha256)?' if checksum else ''), parsed.path)):
        raise ValueError('Use an official HTTPS MusicBrainz canonical .tar.zst archive URL')
    return url


def official_open(request):
    official_url(request.full_url, checksum=True)
    response = urlopen(request, timeout=30)
    try:
        official_url(response.geturl(), checksum=True)
    except ValueError:
        response.close()
        raise
    return response


def import_archive(archive, database, zstd, limit):
    """Read one CSV directly from the decompression pipe; never extract files."""
    if Path(database).name == 'whos_on_repeat.sqlite3':
        raise ValueError('Catalog storage must be separate from the private game database')
    store = CatalogStore(database)
    store.initialize()
    process = subprocess.Popen([str(zstd), '-dc', str(archive)], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    try:
        result = None
        with tarfile.open(fileobj=process.stdout, mode='r|') as bundle:
            for member in bundle:
                if member.isfile() and Path(member.name).name == CSV_MEMBER:
                    if result is not None or member.name.startswith('/') or '..' in Path(member.name).parts:
                        raise ValueError('Duplicate or unsafe canonical CSV member')
                    # codecs avoids tarfile's non-seekable pipe wrapper querying
                    # seekable() on its internal _Stream (Python 3.12).
                    with bundle.extractfile(member) as raw:
                        stream = codecs.getreader('utf-8-sig')(raw)
                        result = import_canonical(stream, store, limit=limit)
                    if limit is not None:
                        return result
        if result is None:
            raise ValueError('Canonical metadata CSV is missing from the archive')
        # A complete import checks the decompressor's exit status too. Remaining
        # archive members are streamed past, without extraction or retention.
        for _ in iter(lambda: process.stdout.read(1024**2), b''):
            pass
        if process.wait(timeout=30) != 0:
            raise ValueError('zstd could not decode the complete archive')
        return result
    finally:
        # A bounded import or a CSV preceding other archive members intentionally
        # stops decompression early. The entire compressed archive was hashed.
        if process.poll() is None:
            process.terminate()
        process.stdout.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main(argv=None):
    pinned = json.loads((ROOT / 'backend/catalog/starter/provenance.json').read_text())['source_url']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=pinned, help='Pinned official canonical archive URL')
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('DATA_DIR', './data')))
    parser.add_argument('--limit', type=int, default=100000, help='Input rows to import; default 100000')
    parser.add_argument('--all', action='store_true', help='Import every row in the canonical CSV')
    parser.add_argument('--info', action='store_true', help='Print source, size and paths without writing files')
    parser.add_argument('--download-only', action='store_true', help='Verify and retain the archive without importing')
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error('--limit must be positive')
    try:
        official_url(args.url)
        # --info has no dependency on zstd and no filesystem side effects.
        zstd = shutil.which('zstd')
        if not args.info and not args.download_only and zstd is None:
            raise ValueError('zstd is required on PATH before downloading for import')
        info = archive_info(args.url, opener=official_open)
        archive = args.data_dir / 'catalog-downloads' / Path(urlsplit(args.url).path).name
        database = args.data_dir / 'catalog.sqlite3'
        print(json.dumps({**info, 'archive': str(archive), 'database': str(database),
                          'import_rows': 'all' if args.all else args.limit,
                          'note': 'The full compressed archive downloads even for a bounded import; metadata only, no audio.'}))
        if args.info:
            return 0
        last_report = 0

        def progress(downloaded, total):
            nonlocal last_report
            if downloaded - last_report >= 64 * 1024**2 or downloaded == total:
                print(f'Downloaded {downloaded / 1024**2:.0f}/{total / 1024**2:.0f} MiB', file=sys.stderr)
                last_report = downloaded

        download_archive(info, archive, opener=official_open, progress=progress)
        if args.download_only:
            return 0
        result = import_archive(archive, database, zstd, None if args.all else args.limit)
        _write_json(archive.with_name(archive.name + '.imported.json'),
                    {**info, **result, 'database': str(database), 'limit': None if args.all else args.limit})
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, sqlite3.DatabaseError, tarfile.TarError, RuntimeError) as error:
        print(f'Catalog setup failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
