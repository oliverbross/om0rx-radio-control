#!/usr/bin/env python3
"""Smoke checks for the no-build frontend module contract."""

from pathlib import Path
import re

import _bootstrap  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = PROJECT_ROOT / "frontend"
APP_MAIN = FRONTEND / "js" / "app-main.js"
INDEX = FRONTEND / "index.html"

REQUIRED_MODULES = {
    "js/config-modal.js": "RadioControlConfig",
    "js/solar-data.js": "RadioControlSolar",
    "js/wavelog-stats.js": "RadioControlWavelogStats",
}


def script_sources() -> list[str]:
    html = INDEX.read_text(encoding="utf-8")
    return re.findall(r'<script\s+src="([^"]+)"', html)


def test_required_modules_load_before_app_main():
    scripts = script_sources()
    assert "js/app-main.js" in scripts, "app-main.js is not loaded by index.html"
    app_main_index = scripts.index("js/app-main.js")

    missing = [script for script in REQUIRED_MODULES if script not in scripts]
    assert not missing, f"Missing frontend module script tags: {missing}"

    late = [script for script in REQUIRED_MODULES if scripts.index(script) > app_main_index]
    assert not late, f"Modules must load before app-main.js: {late}"


def test_required_modules_expose_expected_globals():
    for script, global_name in REQUIRED_MODULES.items():
        module_path = FRONTEND / script
        assert module_path.exists(), f"Missing module file: {script}"
        content = module_path.read_text(encoding="utf-8")
        assert f"window.{global_name}" in content, f"{script} does not expose window.{global_name}"
        assert "data:" in content, f"{script} does not define a data section"
        assert "methods:" in content, f"{script} does not define a methods section"


def test_app_main_merges_required_modules():
    content = APP_MAIN.read_text(encoding="utf-8")
    for global_name in REQUIRED_MODULES.values():
        assert f"window.{global_name}" in content, f"app-main.js does not check {global_name}"
        assert f"...window.{global_name}.data" in content, f"app-main.js does not merge {global_name}.data"
        assert f"...window.{global_name}.methods" in content, f"app-main.js does not merge {global_name}.methods"


def test_obvious_frontend_junk_is_not_tracked():
    assert not (FRONTEND / "conosle.log").exists(), "frontend/conosle.log should not exist"


if __name__ == "__main__":
    test_required_modules_load_before_app_main()
    test_required_modules_expose_expected_globals()
    test_app_main_merges_required_modules()
    test_obvious_frontend_junk_is_not_tracked()
    print("Frontend module contract smoke checks passed")
