"""Offline Wavelog upload outbox backed by an ADIF file."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from radio_control import config
from radio_control.wavelog_api import WavelogClient

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

            existing = set(self.records())
            if normalized in existing:
                logger.info("QSO already exists in Wavelog outbox; skipping duplicate")
                return True

            self._ensure_file()
            with open(self.outbox_path, "a", encoding="utf-8") as handle:
                handle.write(normalized + "\n\n")
                handle.flush()
            logger.warning("Queued QSO for later Wavelog upload: %s", self.outbox_path)
            return True
        except Exception as exc:
            logger.error("Failed to write Wavelog outbox: %s", exc, exc_info=True)
            return False

    def records(self) -> list[str]:
        """Return queued ADIF records without the header."""
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
    ) -> dict[str, Any]:
        """Try to upload queued records to Wavelog and remove successes."""
        client = wavelog_client or WavelogClient()
        records = self.records()
        if not records:
            return {"success": True, "attempted": 0, "uploaded": 0, "remaining": 0}

        attempted = 0
        uploaded = 0
        duplicates = 0
        failures = []
        remaining = records[:]

        for record in records[:max_records]:
            attempted += 1
            result = await client.submit_adif_string(record)
            if result.get("success"):
                uploaded += 1
                remaining.remove(record)
                logger.info("Uploaded queued Wavelog outbox record (%d/%d)", uploaded, attempted)
            elif self._is_duplicate_upload_result(result):
                duplicates += 1
                remaining.remove(record)
                logger.info("Removed queued Wavelog outbox record already present in Wavelog (%d/%d)", duplicates, attempted)
            else:
                failures.append(result.get("message") or result.get("error") or "Unknown error")
                break

        self._rewrite(remaining)
        return {
            "success": not failures,
            "attempted": attempted,
            "uploaded": uploaded,
            "duplicates": duplicates,
            "remaining": len(remaining),
            "failures": failures,
        }

    async def replay_periodically(
        self,
        wavelog_client: Optional[WavelogClient] = None,
        interval_seconds: int = 60,
        max_records: int = 20,
    ):
        """Background retry loop for queued Wavelog uploads."""
        while True:
            try:
                await self.replay(wavelog_client, max_records=max_records)
            except Exception as exc:
                logger.warning("Wavelog outbox replay failed: %s", exc)
            await asyncio.sleep(interval_seconds)

    def _ensure_file(self) -> None:
        if not self.outbox_path.exists():
            self.outbox_path.write_text(self.ADIF_HEADER + "\n\n", encoding="utf-8")

    def _rewrite(self, records: list[str]) -> None:
        self._ensure_file()
        backup_path = self.outbox_path.with_suffix(self.outbox_path.suffix + ".bak")
        shutil.copy2(self.outbox_path, backup_path)
        content = self.ADIF_HEADER + "\n\n"
        if records:
            content += "\n\n".join(self._normalize_record(record) for record in records)
            content += "\n\n"
        self.outbox_path.write_text(content, encoding="utf-8")

    @staticmethod
    def _normalize_record(adif_record: str) -> str:
        record = (adif_record or "").strip()
        record = re.sub(r"<eor>\s*$", "", record, flags=re.IGNORECASE).strip()
        if not record:
            return ""
        return record + "\n<eor>"

    @staticmethod
    def _is_duplicate_upload_result(result: Dict[str, Any]) -> bool:
        text = " ".join(
            str(result.get(key) or "")
            for key in ("message", "error")
        ).lower()
        return "duplicate" in text

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
