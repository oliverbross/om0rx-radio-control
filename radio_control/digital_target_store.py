"""PostgreSQL persistence for Digital automation targets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Mapping, Optional

from radio_control.postgres_store import connect, initialize_schema, should_use_postgres

logger = logging.getLogger(__name__)


DIGITAL_TARGET_COLUMNS = [
    "key",
    "call",
    "band",
    "mode",
    "source",
    "message",
    "grid",
    "country",
    "dxcc",
    "continent",
    "cq_zone",
    "itu_zone",
    "call_status",
    "dxcc_status",
    "status_source",
    "score",
    "snr",
    "audio_offset",
    "dial_frequency",
    "created_at",
    "updated_at",
    "first_heard_at",
    "last_heard_at",
    "heard_slot_start_at",
    "last_attempt_at",
    "backoff_until",
    "attempts",
    "state",
    "reason",
    "heard",
]


def _target_mapping(target: Any) -> dict[str, Any]:
    if hasattr(target, "to_dict"):
        data = dict(target.to_dict())
    elif isinstance(target, Mapping):
        data = dict(target)
    else:
        raise TypeError("Digital target persistence expects a mapping or target with to_dict()")
    return {column: data.get(column) for column in DIGITAL_TARGET_COLUMNS}


class PostgresDigitalTargetStore:
    """Small repository for backend-owned WSJT/Digital automation queue state."""

    def __init__(self) -> None:
        initialize_schema()

    def upsert_target(self, target: Any) -> None:
        data = _target_mapping(target)
        if not data.get("key") or not data.get("call"):
            return

        columns = DIGITAL_TARGET_COLUMNS
        placeholders = ", ".join(["%s"] * len(columns))
        updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column != "key")

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO digital_targets ({", ".join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT (key) DO UPDATE SET {updates}
                    """,
                    [data.get(column) for column in columns],
                )
            conn.commit()

    def load_recent_targets(self, *, limit: int = 250, max_age_hours: int = 24) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        limit = max(1, min(int(limit or 250), 1000))

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {", ".join(DIGITAL_TARGET_COLUMNS)}
                    FROM digital_targets
                    WHERE COALESCE(updated_at, created_at, now()) >= %s
                    ORDER BY COALESCE(updated_at, created_at, now()) DESC
                    LIMIT %s
                    """,
                    (cutoff, limit),
                )
                rows = cur.fetchall()

        return [dict(zip(DIGITAL_TARGET_COLUMNS, row)) for row in rows]

    def delete_old_targets(self, *, max_age_hours: int = 72) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM digital_targets
                    WHERE COALESCE(updated_at, created_at, now()) < %s
                    """,
                    (cutoff,),
                )
                deleted = int(cur.rowcount or 0)
            conn.commit()
        return deleted


def get_digital_target_store() -> Optional[PostgresDigitalTargetStore]:
    """Return the configured Digital target store, failing soft for optional setups."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if not should_use_postgres():
        return None
    try:
        return PostgresDigitalTargetStore()
    except Exception as exc:
        logger.warning("Digital target PostgreSQL persistence unavailable: %s", exc)
        return None
