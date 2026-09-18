from pathlib import Path

from jev_vs.config import Config, load_config


def test_defaults_when_no_file():
    cfg = load_config(None)
    assert cfg.plugin_port == 48231
    assert cfg.dashboard_port == 48232
    assert cfg.tick_hz == 4.0
    assert cfg.model == "jev-latest"
    assert cfg.log_dir == "runs"
    assert cfg.state_file == "pins.json"


def test_file_overrides_defaults(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[plugin]\nport = 5000\n[brain]\ntick_hz = 2.5\nmodel = "jev-1.13.0"\nstate_file = "pins-test.json"\n')
    cfg = load_config(p)
    assert cfg.plugin_port == 5000
    assert cfg.tick_hz == 2.5
    assert cfg.model == "jev-1.13.0"
    assert cfg.state_file == "pins-test.json"
    assert cfg.dashboard_port == 48232


def test_config_is_frozen():
    cfg = Config()
    try:
        cfg.tick_hz = 1.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Config must be frozen")
