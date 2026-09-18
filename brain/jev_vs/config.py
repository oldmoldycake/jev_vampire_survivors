"""Runtime configuration loaded from config.toml. Thresholds live in questions.py."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Config:
    plugin_host: str = "127.0.0.1"
    plugin_port: int = 48231
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 48232
    tick_hz: float = 4.0
    model: str = "jev-latest"
    request_timeout_s: float = 0.8
    max_retries: int = 1
    log_dir: str = "runs"


def load_config(path: Path | None) -> Config:
    cfg = Config()
    if path is None:
        return cfg
    data = tomllib.loads(Path(path).read_text())
    plugin = data.get("plugin", {})
    dash = data.get("dashboard", {})
    brain = data.get("brain", {})
    return replace(
        cfg,
        plugin_host=plugin.get("host", cfg.plugin_host),
        plugin_port=int(plugin.get("port", cfg.plugin_port)),
        dashboard_host=dash.get("host", cfg.dashboard_host),
        dashboard_port=int(dash.get("port", cfg.dashboard_port)),
        tick_hz=float(brain.get("tick_hz", cfg.tick_hz)),
        model=str(brain.get("model", cfg.model)),
        request_timeout_s=float(brain.get("request_timeout_s", cfg.request_timeout_s)),
        max_retries=int(brain.get("max_retries", cfg.max_retries)),
        log_dir=str(brain.get("log_dir", cfg.log_dir)),
    )
