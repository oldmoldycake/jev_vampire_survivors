from jev_vs.__main__ import build, parse_args
from jev_vs.config import Config


def test_parse_args_defaults_and_overrides(tmp_path):
    a = parse_args([])
    assert a.log_level == "INFO"
    p = tmp_path / "x.toml"
    p.write_text("[plugin]\nport = 1\n")
    a = parse_args(["--config", str(p), "--log-level", "DEBUG"])
    assert a.config == p and a.log_level == "DEBUG"


async def test_build_wires_server_and_app(tmp_path):
    srv, app = build(Config(plugin_port=0, log_dir=str(tmp_path)))
    assert srv.config.plugin_port == 0
    routes = {r.resource.canonical for r in app.router.routes()}
    assert "/" in routes and "/ws" in routes
    assert srv.decider.jev is not None

    from tests.conftest import FakeJev
    fake = FakeJev()
    srv2, _ = build(Config(plugin_port=0, log_dir=str(tmp_path)), jev=fake)
    assert srv2.decider.jev is fake
