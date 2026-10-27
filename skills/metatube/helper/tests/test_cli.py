import json

import pytest

from metatube_helper import cli
from metatube_helper.sidecars import load_sidecar, set_video_id
from metatube_helper.ytstudio import RunResult

SIDECAR = 'title: "Café — intro"\ncategory_id: "28"\n'


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("METATUBE_CONFIG", str(tmp_path / "cfg" / "config.yaml"))


def run(capsys, *argv):
    code = cli.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def write(folder, name, text=""):
    (folder / name).write_text(text, encoding="utf-8")


def test_discover_json_round_trip(tmp_path, capsys):
    write(tmp_path, "ep1.mp4")
    write(tmp_path, "ep1.md", "Notes: " + "this clip shows how the repo is installed and run step by step " * 3)
    write(tmp_path, "ep1.yaml", SIDECAR)
    code, out = run(capsys, "discover", str(tmp_path))
    assert code == 0 and out["fully_paired"] is True
    assert out["videos"][0]["sidecar"] == str(tmp_path / "ep1.yaml")
    assert out["videos"][0]["has_source"] is True


def test_discover_missing_folder_exit_2(tmp_path, capsys):
    code, out = run(capsys, "discover", str(tmp_path / "nope"))
    assert code == 2 and "error" in out


def test_discover_keeps_non_ascii(tmp_path, capsys):
    write(tmp_path, "café.mp4")
    cli.main(["discover", str(tmp_path)])
    assert "café" in capsys.readouterr().out


def test_lint_folder_exit_codes(tmp_path, capsys):
    write(tmp_path, "good.yaml", SIDECAR + "tags: [a, b, c, d, e, f, g, h]\n")
    write(tmp_path, "bad.yaml", "title: x\n")
    code, out = run(capsys, "lint", str(tmp_path))
    assert code == 1 and out["ok"] is False
    assert out["results"][str(tmp_path / "bad.yaml")]["errors"]
    assert out["results"][str(tmp_path / "good.yaml")]["errors"] == []


def test_update_requires_video_id(tmp_path, capsys):
    write(tmp_path, "ep1.yaml", SIDECAR)
    code, out = run(capsys, "update", str(tmp_path / "ep1.yaml"))
    assert code == 1 and "match" in out["error"]


def test_update_builds_argv_and_studio_url(tmp_path, capsys, monkeypatch):
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    seen = {}

    def fake(args, profile=None):
        seen["args"] = args
        return RunResult(["ytstudio", *args], 0, "preview", "")

    monkeypatch.setattr(cli, "run_ytstudio", fake)
    code, out = run(capsys, "update", str(tmp_path / "ep1.yaml"))
    assert code == 0
    assert out["studio_url"] == "https://studio.youtube.com/video/abcdefghijk/edit"
    assert seen["args"] == ["videos", "update", "--title", "Café — intro", "--", "abcdefghijk"]
    assert "--execute" not in seen["args"]


def test_set_video_id_from_url(tmp_path, capsys):
    write(tmp_path, "ep1.yaml", SIDECAR)
    code, out = run(capsys, "set-video-id", str(tmp_path / "ep1.yaml"), "https://youtu.be/abcdefghijk")
    assert code == 0 and out["video_id"] == "abcdefghijk"
    assert load_sidecar(tmp_path / "ep1.yaml")["video_id"] == "abcdefghijk"


def test_set_video_id_conflict_exit_1(tmp_path, capsys):
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    code, out = run(capsys, "set-video-id", str(tmp_path / "ep1.yaml"), "zzzzzzzzzzz")
    assert code == 1 and "error" in out


def test_quota_upload_over_safe_daily(tmp_path, capsys):
    for i in range(7):
        write(tmp_path, f"ep{i}.mp4")
        write(tmp_path, f"ep{i}.yaml", SIDECAR)
    code, out = run(capsys, "quota", str(tmp_path), "--mode", "upload")
    assert out["count"] == 7 and out["estimated_units"] == 11200 and out["over_safe_daily"] is True


def test_upload_reports_now_live(tmp_path, capsys, monkeypatch):
    write(tmp_path, "ep1.mp4")
    write(tmp_path, "ep1.yaml", SIDECAR)

    def fake(args, profile=None):
        if "--execute" in args:
            set_video_id(tmp_path / "ep1.yaml", "abcdefghijk")
        return RunResult(["ytstudio", *args], 0, "ok ep1.mp4 -> https://youtu.be/abcdefghijk", "")

    monkeypatch.setattr("metatube_helper.ytstudio.run_ytstudio", fake)
    code, out = run(capsys, "upload", str(tmp_path), "--execute")
    assert code == 0 and out["now_live"] == ["ep1"]
    assert out["plan"]["mode"] == "folder" and out["audit_passed"] is False


def test_config_set_then_show(capsys):
    code, _ = run(capsys, "config", "set", "audit_passed", "true")
    assert code == 0
    code, out = run(capsys, "config", "show")
    assert out["audit_passed"] is True and out["mode"] == "upload" and "path" in out


def test_config_set_unknown_key_exit_1(capsys):
    code, out = run(capsys, "config", "set", "token", "x")
    assert code == 1 and "error" in out


