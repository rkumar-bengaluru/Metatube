"""Run ytstudio-cli safely: argv lists (no shell), UTF-8 forced, profile via env."""

import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from metatube_helper.discover import Discovery
from metatube_helper.match import ChannelVideo

PINNED_VERSION = "0.4.2"
QUOTA_UPLOAD = 1600
QUOTA_UPDATE = 50
QUOTA_PLAYLIST_CREATE = 50
QUOTA_PLAYLIST_ADD = 50
QUOTA_CAPTION_LIST = 50
QUOTA_CAPTION_INSERT = 400
DAILY_QUOTA = 10000
SAFE_UPLOADS_PER_DAY = 6

_API_DISABLED_MARKERS = ("has not been used in project", "it is disabled", "accessNotConfigured")
_EXPIRED_MARKERS = ("Session expired", "re-authenticate", "Credentials expired")
_NOT_INIT_MARKERS = ("No client secrets", "Not authenticated", "ytstudio init", "ytstudio login")


@dataclass
class RunResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class AuthResult:
    status: Literal["ok", "expired", "not_initialized", "not_installed", "api_disabled", "error"]
    detail: str


@dataclass
class UploadPlan:
    mode: Literal["folder", "per_file"]
    pending: list[Path]
    skipped_live: list[Path]
    not_ready: list[Path]
    commands: list[list[str]]


def run_ytstudio(args: list[str], profile: str | None = None) -> RunResult:
    argv = ["ytstudio", *args]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if profile:
        env["YTSTUDIO_PROFILE"] = profile
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
        )
    except FileNotFoundError:
        return RunResult(argv, 127, "", "ytstudio not found on PATH")
    return RunResult(argv, proc.returncode, proc.stdout or "", proc.stderr or "")


_IS_WINDOWS = os.name == "nt"


def ytstudio_python() -> Path | None:
    """ytstudio's own interpreter (a uv tool venv), or None if it can't be found."""
    try:
        proc = subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    venv = Path(proc.stdout.strip()) / "ytstudio-cli"
    py = venv / "Scripts" / "python.exe" if _IS_WINDOWS else venv / "bin" / "python"
    return py if py.exists() else None


def run_captions(args: list[str], profile: str | None = None) -> RunResult:
    """Run yt_captions.py under ytstudio's Python (it needs googleapiclient and ytstudio.services)."""
    py = ytstudio_python()
    if py is None:
        return RunResult(["yt_captions.py", *args], 127, "", "ytstudio's Python not found (uv tool dir)")
    argv = [str(py), str(Path(__file__).parent / "yt_captions.py"), *args]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if profile:
        env["YTSTUDIO_PROFILE"] = profile
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return RunResult(argv, proc.returncode, proc.stdout or "", proc.stderr or "")


def installed_version() -> str | None:
    result = run_ytstudio(["--version"])
    if result.returncode != 0:
        return None
    m = re.search(r"\d+\.\d+\.\d+", result.stdout + result.stderr)
    return m.group(0) if m else None


def auth_check(profile: str | None) -> AuthResult:
    result = run_ytstudio(["videos", "list", "-n", "1", "-o", "json"], profile)
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode == 0:
        return AuthResult("ok", "")
    if result.returncode == 127:
        return AuthResult("not_installed", output)
    if any(m in output for m in _API_DISABLED_MARKERS):
        return AuthResult("api_disabled", output)
    # Check expiry before "not initialized": the expiry message also mentions "ytstudio login".
    if any(m in output for m in _EXPIRED_MARKERS):
        return AuthResult("expired", output)
    if any(m in output for m in _NOT_INIT_MARKERS):
        return AuthResult("not_initialized", output)
    return AuthResult("error", output[-2000:])


def video_exists(video_id: str, profile: str | None) -> bool | None:
    """True/False when YouTube answers clearly; None when it can't tell (auth, network...)."""
    result = run_ytstudio(["videos", "show", "-o", "json", "--", video_id], profile)
    if result.returncode == 0:
        return True
    if "Video not found" in result.stdout + result.stderr:
        return False
    return None


def _json_of(stdout: str) -> dict:
    """The JSON ytstudio printed, ignoring anything after it (its "Update available" notice)."""
    return json.JSONDecoder().raw_decode(stdout.lstrip())[0]


def list_channel_videos(profile: str | None, limit: int = 50) -> list[ChannelVideo]:
    result = run_ytstudio(["videos", "list", "-n", str(limit), "-o", "json"], profile)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr).strip() or "ytstudio videos list failed")
    payload = _json_of(result.stdout)
    return [
        ChannelVideo(id=v["id"], title=v.get("title", ""), privacy=v.get("privacy", ""),
                     published_at=v.get("published_at", ""), description=v.get("description", ""),
                     tags=list(v.get("tags") or []))
        for v in payload.get("videos", [])
    ]


def update_argv(video_id: str, sidecar: Mapping[str, Any], execute: bool) -> list[str]:
    argv = ["videos", "update", "--title", str(sidecar["title"])]
    if sidecar.get("description"):
        argv += ["--description", str(sidecar["description"])]
    tags = list(sidecar.get("tags") or [])
    if any("," in str(t) for t in tags):
        raise ValueError("a tag contains a comma; ytstudio --tags splits on commas")
    if tags:
        argv += ["--tags", ",".join(str(t) for t in tags)]
    if execute:
        argv.append("--execute")
    # Ids may start with "-"; after "--" click treats it as positional, not an option.
    return [*argv, "--", video_id]


