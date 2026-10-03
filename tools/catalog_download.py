"""Bounded, resumable downloads verified against the publisher's SHA-256."""

import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


MAX_ARCHIVE_BYTES = 8 * 1024**3
CHUNK_BYTES = 1024**2


def _open(request):
    return urlopen(request, timeout=30)


def archive_info(url, opener=_open):
    with opener(Request(url, method='HEAD', headers={'Accept-Encoding': 'identity'})) as response:
        size = int(response.headers.get('Content-Length', '0'))
        validator = response.headers.get('ETag') or response.headers.get('Last-Modified')
    if not 0 < size <= MAX_ARCHIVE_BYTES:
        raise ValueError('Archive size is missing or exceeds the 8 GiB safety limit')
    with opener(Request(url + '.sha256')) as response:
        checksum = response.read(1025).decode('ascii').strip()
    if not re.fullmatch(r'[a-fA-F0-9]{64}', checksum):
        raise ValueError('Expected the official plain SHA-256 checksum')
    return {'url': url, 'bytes': size, 'sha256': checksum.lower(), 'validator': validator}


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def download_archive(info, destination, opener=_open, progress=None):
    """Retain interrupted bytes; publish the final path only after verification."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + '.part')
    state = destination.with_name(destination.name + '.partial.json')
    verified = destination.with_name(destination.name + '.verified.json')
    if destination.exists():
        if destination.stat().st_size != info['bytes'] or _sha256(destination) != info['sha256']:
            raise ValueError('Existing archive failed verification; move it aside before retrying')
        _write_json(verified, info)
        return destination

    try:
        previous = json.loads(state.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previous = None
    offset = part.stat().st_size if part.exists() and previous == info else 0
    if offset > info['bytes']:
        offset = 0
    if offset == 0 and part.exists():
        # Never associate an old prefix with a new source/hash if requesting the
        # new download fails before the response opens its output file.
        with part.open('wb'):
            pass
    _write_json(state, info)
    if offset != info['bytes']:
        headers = {'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
            if info['validator']:
                headers['If-Range'] = info['validator']
        with opener(Request(info['url'], headers=headers)) as response:
            if response.status == 206:
                expected = f'bytes {offset}-{info["bytes"] - 1}/{info["bytes"]}'
                if response.headers.get('Content-Range') != expected:
                    raise ValueError('Invalid resume Content-Range')
            elif response.status == 200:
                offset = 0  # A server may ignore Range or reject a stale validator.
            else:
                raise ValueError(f'Unexpected download status: {response.status}')
            remaining = info['bytes'] - offset
            if int(response.headers.get('Content-Length', '-1')) != remaining:
                raise ValueError('Download Content-Length disagrees with the official archive size')
            with part.open('ab' if offset else 'wb') as stream:
                received = 0
                while True:
                    chunk = response.read(min(CHUNK_BYTES, remaining - received + 1))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > remaining:
                        raise ValueError('Download exceeded its declared size')
                    stream.write(chunk)
                    if progress:
                        progress(offset + received, info['bytes'])
                if received != remaining:
                    raise ValueError('Download ended before its declared size; rerun to resume')
    if part.stat().st_size != info['bytes'] or _sha256(part) != info['sha256']:
        # A complete bad download cannot be resumed. Keep it for inspection, but
        # invalidate its partial state so the next attempt starts from byte zero.
        state.unlink(missing_ok=True)
        raise ValueError('Archive SHA-256 verification failed; rerun to download again')
    part.replace(destination)
    _write_json(verified, info)
    state.unlink(missing_ok=True)
    return destination
