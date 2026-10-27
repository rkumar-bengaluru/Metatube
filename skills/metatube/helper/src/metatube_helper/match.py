"""Match local video files to videos the owner uploaded in YouTube Studio."""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from metatube_helper.discover import VideoEntry

_ID = r"[A-Za-z0-9_-]{11}"
_REF_PATTERNS = [
    re.compile(rf"^({_ID})$"),
    re.compile(rf"youtu\.be/({_ID})(?:[?&/#]|$)"),
    re.compile(rf"[?&]v=({_ID})(?:[&#]|$)"),
    re.compile(rf"/(?:video|shorts|embed|live)/({_ID})(?:[?&/#]|$)"),
]


@dataclass
class ChannelVideo:
    id: str
    title: str
    privacy: str
    published_at: str


@dataclass
class Match:
    stem: str
    status: Literal["preset", "matched", "ambiguous", "missing"]
    video_id: str | None
    candidates: list[ChannelVideo] = field(default_factory=list)


def _key(text: str) -> str:
    return text.strip().casefold()


def match_videos(entries: list[VideoEntry], channel: list[ChannelVideo]) -> list[Match]:
    entries = [e for e in entries if e.sidecar is not None]
    claimed = {e.video_id for e in entries if e.video_id}
    free = [v for v in channel if v.id not in claimed]

    found: dict[int, list[ChannelVideo]] = {}
    for i, e in enumerate(entries):
        if not e.video_id:
            names = {_key(e.stem), _key(e.path.name)}
            found[i] = [v for v in free if _key(v.title) in names]
    single_hits = Counter(c[0].id for c in found.values() if len(c) == 1)

    matches: list[Match] = []
    for i, e in enumerate(entries):
        if e.video_id:
            matches.append(Match(e.stem, "preset", e.video_id))
            continue
        cands = found[i]
        if not cands:
            matches.append(Match(e.stem, "missing", None))
        elif len(cands) == 1 and single_hits[cands[0].id] == 1:
            matches.append(Match(e.stem, "matched", cands[0].id, cands))
        else:
            matches.append(Match(e.stem, "ambiguous", None, cands))
    return matches


def parse_video_ref(ref: str) -> str:
    ref = ref.strip()
    for pattern in _REF_PATTERNS:
        m = pattern.search(ref)
        if m:
            return m.group(1)
    raise ValueError(f"not a YouTube video id or URL: {ref!r}")
