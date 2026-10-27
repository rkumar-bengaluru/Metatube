import json
import subprocess
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
    assert argv[:3] == ["videos", "update", "abcdefghijk"]
    assert argv[argv.index("--description") + 1] == desc
    assert argv[argv.index("--tags") + 1] == "a,b"
    assert "--execute" not in argv
    assert update_argv("abcdefghijk", {"title": "T"}, execute=True)[-1] == "--execute"


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
