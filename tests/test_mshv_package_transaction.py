import hashlib
import json
import shutil
import subprocess
import os
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "scripts" / "mshv" / "install_staged_runtime.ps1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_runtime(path: Path, payload: bytes, mutable: bytes) -> None:
    path.mkdir(parents=True)
    (path / "settings").mkdir()
    (path / "MSHV_OM0RX.exe").write_bytes(payload)
    (path / "settings" / "ms_operator").write_bytes(mutable)
    manifest = {
        "schema": 1,
        "provider": "mshv_auto_dx",
        "files": {"MSHV_OM0RX.exe": _sha(path / "MSHV_OM0RX.exe")},
        "mutable_paths": [
            ".history-import.lock", "history-import.json", "history-backups/**", "log/**", "logs/**",
            "settings/autodx.ini", "settings/ms_*", "settings/*.txt", "settings/azel.dat",
            "settings/database/worked.db", "settings/database/worked.db-*",
            "settings/database/wavelog_delta_state.json",
            "settings/database/award_hunting.json",
            "settings/database/dxpedition_watch.json",
            "settings/database/autodx_ignore.json",
            "settings/database/autodx_status_owner.json",
            "settings/database/lotw-users.txt",
            "settings/database/confirmed-dxcc.txt",
            "settings/database/status-colors.ini",
            "settings/database/us-states.txt",
            "settings/database/msloc_db*", "settings/database/msbcn_db*",
            "settings/database/mstn_db*", "settings/database/sat.dat",
        ],
        "executable_sha256": _sha(path / "MSHV_OM0RX.exe"),
    }
    (path / "om0rx-build.json").write_text(json.dumps(manifest), encoding="utf-8")


