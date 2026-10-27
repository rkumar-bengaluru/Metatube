"""metatube-helper: JSON subcommands the MetaTube skill calls. One JSON object per run on stdout."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from metatube_helper import ytstudio
from metatube_helper.config import config_path, default_mode, load_config, save_config, set_value
from metatube_helper.discover import discover, to_jsonable
from metatube_helper.match import match_videos, parse_video_ref
from metatube_helper.schema import lint
from metatube_helper.sidecars import (
    LiveSidecarError,
    load_sidecar,
    replace_video_id,
    set_video_id,
    write_sidecar,
)
from metatube_helper.ytstudio import (
    PINNED_VERSION,
    SAFE_UPLOADS_PER_DAY,
    auth_check,
    estimate_quota,
    installed_version,
    list_channel_videos,
    plan_upload,
    run_ytstudio,
    update_argv,
    video_exists,
)

CLIENT_SECRETS = Path.home() / ".config" / "ytstudio-cli" / "client_secrets.json"


def _emit(payload: Any, code: int = 0) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return code


def _error(message: str, code: int = 1) -> int:
    return _emit({"error": message}, code)


def _profile() -> str:
    return load_config().ytstudio_profile


def cmd_discover(a: argparse.Namespace) -> int:
    folder = Path(a.folder)
    if not folder.is_dir():
        return _error(f"not a folder: {folder}", 2)
    d = discover(folder)
    return _emit(d)


def cmd_lint(a: argparse.Namespace) -> int:
    path = Path(a.path)
    files = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    results = {}
    for f in files:
        try:
            r = lint(load_sidecar(f))
            results[str(f)] = {"errors": r.errors, "warnings": r.warnings}
        except Exception as exc:
            results[str(f)] = {"errors": [f"cannot parse: {exc}"], "warnings": []}
    ok = all(not r["errors"] for r in results.values())
    return _emit({"results": results, "ok": ok}, 0 if ok else 1)


def cmd_auth_check(a: argparse.Namespace) -> int:
    r = auth_check(_profile())
    payload = {"status": r.status, "detail": r.detail,
               "installed_version": installed_version(), "pinned_version": PINNED_VERSION}
    return _emit(payload, 0 if r.status == "ok" else 1)


def cmd_match(a: argparse.Namespace) -> int:
    d = discover(Path(a.folder))
    try:
        channel = list_channel_videos(_profile(), limit=a.limit)
    except RuntimeError as exc:
        return _error(str(exc))
    return _emit({"matches": match_videos(d.videos, channel)})


def cmd_set_video_id(a: argparse.Namespace) -> int:
    sidecar = Path(a.sidecar)
    try:
        video_id = parse_video_ref(a.ref)
        holders = [v.stem for v in discover(sidecar.parent).videos
                   if v.video_id == video_id and v.sidecar != sidecar]
        if holders:
            return _error(f"video {video_id} is already assigned to {', '.join(holders)}")
        old = load_sidecar(sidecar).get("video_id")
        if a.replace_deleted and old and old != video_id:
            exists = video_exists(old, _profile())
            if exists is not False:
                state = "still exists" if exists else "could not be checked"
                return _error(f"current video {old} {state}; refusing to replace it")
            replace_video_id(sidecar, video_id, expected_old=old)
        else:
            set_video_id(sidecar, video_id)
    except (ValueError, LiveSidecarError) as exc:
        return _error(str(exc))
    return _emit({"sidecar": a.sidecar, "video_id": video_id})


def cmd_write_sidecar(a: argparse.Namespace) -> int:
    target = Path(a.sidecar)
    try:
        data = load_sidecar(Path(a.draft))
        existing_id = load_sidecar(target).get("video_id") if target.exists() else None
        if existing_id and "video_id" not in data:
            data["video_id"] = existing_id  # a revision of a live video keeps its id
        result = lint(data)
        if not result.ok:
            return _emit({"errors": result.errors, "warnings": result.warnings}, 1)
        write_sidecar(target, data)
    except (ValueError, LiveSidecarError) as exc:
        return _error(str(exc))
    return _emit({"sidecar": str(target), "written": True, "warnings": result.warnings})


def cmd_update(a: argparse.Namespace) -> int:
    data = load_sidecar(Path(a.sidecar))
    video_id = data.get("video_id")
    if not video_id:
        return _error("no video_id; run match first")
    try:
        args = update_argv(video_id, data, execute=a.execute)
    except ValueError as exc:
        return _error(str(exc))
    r = run_ytstudio(args, _profile())
    return _emit({"argv": r.argv, "returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr,
                  "studio_url": f"https://studio.youtube.com/video/{video_id}/edit"}, r.returncode)


def cmd_upload(a: argparse.Namespace) -> int:
    folder = Path(a.folder)
    before = {v.stem for v in discover(folder).videos if v.live}
    plan = plan_upload(discover(folder), a.max)
    results = ytstudio.run_upload(plan, execute=a.execute, profile=_profile())
    after = {v.stem for v in discover(folder).videos if v.live}
    code = results[-1].returncode if results else 0
    payload = {"plan": plan, "results": results, "now_live": sorted(after - before),
               "audit_passed": load_config().audit_passed}
    if not a.execute:
        payload.update(_possible_duplicates(plan))
    return _emit(payload, code)


def _possible_duplicates(plan: ytstudio.UploadPlan) -> dict:
    """Pending videos whose name matches a channel title were probably uploaded in Studio already."""
    try:
        channel = list_channel_videos(_profile())
    except (RuntimeError, ValueError) as exc:
        return {"possible_duplicates": [], "duplicate_check_error": str(exc)}
    dupes = []
    for path in plan.pending:
        names = {path.stem.casefold(), path.name.casefold()}
        ids = [v.id for v in channel if v.title.strip().casefold() in names]
        if ids:
            dupes.append({"stem": path.stem, "video_ids": ids})
    return {"possible_duplicates": dupes}


def cmd_quota(a: argparse.Namespace) -> int:
    d = discover(Path(a.folder))
    if a.mode == "upload":
        count = len([v for v in d.videos if v.sidecar is not None and not v.live])
        units = estimate_quota(uploads=count)
    else:
        count = len([v for v in d.videos if v.sidecar is not None])
        units = estimate_quota(updates=count)
    return _emit({"count": count, "estimated_units": units, "daily_quota": ytstudio.DAILY_QUOTA,
                  "over_safe_daily": a.mode == "upload" and count > SAFE_UPLOADS_PER_DAY})


def _config_payload() -> dict:
    cfg = load_config()
    brand = config_path().parent / "brand.md"
    return {**to_jsonable(cfg), "mode": default_mode(cfg), "path": str(config_path()),
            "brand_path": str(brand), "brand_exists": brand.exists()}


def cmd_config(a: argparse.Namespace) -> int:
    if a.action == "set":
        try:
            save_config(set_value(load_config(), a.key, a.value))
        except ValueError as exc:
            return _error(str(exc))
    return _emit(_config_payload())


def cmd_secrets_present(a: argparse.Namespace) -> int:
    return _emit({"client_secrets_present": CLIENT_SECRETS.exists()})


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="metatube-helper")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("discover"); s.add_argument("folder"); s.set_defaults(fn=cmd_discover)
    s = sub.add_parser("lint"); s.add_argument("path"); s.set_defaults(fn=cmd_lint)
    s = sub.add_parser("auth-check"); s.set_defaults(fn=cmd_auth_check)
    s = sub.add_parser("match"); s.add_argument("folder"); s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_match)
    s = sub.add_parser("set-video-id"); s.add_argument("sidecar"); s.add_argument("ref")
    s.add_argument("--replace-deleted", action="store_true"); s.set_defaults(fn=cmd_set_video_id)
    s = sub.add_parser("write-sidecar"); s.add_argument("sidecar")
    s.add_argument("--from", dest="draft", required=True); s.set_defaults(fn=cmd_write_sidecar)
    s = sub.add_parser("update"); s.add_argument("sidecar"); s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_update)
    s = sub.add_parser("upload"); s.add_argument("folder"); s.add_argument("--execute", action="store_true")
    s.add_argument("--max", type=int, default=None); s.set_defaults(fn=cmd_upload)
    s = sub.add_parser("quota"); s.add_argument("folder")
    s.add_argument("--mode", choices=["update", "upload"], required=True); s.set_defaults(fn=cmd_quota)
    s = sub.add_parser("config"); cs = s.add_subparsers(dest="action", required=True)
    cs.add_parser("show").set_defaults(fn=cmd_config)
    c = cs.add_parser("set"); c.add_argument("key"); c.add_argument("value"); c.set_defaults(fn=cmd_config)
    s = sub.add_parser("secrets-present"); s.set_defaults(fn=cmd_secrets_present)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