@dataclass
class PlaylistInfo:
    id: str
    title: str
    item_count: int
    privacy: str


@dataclass
class PlaylistItem:
    video_id: str
    title: str
    position: int


# ytstudio pages internally up to -n. A partial list could hide a duplicate playlist or misplace an
# episode, so the helper asks for everything and fails closed if ytstudio still reports another page.
PLAYLIST_READ_LIMIT = "5000"


def _json_or_raise(result: RunResult, what: str) -> dict:
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr).strip() or f"ytstudio {what} failed")
    payload = _json_of(result.stdout)
    if payload.get("next_page_token"):
        raise RuntimeError(f"ytstudio {what} returned only part of the list (more than {PLAYLIST_READ_LIMIT})")
    return payload


def list_playlists(profile: str | None) -> list[PlaylistInfo]:
    args = ["playlists", "list", "-n", PLAYLIST_READ_LIMIT, "-o", "json"]
    payload = _json_or_raise(run_ytstudio(args, profile), "playlists list")
    return [
        PlaylistInfo(id=p["id"], title=p.get("title", ""), item_count=int(p.get("item_count") or 0),
                     privacy=p.get("privacy", ""))
        for p in payload.get("playlists", [])
    ]


def playlist_items(playlist_id: str, profile: str | None) -> list[PlaylistItem]:
    """Items in playlist order. Ids may start with "-", so the id goes after "--"."""
    args = ["playlists", "items", "-n", PLAYLIST_READ_LIMIT, "-o", "json", "--", playlist_id]
    payload = _json_or_raise(run_ytstudio(args, profile), "playlists items")
    return [
        PlaylistItem(video_id=i.get("video_id", ""), title=i.get("title", ""), position=int(i.get("position") or 0))
        for i in payload.get("items", [])
    ]


def create_playlist_argv(title: str, description: str, privacy: str, language: str | None, execute: bool) -> list[str]:
    argv = ["playlists", "create", "--title", title, "--description", description, "--privacy", privacy]
    if language:
        argv += ["--language", language]
    if execute:
        argv.append("--execute")
    return argv


# rich wraps `✓ Created: <title> (<id>)` at 80 columns when stdout is captured, so the id may sit on
# its own line; ids have no spaces, so they are never split. ytstudio prints "unknown" if YouTube
# returned no id.
_CREATED = re.compile(r"Created: .*?\s\(([A-Za-z0-9_-]+)\)\s*\Z", re.DOTALL)


def parse_created_id(stdout: str) -> str:
    m = _CREATED.search(stdout)
    if not m or m.group(1) == "unknown":
        raise ValueError(f"no playlist id in ytstudio output: {stdout.strip()!r}")
    return m.group(1)


def add_argv(playlist_id: str, video_id: str, position: int, execute: bool) -> list[str]:
    opts = ["--video", video_id, "--position", str(position)] + (["--execute"] if execute else [])
    if playlist_id.startswith("-"):
        # After "--" click treats it as positional, not an option; options must come first then.
        return ["playlists", "add", *opts, "--", playlist_id]
    return ["playlists", "add", playlist_id, *opts]


def plan_upload(d: Discovery, max_uploads: int | None) -> UploadPlan:
    pending = [v.path for v in d.videos if v.sidecar is not None and not v.live]
    skipped = [v.path for v in d.videos if v.live]
    not_ready = [v.path for v in d.videos if v.sidecar is None]
    # Absolute paths never start with "-", so click can't mistake them for options.
    if d.fully_paired:
        cmd = ["videos", "upload", os.path.abspath(d.folder)]
        if max_uploads:
            cmd += ["--max", str(max_uploads)]
        commands = [cmd]
        mode: Literal["folder", "per_file"] = "folder"
    else:
        chosen = pending[:max_uploads] if max_uploads else pending
        commands = [["videos", "upload", os.path.abspath(p)] for p in chosen]
        mode = "per_file"
    if max_uploads:
        pending = pending[:max_uploads]
    return UploadPlan(mode, pending, skipped, not_ready, commands)


def run_upload(plan: UploadPlan, execute: bool, profile: str | None) -> list[RunResult]:
    results: list[RunResult] = []
    for cmd in plan.commands:
        result = run_ytstudio([*cmd, "--execute"] if execute else cmd, profile)
        results.append(result)
        if result.returncode != 0:
            break
    return results


def estimate_quota(
    uploads: int = 0,
    updates: int = 0,
    playlist_creates: int = 0,
    playlist_adds: int = 0,
    caption_lists: int = 0,
    caption_inserts: int = 0,
) -> int:
    return (
        uploads * QUOTA_UPLOAD
        + updates * QUOTA_UPDATE
        + playlist_creates * QUOTA_PLAYLIST_CREATE
        + playlist_adds * QUOTA_PLAYLIST_ADD
        + caption_lists * QUOTA_CAPTION_LIST
        + caption_inserts * QUOTA_CAPTION_INSERT
    )
