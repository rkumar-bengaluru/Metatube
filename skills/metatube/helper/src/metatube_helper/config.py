"""MetaTube config: identifiers and defaults only, never tokens."""

import dataclasses
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML

DEFAULTS: dict = {
    "privacy": "public",
    "category_id": "28",
    "default_language": "en",
    "default_audio_language": "en",
    "made_for_kids": False,
}

_BOOL_KEYS = {"audit_passed", "defaults.made_for_kids"}


@dataclass
class Config:
    ytstudio_profile: str = "default"
    channel_id: str | None = None
    channel_title: str | None = None
    gcp_project: str | None = None
    ytstudio_version: str = "0.4.2"
    audit_passed: bool = False
    defaults: dict = field(default_factory=lambda: dict(DEFAULTS))


def config_path() -> Path:
    override = os.environ.get("METATUBE_CONFIG")
    return Path(override) if override else Path.home() / ".config" / "metatube" / "config.yaml"


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    raw = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    known = {f.name for f in dataclasses.fields(Config)}
    cfg = Config(**{k: v for k, v in raw.items() if k in known and k != "defaults"})
    cfg.defaults = {**DEFAULTS, **{k: v for k, v in (raw.get("defaults") or {}).items() if k in DEFAULTS}}
    return cfg


def save_config(cfg: Config) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.dump(dataclasses.asdict(cfg), buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    raise ValueError(f"expected true/false, got {value!r}")


def set_value(cfg: Config, key: str, value: str) -> Config:
    parsed: object = _parse_bool(value) if key in _BOOL_KEYS else value
    if key.startswith("defaults."):
        sub = key.removeprefix("defaults.")
        if sub not in DEFAULTS:
            raise ValueError(f"unknown config key: {key}")
        return dataclasses.replace(cfg, defaults={**cfg.defaults, sub: parsed})
    if key not in {f.name for f in dataclasses.fields(Config)} or key == "defaults":
        raise ValueError(f"unknown config key: {key}")
    return dataclasses.replace(cfg, **{key: parsed})


def default_mode(cfg: Config) -> Literal["update", "upload"]:
    return "upload" if cfg.audit_passed else "update"
