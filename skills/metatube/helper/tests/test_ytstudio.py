import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from metatube_helper import ytstudio
from metatube_helper.discover import discover
from metatube_helper.ytstudio import (
    auth_check,
    estimate_quota,
    list_channel_videos,
    plan_upload,
    run_upload,
    run_ytstudio,
    update_argv,
)

SIDECAR = 'title: a\ncategory_id: "28"\n'


class FakeRun:
    """Records calls to subprocess.run and replays scripted (returncode, stdout) results."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        result = self.results.pop(0) if self.results else (0, "")
        if isinstance(result, Exception):
            raise result
        code, out = result
        return SimpleNamespace(returncode=code, stdout=out, stderr="")


@pytest.fixture
def fake(monkeypatch):
    def install(*results):
        f = FakeRun(*results)
        monkeypatch.setattr(subprocess, "run", f)
        return f

    return install


def write(folder, name, text=""):
    (folder / name).write_text(text, encoding="utf-8")


def test_run_sets_utf8_env_and_profile(fake):
    f = fake((0, "ok"))
    r = run_ytstudio(["status"], profile="work")
    argv, kwargs = f.calls[0]
    assert argv[0] == "ytstudio" and argv[1:] == ["status"]
    assert kwargs["env"]["PYTHONUTF8"] == "1"
    assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    assert kwargs["env"]["YTSTUDIO_PROFILE"] == "work"
    assert not kwargs.get("shell")
    assert r.returncode == 0 and r.stdout == "ok"


def test_run_missing_binary_gives_127(fake):
    fake(FileNotFoundError())
    assert run_ytstudio(["status"]).returncode == 127


def test_update_argv_passes_description_verbatim():
    desc = 'Línea 1\n\n"q" $HOME `x` — é\n'
    argv = update_argv("abcdefghijk", {"title": "T", "description": desc, "tags": ["a", "b"]}, execute=False)
    assert argv[:2] == ["videos", "update"] and argv[-2:] == ["--", "abcdefghijk"]
    assert argv[argv.index("--description") + 1] == desc
    assert argv[argv.index("--tags") + 1] == "a,b"
    assert "--execute" not in argv
    assert "--execute" in update_argv("abcdefghijk", {"title": "T"}, execute=True)


def test_update_argv_id_starting_with_dash_is_positional():
    argv = update_argv("-AbCdEfGhIj", {"title": "T"}, execute=True)
    assert argv[-2:] == ["--", "-AbCdEfGhIj"]
    assert argv.index("--execute") < argv.index("--")


def test_update_argv_reaches_child_process_byte_exact():
    desc = 'Línea 1\n\t"q" $HOME `x` \\ — é\n'
    argv = update_argv("-AbCdEfGhIj", {"title": "T", "description": desc}, execute=False)
    echo = "import sys,json; sys.stdout.reconfigure(encoding='utf-8'); print(json.dumps(sys.argv[1:]))"
    out = subprocess.run([sys.executable, "-c", echo, *argv], capture_output=True, text=True,
                         encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    assert json.loads(out.stdout) == argv


def test_update_argv_omits_tags_when_none():
    assert "--tags" not in update_argv("abcdefghijk", {"title": "T"}, execute=False)


def test_update_argv_rejects_comma_tag():
    with pytest.raises(ValueError):
        update_argv("abcdefghijk", {"title": "T", "tags": ["a,b"]}, execute=False)


@pytest.mark.parametrize(
    "result,status",
    [
        ((0, '{"videos": []}'), "ok"),
        ((1, "Session expired or revoked. Run ytstudio login to re-authenticate."), "expired"),
        ((1, "No client secrets found. Run 'ytstudio init' first."), "not_initialized"),
        (FileNotFoundError(), "not_installed"),
        ((1, "boom"), "error"),
    ],
)
def test_auth_check_classifies(fake, result, status):
    fake(result)
    assert auth_check(None).status == status


def test_list_channel_videos_parses_json(fake):
    payload = {"videos": [
        {"id": "aaaaaaaaaaa", "title": "ep1", "privacy": "private", "published_at": "2026-10-27", "views": 0},
        {"id": "bbbbbbbbbbb", "title": "ep2", "privacy": "public", "published_at": "2026-10-26", "views": 3},
    ]}
    f = fake((0, json.dumps(payload)))
    vids = list_channel_videos(None, limit=50)
    assert [(v.id, v.title, v.privacy) for v in vids] == [("aaaaaaaaaaa", "ep1", "private"), ("bbbbbbbbbbb", "ep2", "public")]
    assert f.calls[0][0][1:] == ["videos", "list", "-n", "50", "-o", "json"]


def test_json_survives_update_notice_after_it(fake):
    out = json.dumps({"videos": [{"id": "aaaaaaaaaaa", "title": "ep1"}]})
    fake((0, out + "\n\nUpdate available: 0.4.2 → 0.5.0\nRun: uv tool upgrade ytstudio-cli\n"))
    assert [v.id for v in list_channel_videos(None)] == ["aaaaaaaaaaa"]


def test_list_channel_videos_raises_on_failure(fake):
    fake((1, "Session expired"))
    with pytest.raises(RuntimeError):
        list_channel_videos(None)


def test_plan_folder_when_fully_paired_and_max(tmp_path):
    for stem in ("ep1", "ep2", "ep3"):
        write(tmp_path, stem + ".mp4")
    write(tmp_path, "ep1.yaml", SIDECAR)
    write(tmp_path, "ep2.yaml", SIDECAR)
    write(tmp_path, "ep3.yaml", SIDECAR + "video_id: abcdefghijk\n")
    plan = plan_upload(discover(tmp_path), max_uploads=1)
    assert plan.mode == "folder"
    assert plan.pending == [tmp_path / "ep1.mp4"]
    assert plan.skipped_live == [tmp_path / "ep3.mp4"]
    assert plan.commands == [["videos", "upload", str(tmp_path), "--max", "1"]]


def test_plan_per_file_when_missing_sidecar(tmp_path):
    write(tmp_path, "ep1.mp4")
    write(tmp_path, "ep1.yaml", SIDECAR)
    write(tmp_path, "ep2.mp4")
    plan = plan_upload(discover(tmp_path), max_uploads=None)
    assert plan.mode == "per_file"
    assert plan.not_ready == [tmp_path / "ep2.mp4"]
    assert plan.commands == [["videos", "upload", str(tmp_path / "ep1.mp4")]]


def test_run_upload_stops_on_first_failure(fake, tmp_path):
    f = fake((0, ""), (1, "quotaExceeded"), (0, ""))
    plan = ytstudio.UploadPlan("per_file", [], [], [], [["videos", "upload", "a"], ["videos", "upload", "b"], ["videos", "upload", "c"]])
    results = run_upload(plan, execute=True, profile=None)
    assert [r.returncode for r in results] == [0, 1]
    assert all(call[0][-1] == "--execute" for call in f.calls)


def test_estimate_quota():
    assert estimate_quota(uploads=7, updates=2) == 11300


def test_auth_check_api_disabled(fake):
    fake((1, "YouTube Data API v3 has not been used in project 240379470336 before or it is disabled."))
    assert auth_check(None).status == "api_disabled"


@pytest.mark.parametrize("result,expected", [
    ((0, '{"id": "abcdefghijk"}'), True),
    ((1, "Video not found: abcdefghijk"), False),
    ((1, "Session expired or revoked."), None),
])
def test_video_exists(fake, result, expected):
    from metatube_helper.ytstudio import video_exists
    f = fake(result)
    assert video_exists("abcdefghijk", None) is expected
    assert f.calls[0][0][1:] == ["videos", "show", "-o", "json", "--", "abcdefghijk"]


def test_estimate_quota_new_kinds():
    assert estimate_quota(playlist_creates=1, playlist_adds=3, caption_lists=2, caption_inserts=1) == 50 + 150 + 100 + 400


def test_parse_created_id():
    from metatube_helper.ytstudio import parse_created_id
    assert parse_created_id("✓ Created: Cube — café (PLabc_123-x)\n") == "PLabc_123-x"
    # rich wraps at 80 columns when stdout is captured, putting the id on its own line
    wrapped = "✓ Created: Build a Rubik cube solver in Python from scratch — full series \n(PLabc_123-x)\n"
    assert parse_created_id(wrapped) == "PLabc_123-x"
    for bad in ("garbage", "", "✓ Created: Cube (unknown)\n"):
        with pytest.raises(ValueError):
            parse_created_id(bad)


def test_list_playlists_parses_json(fake):
    from metatube_helper.ytstudio import PlaylistInfo, list_playlists
    f = fake((0, json.dumps({"playlists": [{"id": "PL1", "title": "Cube", "description": "", "published_at": "",
                                            "item_count": 3, "privacy": "public"}],
                             "next_page_token": None, "total_results": 1})))
    assert list_playlists("work") == [PlaylistInfo("PL1", "Cube", 3, "public")]
    assert f.calls[0][0][1:] == ["playlists", "list", "-n", "5000", "-o", "json"]


def test_playlist_items_parses_json_and_raises(fake):
    from metatube_helper.ytstudio import PlaylistItem, playlist_items
    f = fake((0, json.dumps({"items": [{"id": "UExx", "video_id": "abcdefghijk", "title": "ep1", "position": 0,
                                        "added_at": "", "note": ""}]})),
             (1, "Session expired or revoked."))
    assert playlist_items("-PL1", None) == [PlaylistItem("abcdefghijk", "ep1", 0)]
    assert f.calls[0][0][1:] == ["playlists", "items", "-n", "5000", "-o", "json", "--", "-PL1"]
    with pytest.raises(RuntimeError, match="Session expired"):
        playlist_items("PL1", None)


def test_create_playlist_argv():
    from metatube_helper.ytstudio import create_playlist_argv
    assert create_playlist_argv("Cube", "About cube.", "public", "en", execute=False) == [
        "playlists", "create", "--title", "Cube", "--description", "About cube.", "--privacy", "public",
        "--language", "en"]
    assert create_playlist_argv("Cube", "", "private", None, execute=True)[-1] == "--execute"


def test_add_argv():
    from metatube_helper.ytstudio import add_argv
    assert add_argv("PL1", "-bcdefghijk", 2, execute=False) == [
        "playlists", "add", "PL1", "--video", "-bcdefghijk", "--position", "2"]
    assert add_argv("PL1", "abcdefghijk", 0, execute=True)[-1] == "--execute"
    assert add_argv("-PL1", "abcdefghijk", 0, execute=True) == [
        "playlists", "add", "--video", "abcdefghijk", "--position", "0", "--execute", "--", "-PL1"]


def test_playlist_reads_fail_closed_on_another_page(fake):
    from metatube_helper.ytstudio import list_playlists, playlist_items
    fake((0, json.dumps({"playlists": [], "next_page_token": "CDIQAA"})),
         (0, json.dumps({"items": [], "next_page_token": "CDIQAA"})))
    with pytest.raises(RuntimeError, match="part of the list"):
        list_playlists(None)
    with pytest.raises(RuntimeError, match="part of the list"):
        playlist_items("PL1", None)


def _fake_uv_dir(tmp_path, layout):
    py = tmp_path / "ytstudio-cli" / layout
    py.parent.mkdir(parents=True)
    py.write_text("")
    return py


@pytest.mark.parametrize("windows,layout", [(True, "Scripts/python.exe"), (False, "bin/python")])
def test_ytstudio_python_paths(fake, monkeypatch, tmp_path, windows, layout):
    py = _fake_uv_dir(tmp_path, layout)
    monkeypatch.setattr(ytstudio, "_IS_WINDOWS", windows)
    f = fake((0, str(tmp_path) + "\n"))
    assert ytstudio.ytstudio_python() == py
    assert f.calls[0][0] == ["uv", "tool", "dir"]


def test_ytstudio_python_missing(fake, tmp_path):
    fake((0, str(tmp_path)))
    assert ytstudio.ytstudio_python() is None
    fake(FileNotFoundError())
    assert ytstudio.ytstudio_python() is None


def test_run_captions_env_and_argv(fake, monkeypatch, tmp_path):
    py = tmp_path / "python"
    monkeypatch.setattr(ytstudio, "ytstudio_python", lambda: py)
    f = fake((0, '{"tracks": []}'))
    r = ytstudio.run_captions(["list", "vid"], profile="work")
    argv, kwargs = f.calls[0]
    assert argv[0] == str(py) and argv[1].endswith("yt_captions.py") and argv[2:] == ["list", "vid"]
    assert kwargs["env"]["YTSTUDIO_PROFILE"] == "work" and kwargs["env"]["PYTHONUTF8"] == "1"
    assert r.returncode == 0 and r.stdout == '{"tracks": []}'


def test_run_captions_missing_interpreter(monkeypatch):
    monkeypatch.setattr(ytstudio, "ytstudio_python", lambda: None)
    assert ytstudio.run_captions(["list", "v"], None).returncode == 127
