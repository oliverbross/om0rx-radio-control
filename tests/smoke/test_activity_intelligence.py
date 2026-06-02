from pathlib import Path
from datetime import UTC, datetime, timedelta

import duckdb

from activity_intelligence.adapters import (
    Ng3kAdxoAdapter,
    LocalContestDefinitionsAdapter,
    RawFetchResult,
    SotaAlertsAdapter,
    SwpcDrapAdapter,
    SwpcKpAdapter,
    SwpcSolarFluxAdapter,
    SwpcSolarWindAdapter,
    SwpcXrayAdapter,
    Wa7bnmRssAdapter,
    WwffSpotsAdapter,
    parse_rbn_line,
)
from activity_intelligence.models import Dxpedition, PortableActivation, PortableReference, SpaceWeatherSnapshot, StationStateSample
from activity_intelligence.repository import ActivityRepository
from activity_intelligence.services import ActivityIntelligenceService


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "activity"


def test_parse_rbn_line_extracts_core_fields():
    spot = parse_rbn_line("DX de DL1ABC-#: 14027.0 OM0RX  23 dB  28 WPM  CQ  1234Z")

    assert spot is not None
    assert spot.skimmer_call == "DL1ABC"
    assert spot.spotted_call == "OM0RX"
    assert spot.frequency_khz == 14027.0
    assert spot.band == "20m"
    assert spot.snr_db == 23
    assert spot.speed_wpm == 28
    assert spot.cq_flag is True


def test_parse_rbn_line_infers_digital_mode_from_existing_rbl_comment():
    spot = parse_rbn_line("DX de EA1ABC-#: 14074.0 OM0RX RBN FT8 -12 dB CQ")

    assert spot is not None
    assert spot.mode == "FT8"
    assert spot.snr_db == -12


def test_portable_json_adapter_normalizes_activation():
    raw = RawFetchResult(
        source_id="WWFF_SPOTS",
        url="https://spots.wwff.co/static/spots.json",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body='[{"callsign":"VK3ABC/P","reference":"VKFF-1000","frequency":"7144","mode":"SSB","comments":"WWFF VKFF-1000"}]',
    )

    parsed = WwffSpotsAdapter().parse(raw)

    activations = parsed["portable_activations"]
    assert len(activations) == 1
    assert activations[0].program == "WWFF"
    assert activations[0].activator_call == "VK3ABC/P"
    assert activations[0].references == ["VKFF-1000"]
    assert activations[0].frequency_khz == 7144


def test_sota_alerts_parse_current_api_reference_shape():
    raw = RawFetchResult(
        source_id="SOTA_ALERTS",
        url="https://api-db2.sota.org.uk/api/alerts/10/all/all",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(
            '[{"timeStamp":"2026-06-01T19:04:07Z","dateActivated":"2026-06-01T22:00:00Z",'
            '"associationCode":"JA","summitCode":"YM-150","summitDetails":"Akibayama, 561m",'
            '"activatingCallsign":"JQ7CPP/7","frequency":"21-cw, 18-cw","comments":""}]'
        ),
    )

    parsed = SotaAlertsAdapter().parse(raw)
    activation = parsed["portable_activations"][0]
    reference = parsed["portable_references"][0]

    assert activation.activator_call == "JQ7CPP/7"
    assert activation.references == ["JA/YM-150"]
    assert activation.type == "ALERT"
    assert reference.reference == "JA/YM-150"
    assert reference.name == "Akibayama, 561m"


def test_ng3k_adxo_fixture_parses_dxpeditions():
    raw = RawFetchResult(
        source_id="NG3K_ADXO",
        url="https://www.ng3k.com/misc/adxo.html",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(FIXTURES / "ng3k_adxo_sample.html").read_text(encoding="utf-8"),
    )

    parsed = Ng3kAdxoAdapter().parse(raw)
    calls = {item.callsign for item in parsed["dxpeditions"]}
    by_call = {item.callsign: item for item in parsed["dxpeditions"]}

    assert "A31WW" in calls
    assert "3G0Z" in calls
    assert "VJ1L" in calls
    assert "2026" not in calls
    assert "JUN01" not in calls
    assert by_call["VJ1L"].dxcc_entity == "Lord Howe I"


