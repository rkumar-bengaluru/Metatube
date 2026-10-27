"""UTF-8, comment-preserving sidecar IO. An existing video_id is never changed or removed."""

import io
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString

from metatube_helper.schema import ALLOWED_KEYS


class LiveSidecarError(Exception):
    """Raised when a write would change or remove an existing video_id."""


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def load_sidecar(path: Path) -> CommentedMap:
    data = _yaml().load(Path(path).read_text(encoding="utf-8"))
    return data if data is not None else CommentedMap()


def write_sidecar(path: Path, data: Mapping[str, Any]) -> None:
    path = Path(path)
    unknown = set(data) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"unknown sidecar keys: {', '.join(sorted(unknown))}")

    if path.exists():
        existing_id = load_sidecar(path).get("video_id")
        if existing_id is not None and data.get("video_id") != existing_id:
            raise LiveSidecarError(
                f"{path.name}: video_id {existing_id} is live and cannot be changed or removed"
            )

    out = data if isinstance(data, CommentedMap) else CommentedMap(data)
    for key, value in out.items():
        if isinstance(value, str) and "\n" in value:
            out[key] = LiteralScalarString(value)

    buf = io.StringIO()
    _yaml().dump(out, buf)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def set_video_id(path: Path, video_id: str) -> None:
    data = load_sidecar(path)
    existing = data.get("video_id")
    if existing == video_id:
        return
    if existing is not None:
        raise LiveSidecarError(f"{Path(path).name}: already has video_id {existing}")
    data["video_id"] = video_id
    write_sidecar(path, data)
