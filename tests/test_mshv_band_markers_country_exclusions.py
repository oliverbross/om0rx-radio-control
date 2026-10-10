"""Regression contracts for band markers and AutoDX country exclusions."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "docs/mshv/om0rx-band-markers-country-exclusions.patch"


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_band_marker_is_inserted_in_both_decode_lists_only_on_transition():
    patch = PATCH.read_text(encoding="utf-8")
    assert "void DecodeList::InsertBandSeparator(QString band)" in patch
    assert "QDateTime::currentDateTimeUtc()" in patch
    assert "setFirstColumnSpanned" in patch
    assert "if (m_lastDecodeBandMarker != i)" in patch
    assert "TDecodeList1->InsertBandSeparator(temp_band);" in patch
    assert "TDecodeList2->InsertBandSeparator(temp_band);" in patch


def test_country_exclusions_are_persisted_parsed_and_enforced_before_scoring():
    patch = PATCH.read_text(encoding="utf-8")
    assert '"Eligibility/ExcludedCountriesByBand"' in patch
    assert "QPlainTextEdit *m_excludedCountriesByBand" in patch
    assert "QMap<int, QSet<QString> > excludedCountriesByBand" in patch
    assert 'value == "USA" || value == "US"' in patch
    assert "setExcludedCountriesByBand(config.excludedCountriesByBand)" in patch
    assert 'target.priorityReason = QString("Country excluded on this band: %1")' in patch


def test_patch_is_in_build_package_and_attestation_stacks():
    patch_name = "om0rx-band-markers-country-exclusions.patch"
    for script in (
        "scripts/mshv/prepare_mshv.ps1",
        "scripts/mshv/assert_source.ps1",
        "scripts/mshv/test_clean_patch.ps1",
        "scripts/mshv/build_mshv.ps1",
        "scripts/mshv/package_mshv.ps1",
        "scripts/mshv/assert_release.ps1",
    ):
        assert patch_name in _text(script)

    package = _text("scripts/mshv/package_mshv.ps1")
    release = _text("scripts/mshv/assert_release.ps1")
    assert "band_markers_country_exclusions_patch_sha256" in package
    assert "band_markers_v1" in package
    assert "country_exclusions_by_band_v1" in package
    assert "band_markers_country_exclusions_patch_sha256" in release
    assert "band_markers_v1" in release
    assert "country_exclusions_by_band_v1" in release
