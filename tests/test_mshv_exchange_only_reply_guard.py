from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "docs" / "mshv" / "om0rx-exchange-only-reply-guard.patch"


def test_exchange_only_reply_guard_is_maintained_and_packaged():
    patch = PATCH.read_text(encoding="utf-8")
    assert 'exchange == "RRR" || exchange == "RR73"' in patch
    assert 'if (target.isCallingMe && parsedMessage.isExchangeOnly)' in patch
    assert 'Exchange-only reply is not a new caller' in patch

    for script_name in ("prepare_mshv.ps1", "assert_source.ps1", "test_clean_patch.ps1"):
        script = (ROOT / "scripts" / "mshv" / script_name).read_text(encoding="utf-8")
        assert "om0rx-exchange-only-reply-guard.patch" in script

    build = (ROOT / "scripts" / "mshv" / "build_mshv.ps1").read_text(encoding="utf-8")
    package = (ROOT / "scripts" / "mshv" / "package_mshv.ps1").read_text(encoding="utf-8")
    release = (ROOT / "scripts" / "mshv" / "assert_release.ps1").read_text(encoding="utf-8")
    assert "exchange_only_reply_guard_patch_sha256" in build
    assert "exchange_only_reply_guard_v1" in package
    assert "exchange_only_reply_guard_v1" in release


def test_native_regression_fixture_covers_rrr_rr73_and_73():
    native = (ROOT / "tests" / "mshv" / "target_scorer_integration_test.cpp").read_text(
        encoding="utf-8"
    )
    for exchange in ("RRR", "RR73", "73"):
        assert f'OM0RX RA3WY {exchange}' in native
    assert "!exchangeOnly.isCallingMe" in native
    assert "exchangeOnly.priority == 0" in native
