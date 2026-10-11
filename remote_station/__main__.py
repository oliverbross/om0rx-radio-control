"""Command-line entry point for the Windows remote-station agent."""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from .app import create_app
from .config import AgentConfigError, default_config_path, load_agent_config, write_default_config
from .controller_ownership import (
    CONFLICT_EXIT_CODE,
    ControllerOwnershipConflict,
    ControllerOwnershipError,
    StationControllerOwnership,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m remote_station")
    parser.add_argument(
        "command", choices=("init", "check", "run", "config-path"), nargs="?", default="run"
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--log-level", default="info", choices=("debug", "info", "warning", "error")
    )
    parser.add_argument("--launch-source", default="direct-python")
    return parser


def main() -> int:
    args = _parser().parse_args()
    path = args.config or default_config_path()
    if args.command == "config-path":
        print(path.expanduser().resolve())
        return 0
    if args.command == "init":
        created = write_default_config(path)
        print(f"Created {created}")
        print(
            "Set flex.host and review the complete band policy before enabling commissioned control."
        )
        return 0
    try:
        config = load_agent_config(path)
    except AgentConfigError as exc:
        raise SystemExit(str(exc)) from exc
    if args.command == "check":
        print(f"Configuration valid: {config.path}")
        print(
            f"FLEX {config.flex_host}:{config.flex_port}; KPA {config.kpa_port}; KAT {config.kat_port}"
        )
        print(f"Commissioned controls: {'enabled' if config.commissioned else 'locked'}")
        return 0

    log_path = config.path.with_name("agent.log")
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(
                log_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )
    entry_logger = logging.getLogger(__name__)
    entry_logger.info("Remote station agent log: %s", log_path)
    ownership = StationControllerOwnership(
        "python-remote-station-agent",
        args.launch_source,
    )
    try:
        ownership.acquire()
    except ControllerOwnershipConflict as exc:
        entry_logger.critical("%s", exc)
        return CONFLICT_EXIT_CODE
    except (ControllerOwnershipError, OSError) as exc:
        entry_logger.critical("Station controller ownership could not be established: %s", exc)
        return CONFLICT_EXIT_CODE + 1
    try:
        if ownership.abandoned:
            previous = ownership.previous_owner
            prior = (
                f"{previous.controller_family} PID {previous.pid}"
                if previous
                else "unknown prior controller"
            )
            entry_logger.warning(
                "Recovered abandoned station-controller ownership from %s; "
                "normal startup safety validation remains required.",
                prior,
            )
        uvicorn.run(
            create_app(config),
            host=config.bind_host,
            port=config.bind_port,
            log_level=args.log_level,
            log_config=None,
            access_log=False,
        )
    finally:
        ownership.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
