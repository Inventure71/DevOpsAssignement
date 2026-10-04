"""Expiring, browser-bound PKCE receipts and background imports, without SQL."""

import base64
import hashlib
import logging
import secrets
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from backend.core.errors import DomainError

LIFETIME_SECONDS = 15 * 60
logger = logging.getLogger(__name__)


@dataclass
class Receipt:
    state: str
    verifier: str
    payload: dict
    expires: float
    status: str = "pending"
    admission: dict | None = None
    error: dict | None = None


class MusicAdmissions:
    def __init__(self, spotify, importer, admit, *, enabled, clock=time.monotonic):
        self.spotify, self.importer, self.admit = spotify, importer, admit
        self.enabled, self.clock = enabled, clock
        self._receipts = {}
        self._lock = threading.RLock()
        self._workers = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="music-import"
        )
        self._closed = False

    def begin(self, payload, existing=None):
        if not self.enabled:
            raise DomainError(
                "music_not_configured",
                "Spotify and Apple Music must be configured for Normal mode.",
                503,
            )
        with self._lock:
            self._prune()
            old = self._receipts.get(existing)
            if old and old.status in ("pending", "processing"):
                raise DomainError(
                    "music_admission_in_progress",
                    "A Spotify sign-in is already in progress in this browser.",
                    409,
                )
            if self._closed or len(self._receipts) >= 64:
                raise DomainError(
                    "music_admission_busy",
                    "Music sign-in is busy. Try again shortly.",
                    503,
                )
            credential = secrets.token_urlsafe(32)
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            authorization_url = self.spotify.authorization_url(state, challenge)
            self._receipts[credential] = Receipt(
                state, verifier, dict(payload), self.clock() + LIFETIME_SECONDS
            )
            return credential, authorization_url

    def callback(self, credential, state, code=None, error=None):
        with self._lock:
            receipt = self._get(credential)
            if not isinstance(state, str) or not secrets.compare_digest(
                receipt.state, state
            ):
                raise DomainError(
                    "invalid_music_state",
                    "This Spotify sign-in could not be verified. Start again.",
                    400,
                )
            if receipt.status != "pending":
                raise DomainError(
                    "music_callback_used",
                    "This Spotify sign-in has already been processed.",
                    409,
                )
            if error or not code:
                self._fail(
                    receipt,
                    DomainError(
                        "music_authorization_denied",
                        "Spotify sign-in was cancelled or refused.",
                        400,
                    ),
                )
                return
            if (
                sum(item.status == "processing" for item in self._receipts.values())
                >= 8
            ):
                self._fail(
                    receipt,
                    DomainError(
                        "music_admission_busy",
                        "Music import is busy. Start again shortly.",
                        503,
                    ),
                )
                return
            receipt.status = "processing"
            receipt.state = ""
            self._workers.submit(self._import, credential, code, receipt.verifier)
            receipt.verifier = ""

    def _import(self, credential, code, verifier):
        token = None
        try:
            with self._lock:
                self._get(credential)
            token = self.spotify.exchange_code(code, verifier)
            with self._lock:
                receipt = self._get(credential)
                payload = dict(receipt.payload)
            imported = self.importer.import_account(
                token, include_decoys=not payload.get("room_id")
            )
            token = None
            with self._lock:
                receipt = self._get(credential)
                if self._closed:
                    return
                receipt.admission = self.admit(
                    payload, imported, lambda: self.clock() < receipt.expires
                )
                receipt.status = "complete"
                receipt.expires = self.clock() + LIFETIME_SECONDS
                receipt.payload = {}
        except DomainError as exc:
            with self._lock:
                receipt = self._receipts.get(credential)
                if receipt:
                    self._fail(receipt, exc)
        except Exception as exc:
            # Log source frames, never exception text or locals: provider errors
            # can contain tokens, authorization codes or personal account data.
            logger.error(
                "Unexpected music import failure (%s); frames=%s",
                type(exc).__name__,
                [
                    (frame.filename, frame.lineno, frame.name)
                    for frame in traceback.extract_tb(exc.__traceback__)
                ],
            )
            with self._lock:
                receipt = self._receipts.get(credential)
                if receipt:
                    self._fail(
                        receipt,
                        DomainError(
                            "music_import_failed",
                            "Music import failed. Start Spotify sign-in again.",
                            503,
                        ),
                    )
        finally:
            token = None

    def status(self, credential):
        with self._lock:
            receipt = self._get(credential)
            return {
                "status": receipt.status,
                **({"error": dict(receipt.error)} if receipt.error else {}),
            }, receipt.admission

    def cancel(self, credential):
        with self._lock:
            self._receipts.pop(credential, None)

    def close(self):
        with self._lock:
            self._closed = True
            self._receipts.clear()
        self._workers.shutdown(wait=False, cancel_futures=True)

    def _get(self, credential):
        self._prune()
        receipt = self._receipts.get(credential)
        if receipt is None:
            raise DomainError(
                "music_admission_expired", "Spotify sign-in expired. Start again.", 401
            )
        return receipt

    def _prune(self):
        now = self.clock()
        self._receipts = {
            key: value for key, value in self._receipts.items() if value.expires > now
        }

    @staticmethod
    def _fail(receipt, exc):
        logger.warning("Music admission failed: code=%s", exc.code)
        receipt.status = "failed"
        receipt.error = {
            "code": exc.code,
            "message": exc.message,
            "details": dict(exc.details),
            "retryable": exc.status in (429, 503),
        }
        delay = exc.details.get("retry_after_seconds")
        if exc.status == 429 and isinstance(delay, int) and delay > 0:
            receipt.error["message"] += f" Try again in {delay} seconds."
        receipt.state = receipt.verifier = ""
        receipt.payload = {}