def _replace_runtime_executable(path: Path, executable: Path) -> None:
    shutil.copy2(executable, path / "MSHV_OM0RX.exe")
    manifest_path = path / "om0rx-build.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    executable_hash = _sha(path / "MSHV_OM0RX.exe")
    manifest["files"]["MSHV_OM0RX.exe"] = executable_hash
    manifest["executable_sha256"] = executable_hash
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_runtime_transaction_replaces_immutable_bundle_and_preserves_backup(tmp_path: Path) -> None:
    work = tmp_path / "build"
    old_runtime = work / "phase1-runtime"
    staged = work / "runtime-stage-11111111111111111111111111111111"
    _write_runtime(old_runtime, b"old-executable", b"operator-state")
    _write_runtime(staged, b"new-executable", b"operator-state")

    result = subprocess.run(
        [
            shutil.which("pwsh.exe") or "powershell.exe",
            "-NoProfile",
            "-File",
            str(INSTALLER),
            "-StagedRuntime",
            str(staged),
            "-Destination",
            str(old_runtime),
            "-WorkRoot",
            str(work),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (old_runtime / "MSHV_OM0RX.exe").read_bytes() == b"new-executable"
    assert (old_runtime / "settings" / "ms_operator").read_bytes() == b"operator-state"
    backups = list(work.glob("runtime-previous-*"))
    assert len(backups) == 1
    assert (backups[0] / "MSHV_OM0RX.exe").read_bytes() == b"old-executable"
    assert "Previous runtime preserved" in result.stdout


def test_runtime_transaction_refreshes_mutable_state_from_live_destination_at_swap(tmp_path: Path) -> None:
    work = tmp_path / "build"
    destination = work / "runtime"
    staged = work / "runtime-stage-12121212121212121212121212121212"
    _write_runtime(destination, b"old-executable", b"latest-operator-state")
    _write_runtime(staged, b"new-executable", b"stale-prestage-state")
    (destination / "settings" / "database").mkdir(parents=True)
    (destination / "settings" / "database" / "wavelog_delta_state.json").write_bytes(b"latest-delta")
    (destination / "settings" / "database" / "award_hunting.json").write_bytes(b"latest-award-watch")
    (destination / "settings" / "database" / "dxpedition_watch.json").write_bytes(b"latest-watch")
    (destination / "settings" / "database" / "autodx_status_owner.json").write_bytes(b"latest-owner")

    result = _run_installer(staged, destination, work)

    assert result.returncode == 0, result.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"new-executable"
    assert (destination / "settings" / "ms_operator").read_bytes() == b"latest-operator-state"
    assert (destination / "settings" / "database" / "wavelog_delta_state.json").read_bytes() == b"latest-delta"
    assert (destination / "settings" / "database" / "award_hunting.json").read_bytes() == b"latest-award-watch"
    assert (destination / "settings" / "database" / "dxpedition_watch.json").read_bytes() == b"latest-watch"
    assert (destination / "settings" / "database" / "autodx_status_owner.json").read_bytes() == b"latest-owner"


def test_runtime_transaction_refuses_running_exact_destination_without_partial_mutation(tmp_path: Path) -> None:
    work = tmp_path / "build"
    destination = work / "runtime"
    staged = work / "runtime-stage-13131313131313131313131313131313"
    _write_runtime(destination, b"old-executable", b"latest-operator-state")
    _write_runtime(staged, b"new-executable", b"stale-prestage-state")
    ping = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "ping.exe"
    assert ping.is_file()
    _replace_runtime_executable(destination, ping)
    destination_exe_before = _sha(destination / "MSHV_OM0RX.exe")
    destination_mutable_before = _sha(destination / "settings" / "ms_operator")
    staged_exe_before = _sha(staged / "MSHV_OM0RX.exe")
    staged_mutable_before = _sha(staged / "settings" / "ms_operator")

    running = subprocess.Popen(
        [str(destination / "MSHV_OM0RX.exe"), "-t", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        assert running.poll() is None
        result = _run_installer(staged, destination, work)
    finally:
        running.terminate()
        try:
            running.wait(timeout=5)
        except subprocess.TimeoutExpired:
            running.kill()
            running.wait(timeout=5)

    assert result.returncode != 0
    assert "Stop the destination MSHV runtime before installation" in result.stderr
    assert _sha(destination / "MSHV_OM0RX.exe") == destination_exe_before
    assert _sha(destination / "settings" / "ms_operator") == destination_mutable_before
    assert _sha(staged / "MSHV_OM0RX.exe") == staged_exe_before
    assert _sha(staged / "settings" / "ms_operator") == staged_mutable_before
    assert not list(work.glob("runtime-previous-*"))
    assert not list(work.glob("runtime-failed-*"))


def test_package_supports_attested_stage_only_mode_for_short_final_swap():
    package = (PROJECT_ROOT / "scripts" / "mshv" / "package_mshv.ps1").read_text(encoding="utf-8")
    build = (PROJECT_ROOT / "scripts" / "mshv" / "build_mshv.ps1").read_text(encoding="utf-8")
    assert "[switch]$StageOnly" in package
    assert "PRESTAGED_RUNTIME=" in package
    assert "if ($runningRuntime -and -not $StageOnly)" in package
    assert "[switch]$StageOnlyPackage" in build
    assert "$packageArgs.StageOnly = $true" in build


def test_runtime_transaction_accepts_dedicated_phase2_stage_destination(tmp_path: Path) -> None:
    work = tmp_path / "build"
    destination = work / "phase2-runtime"
    staged = work / "runtime-stage-88888888888888888888888888888888"
    _write_runtime(staged, b"phase2-executable", b"operator-state")

    result = _run_installer(staged, destination, work)

    assert result.returncode == 0, result.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"phase2-executable"


def test_runtime_transaction_migrates_known_legacy_mutable_subset_but_rejects_unknown(
    tmp_path: Path,
) -> None:
    work = tmp_path / "build"
    destination = work / "runtime"
    staged = work / "runtime-stage-99999999999999999999999999999991"
    _write_runtime(destination, b"legacy-executable", b"legacy-operator-state")
    legacy_manifest_path = destination / "om0rx-build.json"
    legacy_manifest = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
    legacy_manifest["mutable_paths"].remove("settings/database/wavelog_delta_state.json")
    legacy_manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
    _write_runtime(staged, b"phase2-executable", b"phase2-operator-state")

    accepted = _run_installer(staged, destination, work)

    assert accepted.returncode == 0, accepted.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"phase2-executable"
    assert len(list(work.glob("runtime-previous-*"))) == 1

    rejected_destination = work / "phase1-runtime"
    rejected_stage = work / "runtime-stage-99999999999999999999999999999992"
    _write_runtime(rejected_destination, b"untrusted-old-executable", b"operator-state")
    rejected_manifest_path = rejected_destination / "om0rx-build.json"
    rejected_manifest = json.loads(rejected_manifest_path.read_text(encoding="utf-8"))
    rejected_manifest["mutable_paths"].append("settings/untrusted/**")
    rejected_manifest_path.write_text(json.dumps(rejected_manifest), encoding="utf-8")
    _write_runtime(rejected_stage, b"new-executable", b"operator-state")

    rejected = _run_installer(rejected_stage, rejected_destination, work)

    assert rejected.returncode != 0
    assert "not a known whitelist subset" in rejected.stderr
    assert (rejected_destination / "MSHV_OM0RX.exe").read_bytes() == b"untrusted-old-executable"
    assert rejected_stage.exists()


def _run_installer(staged: Path, destination: Path, work: Path, *, env=None, check=False):
    return subprocess.run(
        [
            shutil.which("pwsh.exe") or "powershell.exe",
            "-NoProfile",
            "-File",
            str(INSTALLER),
            "-StagedRuntime",
            str(staged),
            "-Destination",
            str(destination),
            "-WorkRoot",
            str(work),
        ],
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def test_runtime_transaction_rejects_unapproved_destination_and_bad_inventory(tmp_path: Path) -> None:
    work = tmp_path / "build"
    staged = work / "runtime-stage-22222222222222222222222222222222"
    _write_runtime(staged, b"new-executable", b"operator-state")
    invalid_destination = work / "arbitrary-runtime"
    result = _run_installer(staged, invalid_destination, work)
    assert result.returncode != 0
    assert "destination is not approved" in result.stderr
    assert staged.exists()

    approved = work / "phase1-runtime"
    (staged / "undeclared.dll").write_bytes(b"not-in-manifest")
    result = _run_installer(staged, approved, work)
    assert result.returncode != 0
    assert "undeclared immutable files" in result.stderr
    assert staged.exists()
    assert not approved.exists()


def test_runtime_transaction_rolls_back_after_injected_post_swap_failure(tmp_path: Path) -> None:
    work = tmp_path / "build"
    destination = work / "phase1-runtime"
    staged = work / "runtime-stage-33333333333333333333333333333333"
    _write_runtime(destination, b"old-executable", b"operator-state")
    _write_runtime(staged, b"new-executable", b"operator-state")
    env = os.environ.copy()
    env["OM0RX_PACKAGE_TRANSACTION_TEST"] = "fail-after-swap"

    result = _run_installer(staged, destination, work, env=env)

    assert result.returncode != 0
    assert "Injected post-swap validation failure" in result.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"old-executable"
    failed = list(work.glob("runtime-failed-*"))
    assert len(failed) == 1
    assert (failed[0] / "MSHV_OM0RX.exe").read_bytes() == b"new-executable"


def test_runtime_transaction_rejects_reparse_stage_and_ambiguous_stage_name(tmp_path: Path) -> None:
    work = tmp_path / "build"
    real_stage = work / "real-stage"
    _write_runtime(real_stage, b"new-executable", b"operator-state")
    link_stage = work / "runtime-stage-44444444444444444444444444444444"
    try:
        link_stage.symlink_to(real_stage, target_is_directory=True)
    except OSError:
        junction = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link_stage), str(real_stage)],
            capture_output=True,
            text=True,
        )
        assert junction.returncode == 0, junction.stderr or junction.stdout

    result = _run_installer(link_stage, work / "phase1-runtime", work)
    assert result.returncode != 0
    assert "reparse point" in result.stderr
    link_stage.rmdir()

    ambiguous = work / "runtime-stage-not-a-guid"
    _write_runtime(ambiguous, b"new-executable", b"operator-state")
    result = _run_installer(ambiguous, work / "phase1-runtime", work)
    assert result.returncode != 0
    assert "approved deterministic stage" in result.stderr


def test_runtime_transaction_rejects_empty_or_executable_less_manifest_without_touching_destination(
    tmp_path: Path,
) -> None:
    work = tmp_path / "build"
    destination = work / "phase1-runtime"
    _write_runtime(destination, b"old-executable", b"operator-state")

    empty_stage = work / "runtime-stage-55555555555555555555555555555555"
    _write_runtime(empty_stage, b"new-executable", b"operator-state")
    empty_manifest_path = empty_stage / "om0rx-build.json"
    empty_manifest = json.loads(empty_manifest_path.read_text(encoding="utf-8"))
    empty_manifest["files"] = {}
    empty_manifest["executable_sha256"] = None
    empty_manifest_path.write_text(json.dumps(empty_manifest), encoding="utf-8")

    result = _run_installer(empty_stage, destination, work)
    assert result.returncode != 0
    assert "immutable file inventory is empty" in result.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"old-executable"
    assert empty_stage.exists()

    null_hash_stage = work / "runtime-stage-77777777777777777777777777777777"
    _write_runtime(null_hash_stage, b"new-executable", b"operator-state")
    null_hash_manifest_path = null_hash_stage / "om0rx-build.json"
    null_hash_manifest = json.loads(null_hash_manifest_path.read_text(encoding="utf-8"))
    null_hash_manifest["executable_sha256"] = None
    null_hash_manifest_path.write_text(json.dumps(null_hash_manifest), encoding="utf-8")

    result = _run_installer(null_hash_stage, destination, work)
    assert result.returncode != 0
    assert "executable_sha256 must be a non-null 64-hex SHA256" in result.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"old-executable"
    assert null_hash_stage.exists()

    missing_exe_stage = work / "runtime-stage-66666666666666666666666666666666"
    _write_runtime(missing_exe_stage, b"new-executable", b"operator-state")
    (missing_exe_stage / "MSHV_OM0RX.exe").unlink()
    marker = missing_exe_stage / "immutable.txt"
    marker.write_bytes(b"declared-but-not-executable")
    missing_manifest_path = missing_exe_stage / "om0rx-build.json"
    missing_manifest = json.loads(missing_manifest_path.read_text(encoding="utf-8"))
    missing_manifest["files"] = {"immutable.txt": _sha(marker)}
    missing_manifest_path.write_text(json.dumps(missing_manifest), encoding="utf-8")

    result = _run_installer(missing_exe_stage, destination, work)
    assert result.returncode != 0
    assert "does not explicitly declare MSHV_OM0RX.exe" in result.stderr
    assert (destination / "MSHV_OM0RX.exe").read_bytes() == b"old-executable"
    assert missing_exe_stage.exists()
