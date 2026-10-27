"""Sidecar schema (mirrors ytstudio-cli 0.4.2 UploadSpec) and MetaTube lint rules."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

SUPPORTED_VIDEO_EXTS: tuple[str, ...] = (".mp4", ".mov", ".mkv", ".webm")
UNSUPPORTED_VIDEO_EXTS: tuple[str, ...] = (".avi", ".wmv", ".m4v", ".flv", ".mpg", ".mpeg", ".3gp")

TITLE_SOFT_MAX = 70
TAGS_MIN, TAGS_MAX = 8, 15
TAGS_TOTAL_MAX_CHARS = 500
DESCRIPTION_MAX_BYTES = 5000


class Privacy(StrEnum):
    private = "private"
    unlisted = "unlisted"
    public = "public"


class Sidecar(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = ""
    privacy: Privacy = Privacy.private
    publish_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    category_id: str = Field(min_length=1)
    default_language: str | None = None
    default_audio_language: str | None = None
    made_for_kids: bool = False
    video_id: str | None = None
    uploaded_at: datetime | None = None

    model_config = {"extra": "forbid"}

    @field_validator("publish_at")
    @classmethod
    def _publish_at_tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("publish_at must include a timezone (e.g. +05:30)")
        return v

    @model_validator(mode="after")
    def _publish_at_future(self) -> "Sidecar":
        if self.publish_at is not None and self.publish_at <= datetime.now(UTC):
            raise ValueError("publish_at must be in the future")
        return self


ALLOWED_KEYS: frozenset[str] = frozenset(Sidecar.model_fields)


@dataclass
class LintResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint(data: Mapping[str, Any]) -> LintResult:
    result = LintResult()
    try:
        spec = Sidecar.model_validate(dict(data))
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "sidecar"
            result.errors.append(f"{loc}: {err['msg']}")
        return result

    if len(spec.title) > TITLE_SOFT_MAX:
        result.warnings.append(f"title: {len(spec.title)} chars, aim for <= {TITLE_SOFT_MAX}")
    for name in ("title", "description"):
        if any(ch in getattr(spec, name) for ch in "<>"):
            result.errors.append(f"{name}: YouTube rejects '<' and '>'")
    desc_bytes = len(spec.description.encode("utf-8"))
    if desc_bytes > DESCRIPTION_MAX_BYTES:
        result.errors.append(f"description: {desc_bytes} bytes, YouTube allows {DESCRIPTION_MAX_BYTES}")
    for tag in spec.tags:
        if "," in tag:
            result.errors.append(f"tags: {tag!r} contains a comma (ytstudio splits tags on commas)")
    # YouTube counts the separating commas and wraps multi-word tags in quotes.
    total = sum(len(t) + (2 if " " in t else 0) for t in spec.tags) + max(len(spec.tags) - 1, 0)
    if total > TAGS_TOTAL_MAX_CHARS:
        result.errors.append(f"tags: {total} chars as YouTube counts them, limit {TAGS_TOTAL_MAX_CHARS}")
    if not TAGS_MIN <= len(spec.tags) <= TAGS_MAX:
        result.warnings.append(f"tags: {len(spec.tags)} tags, aim for {TAGS_MIN}-{TAGS_MAX}")
    if spec.publish_at is not None and spec.privacy != Privacy.private:
        result.warnings.append("publish_at is set: ytstudio forces privacy to private")
    return result
