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


def write_p(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _walker_series(tmp_path, under_walker=True):
    base = tmp_path / "myrepo" / ".walker" / "series" if under_walker else tmp_path / "loose"
    s = base / "cube"
    write_p(s / "series.yaml", "format: walker/0.2\nseries: {name: cube-gs}\nepisodes: [ep1]\nproject: {walked_tag: v1}\n")
    write_p(s / "ep1" / "walker.yaml", "format: walker/0.2\n")
    return s


def test_cli_walker_status_episode_folder_exit_2(tmp_path, capsys):
    s = _walker_series(tmp_path)
    code, out = run(capsys, "walker-status", str(s / "ep1"))
    assert code == 2 and str(s) in out["error"]


def test_cli_walker_status_unknown_repo_then_repo_flag(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("WALKER_HOME", str(tmp_path / "wh"))
    s = _walker_series(tmp_path, under_walker=False)
    code, out = run(capsys, "walker-status", str(s))
    assert code == 1 and "repo name unknown" in out["error"]
    code, out = run(capsys, "walker-status", str(s), "--repo", "myrepo")
    assert code == 0 and out["repo"] == "myrepo" and out["episodes"][0]["status"] == "not_rendered"
    code, out = run(capsys, "walker-status", str(s))
    assert code == 0 and out["repo"] == "myrepo"


def test_cli_walker_sync_copies_ids(tmp_path, capsys, monkeypatch):
    home = tmp_path / "wh"
    monkeypatch.setenv("WALKER_HOME", str(home))
    s = _walker_series(tmp_path)
    d = home / "myrepo" / "series" / "cube-gs" / "ep1" / "video" / "20261027-100000"
    write_p(d / "cube-gs-ep1.mp4")
    write_p(d / "cube-gs-ep1.yaml", "video_id: abcDEF12345\n")
    code, out = run(capsys, "walker-sync", str(s))
    assert code == 0
    from metatube_helper.manifest import load_manifest

    rec = load_manifest(s).episodes["ep1"]
    assert rec.video_id == "abcDEF12345" and rec.run_id == "20261027-100000"


WALKER_SERIES = "format: walker/0.2\nseries: {name: cube-gs}\nepisodes: [ep1, ep2]\nproject: {walked_tag: v1}\n"


def _rendered_series(tmp_path, monkeypatch, ids=(None, None)):
    """A Walker series with two rendered episodes, each with a sidecar. Returns (series folder, run folders)."""
    home = tmp_path / "wh"
    monkeypatch.setenv("WALKER_HOME", str(home))
    s = tmp_path / "myrepo" / ".walker" / "series" / "cube"
    write_p(s / "series.yaml", WALKER_SERIES)
    runs = []
    for ep, vid in zip(("ep1", "ep2"), ids):
        write_p(s / ep / "walker.yaml", "format: walker/0.2\n")
        d = home / "myrepo" / "series" / "cube-gs" / ep / "video" / "20261027-100000"
        write_p(d / f"cube-gs-{ep}.mp4")
        write_p(d / f"cube-gs-{ep}.yaml", SIDECAR + (f"video_id: {vid}\n" if vid else ""))
        runs.append(d)
    return s, runs


def test_match_walker_series(tmp_path, capsys, monkeypatch):
    from metatube_helper.match import ChannelVideo
    s, _ = _rendered_series(tmp_path, monkeypatch)
    vids = [ChannelVideo("aaaaaaaaaaa", "cube gs ep1", "private", "2026-10-27"),
            ChannelVideo("bbbbbbbbbbb", "cube-gs-ep2", "private", "2026-10-27")]
    monkeypatch.setattr(cli, "list_channel_videos", lambda profile, limit=50: vids)
    code, out = run(capsys, "match", str(s))
    assert code == 0
    assert [m["status"] for m in out["matches"]] == ["matched", "matched"]


def test_set_video_id_source_refuses_id_held_by_other_episode(tmp_path, capsys, monkeypatch):
    s, runs = _rendered_series(tmp_path, monkeypatch, ids=("abcdefghijk", None))
    target = runs[1] / "cube-gs-ep2.yaml"
    code, out = run(capsys, "set-video-id", str(target), "abcdefghijk", "--source", str(s))
    assert code == 1 and "ep1" in out["error"]
    assert "video_id" not in load_sidecar(target)
    code, out = run(capsys, "set-video-id", str(target), "zzzzzzzzzzz", "--source", str(s))
    assert code == 0 and load_sidecar(target)["video_id"] == "zzzzzzzzzzz"


def test_quota_walker_series_counts_playlist(tmp_path, capsys, monkeypatch):
    s, _ = _rendered_series(tmp_path, monkeypatch)
    code, out = run(capsys, "quota", str(s), "--mode", "update")
    assert code == 0 and out["count"] == 2 and out["estimated_units"] == 2 * 50 + 50 + 2 * 50


def test_quota_walker_series_skips_added_and_existing_playlist(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import Manifest, PlaylistRecord, save_manifest
    s, _ = _rendered_series(tmp_path, monkeypatch, ids=("abcdefghijk", "lmnopqrstuv"))
    save_manifest(s, Manifest(repo="myrepo", playlist=PlaylistRecord("t", "d", "private", id="PL1", added=["abcdefghijk"])))
    code, out = run(capsys, "quota", str(s), "--mode", "update")
    assert out["estimated_units"] == 2 * 50 + 1 * 50


def test_quota_single_walker_source_has_no_playlist_cost(tmp_path, capsys, monkeypatch):
    home = tmp_path / "wh"
    monkeypatch.setenv("WALKER_HOME", str(home))
    s = tmp_path / "myrepo" / ".walker"
    write_p(s / "walker.yaml", "format: walker/0.2\nproject: {walked_tag: v1}\n")
    d = home / "myrepo" / "video" / "20261027-100000"
    write_p(d / "myrepo-v1.mp4")
    write_p(d / "myrepo-v1.yaml", SIDECAR)
    code, out = run(capsys, "quota", str(s), "--mode", "update")
    assert code == 0 and out["count"] == 1 and out["estimated_units"] == 50


PLAYLIST_DRAFT = 'title: "cube-gs"\ndescription: "What the series covers."\nprivacy: public\n'


def _playlist_series(tmp_path, monkeypatch, ids=("abcdefghijk", "lmnopqrstuv"), playlist_id=None, added=()):
    from metatube_helper.manifest import Manifest, PlaylistRecord, save_manifest
    s, _ = _rendered_series(tmp_path, monkeypatch, ids=ids)
    save_manifest(s, Manifest(repo="myrepo", playlist=PlaylistRecord(
        "cube-gs", "What the series covers.", "public", id=playlist_id, added=list(added))))
    return s


class FakeYt:
    """Stands in for cli.run_ytstudio; records argv and scripts create/add output."""

    def __init__(self, created="✓ Created: cube-gs (PLnew_1)\n", add_out="Done: 1 added, 0 failed\n", on_add=None):
        self.calls, self.created, self.add_out, self.on_add = [], created, add_out, on_add

    def __call__(self, args, profile=None):
        self.calls.append(args)
        if args[:2] == ["playlists", "add"] and self.on_add:
            self.on_add(args)
        out = self.created if args[:2] == ["playlists", "create"] else self.add_out
        return RunResult(["ytstudio", *args], 0, out, "")


def test_playlist_draft_writes_manifest_keeping_id(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    s = _playlist_series(tmp_path, monkeypatch, playlist_id="PL1", added=["abcdefghijk"])
    write(tmp_path, "draft.yaml", PLAYLIST_DRAFT.replace("public", "unlisted"))
    code, out = run(capsys, "playlist-draft", str(s), "--from", str(tmp_path / "draft.yaml"))
    assert code == 0
    pl = load_manifest(s).playlist
    assert (pl.privacy, pl.id, pl.added) == ("unlisted", "PL1", ["abcdefghijk"])


def test_playlist_draft_lint_errors(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    s, _ = _rendered_series(tmp_path, monkeypatch)
    write(tmp_path, "draft.yaml", 'title: "a <b>"\nprivacy: secret\n')
    code, out = run(capsys, "playlist-draft", str(s), "--from", str(tmp_path / "draft.yaml"))
    assert code == 1 and len(out["errors"]) == 2
    assert load_manifest(s).playlist is None


def test_playlist_draft_refuses_single(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("WALKER_HOME", str(tmp_path / "wh"))
    s = tmp_path / "myrepo" / ".walker"
    write_p(s / "walker.yaml", "format: walker/0.2\nproject: {walked_tag: v1}\n")
    write(tmp_path, "draft.yaml", PLAYLIST_DRAFT)
    code, out = run(capsys, "playlist-draft", str(s), "--from", str(tmp_path / "draft.yaml"))
    assert code == 1 and "series" in out["error"]
    assert not (s / "metatube.yaml").exists()


def test_playlist_requires_draft(tmp_path, capsys, monkeypatch):
    s, _ = _rendered_series(tmp_path, monkeypatch)
    code, out = run(capsys, "playlist", str(s))
    assert code == 1 and out["error"] == "no playlist draft; run generate"


def test_playlist_collision_stops(tmp_path, capsys, monkeypatch):
    from metatube_helper.ytstudio import PlaylistInfo, PlaylistItem
    s = _playlist_series(tmp_path, monkeypatch)
    yt = FakeYt()
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    monkeypatch.setattr(cli, "list_playlists", lambda profile: [PlaylistInfo("PLold", " Cube-GS ", 2, "public")])
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: [
        PlaylistItem("abcdefghijk", "Install", 0), PlaylistItem("zzzzzzzzzzz", "Pasta", 1)])
    code, out = run(capsys, "playlist", str(s), "--execute")
    assert code == 1 and yt.calls == []
    [c] = out["collision"]
    assert c["id"] == "PLold" and len(c["items"]) == 2
    assert [f["video_id"] for f in c["flagged"]] == ["zzzzzzzzzzz"]


def test_playlist_dry_run_shows_create_and_adds(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    s = _playlist_series(tmp_path, monkeypatch)
    yt = FakeYt()
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    monkeypatch.setattr(cli, "list_playlists", lambda profile: [])
    code, out = run(capsys, "playlist", str(s))
    assert code == 0 and yt.calls == []
    assert out["create"]["argv"] == ["ytstudio", "playlists", "create", "--title", "cube-gs", "--description",
                                     "What the series covers.", "--privacy", "public", "--language", "en"]
    assert [(a["episode"], a["position"]) for a in out["adds"]] == [("ep1", 0), ("ep2", 1)]
    assert "--execute" not in out["adds"][0]["argv"]
    assert load_manifest(s).playlist.id is None


def test_playlist_execute_creates_then_adds(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    from metatube_helper.ytstudio import PlaylistItem
    s = _playlist_series(tmp_path, monkeypatch)
    ids_at_add = []
    yt = FakeYt(on_add=lambda args: ids_at_add.append(load_manifest(s).playlist.id))
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    monkeypatch.setattr(cli, "list_playlists", lambda profile: [])
    reads = iter([[], [PlaylistItem("abcdefghijk", "ep1", 0), PlaylistItem("lmnopqrstuv", "ep2", 1)]])
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: next(reads))
    code, out = run(capsys, "playlist", str(s), "--execute")
    assert code == 0, out
    assert yt.calls[0][:2] == ["playlists", "create"] and yt.calls[0][-1] == "--execute"
    assert yt.calls[1] == ["playlists", "add", "PLnew_1", "--video", "abcdefghijk", "--position", "0", "--execute"]
    assert yt.calls[2] == ["playlists", "add", "PLnew_1", "--video", "lmnopqrstuv", "--position", "1", "--execute"]
    assert ids_at_add == ["PLnew_1", "PLnew_1"]
    pl = load_manifest(s).playlist
    assert pl.id == "PLnew_1" and pl.added == ["abcdefghijk", "lmnopqrstuv"]
    assert out["not_added"] == []


def test_playlist_create_unparsed_output_stops(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    s = _playlist_series(tmp_path, monkeypatch)
    yt = FakeYt(created="something else\n")
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    monkeypatch.setattr(cli, "list_playlists", lambda profile: [])
    code, out = run(capsys, "playlist", str(s), "--execute")
    assert code == 1 and "playlist-adopt" in out["error"] and out["stdout"] == "something else\n"
    assert len(yt.calls) == 1 and load_manifest(s).playlist.id is None


def test_playlist_add_reported_failed(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    from metatube_helper.ytstudio import PlaylistItem
    s = _playlist_series(tmp_path, monkeypatch, playlist_id="PL1")
    yt = FakeYt()
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    reads = iter([[], [PlaylistItem("abcdefghijk", "ep1", 0)]])
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: next(reads))
    code, out = run(capsys, "playlist", str(s), "--execute")
    assert code == 1
    [missing] = out["not_added"]
    assert missing["episode"] == "ep2" and missing["video_id"] == "lmnopqrstuv" and missing["position"] == 1
    assert missing["returncode"] == 0 and missing["stdout"] == "Done: 1 added, 0 failed\n"
    assert missing["argv"][:3] == ["ytstudio", "playlists", "add"]
    assert load_manifest(s).playlist.added == ["abcdefghijk"]


def test_playlist_add_stops_after_a_failed_add(tmp_path, capsys, monkeypatch):
    s = _playlist_series(tmp_path, monkeypatch, playlist_id="PL1")
    yt = FakeYt(add_out="Not found abcdefghijk\nDone: 0 added, 1 failed\n")
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: [])
    code, out = run(capsys, "playlist", str(s), "--execute")
    assert code == 1 and len(yt.calls) == 1
    assert [(n["episode"], n["returncode"]) for n in out["not_added"]] == [("ep1", 0), ("ep2", None)]


def test_playlist_refuses_on_disagreement(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import EpisodeRecord, load_manifest, save_manifest
    s = _playlist_series(tmp_path, monkeypatch, playlist_id="PL1")
    m = load_manifest(s)
    m.episodes["ep1"] = EpisodeRecord(video_id="zzzzzzzzzzz")
    save_manifest(s, m)
    yt = FakeYt()
    monkeypatch.setattr(cli, "run_ytstudio", yt)
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: [])
    code, out = run(capsys, "playlist", str(s), "--execute")
    assert code == 1 and out["disagreements"][0]["episode"] == "ep1" and yt.calls == []


def test_playlist_adopt_requires_confirm(tmp_path, capsys, monkeypatch):
    from metatube_helper.manifest import load_manifest
    from metatube_helper.ytstudio import PlaylistItem
    s = _playlist_series(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: [
        PlaylistItem("abcdefghijk", "Install", 0), PlaylistItem("zzzzzzzzzzz", "Pasta", 1)])
    code, out = run(capsys, "playlist-adopt", str(s), "PLold")
    assert code == 0 and out["adopted"] is False
    assert [f["video_id"] for f in out["flagged"]] == ["zzzzzzzzzzz"] and len(out["items"]) == 2
    assert load_manifest(s).playlist.id is None
    code, out = run(capsys, "playlist-adopt", str(s), "PLold", "--confirm")
    assert code == 0 and out["adopted"] is True
    pl = load_manifest(s).playlist
    assert pl.id == "PLold" and pl.added == ["abcdefghijk"]


def test_playlist_adopt_refuses_to_replace_existing_id(tmp_path, capsys, monkeypatch):
    s = _playlist_series(tmp_path, monkeypatch, playlist_id="PL1")
    monkeypatch.setattr(cli, "playlist_items", lambda pid, profile: [])
    code, out = run(capsys, "playlist-adopt", str(s), "PLother", "--confirm")
    assert code == 1 and "PL1" in out["error"]
