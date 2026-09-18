"""python -m jev_vs  |  uv run jev-vs"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web

from .config import Config, load_config
from .dashboard import make_app, run_dashboard
from .decide import Decider
from .hub import Hub
from .jev_client import JevClient
from .questions import DEFAULT_THRESHOLDS
from .runlog import RunLog
from .server import PluginServer
from .stats import Stats

log = logging.getLogger("jev_vs")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    default_cfg = Path(__file__).resolve().parent.parent / "config.toml"
    p = argparse.ArgumentParser(prog="jev-vs", description="Jev plays Vampire Survivors: brain")
    p.add_argument("--config", type=Path, default=default_cfg if default_cfg.exists() else None)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def build(config: Config, jev=None) -> tuple[PluginServer, web.Application]:
    jev = jev or JevClient(model=config.model, timeout_s=config.request_timeout_s, max_retries=config.max_retries)
    server = PluginServer(config, Decider(jev, DEFAULT_THRESHOLDS), RunLog(Path(config.log_dir)), Hub(), Stats())
    return server, make_app(server)


async def run(config: Config) -> None:
    if not os.environ.get("TYPESAFE_API_KEY"):
        log.warning("TYPESAFE_API_KEY is not set; every decision will be a fallback")
    server, app = build(config)
    await server.start()
    runner = await run_dashboard(app, config.dashboard_host, config.dashboard_port)
    log.info("brain ready: plugin port %d, dashboard http://%s:%d/", server.port, config.dashboard_host, config.dashboard_port)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    log.info("shutting down")
    await server.stop()
    await runner.cleanup()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    asyncio.run(run(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
