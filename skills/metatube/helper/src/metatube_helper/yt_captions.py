"""List/insert YouTube caption tracks. Run by ytstudio's own Python, never imported by the helper.

Auth goes through ytstudio.services, so MetaTube never opens ytstudio's token or client-secret files.
The profile comes from the YTSTUDIO_PROFILE env var, which ytstudio itself honours. Imports of
googleapiclient/ytstudio stay inside functions so tests can import this module without them.
"""

import argparse
import contextlib
import json
import sys

ONE_CUE_SRT = "1\n00:00:00,000 --> 00:00:01,000\n.\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="yt_captions")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list").add_argument("video_id")
    ins = sub.add_parser("insert")
    ins.add_argument("video_id")
    ins.add_argument("--language", required=True)
    return p.parse_args(argv)


def _service():
    from ytstudio.services import get_data_service

    # ytstudio prints its own messages to stdout; keep stdout for our single JSON object.
    with contextlib.redirect_stdout(sys.stderr):
        return get_data_service()


def list_tracks(video_id: str) -> dict:
    resp = _service().captions().list(part="snippet", videoId=video_id).execute()
    return {"tracks": [
        {"id": i.get("id", ""), "language": i.get("snippet", {}).get("language", ""),
         "name": i.get("snippet", {}).get("name", ""), "kind": i.get("snippet", {}).get("trackKind", "")}
        for i in resp.get("items", [])
    ]}


def insert_track(video_id: str, language: str) -> dict:
    from googleapiclient.http import MediaInMemoryUpload

    body = {"snippet": {"videoId": video_id, "language": language, "name": "", "isDraft": False}}
    media = MediaInMemoryUpload(ONE_CUE_SRT.encode(), mimetype="application/octet-stream")
    resp = _service().captions().insert(part="snippet", body=body, media_body=media).execute()
    return {"inserted": resp.get("id", "")}


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        out = list_tracks(args.video_id) if args.command == "list" else insert_track(args.video_id, args.language)
    except BaseException as e:  # typer.Exit and HttpError both end here; never print credentials
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
