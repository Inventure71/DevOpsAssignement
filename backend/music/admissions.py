"""Browser-bound connection receipts; provider work precedes atomic admission."""

import logging
import secrets
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from backend.core.errors import DomainError
from backend.music.authorization import AuthorizationFlow

LIFETIME_SECONDS = 15 * 60
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectedSource:
    label: str
    authorization: AuthorizationFlow
    importer: Any
    enabled: bool


@dataclass(repr=False)
class Receipt:
    provider: str
    context: Any
    payload: dict
    expires: float
    admission_id: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    status: str = "pending"
    admission: dict | None = None
    error: dict | None = None


class MusicAdmissions:
    def __init__(self, providers, admit, *, clock=time.monotonic):
        self.providers, self.admit, self.clock = dict(providers), admit, clock
        self._receipts = {}
        self._lock = threading.RLock()
        self._workers = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="music-import"
        )
        self._closed = False

    @property
    def enabled(self):
        return any(source.enabled for source in self.providers.values())

    def require_provider(self, provider):
        source = self.providers.get(provider)
        if source is None or not source.enabled:
            raise DomainError(
                "music_provider_unavailable",
                "This music connection is unavailable.",
                503,
            )
        return source

    def configuration(self, origin):
        return {
            provider: {
                "id": provider,
                "label": source.label,
                "enabled": source.enabled,
                "reason": None if source.enabled else "Unavailable in this session.",
                **source.authorization.configuration(origin),
            }
            for provider, source in self.providers.items()
        }

    def begin(self, payload, existing=None, *, origin):
        provider = payload["provider"]
        source = self.require_provider(provider)
        with self._lock:
            self._prune()
            old = self._receipts.get(existing)
            if old and old.status in ("pending", "processing", "complete"):
                raise DomainError(
                    "music_admission_in_progress",
                    "Finish or cancel the current music connection first.",
                    409,
                )
            if self._closed or len(self._receipts) >= 64:
                raise DomainError(
                    "music_admission_busy",
                    "Music sign-in is busy. Try again shortly.",
                    503,
                )
            credential = secrets.token_urlsafe(32)
            action, context = source.authorization.begin(origin)
            self._receipts[credential] = Receipt(
                provider, context, dict(payload), self.clock() + LIFETIME_SECONDS
            )
            return credential, action

    def callback(self, credential, provider, response):
        with self._lock:
            receipt = self._get(credential)
            if receipt.provider != provider:
                raise DomainError(
                    "invalid_music_provider",
                    "This connection belongs to another provider.",
                    400,
                )
            if receipt.status != "pending":
                raise DomainError(
                    "music_callback_used",
                    "This music sign-in has already been processed.",
                    409,
                )
            source = self.require_provider(provider)
            try:
                source.authorization.validate(receipt.context, response)
            except DomainError as exc:
                if exc.code == "invalid_music_state":
                    raise
                self._fail(receipt, exc)
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
            context = receipt.context
            receipt.context = None
            receipt.status = "processing"
            self._workers.submit(
                self._import, credential, source, context, dict(response)
            )

    def _import(self, credential, source, context, response):
        token = None
        try:
            with self._lock:
                self._get(credential)
            token = source.authorization.finish(context, response)
            context = response = None
            with self._lock:
                payload = dict(self._get(credential).payload)
            imported = source.importer.import_account(
                token, include_decoys=not payload.get("room_id")
            )
            token = None
            if imported.get("provider") != payload["provider"]:
                raise DomainError(
                    "invalid_music_import",
                    "The music source returned a different provider.",
                    503,
                )
            # Cancellation takes this same lock. It either removes the receipt
            # before SQL writes, or returns the completed room credential.
            with self._lock:
                receipt = self._get(credential)
                if self._closed:
                    return
                receipt.admission = self.admit(
                    payload, imported, lambda: self.clock() < receipt.expires
                )
                receipt.status = "complete"
                receipt.expires = self.clock() + LIFETIME_SECONDS
        except DomainError as exc:
            with self._lock:
                receipt = self._receipts.get(credential)
                if receipt:
                    self._fail(receipt, exc)
        except Exception as exc:  # noqa: BLE001 - worker boundary must record failure
            # Provider errors may contain credentials; retain stack frames only.
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
                            "Music import failed. Connect your music again.",
                            503,
                        ),
                    )
        finally:
            token = context = response = None

    @staticmethod
    def _result(receipt):
        return {
            "admission_id": receipt.admission_id,
            "status": receipt.status,
            "provider": receipt.provider,
            "connection": dict(receipt.payload),
            **({"error": dict(receipt.error)} if receipt.error else {}),
        }, receipt.admission

    def status(self, credential):
        with self._lock:
            return self._result(self._get(credential))

    def cancel(self, credential):
        with self._lock:
            self._prune()
            receipt = self._receipts.get(credential)
            if receipt and receipt.status == "complete":
                return self._result(receipt)
            self._receipts.pop(credential, None)
            return {"status": "cancelled"}, None

    def acknowledge(self, credential, admission_id):
        """Retire only the completed connection accepted by this browser tab."""
        with self._lock:
            self._prune()
            receipt = self._receipts.get(credential)
            if receipt is None:
                return True  # An already retired receipt is safe to acknowledge again.
            if receipt.admission_id != admission_id:
                return False  # Another tab has replaced the shared cookie.
            if receipt.status != "complete":
                raise DomainError(
                    "music_admission_incomplete",
                    "The music connection is not complete.",
                    409,
                )
            self._receipts.pop(credential, None)
            return True

    def retire_player(self, room_id, player_id):
        """Explicit Leave retires unacknowledged delivery receipts too."""
        with self._lock:
            self._receipts = {
                key: receipt
                for key, receipt in self._receipts.items()
                if not (
                    receipt.status == "complete"
                    and receipt.admission["room"]["id"] == room_id
                    and receipt.admission["player"]["id"] == player_id
                )
            }

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
                "music_admission_expired", "Music sign-in expired. Start again.", 401
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
        receipt.context = None
        receipt.error = {
            "code": exc.code,
            "message": exc.message,
            "details": dict(exc.details),
            "retryable": exc.status in (429, 503),
        }
        delay = exc.details.get("retry_after_seconds")
        if exc.status == 429 and isinstance(delay, int) and delay > 0:
            receipt.error["message"] += f" Try again in {delay} seconds."
