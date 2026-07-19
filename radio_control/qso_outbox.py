"""Offline Wavelog upload outbox backed by an ADIF file."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from radio_control import config
from radio_control.wavelog_api import WavelogClient
from radio_control.persistence import atomic_write_text, durable_append_text, locked_file

logger = logging.getLogger(__name__)


class QSOOutbox:
    """Queue failed Wavelog uploads in ADIF and replay them later."""

    ADIF_HEADER = """Wavelog Offline Upload Outbox
<ADIF_VER:4>3.1.0
<PROGRAMID:19>OM0RX Radio Control
<PROGRAMVERSION:5>2.0.0
<EOH>"""

    def __init__(self, outbox_path: str | Path | None = None):
        self.outbox_path = Path(outbox_path or (config.LOGS_DIR / "wavelog_outbox.adif"))
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        self._replay_lock = asyncio.Lock()

    def enqueue(self, qso_data: Dict[str, Any], reason: str = "") -> bool:
        """Append one failed Wavelog upload to the outbox."""
        try:
            client = WavelogClient()
            record = client.build_adif_string(qso_data)
            if reason:
                record = self._add_app_note(record, f"Wavelog upload queued: {reason}")
            return self.enqueue_adif(record)
        except Exception as exc:
            logger.error("Failed to enqueue QSO in Wavelog outbox: %s", exc, exc_info=True)
            return False

    def enqueue_adif(self, adif_record: str) -> bool:
        """Append one ADIF record to the outbox, skipping exact duplicates."""
        try:
            normalized = self._normalize_record(adif_record)
            if not normalized:
                return False

            with locked_file(self.outbox_path):
                existing_records = self._records_unlocked()
                existing = set(existing_records)
                if normalized in existing:
                    logger.info("QSO already exists in Wavelog outbox; skipping duplicate")
                    return True
                identity = self._loose_identity(normalized)
                if identity and identity in {self._loose_identity(record) for record in existing_records}:
                    logger.info("QSO already exists in Wavelog outbox by call/date/band/mode; skipping duplicate")
                    return True

                self._ensure_file_unlocked()
                durable_append_text(self.outbox_path, normalized + "\n\n")
            logger.warning("Queued QSO for later Wavelog upload: %s", self.outbox_path)
            return True
        except Exception as exc:
            logger.error("Failed to write Wavelog outbox: %s", exc, exc_info=True)
            return False

    def records(self) -> list[str]:
        """Return queued ADIF records without the header."""
        with locked_file(self.outbox_path):
            return self._records_unlocked()

    def _records_unlocked(self) -> list[str]:
        if not self.outbox_path.exists():
            return []
        content = self.outbox_path.read_text(encoding="utf-8", errors="ignore")
        content = re.sub(r"^.*?<eoh>", "", content, flags=re.IGNORECASE | re.DOTALL)
        records = []
        for part in re.split(r"<eor>", content, flags=re.IGNORECASE):
            if "<call:" not in part.lower():
                continue
            records.append(self._normalize_record(part))
        return [record for record in records if record]

    def count(self) -> int:
        return len(self.records())

    def status(self) -> dict[str, Any]:
        return {
            "path": str(self.outbox_path),
            "exists": self.outbox_path.exists(),
            "queued": self.count(),
            "size_bytes": self.outbox_path.stat().st_size if self.outbox_path.exists() else 0,
        }

    async def replay(
        self,
        wavelog_client: Optional[WavelogClient] = None,
        max_records: int = 20,
        on_resolved_record: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        """Try to upload queued records to Wavelog and remove successes."""
        async with self._replay_lock:
            client = wavelog_client or WavelogClient()
            records = self.records()
            if not records:
                return {"success": True, "attempted": 0, "uploaded": 0, "remaining": 0}

            attempted = 0
            uploaded = 0
            duplicates = 0
            failures = []
            for record in records[:max_records]:
                attempted += 1
                result = await client.submit_adif_string(record)
                resolved = bool(result.get("success")) or self._is_duplicate_upload_result(result)
                if not resolved:
                    failures.append(result.get("message") or result.get("error") or "Unknown error")
                    break
                if result.get("success"):
                    uploaded += 1
                else:
                    duplicates += 1
                self._remove_record(record)
                self._notify_resolved(record, on_resolved_record)
            remaining_count = self.count()
            return {
                "success": not failures,
                "attempted": attempted,
                "uploaded": uploaded,
                "duplicates": duplicates,
                "remaining": remaining_count,
                "failures": failures,
            }

    async def replay_periodically(
        self,
        wavelog_client: Optional[WavelogClient] = None,
        interval_seconds: int = 60,
        max_records: int = 20,
        on_resolved_record: Optional[Callable[[str], None]] = None,
    ):
        """Background retry loop for queued Wavelog uploads."""
        while True:
            try:
                await self.replay(
                    wavelog_client,
                    max_records=max_records,
                    on_resolved_record=on_resolved_record,
                )
            except Exception as exc:
                logger.warning("Wavelog outbox replay failed: %s", exc)
            await asyncio.sleep(interval_seconds)

    def _ensure_file(self) -> None:
        with locked_file(self.outbox_path):
            self._ensure_file_unlocked()

    def _ensure_file_unlocked(self) -> None:
        if not self.outbox_path.exists():
            atomic_write_text(self.outbox_path, self.ADIF_HEADER + "\n\n")

    def _rewrite(self, records: list[str]) -> None:
        with locked_file(self.outbox_path):
            content = self.ADIF_HEADER + "\n\n"
            if records:
                content += "\n\n".join(self._normalize_record(record) for record in records) + "\n\n"
            atomic_write_text(self.outbox_path, content, backup=True)

    def _remove_record(self, resolved_record: str) -> None:
        """Remove one resolved record without erasing records enqueued during upload."""
        with locked_file(self.outbox_path):
            current = self._records_unlocked()
            try:
                current.remove(self._normalize_record(resolved_record))
            except ValueError:
                return
            self._rewrite(current)

    @staticmethod
    def _normalize_record(adif_record: str) -> str:
        record = (adif_record or "").strip()
        record = re.sub(r"<eor>\s*$", "", record, flags=re.IGNORECASE).strip()
        if not record:
            return ""
        return record + "\n<eor>"

    @staticmethod
    def _adif_fields(adif_record: str) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        for match in re.finditer(r"<([^:/>\s]+):(\d+)(?::[^>]*)?>", adif_record or "", flags=re.IGNORECASE):
            name = match.group(1).strip().lower()
            try:
                length = int(match.group(2))
            except ValueError:
                continue
            fields[name] = (adif_record[match.end():match.end() + length] or "").strip()
        return fields

    @classmethod
    def _loose_identity(cls, adif_record: str) -> str:
        fields = cls._adif_fields(adif_record)
        call = fields.get("call", "").upper()
        qso_date = fields.get("qso_date", "")
        band = fields.get("band", "").lower()
        mode = (fields.get("submode") or fields.get("mode") or "").upper()
        if not call or not qso_date or not band or not mode:
            return ""
        return "|".join((call, qso_date, band, mode))

    @staticmethod
    def _is_duplicate_upload_result(result: Dict[str, Any]) -> bool:
        text = " ".join(
            str(result.get(key) or "")
            for key in ("message", "error")
        ).lower()
        return "duplicate" in text

    @staticmethod
    def _notify_resolved(adif_record: str, callback: Optional[Callable[[str], None]]) -> None:
        if callback is None:
            return
        try:
            callback(adif_record)
        except Exception as exc:
            logger.debug("Wavelog outbox resolved-record callback failed: %s", exc, exc_info=True)

    @staticmethod
    def _add_app_note(adif_record: str, note: str) -> str:
        record = re.sub(r"<eor>\s*$", "", adif_record.strip(), flags=re.IGNORECASE)
        field = f"<app_om0rx_outbox_reason:{len(note)}>{note}"
        return record + field + "<eor>"


_outbox_instance: Optional[QSOOutbox] = None


def get_qso_outbox() -> QSOOutbox:
    global _outbox_instance
    if _outbox_instance is None:
        _outbox_instance = QSOOutbox()
    return _outbox_instance
