"""Find videos, their sidecars and source material in a project folder (non-recursive)."""

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metatube_helper.schema import SUPPORTED_VIDEO_EXTS, UNSUPPORTED_VIDEO_EXTS
from metatube_helper.sidecars import load_sidecar

NOTES_EXTS = (".md", ".txt")
TRANSCRIPT_EXTS = (".srt", ".vtt")
SLIDES_EXTS = (".pdf", ".pptx")
THUMBNAIL_EXTS = (".jpg", ".png")


@dataclass
class VideoEntry:
    path: Path
    stem: str
    sidecar: Path | None
    video_id: str | None
    notes: list[Path]
    transcripts: list[Path]
    slides: list[Path]
    thumbnail: Path | None
    folder_source: bool = False
    sidecar_error: str | None = None
    thin_sources: list[Path] = dataclasses.field(default_factory=list)

    @property
    def live(self) -> bool:
        return self.video_id is not None

    @property
    def has_source(self) -> bool:
        usable = [p for p in self.notes + self.transcripts + self.slides if p not in self.thin_sources]
        return bool(usable or self.folder_source)


@dataclass
class Discovery:
    folder: Path
    videos: list[VideoEntry]
    unsupported: list[Path]
    orphan_sidecars: list[Path]
    folder_readme: Path | None

    @property
    def fully_paired(self) -> bool:
        return all(v.sidecar is not None for v in self.videos) and not self.orphan_sidecars


MIN_NOTES_WORDS = 20
MIN_TRANSCRIPT_WORDS = 3
_FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*(\n|\Z)", re.DOTALL)
_CUE_LINE = re.compile(r"^(\d+|WEBVTT.*|[\d:.,]+\s*-->\s*[\d:.,]+.*)$")


def _is_thin(path: Path) -> bool:
    """True when a source file has too little real content to write metadata from."""
    ext = path.suffix.lower()
    if ext in SLIDES_EXTS:
        return path.stat().st_size == 0
    text = path.read_text(encoding="utf-8", errors="replace")
    if ext in TRANSCRIPT_EXTS:
        words = [w for line in text.splitlines() if not _CUE_LINE.match(line.strip()) for w in line.split()]
        return len(words) < MIN_TRANSCRIPT_WORDS
    body = _FRONTMATTER.sub("", text)
    return len(re.findall(r"\w+", body)) < MIN_NOTES_WORDS


def _siblings(files: dict[str, Path], stem: str, exts: tuple[str, ...]) -> list[Path]:
    return [files[stem + ext] for ext in exts if stem + ext in files]


def discover(folder: Path) -> Discovery:
    folder = Path(folder)
    children = sorted(p for p in folder.iterdir() if p.is_file())
    files = {p.name: p for p in children}
    readme = next((p for p in children if p.name.lower() == "readme.md"), None)

    video_paths = [p for p in children if p.suffix.lower() in SUPPORTED_VIDEO_EXTS]
    unsupported = [p for p in children if p.suffix.lower() in UNSUPPORTED_VIDEO_EXTS]
    video_stems = {p.stem for p in video_paths}
    single_with_readme = len(video_paths) == 1 and readme is not None and not _is_thin(readme)

    videos: list[VideoEntry] = []
    for path in video_paths:
        stem = path.stem
        sidecar = files.get(stem + ".yaml")
        video_id, error = None, None
        if sidecar is not None:
            try:
                video_id = load_sidecar(sidecar).get("video_id")
            except Exception as exc:  # malformed YAML: report, don't crash discovery
                error = str(exc)
        notes = [p for p in _siblings(files, stem, NOTES_EXTS) if p != readme]
        transcripts = _siblings(files, stem, TRANSCRIPT_EXTS)
        slides = _siblings(files, stem, SLIDES_EXTS)
        thumbs = _siblings(files, stem, THUMBNAIL_EXTS)
        videos.append(
            VideoEntry(
                path=path,
                stem=stem,
                sidecar=sidecar,
                video_id=video_id,
                notes=notes,
                transcripts=transcripts,
                slides=slides,
                thumbnail=thumbs[0] if thumbs else None,
                folder_source=single_with_readme,
                sidecar_error=error,
                thin_sources=[p for p in notes + transcripts + slides if _is_thin(p)],
            )
        )

    orphans = [p for p in children if p.suffix == ".yaml" and p.stem not in video_stems]
    return Discovery(folder, videos, unsupported, orphans, readme)


def to_jsonable(obj: Any) -> Any:
    """Convert dataclasses (including properties of ours), Paths and containers to JSON-safe data."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        for name, attr in vars(type(obj)).items():
            if isinstance(attr, property):
                out[name] = to_jsonable(getattr(obj, name))
        return out
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
