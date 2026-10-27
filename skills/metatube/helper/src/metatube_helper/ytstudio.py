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


def list_channel_videos(profile: str | None, limit: int = 50) -> list[ChannelVideo]:
    result = run_ytstudio(["videos", "list", "-n", str(limit), "-o", "json"], profile)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr).strip() or "ytstudio videos list failed")
    payload = json.loads(result.stdout)
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


def estimate_quota(uploads: int = 0, updates: int = 0) -> int:
    return uploads * QUOTA_UPLOAD + updates * QUOTA_UPDATE
