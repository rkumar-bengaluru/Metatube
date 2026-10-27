import pytest

from metatube_helper.config import Config, default_mode, load_config, save_config, set_value


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    path = tmp_path / "metatube" / "config.yaml"
    monkeypatch.setenv("METATUBE_CONFIG", str(path))
    return path


def test_missing_file_gives_defaults(cfg_path):
    cfg = load_config()
    assert cfg.defaults["privacy"] == "public"
    assert cfg.defaults["category_id"] == "28"
    assert cfg.defaults["made_for_kids"] is False
    assert default_mode(cfg) == "update"


def test_save_load_round_trip(cfg_path):
    save_config(Config(channel_id="UC123", channel_title="Café Dev", gcp_project="p1"))
    cfg = load_config()
    assert (cfg.channel_id, cfg.channel_title, cfg.gcp_project) == ("UC123", "Café Dev", "p1")
    assert cfg.defaults["default_language"] == "en"


def test_set_value_bool_and_nested(cfg_path):
    cfg = set_value(Config(), "audit_passed", "true")
    assert default_mode(cfg) == "upload"
    cfg = set_value(cfg, "defaults.category_id", "27")
    cfg = set_value(cfg, "defaults.made_for_kids", "false")
    assert cfg.defaults["category_id"] == "27" and cfg.defaults["made_for_kids"] is False


def test_set_value_unknown_key_raises():
    with pytest.raises(ValueError):
        set_value(Config(), "refresh_token", "x")
    with pytest.raises(ValueError):
        set_value(Config(), "defaults.nope", "x")


def test_config_never_contains_token_keys(cfg_path):
    save_config(Config(channel_id="UC123"))
    text = cfg_path.read_text(encoding="utf-8")
    for word in ("token", "refresh_token", "client_secret"):
        assert word not in text
