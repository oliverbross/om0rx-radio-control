from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/build/mshv-auto-dx/src/MSHV_2762/src"


def _function(source: str, signature: str, next_signature: str) -> str:
    return source.split(signature, 1)[1].split(next_signature, 1)[0]


def test_wall_clock_is_decimated_without_decimating_refresh_loop():
    core = (SOURCE / "HvMsCore/mscore.cpp").read_text(encoding="utf-8")
    main = (SOURCE / "main_ms.cpp").read_text(encoding="utf-8")
    refresh_t = core.split("void MsCore::Refresh_t()", 1)[1]
    refresh = _function(main, "void Main_Ms::Refresh()", "void Main_Ms::SetAuto")

    # Audio reads and the 5 ms state-machine signal remain unconditional.
    assert "ReadData();" in refresh_t
    assert refresh_t.count("emit Refresh_time();") == 1

    # Only the second-resolution label/log strings are gated.
    assert "ui_clock_second != last_ui_clock_epoch_second" in refresh
    assert "THvTxW->SetDataTime(utc_t);" in refresh
    assert refresh.index("ui_clock_second != last_ui_clock_epoch_second") < refresh.index(
        "THvTxW->SetDataTime(utc_t);"
    )
    assert 'toString("ss")' not in refresh
    assert 'toString("zzz")' not in refresh
    assert 'toString("mm")' not in refresh
    assert "utc_clock.msec()" in refresh
    assert "time_pos_1period" in refresh


def test_history_uses_freshness_checked_conditional_get():
    source = (SOURCE / "HvAutoDxer/autodxercore.cpp").read_text(encoding="utf-8")
    request = _function(
        source,
        "void AutoDxerCore::refreshWavelogHistory()",
        "void AutoDxerCore::applyWavelogHistoryReply",
    )
    reply = _function(
        source,
        "void AutoDxerCore::applyWavelogHistoryReply",
        "bool AutoDxerCore::applyUnmodifiedWavelogHistoryReply",
    )
    unchanged = _function(
        source,
        "bool AutoDxerCore::applyUnmodifiedWavelogHistoryReply",
        "void AutoDxerCore::noteTransientHistoryFailure",
    )

    assert 'setRawHeader("If-None-Match", m_historyEntityTag)' in request
    assert "now <= m_historyRepresentationValidUntil" in request
    assert "httpStatus == 304" in reply
    assert reply.index("httpStatus == 304") < reply.index("QJsonDocument::fromJson")
    assert "QJsonDocument::fromJson" not in unchanged
    assert 'rawHeader("X-OM0RX-History-Generated-At")' in unchanged
    assert 'rawHeader("X-OM0RX-History-Max-Age")' in unchanged
    assert "AutoDxHistoryConditional::hasExactEntityTag" in unchanged
    assert "age < 0 || age > maxAge" in unchanged
    assert 'revokeHistoricalNovelty("stale-history-response")' in unchanged
    assert "setHistoricalNoveltyAllowed(true)" in unchanged


def test_decode_insert_batches_only_viewport_work_and_keeps_row_immediate():
    source = (SOURCE / "HvDecodeList/decodelist.cpp").read_text(encoding="utf-8")
    insert = _function(
        source,
        "void DecodeList::InsertItem_hv",
        "void DecodeList::Clear_List",
    )

    disable = insert.index("viewport()->setUpdatesEnabled(false)")
    schedule = insert.index("QTimer::singleShot(0, this, SLOT(FlushModelBatchRepaint()))")
    prune = insert.index("model.removeRows(0, excessRows)")
    append = insert.index("model.appendRow(qlsi)")
    assert disable < schedule < prune < append
    assert "model.removeRow(0)" not in insert
    # The model insertion itself is synchronous; only paints are coalesced to
    # the next event-loop turn. The existing 80 ms timer remains
    # scroll/selection housekeeping only.
    assert append < insert.index("list_rfresh_timer->start(80)")
