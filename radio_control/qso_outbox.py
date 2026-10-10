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
            record = str(qso_data.get("adif_text") or "").strip() or client.build_adif_string(qso_data)
            record = self._add_identity_fields(record, qso_data)
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
                identity = self._exact_identity(normalized)
                if identity and identity in {self._exact_identity(record) for record in existing_records}:
                    logger.info("QSO already exists in Wavelog outbox by exact event/QSO identity; skipping duplicate")
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
                if not result.get("success"):
                    readback = await asyncio.to_thread(self._exact_readback_result, record)
                    if readback.get("identity_verified"):
                        result = {**result, **readback, "duplicate": True}
                resolved = bool(result.get("success")) or self._is_duplicate_upload_result(result)
                if not resolved:
                    failures.append(result.get("message") or result.get("error") or "Unknown error")
                    break
                if result.get("success"):
                    uploaded += 1
                else:
                    duplicates += 1
                try:
                    self._acknowledge_mshv_history(record)
                    # Promote the exact QSO (including portable-reference
                    # fields) into durable local read state before deleting
                    # the only offline replay record.  A callback failure is
                    # retryable through Wavelog's verified-duplicate path.
                    self._notify_resolved(record, on_resolved_record)
                except Exception as exc:
                    # Keep the outbox record. A later duplicate response is a
                    # safe retry, while dropping it here could lose the only
                    # transition from pending to Wavelog-authoritative history.
                    failures.append(f"MSHV history acknowledgement failed (including local cache): {exc}")
                    break
                self._remove_record(record)
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
    def _exact_identity(cls, adif_record: str) -> str:
        fields = cls._adif_fields(adif_record)
        event_id = fields.get("app_om0rx_event_id", "").lower()
        provider = fields.get("app_om0rx_provider", "").lower()
        station = (fields.get("app_om0rx_station") or fields.get("station_callsign") or "").upper()
        client = fields.get("app_om0rx_client_id", "")
        if event_id and provider:
            return "event|" + "|".join((provider, station, client, event_id))
        call = fields.get("call", "").upper()
        qso_date = fields.get("qso_date", "")
        time_on = fields.get("time_on", "")
        time_off = fields.get("time_off", "")
        frequency = fields.get("freq", "")
        mode = (fields.get("submode") or fields.get("mode") or "").upper()
        if not call or not qso_date or not time_on or not frequency or not mode:
            return ""
        return "qso|" + "|".join((station, call, qso_date, time_on, time_off, frequency, mode))

    @staticmethod
    def _is_duplicate_upload_result(result: Dict[str, Any]) -> bool:
        # Never infer authority from free-form server text. A duplicate is
        # resolved only after the Wavelog client has returned a structured
        # duplicate outcome and verified the exact record identity/readback.
        return result.get("duplicate") is True and result.get("identity_verified") is True

    @classmethod
    def _exact_readback_result(cls, adif_record: str) -> Dict[str, Any]:
        """Verify a failed/duplicate upload using the canonical Wavelog row."""
        from datetime import datetime, timezone
        from services.wavelog_log import get_wavelog_log_service

        fields = cls._adif_fields(adif_record)
        provider = fields.get("app_om0rx_provider", "").lower()
        event_id = fields.get("app_om0rx_event_id", "").lower()
        station = (fields.get("app_om0rx_station") or fields.get("station_callsign") or "").upper()
        client_id = fields.get("app_om0rx_client_id", "")
        if provider == "mshv_auto_dx" and (
            not re.fullmatch(r"[0-9a-f]{64}", event_id)
            or station != "OM0RX"
            or not client_id
        ):
            return {"identity_verified": False, "reason": "exact-readback-correlation-incomplete"}
        date = "".join(c for c in fields.get("qso_date", "") if c.isdigit())[:8]
        on = "".join(c for c in (fields.get("time_on") or fields.get("app_om0rx_time_on") or "") if c.isdigit())
        off = "".join(c for c in (fields.get("time_off") or fields.get("app_om0rx_time_off") or "") if c.isdigit())
        if len(date) != 8 or len(on) != 6 or len(off) != 6:
            return {"identity_verified": False, "reason": "exact-readback-identity-invalid"}
        try:
            expected_on = datetime.strptime(date + on, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            expected_off = datetime.strptime(date + off, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            frequency_hz = int(round(float(fields.get("app_om0rx_frequency_hz") or float(fields.get("freq", 0)) * 1_000_000)))
        except (TypeError, ValueError):
            return {"identity_verified": False, "reason": "exact-readback-identity-invalid"}
        if not fields.get("call") or not (fields.get("submode") or fields.get("mode")) or frequency_hz <= 0:
            return {"identity_verified": False, "reason": "exact-readback-identity-invalid"}
        identity = {
            "provider": provider, "event_id": event_id,
            "station_callsign": station, "client_id": client_id,
            "call": fields.get("call", "").upper(),
            "mode": (fields.get("submode") or fields.get("mode") or "").upper(),
            "frequency_hz": frequency_hz,
            "time_on_utc": expected_on, "time_off_utc": expected_off,
        }
        verified = get_wavelog_log_service().find_exact_qso(
            identity, station_id=int(getattr(config, "WAVELOG_STATION_ID", 1)),
        )
        if not verified.get("verified"):
            return {"identity_verified": False, "reason": verified.get("reason")}
        return {
            "identity_verified": True,
            "readback_verified": True,
            "readback_identity_exact": True,
            "readback_wavelog_id": verified["matches"][0].get("id"),
        }

    @staticmethod
    def _notify_resolved(adif_record: str, callback: Optional[Callable[[str], None]]) -> None:
        if callback is None:
            return
        callback(adif_record)

    @staticmethod
    def _acknowledge_mshv_history(adif_record: str) -> None:
        # Import lazily so the standalone outbox stays lightweight. Records
        # without a matching MSHV pending delta must be reconstructed from the
        # embedded identity before acknowledgement.  Otherwise the outbox row
        # remains the only durable authority boundary and must not be removed.
        from services.digital_logging import acknowledge_outbox_resolution
        result = acknowledge_outbox_resolution(adif_record)
        delta = result.get("history_delta") if isinstance(result, dict) else None
        fields = QSOOutbox._adif_fields(adif_record)
        is_mshv = fields.get("app_om0rx_provider", "").lower() == "mshv_auto_dx"
        if is_mshv and (not isinstance(delta, dict) or not delta.get("recorded")):
            reason = delta.get("reason") if isinstance(delta, dict) else None
            raise RuntimeError(reason or "MSHV history delta was not acknowledged")

    @staticmethod
    def _add_identity_fields(adif_record: str, qso_data: Dict[str, Any]) -> str:
        """Embed replay/correlation identity that Wavelog is not required to store."""
        values = {
            "APP_OM0RX_PROVIDER": qso_data.get("provider"),
            "APP_OM0RX_STATION": qso_data.get("station_callsign"),
            "APP_OM0RX_CLIENT_ID": qso_data.get("client_id"),
            "APP_OM0RX_EVENT_ID": qso_data.get("event_id"),
            "APP_OM0RX_TIME_ON": qso_data.get("time_on"),
            "APP_OM0RX_TIME_OFF": qso_data.get("time_off"),
            "APP_OM0RX_FREQUENCY_HZ": qso_data.get("frequency_hz"),
        }
        record = re.sub(r"<eor>\s*$", "", (adif_record or "").strip(), flags=re.IGNORECASE)
        for name, raw in values.items():
            value = str(raw or "").strip()
            if value:
                record += f"<{name}:{len(value)}>{value}"
        return record + "<eor>"

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