def test_write_sidecar_from_draft_lints_and_writes(tmp_path, capsys):
    draft = tmp_path / "draft.yaml"
    write(tmp_path, "draft.yaml", SIDECAR + "tags: [a, b, c, d, e, f, g, h]\n")
    code, out = run(capsys, "write-sidecar", str(tmp_path / "ep1.yaml"), "--from", str(draft))
    assert code == 0 and load_sidecar(tmp_path / "ep1.yaml")["title"] == "Café — intro"


def test_write_sidecar_refuses_lint_errors(tmp_path, capsys):
    write(tmp_path, "draft.yaml", "title: x\n")
    code, out = run(capsys, "write-sidecar", str(tmp_path / "ep1.yaml"), "--from", str(tmp_path / "draft.yaml"))
    assert code == 1 and not (tmp_path / "ep1.yaml").exists() and out["errors"]


def test_write_sidecar_keeps_live_video_id_even_if_draft_drops_it(tmp_path, capsys):
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    write(tmp_path, "draft.yaml", 'title: "New title"\ncategory_id: "28"\n')
    code, out = run(capsys, "write-sidecar", str(tmp_path / "ep1.yaml"), "--from", str(tmp_path / "draft.yaml"))
    data = load_sidecar(tmp_path / "ep1.yaml")
    assert code == 0 and data["video_id"] == "abcdefghijk" and data["title"] == "New title"


def test_write_sidecar_refuses_changed_video_id(tmp_path, capsys):
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    write(tmp_path, "draft.yaml", SIDECAR + "video_id: zzzzzzzzzzz\n")
    code, out = run(capsys, "write-sidecar", str(tmp_path / "ep1.yaml"), "--from", str(tmp_path / "draft.yaml"))
    assert code == 1 and load_sidecar(tmp_path / "ep1.yaml")["video_id"] == "abcdefghijk"


def test_set_video_id_refuses_id_claimed_by_sibling(tmp_path, capsys):
    write(tmp_path, "ep1.mp4")
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    write(tmp_path, "ep2.mp4")
    write(tmp_path, "ep2.yaml", SIDECAR)
    code, out = run(capsys, "set-video-id", str(tmp_path / "ep2.yaml"), "abcdefghijk")
    assert code == 1 and "ep1" in out["error"]
    assert "video_id" not in load_sidecar(tmp_path / "ep2.yaml")


def test_match_includes_current_description_and_tags(tmp_path, capsys, monkeypatch):
    from metatube_helper.match import ChannelVideo
    write(tmp_path, "ep1.mp4")
    write(tmp_path, "ep1.yaml", SIDECAR)
    vids = [ChannelVideo("aaaaaaaaaaa", "ep1", "private", "2026-10-27", description="old desc", tags=["old"])]
    monkeypatch.setattr(cli, "list_channel_videos", lambda profile, limit=50: vids)
    code, out = run(capsys, "match", str(tmp_path))
    cand = out["matches"][0]["candidates"][0]
    assert cand["description"] == "old desc" and cand["tags"] == ["old"]


def test_upload_dry_run_flags_videos_already_on_channel(tmp_path, capsys, monkeypatch):
    from metatube_helper.match import ChannelVideo
    write(tmp_path, "ep1.mp4")
    write(tmp_path, "ep1.yaml", SIDECAR)
    monkeypatch.setattr(cli, "list_channel_videos",
                        lambda profile, limit=50: [ChannelVideo("aaaaaaaaaaa", "ep1", "private", "2026-10-27")])
    monkeypatch.setattr("metatube_helper.ytstudio.run_ytstudio",
                        lambda args, profile=None: RunResult(["ytstudio", *args], 0, "Dry-run.", ""))
    code, out = run(capsys, "upload", str(tmp_path))
    assert out["possible_duplicates"] == [{"stem": "ep1", "video_ids": ["aaaaaaaaaaa"]}]


def test_config_show_reports_brand_file(tmp_path, capsys):
    code, out = run(capsys, "config", "show")
    assert out["brand_path"].endswith("brand.md") and out["brand_exists"] is False
    from pathlib import Path
    Path(out["brand_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(out["brand_path"]).write_text("Friendly, precise.", encoding="utf-8")
    code, out = run(capsys, "config", "show")
    assert out["brand_exists"] is True


def test_set_video_id_replace_deleted(tmp_path, capsys, monkeypatch):
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    monkeypatch.setattr(cli, "video_exists", lambda vid, profile=None: False)
    code, out = run(capsys, "set-video-id", str(tmp_path / "ep1.yaml"), "zzzzzzzzzzz", "--replace-deleted")
    assert code == 0 and load_sidecar(tmp_path / "ep1.yaml")["video_id"] == "zzzzzzzzzzz"


@pytest.mark.parametrize("exists", [True, None])
def test_set_video_id_replace_refused_unless_confirmed_deleted(tmp_path, capsys, monkeypatch, exists):
    write(tmp_path, "ep1.yaml", SIDECAR + "video_id: abcdefghijk\n")
    monkeypatch.setattr(cli, "video_exists", lambda vid, profile=None: exists)
    code, out = run(capsys, "set-video-id", str(tmp_path / "ep1.yaml"), "zzzzzzzzzzz", "--replace-deleted")
    assert code == 1 and load_sidecar(tmp_path / "ep1.yaml")["video_id"] == "abcdefghijk"
