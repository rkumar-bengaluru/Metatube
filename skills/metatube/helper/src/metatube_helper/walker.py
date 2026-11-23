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


@dataclass
class ShortVideo(RunVideo):
    """One of a run's YouTube Shorts: Walker's number for it (1 to 5), its title, hook and why from `short.yaml`, and
    whether its file is gone while its sidecar still holds a `video_id`."""
    number: int = 1
    title: str | None = None
    hook: str | None = None
    why: str | None = None
    missing: bool = False


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


MAX_SHORTS = 5  # Walker's `project.shorts` cap


def short_name(stem: str, number: int) -> str:
    """Walker's name for Short `number`: `<stem>-short`, then `<stem>-short-2` … `<stem>-short-5`."""
    return f"{stem}-short" if number == 1 else f"{stem}-short-{number}"


def _text(entry: dict, key: str) -> str | None:
    value = entry.get(key)
    return str(value) if value else None


def _run_shorts(run: Path, stem: str) -> list[ShortVideo]:
    """The Shorts in `<run>/shorts/`, in Walker's order, each with its title, hook and why from Walker's `short.yaml`
    (entry k-1 is Short k; a missing or unreadable file gives None). A Short whose `.mp4` Walker removed (a failed
    rebuild) but whose sidecar still holds a `video_id` is kept, marked `missing`: it is still on YouTube."""
    folder = run / "shorts"
    entries = _read_yaml(folder / "short.yaml").get("shorts")
    entries = entries if isinstance(entries, list) else []
    out = []
    for k in range(1, MAX_SHORTS + 1):
        name = short_name(stem, k)
        entry = entries[k - 1] if k <= len(entries) and isinstance(entries[k - 1], dict) else {}
        meta = (k, _text(entry, "title"), _text(entry, "hook"), _text(entry, "why"))
        if (folder / f"{name}.mp4").is_file():
            rv = run_video(folder, name)  # its run_id is "shorts"; a Short's is its run's
            out.append(ShortVideo(run.name, rv.folder, rv.video, rv.srt, rv.sidecar, rv.video_id, rv.mtime, *meta))
        elif (sidecar := folder / f"{name}.yaml").is_file() and (vid := _read_yaml(sidecar).get("video_id")):
            out.append(ShortVideo(run.name, folder, folder / f"{name}.mp4", None, sidecar, str(vid), 0.0, *meta,
                                  missing=True))
    return out


def find_shorts(root: Path, stem: str) -> tuple[list[ShortVideo], list[str]]:
    """The Shorts Walker rendered beside one run, in Walker's order: the newest run with a Short on YouTube, else the
    newest run with a Short. And warnings: a newer render's Shorts left out, two renders with Shorts on YouTube, a
    Short on YouTube whose file is gone."""
    if not root.is_dir():
        return [], []
    by_run = [s for run in sorted(p for p in root.iterdir() if p.is_dir()) if (s := _run_shorts(run, stem))]
    live = [s for s in by_run if any(x.video_id for x in s)]
    pick = choose_run([s[0] for s in live]) or choose_run([s[0] for s in by_run])
    shorts = next((s for s in by_run if s[0] is pick), [])
    warnings = []
    if len(live) > 1:
        warnings.append(f"renders {', '.join(s[0].run_id for s in live)} all have Shorts on YouTube; showing "
                        f"{pick.run_id}'s, the newest")
    newest = choose_run([s[0] for s in by_run])
    if live and newest is not pick:
        nums = ", ".join(str(x.number) for x in next(s for s in by_run if s[0] is newest))
        warnings.append(f"the newer render {newest.run_id} has Shorts {nums}; these are {pick.run_id}'s because one "
                        "of them is on YouTube")
    warnings += [f"Short {x.number} is on YouTube ({x.video_id}) but its file is gone (Walker removes a Short whose "
                 "rebuild failed)" for x in shorts if x.missing]
    return shorts, warnings


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
