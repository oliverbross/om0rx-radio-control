"""Regression contracts for reliable FT8/FT4 final-exchange sequencing."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(
    os.environ.get("OM0RX_MSHV_TEST_SOURCE_ROOT", ROOT / "data/build/mshv-auto-dx/src")
).resolve()
SOURCE = SOURCE_ROOT / "MSHV_2762" / "src" / "HvTxW" / "hvtxw.cpp"


def _function(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def test_rrr_keeps_final_exchange_repeating_until_remote_confirmation():
    source = SOURCE.read_text(encoding="utf-8", errors="replace")
    decode_selection = _function(
        source, "void HvTxW::DecListTextAll(QString all_txt,QString str,QString tp,QString tx_rpt,QString freq)"
    )
    active_qso = _function(source, "void HvTxW::SetTextForAutoSeq(QStringList list_in)")

    # MSHV has two RRR branches: one for a newly selected decode and one for
    # the already active QSO.  Neither may prime CountTx73_p to stop Auto after
    # the first RR73/73 transmission.
    for function in (decode_selection, active_qso):
        rrr_branches = function.split("{//msg=3 RRR")[1:]
        assert len(rrr_branches) == 1
        branch = rrr_branches[0]
        before_next_exchange = branch.split("else if", 1)[0]
        assert "SetTxRaportToRB(4,true);" in before_next_exchange
        assert "count_73_auto_seq = 0;" in before_next_exchange
        assert "count_73_auto_seq = 1;" not in before_next_exchange

    # Receipt of the peer's terminal exchange still primes the existing
    # completion path, so logging/reset behavior is unchanged.
    assert 'rpt_inmsg=="73") || rr73_inmsg=="RR73"' in active_qso
    assert "count_73_auto_seq = 2;" in active_qso


def test_repeat_final_exchange_patch_is_in_all_build_and_attestation_stacks():
    patch_name = "om0rx-repeat-final-exchange.patch"
    for script in (
        "prepare_mshv.ps1",
        "assert_source.ps1",
        "test_clean_patch.ps1",
        "build_mshv.ps1",
        "package_mshv.ps1",
        "assert_release.ps1",
    ):
        contents = (ROOT / "scripts" / "mshv" / script).read_text(encoding="utf-8")
        assert patch_name in contents

    package = (ROOT / "scripts" / "mshv" / "package_mshv.ps1").read_text(encoding="utf-8")
    release = (ROOT / "scripts" / "mshv" / "assert_release.ps1").read_text(encoding="utf-8")
    assert "repeat_final_exchange_patch_sha256" in package
    assert "repeat_final_exchange_v1" in package
    assert "repeat_final_exchange_patch_sha256" in release
    assert "repeat_final_exchange_v1" in release
