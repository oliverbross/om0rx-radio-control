import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLEAN_DOC_ROOT = PROJECT_ROOT / "docs" / "wsjtx" / "clean-rebuild"
PREPARE_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "prepare_clean_wsjtz.ps1"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "build_clean_wsjtz.ps1"
RUN_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "run_clean_wsjtz.ps1"


def test_clean_baseline_identity_is_pinned() -> None:
    lock = json.loads((CLEAN_DOC_ROOT / "baseline-lock.json").read_text(encoding="utf-8"))
    upstream = lock["upstream"]

    assert upstream["ref"] == "v2.0.14"
    assert upstream["commit"] == "fa53f635462def9f37b54f63f18e407ecda2ba12"
    assert upstream["tree"] == "2d23c72ddb826f18d21876ac7b6a89642ee0ef34"
    assert upstream["reported_wsjtx_core_version"] == "3.0.0"

    build = json.loads((CLEAN_DOC_ROOT / "build-lock.json").read_text(encoding="utf-8"))
    assert build["source_commit"] == upstream["commit"]
    assert build["source_tree"] == upstream["tree"]
    assert build["build_result"] == "success"


def test_prepare_script_uses_separate_clean_workspace_without_feature_patch() -> None:
    script = PREPARE_SCRIPT.read_text(encoding="utf-8")

    assert '"data\\build"' in script
    assert '"wsjt-z-clean"' in script
    assert '"v2.0.14"' in script
    assert "checkout --detach" in script
    assert "om0rx-wsjtz-enrichment.patch" not in script
    assert "git apply" not in script
    assert "wsjt-z-om0rx" not in script


def test_basic_scope_defers_award_reference_exceptions() -> None:
    decisions = json.loads((CLEAN_DOC_ROOT / "feature-decisions.json").read_text(encoding="utf-8"))

    assert decisions["items"]["20"] == "KEEP_BASIC_NO_AWARD_REFERENCE_EXCEPTIONS"
    assert "deferred" in decisions["scope_note"].lower()


def test_clean_build_separates_build_compatibility_and_band_control_patches() -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "0001-build-allow-omnirig-off.patch" in script
    assert "0002-build-link-fftw-threads-on-windows.patch" in script
    assert "0100-band-qsy-transaction-tracing.patch" in script
    assert "om0rx-wsjtz-enrichment.patch" not in script
    assert "OM0RX_BUILD_WITH_OMNIRIG=OFF" in script
    assert "data\\build\\wsjt-z-clean" in script


def test_band_qsy_patch_has_correlated_request_outcomes() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0100-band-qsy-transaction-tracing.patch").read_text(encoding="utf-8")

    assert "OM0RX_QSY result=request sequence=" in patch
    assert "OM0RX_QSY result=ack sequence=" in patch
    assert "OM0RX_QSY result=timeout sequence=" in patch
    assert "OM0RX_QSY result=superseded sequence=" in patch
    assert "OM0RX_QSY result=failed sequence=" in patch
    assert "operator-band-selector" in patch
    assert "native-band-hopper" in patch
    assert "wspr-band-hopper" in patch
    assert "decoded-spot" in patch

    lock = json.loads((CLEAN_DOC_ROOT / "milestone-1-lock.json").read_text(encoding="utf-8"))
    assert lock["dial_frequency_owner"]["default"] == "wsjtz"
    assert lock["live_flex_qualification"]["result"] == "pending_operator_test"
    assert lock["artifacts"]["executable_sha256"] == "5AE228AB4C1B466B0F462F10CA32107BBA8A4C67B668B13C8AE55D5DC5FF2B7B"


def test_clean_launcher_does_not_start_enrichment_or_rewrite_ini() -> None:
    script = RUN_SCRIPT.read_text(encoding="utf-8")

    assert "om0rx_decode_status_server" not in script
    assert "Set-IniValue" not in script
    assert "Set-IniSectionValue" not in script
    assert "AcceptUDPRequests" not in script
    assert "AutoCall" not in script
    assert "wsjt-z-clean.exe" in script
