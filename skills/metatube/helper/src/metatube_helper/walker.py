"""Read Walker source folders and find the videos Walker rendered for them in its home folder."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML

RUN_ID = re.compile(r"^\d{8}-\d{6}$")


@dataclass
class WalkerSource:
    kind: Literal["series", "single"]
    folder: Path
    title: str
    series_name: str | None
    episodes: list[str]
    project: dict
    repo_name: str | None


@dataclass
class RunVideo:
    run_id: str
    folder: Path
    video: Path
    srt: Path | None
    sidecar: Path | None
    video_id: str | None
    mtime: float


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _is_walker(doc: dict[str, Any]) -> bool:
    return str(doc.get("format") or "").startswith("walker/")


def _series_doc(path: Path) -> dict[str, Any] | None:
    doc = _read_yaml(path)
    return doc if _is_walker(doc) and isinstance(doc.get("series"), dict) else None


def detect(folder: Path) -> Literal["series", "single", "episode", "plain"]:
    if (folder / "series.yaml").is_file() and _series_doc(folder / "series.yaml"):
        return "series"
    if (folder / "walker.yaml").is_file():
        parent = _series_doc(folder.parent / "series.yaml") if (folder.parent / "series.yaml").is_file() else None
        if parent and folder.name in (parent.get("episodes") or []):
            return "episode"
        if _is_walker(_read_yaml(folder / "walker.yaml")):
            return "single"
    return "plain"


def _repo_name(folder: Path) -> str | None:
    if folder.name == ".walker":
        return folder.parent.name or None
    if folder.parent.name == "series" and folder.parent.parent.name == ".walker":
        return folder.parent.parent.parent.name or None
    return None


def load_source(folder: Path, repo_name: str | None = None) -> WalkerSource:
    repo = repo_name or _repo_name(folder)
    if (folder / "series.yaml").is_file():
        doc = _read_yaml(folder / "series.yaml")
        series = doc.get("series") or {}
        name = series.get("name") or folder.name
        return WalkerSource(
            kind="series",
            folder=folder,
            title=str(series.get("title") or name),
            series_name=str(name),
            episodes=[str(e) for e in doc.get("episodes") or []],
            project=doc.get("project") or {},
            repo_name=repo,
        )
    doc = _read_yaml(folder / "walker.yaml")
    project = doc.get("project") or {}
    return WalkerSource(
        kind="single",
        folder=folder,
        title=str(project.get("title") or project.get("name") or repo or folder.name),
        series_name=None,
        episodes=[],
        project=project,
        repo_name=repo,
    )


def walker_home() -> Path:
    env = os.environ.get("WALKER_HOME")
    if env:
        return Path(env).expanduser()
    base = Path("~/.walker").expanduser()
    cfg = base / "config.yaml"
    if cfg.is_file():
        home = _read_yaml(cfg).get("home")
        if home:
            return Path(str(home)).expanduser()
    return base


def sanitize(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem)


def expected_stem(src: WalkerSource, episode: str | None) -> str:
    if src.kind == "series":
        return sanitize(f"{src.series_name}-{episode}")
    tag = src.project.get("walked_tag")
    return sanitize(f"{src.repo_name}-{tag}") if tag else sanitize(str(src.repo_name))


def video_root(src: WalkerSource, episode: str | None) -> Path:
    if src.repo_name is None:
        raise ValueError("repo name unknown")
    home = walker_home() / src.repo_name
    if src.kind == "series":
        return home / "series" / str(src.series_name) / str(episode) / "video"
    return home / "video"


def run_video(folder: Path, stem: str) -> RunVideo:
    """The RunVideo for `<folder>/<stem>.mp4`, with its srt, sidecar and sidecar video id."""
    video = folder / f"{stem}.mp4"
    srt = folder / f"{stem}.srt"
    sidecar = folder / f"{stem}.yaml"
    video_id = None
    if sidecar.is_file():
        vid = _read_yaml(sidecar).get("video_id")
        video_id = str(vid) if vid else None
    return RunVideo(
        run_id=folder.name,
        folder=folder,
        video=video,
        srt=srt if srt.is_file() else None,
        sidecar=sidecar if sidecar.is_file() else None,
        video_id=video_id,
        mtime=video.stat().st_mtime,
    )


def find_runs(root: Path, stem: str) -> tuple[list[RunVideo], list[Path]]:
    """Run folders holding `<stem>.mp4`, and run folders holding only `explainer.mp4`."""
    if not root.is_dir():
        return [], []
    cands: list[RunVideo] = []
    explainers: list[Path] = []
    for run in sorted(p for p in root.iterdir() if p.is_dir()):
        if (run / f"{stem}.mp4").is_file():
            cands.append(run_video(run, stem))
        elif (run / "explainer.mp4").is_file():
            explainers.append(run)
    return cands, explainers


def find_short(root: Path, stem: str) -> RunVideo | None:
    """The Short Walker rendered beside a run (`<run>/shorts/<stem>-short.mp4`): the one on YouTube, else the newest."""
    if not root.is_dir():
        return None
    shorts = [run_video(run / "shorts", f"{stem}-short") for run in sorted(p for p in root.iterdir() if p.is_dir())
              if (run / "shorts" / f"{stem}-short.mp4").is_file()]
    for s in shorts:
        s.run_id = s.folder.parent.name  # the run's id, not "shorts"
    # shortcut: two live Shorts with different ids pick the newest, not a disagreement; add one if it happens
    return choose_run([s for s in shorts if s.video_id]) or choose_run(shorts)


def choose_run(cands: list[RunVideo]) -> RunVideo | None:
    """The newest run: by run id when all ids are Walker timestamps, else by file mtime.

    The mtime fallback is best-effort: copies and syncs change mtimes.
    """
    if not cands:
        return None
    if all(RUN_ID.match(c.run_id) for c in cands):
        return max(cands, key=lambda c: c.run_id)
    return max(cands, key=lambda c: c.mtime)


def odd_run_ids(cands: list[RunVideo]) -> list[str]:
    return [c.run_id for c in cands if not RUN_ID.match(c.run_id)]
