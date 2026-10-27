"""Decide, per episode of a Walker source, which rendered run is used and whether it is live on YouTube."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from metatube_helper.discover import VideoEntry, discover, is_thin
from metatube_helper.manifest import SINGLE_KEY, EpisodeRecord, Manifest
from metatube_helper.walker import (
    RunVideo,
    WalkerSource,
    _read_yaml,
    choose_run,
    expected_stem,
    find_runs,
    odd_run_ids,
    video_root,
)

Status = Literal["ready", "live", "not_rendered", "explainer_only", "live_run_missing", "disagreement"]


@dataclass
class EpisodeState:
    key: str
    position: int
    status: Status
    run: RunVideo | None
    newer_run: str | None
    video_id: str | None
    notes: list[Path]
    transcript: Path | None
    thin_sources: list[Path]
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def has_source(self) -> bool:
        usable = [p for p in self.notes + ([self.transcript] if self.transcript else []) if p not in self.thin_sources]
        return bool(usable)


def _explainer_run(folder: Path) -> RunVideo:
    """A run folder holding only `explainer.mp4`, used because the owner pinned it."""
    video = folder / "explainer.mp4"
    srt = folder / "explainer.srt"
    sidecar = folder / "explainer.yaml"
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


def _note_files(src: WalkerSource, key: str) -> list[Path]:
    base = src.folder / key if src.kind == "series" else src.folder
    names = [base / "story.md", base / "screenplay.md"]
    if src.kind == "series":
        names.append(src.folder / "story.md")
    return [p for p in names if p.is_file()]


def _decide(
    cands: list[RunVideo], explainers: list[Path], rec: EpisodeRecord
) -> tuple[Status, RunVideo | None, str | None, str | None, str]:
    """Returns (status, run, newer_run, video_id, message)."""
    live = [c for c in cands if c.video_id]
    ids = {c.video_id for c in live}
    if len(ids) > 1:
        return "disagreement", None, None, None, f"runs carry different video ids: {', '.join(sorted(str(i) for i in ids))}"
    if live:
        run = choose_run(live)
        assert run is not None
        newest = choose_run(cands)
        newer = newest.run_id if newest and newest.run_id != run.run_id else None
        if rec.video_id and rec.video_id != run.video_id:
            return "disagreement", run, newer, run.video_id, (
                f"metatube.yaml has video id {rec.video_id} but the run's sidecar has {run.video_id}"
            )
        return "live", run, newer, run.video_id, ""
    if rec.video_id:
        return "live_run_missing", None, None, rec.video_id, (
            f"metatube.yaml has video id {rec.video_id} but no rendered run carries it"
        )
    run = None
    if rec.pin_run:
        run = next((c for c in cands if c.run_id == rec.pin_run), None)
    run = run or choose_run(cands)
    if run:
        return "ready", run, None, None, ""
    if explainers:
        return "explainer_only", None, None, None, (
            "only explainer.mp4 was rendered; re-render the episode or give the video id"
        )
    return "not_rendered", None, None, None, ""


def resolve(src: WalkerSource, m: Manifest) -> list[EpisodeState]:
    keys = list(src.episodes) if src.kind == "series" else [SINGLE_KEY]
    states: list[EpisodeState] = []
    for position, key in enumerate(keys, start=1):
        rec = m.episodes.get(key) or EpisodeRecord()
        episode = key if src.kind == "series" else None
        cands, explainers = find_runs(video_root(src, episode), expected_stem(src, episode))
        pinned = next((f for f in explainers if rec.pin_run and f.name == rec.pin_run), None)
        if pinned:
            cands = cands + [_explainer_run(pinned)]
        status, run, newer, video_id, message = _decide(cands, explainers, rec)
        notes = _note_files(src, key)
        transcript = run.srt if run else None
        thin = [p for p in notes + ([transcript] if transcript else []) if is_thin(p)]
        warnings = []
        odd = odd_run_ids(cands)
        if odd:
            warnings.append(
                f"run ids not in Walker's YYYYMMDD-HHMMSS form: {', '.join(odd)}; chose by file time (best effort)"
            )
        states.append(
            EpisodeState(key, position, status, run, newer, video_id, notes, transcript, thin, message, warnings)
        )
    return states


def walker_entries(states: list[EpisodeState]) -> list[VideoEntry]:
    entries = []
    for s in states:
        if s.run:
            entries.extend(e for e in discover(s.run.folder).videos if e.path == s.run.video)
    return entries