def test_refresh_replaces_stale_source_records(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_dxpeditions(
        [
            Dxpedition(
                id="bad-ng3k",
                source_id="NG3K_ADXO",
                callsign="2026",
                aliases=["JUN01"],
                dxcc_entity="bad stale row",
                start_date_utc="2026-06-01T00:00:00Z",
                end_date_utc="2026-06-14T00:00:00Z",
                status="ACTIVE",
                source_url="fixture",
                last_updated_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    raw = RawFetchResult(
        source_id="NG3K_ADXO",
        url="https://www.ng3k.com/misc/adxo.html",
        fetched_at_utc="2026-06-02T10:00:00Z",
        http_status=200,
        body=(FIXTURES / "ng3k_adxo_sample.html").read_text(encoding="utf-8"),
    )

    class FixtureAdapter(Ng3kAdxoAdapter):
        async def fetch_raw(self, client, etag=None, last_modified=None):  # noqa: ANN001
            return raw

    service = ActivityIntelligenceService(repository=repo)
    state = repo.get_source_state("NG3K_ADXO")
    result = __import__("asyncio").run(service._refresh_adapter(None, FixtureAdapter(), state))

    calls = {row[0] for row in repo.conn.execute("SELECT callsign FROM ai_dxpeditions WHERE source_id = 'NG3K_ADXO'").fetchall()}
    aliases = {row[0] for row in repo.conn.execute("SELECT alias_call FROM ai_dxpedition_aliases").fetchall()}
    assert result["ok"] is True
    assert "VJ1L" in calls
    assert "2026" not in calls
    assert "JUN01" not in aliases


def test_wa7bnm_rss_fixture_parses_contest():
    raw = RawFetchResult(
        source_id="WA7BNM_RSS",
        url="https://www.contestcalendar.com/calendar.rss",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(FIXTURES / "wa7bnm_rss_sample.xml").read_text(encoding="utf-8"),
    )

    parsed = Wa7bnmRssAdapter().parse(raw)

    assert parsed["contests"][0].name == "Example CW Contest"
    assert "CW" in parsed["contests"][0].modes


def test_local_contest_definitions_fixture_parses_yaml_subset():
    raw = RawFetchResult(
        source_id="LOCAL_CONTEST_DEFINITIONS",
        url="config/contest_definitions.yaml",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(FIXTURES / "local_contest_definitions.yaml").read_text(encoding="utf-8"),
    )

    parsed = LocalContestDefinitionsAdapter().parse(raw)

    contest = parsed["contests"][0]
    assert contest.id == "local-field-day"
    assert contest.name == "Local Field Day"
    assert contest.bands == ["40M", "20M"]
    assert contest.modes == ["CW", "SSB"]
    assert contest.exchange == "RST + serial"


def test_swpc_kp_fixture_parses_latest_snapshot():
    raw = RawFetchResult(
        source_id="NOAA_SWPC_KP",
        url="https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(FIXTURES / "swpc_kp_sample.json").read_text(encoding="utf-8"),
    )

    parsed = SwpcKpAdapter().parse(raw)

    assert parsed["space_weather"][0].kp == 3.33


def test_extended_swpc_adapters_parse_space_weather_fields():
    fetched = "2026-06-02T10:00:00Z"
    xray = SwpcXrayAdapter().parse(
        RawFetchResult(
            source_id="NOAA_SWPC_XRAY",
            url="xray",
            fetched_at_utc=fetched,
            body='[{"time_tag":"2026-06-02T09:59:00Z","energy":"0.1-0.8nm","flux":0.00012}]',
        )
    )["space_weather"][0]
    wind = SwpcSolarWindAdapter().parse(
        RawFetchResult(
            source_id="NOAA_SWPC_SOLAR_WIND",
            url="wind",
            fetched_at_utc=fetched,
            body='{"mag":"[[],[\\"2026-06-02 09:58:00.000\\",0,0,-9.5]]","plasma":"[[],[\\"2026-06-02 09:58:00.000\\",4.0,710.0,100000]]"}',
        )
    )["space_weather"][0]
    flux = SwpcSolarFluxAdapter().parse(
        RawFetchResult(
            source_id="NOAA_SWPC_SOLAR_FLUX",
            url="flux",
            fetched_at_utc=fetched,
            body='[{"time-tag":"2026-06","f10.7":165.0}]',
        )
    )["space_weather"][0]
    drap = SwpcDrapAdapter().parse(
        RawFetchResult(
            source_id="NOAA_SWPC_DRAP",
            url="drap",
            fetched_at_utc=fetched,
            body='{"time_tag":"2026-06-02T09:59:00Z","drap_affected_frequency_mhz":18.0}',
        )
    )["space_weather"][0]

    assert xray.xray_class == "X1.2"
    assert wind.solar_wind_bz_nt == -9.5
    assert wind.solar_wind_speed_kms == 710
    assert flux.solar_flux_sfu == 165
    assert drap.drap_affected_frequency_mhz == 18


def test_swpc_drap_text_endpoint_parses_max_grid_frequency():
    raw = RawFetchResult(
        source_id="NOAA_SWPC_DRAP",
        url="https://services.swpc.noaa.gov/text/drap_global_frequencies.txt",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(
            "# DRAP Tabular Values\n"
            "# Product Valid At : 2026-06-02 07:00 UTC\n"
            "# Frequency (MHz) as a function of Latitude and Longitude\n"
            "      -178 -174 -170\n"
            "--------------------------------\n"
            " 89 |  4.8  5.1  4.9\n"
            " 87 |  6.2  5.9  6.1\n"
        ),
    )

    drap = SwpcDrapAdapter().parse(raw)["space_weather"][0]

    assert drap.timestamp_utc == "2026-06-02T07:00:00Z"
    assert drap.drap_affected_frequency_mhz == 6.2


def test_enrich_spot_adds_dxpedition_portable_and_propagation(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_dxpeditions(
        [
            Dxpedition(
                id="dx1",
                source_id="TEST",
                callsign="A31WW",
                aliases=[],
                dxcc_entity="Tonga",
                status="ACTIVE",
                source_url="https://example.invalid",
                last_updated_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    repo.upsert_portable_activations(
        [
            PortableActivation(
                id="pa1",
                program="POTA",
                type="ACTIVE_SPOT",
                activator_call="A31WW",
                references=["K-1234"],
                source_id="TEST",
                raw_payload_hash="abc",
                last_seen_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    repo.upsert_space_weather(
        [
            SpaceWeatherSnapshot(
                id="sw1",
                timestamp_utc="2026-06-02T10:00:00Z",
                kp=2,
                source_ids=["TEST"],
            )
        ]
    )
    service = ActivityIntelligenceService(repository=repo)

    spot = {
        "callsign": "A31WW",
        "frequency_mhz": 14.028,
        "band": "20m",
        "mode": "CW",
        "comment": "POTA K-1234",
        "dxcc_status": "ATNO",
    }
    enriched = service.enrich_spot(spot)

    tag_types = {tag["type"] for tag in enriched["activity_tags"]}
    assert "DXPEDITION" in tag_types
    assert "POTA_ACTIVE" in tag_types
    assert enriched["propagation"]["label"] in {"GOOD", "EXCELLENT"}
    assert enriched["priority_score"] >= 70


def test_propagation_uses_extended_swpc_fields_for_poor_warning(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_space_weather(
        [
            SpaceWeatherSnapshot(
                id="swx",
                timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                kp=6,
                xray_class="X1.0",
                solar_wind_speed_kms=720,
                solar_wind_bz_nt=-10,
                solar_flux_sfu=80,
                drap_affected_frequency_mhz=30,
                source_ids=["TEST"],
            )
        ]
    )
    service = ActivityIntelligenceService(repository=repo)

    propagation = service.assess_propagation({"callsign": "A31WW", "frequency_mhz": 14.2, "band": "20m", "mode": "SSB"})

    assert propagation.label == "POOR"
    assert any("X1.0" in reason for reason in propagation.reasons)
    assert any("D-RAP" in reason for reason in propagation.reasons)


def test_propagation_uses_rbn_band_evidence_when_enabled(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_space_weather(
        [
            SpaceWeatherSnapshot(
                id="sw2",
                timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                kp=3,
                solar_flux_sfu=150,
                source_ids=["TEST"],
            )
        ]
    )
    spot = parse_rbn_line("DX de DL1ABC-#: 14027.0 OM0RX  10 dB  28 WPM  CQ", timestamp=datetime.now(UTC))
    assert spot is not None
    repo.upsert_rbn_spot(spot)
    service = ActivityIntelligenceService(repository=repo)

    propagation = service.assess_propagation({"callsign": "A31WW", "frequency_mhz": 14.027, "band": "20m", "mode": "CW"})

    assert any("RBN own-call evidence" in reason for reason in propagation.reasons)


def test_dxpedition_detail_returns_matrix_without_classifier(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_dxpeditions(
        [
            Dxpedition(
                id="dx1",
                source_id="TEST",
                callsign="A31WW",
                dxcc_entity="Tonga",
                status="ACTIVE",
                source_url="https://example.invalid",
                last_updated_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    service = ActivityIntelligenceService(repository=repo)

    detail = __import__("asyncio").run(service.dxpedition_detail("dx1", classifier=None))

    assert detail["ok"] is True
    assert detail["dxpedition"]["callsign"] == "A31WW"
    assert detail["matrixModes"] == ["CW", "SSB", "RTTY", "FT8"]


def test_rbn_summary_builds_analytics_and_station_state(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    now = datetime.now(UTC).replace(microsecond=0)
    lines = [
        ("DX de DL1ABC-#: 14027.0 OM0RX  23 dB  28 WPM  CQ", 35.0),
        ("DX de F6ABC-#: 14028.0 OM0RX  12 dB  26 WPM  CQ", 50.0),
        ("DX de K1ABC-#: 21027.0 OM0RX  17 dB  30 WPM  CQ", 300.0),
    ]
    for offset, (line, bearing) in enumerate(lines):
        spot = parse_rbn_line(line, timestamp=now - timedelta(minutes=offset * 5))
        assert spot is not None
        spot.bearing_from_station_deg = bearing
        repo.upsert_rbn_spot(spot)
    repo.upsert_station_state_sample(
        StationStateSample(
            id="state1",
            timestamp_utc=(now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            frequency_khz=14027,
            mode="CW",
            rotator_bearing_deg=35,
            antenna_name="Yagi",
            power_watts=500,
            tx_state=True,
        )
    )
    service = ActivityIntelligenceService(repository=repo)

    summary = service.rbn_summary(["OM0RX"], minutes=60)

    assert summary["totalReports"] == 3
    assert summary["uniqueSkimmers"] == 3
    assert summary["bestBand"] == "20m"
    assert summary["bestHeading"] == "030-059"
    assert summary["bandSummary"][0]["band"] == "20m"
    assert summary["snrSeries"]
    assert summary["uniqueSkimmerSeries"]
    assert summary["bandOpeningHeatmap"]
    assert summary["antennaComparisons"][0]["label"] == "Yagi"
    assert summary["reports"][0]["stationState"]["antenna_name"] == "Yagi"


def test_contest_context_selects_and_matches_band_mode(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    raw = RawFetchResult(
        source_id="LOCAL_CONTEST_DEFINITIONS",
        url="config/contest_definitions.yaml",
        fetched_at_utc="2026-06-02T10:00:00Z",
        body=(FIXTURES / "local_contest_definitions.yaml").read_text(encoding="utf-8"),
    )
    repo.upsert_contests(LocalContestDefinitionsAdapter().parse(raw)["contests"])
    service = ActivityIntelligenceService(repository=repo)

    selected = service.set_contest_context("local-field-day")
    context = service.contest_context("20m", "USB")

    assert selected["ok"] is True
    assert context["selected"]["name"] == "Local Field Day"
    assert context["candidates"][0]["selected"] is True
    assert context["banner"]["exchange"] == "RST + serial"


def test_dashboard_exposes_source_catalog(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    service = ActivityIntelligenceService(repository=repo)

    dashboard = service.dashboard()

    assert dashboard["ok"] is True
    assert dashboard["sourceCatalog"]
    assert any(source["sourceId"] == "NG3K_ADXO" for source in dashboard["sourceCatalog"])
    assert all("pollSeconds" in source for source in dashboard["sourceCatalog"])


def create_qso_cache(path, references=None):
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE qso_records (
            call VARCHAR,
            qso_datetime TIMESTAMP,
            time_on TIMESTAMP,
            pota_ref VARCHAR,
            sota_ref VARCHAR,
            wwff_ref VARCHAR,
            sig VARCHAR,
            sig_info VARCHAR,
            comment VARCHAR
        )
        """
    )
    for ref in references or []:
        conn.execute(
            "INSERT INTO qso_records VALUES (?, current_timestamp, current_timestamp, ?, '', '', 'POTA', ?, '')",
            ["K1ABC", ref, ref],
        )
    conn.close()


def test_portable_reference_history_marks_new_and_duplicate_refs(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_portable_activations(
        [
            PortableActivation(
                id="pa1",
                program="POTA",
                type="ACTIVE_SPOT",
                activator_call="A31WW",
                references=["K-1234"],
                source_id="TEST",
                raw_payload_hash="abc",
                last_seen_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    qso_db = tmp_path / "qso_log.duckdb"
    create_qso_cache(qso_db)
    service = ActivityIntelligenceService(repository=repo, qso_db_path=qso_db)

    new_ref_spot = service.enrich_spot({"callsign": "A31WW", "frequency_mhz": 14.2, "band": "20m", "mode": "SSB"})
    tag_types = {tag["type"] for tag in new_ref_spot["activity_tags"]}
    fill_payload = new_ref_spot["recommended_actions"][0]["payload"]

    assert "NEW_REFERENCE" in tag_types
    assert fill_payload["pota_ref"] == "K-1234"
    assert fill_payload["sig_info"] == "K-1234"

    create_qso_cache(tmp_path / "worked_qso_log.duckdb", references=["K-1234"])
    worked_service = ActivityIntelligenceService(repository=repo, qso_db_path=tmp_path / "worked_qso_log.duckdb")
    worked_ref_spot = worked_service.enrich_spot({"callsign": "A31WW", "frequency_mhz": 14.2, "band": "20m", "mode": "SSB"})
    worked_tag_types = {tag["type"] for tag in worked_ref_spot["activity_tags"]}

    assert "DUPLICATE" in worked_tag_types
    assert "NEW_REFERENCE" not in worked_tag_types


def test_parksnpeaks_references_keep_actual_program_semantics(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_portable_activations(
        [
            PortableActivation(
                id="pa-pnp",
                program="PARKSNPEAKS",
                type="ACTIVE_SPOT",
                activator_call="VK3ABC/P",
                references=["VKFF-1000", "VK3/VC-001"],
                source_id="PARKSNPEAKS_ALL",
                raw_payload_hash="abc",
                last_seen_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    qso_db = tmp_path / "qso_log.duckdb"
    create_qso_cache(qso_db)
    service = ActivityIntelligenceService(repository=repo, qso_db_path=qso_db)

    enriched = service.enrich_spot(
        {
            "callsign": "VK3ABC/P",
            "frequency_mhz": 7.144,
            "band": "40m",
            "mode": "SSB",
            "comment": "VKFF-1000 VK3/VC-001",
        }
    )

    tags = {(tag["type"], tag["label"]) for tag in enriched["activity_tags"]}
    payloads = [action["payload"] for action in enriched["recommended_actions"]]
    assert ("WWFF_ACTIVE", "WWFF VKFF-1000") in tags
    assert ("SOTA_ACTIVE", "SOTA VK3/VC-001") in tags
    assert any(payload.get("wwff_ref") == "VKFF-1000" for payload in payloads)
    assert any(payload.get("sota_ref") == "VK3/VC-001" for payload in payloads)


def test_reference_lookup_includes_worked_state(tmp_path):
    repo = ActivityRepository(tmp_path / "ai.duckdb")
    repo.upsert_portable_references(
        [
            PortableReference(
                program="POTA",
                reference="K-1234",
                name="Example Park",
                source_id="TEST",
                last_verified_utc="2026-06-02T10:00:00Z",
            )
        ]
    )
    qso_db = tmp_path / "qso_log.duckdb"
    create_qso_cache(qso_db, references=["K-1234"])
    service = ActivityIntelligenceService(repository=repo, qso_db_path=qso_db)

    result = service.lookup_reference("K-1234")

    assert result["results"][0]["workedState"]["worked"] is True
