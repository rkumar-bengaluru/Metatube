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
    write(tmp_path, "ep1.md")
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
    assert seen["args"][:5] == ["videos", "update", "abcdefghijk", "--title", "Café — intro"]
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
