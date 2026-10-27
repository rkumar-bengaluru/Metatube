"""MetaTube bookkeeping (`metatube.yaml`) in a Walker source folder. Sidecars win on video ids."""

import dataclasses
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

MANIFEST_NAME = "metatube.yaml"
SINGLE_KEY = "video"


@dataclass
class EpisodeRecord:
    run_id: str | None = None
    pin_run: str | None = None
    video_id: str | None = None
    blank_caption: bool = False


@dataclass
class PlaylistRecord:
    title: str
    description: str
    privacy: str
    id: str | None = None
    added: list[str] = field(default_factory=list)


@dataclass
class Manifest:
    repo: str | None = None
    episodes: dict[str, EpisodeRecord] = field(default_factory=dict)
    playlist: PlaylistRecord | None = None


@dataclass
class Conflict:
    episode: str
    manifest_id: str
    sidecar_id: str


def _pick(cls, raw: dict) -> dict:
    known = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in raw.items() if k in known}


def load_manifest(folder: Path) -> Manifest:
    path = Path(folder) / MANIFEST_NAME
    if not path.exists():
        return Manifest()
    raw = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    episodes = {
        str(k): EpisodeRecord(**_pick(EpisodeRecord, v or {})) for k, v in (raw.get("episodes") or {}).items()
    }
    pl = raw.get("playlist")
    playlist = PlaylistRecord(**_pick(PlaylistRecord, pl)) if pl else None
    return Manifest(repo=raw.get("repo"), episodes=episodes, playlist=playlist)


def save_manifest(folder: Path, m: Manifest) -> Path:
    path = Path(folder) / MANIFEST_NAME
    buf = io.StringIO()
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.dump(dataclasses.asdict(m), buf)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def sync_ids(m: Manifest, live: dict[str, tuple[str, str]]) -> tuple[Manifest, list[Conflict]]:
    """Copy sidecar video ids into the manifest. `live` maps episode -> (run_id, sidecar video_id)."""
    episodes = {k: dataclasses.replace(v) for k, v in m.episodes.items()}
    conflicts: list[Conflict] = []
    for ep, (run_id, sidecar_id) in live.items():
        rec = episodes.setdefault(ep, EpisodeRecord())
        if not rec.video_id:
            rec.video_id, rec.run_id = sidecar_id, run_id
        elif rec.video_id == sidecar_id:
            rec.run_id = run_id
        else:
            conflicts.append(Conflict(ep, rec.video_id, sidecar_id))
    return dataclasses.replace(m, episodes=episodes), conflicts
