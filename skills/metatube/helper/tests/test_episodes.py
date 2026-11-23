import json
from pathlib import Path

import pytest

from metatube_helper import cli
from metatube_helper.episodes import resolve, walker_entries
from metatube_helper.manifest import EpisodeRecord, Manifest, load_manifest, save_manifest
from metatube_helper.walker import load_source

SERIES_YAML = (
    "format: walker/0.2\n"
    "series: {name: cube-gs, title: \"Cube: getting started\"}\n"
    "episodes: [ep1, ep2]\n"
    "project: {name: Cube, walked_tag: v1.8}\n"
)
WORDS30 = " ".join(f"word{i}" for i in range(30))
SRT = "1\n00:00:00,000 --> 00:00:01,000\nhello there friend again\n"


def _write(p: Path, text: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "whome"
    monkeypatch.setenv("WALKER_HOME", str(h))
    monkeypatch.setenv("METATUBE_CONFIG", str(tmp_path / "cfg" / "config.yaml"))
    return h


@pytest.fixture
def series(tmp_path):
    s = tmp_path / "myrepo" / ".walker" / "series" / "cube"
    _write(s / "series.yaml", SERIES_YAML)
    _write(s / "ep1" / "walker.yaml", "format: walker/0.2\n")
    _write(s / "ep2" / "walker.yaml", "format: walker/0.2\n")
    return s


def run_dir(home, ep, run_id, video_id=None, srt=True):
    stem = f"cube-gs-{ep}"
    d = home / "myrepo" / "series" / "cube-gs" / ep / "video" / run_id
    _write(d / f"{stem}.mp4")
    if srt:
        _write(d / f"{stem}.srt", SRT)
    if video_id:
        _write(d / f"{stem}.yaml", f"video_id: {video_id}\n")
    return d


def states(series, m=None):
    return {s.key: s for s in resolve(load_source(series), m or Manifest())}


def test_not_rendered_episode(home, series):
    run_dir(home, "ep1", "20261027-100000")
    st = states(series)
    assert st["ep1"].status == "ready"
    assert st["ep2"].status == "not_rendered" and st["ep2"].run is None
    assert st["ep2"].position == 2


def test_not_rendered_when_episode_folder_missing(home, series):
    import shutil

    shutil.rmtree(series / "ep2")
    st = states(series)
    assert st["ep2"].status == "not_rendered" and st["ep2"].run is None and not st["ep2"].notes


def test_ready_picks_newest_and_pin(home, series):
    run_dir(home, "ep1", "20261027-100000")
    run_dir(home, "ep1", "20261028-100000")
    assert states(series)["ep1"].run.run_id == "20261028-100000"
    m = Manifest(episodes={"ep1": EpisodeRecord(pin_run="20261027-100000")})
    assert states(series, m)["ep1"].run.run_id == "20261027-100000"


def test_live_run_sticks(home, series):
    old = run_dir(home, "ep1", "20261027-100000", video_id="abcDEF12345")
    run_dir(home, "ep1", "20261028-100000")
    s = states(series)["ep1"]
    assert s.status == "live" and s.run.run_id == "20261027-100000"
    assert s.newer_run == "20261028-100000" and s.video_id == "abcDEF12345"
    assert s.transcript == old / "cube-gs-ep1.srt"


def test_two_live_runs_same_id(home, series):
    run_dir(home, "ep1", "20261027-100000", video_id="abcDEF12345")
    run_dir(home, "ep1", "20261028-100000", video_id="abcDEF12345")
    s = states(series)["ep1"]
    assert s.status == "live" and s.run.run_id == "20261028-100000" and s.newer_run is None


def test_two_live_runs_different_ids(home, series):
    run_dir(home, "ep1", "20261027-100000", video_id="abcDEF12345")
    run_dir(home, "ep1", "20261028-100000", video_id="zzzDEF12345")
    assert states(series)["ep1"].status == "disagreement"


def test_manifest_disagrees_with_sidecar(home, series, capsys):
    run_dir(home, "ep1", "20261027-100000", video_id="abcDEF12345")
    save_manifest(series, Manifest(repo="myrepo", episodes={"ep1": EpisodeRecord(video_id="otherOther1")}))
    before = (series / "metatube.yaml").read_text(encoding="utf-8")
    assert states(series, load_manifest(series))["ep1"].status == "disagreement"
    assert cli.main(["walker-sync", str(series)]) == 1
    assert "conflicts" in capsys.readouterr().out
    assert (series / "metatube.yaml").read_text(encoding="utf-8") == before


def test_live_run_missing(home, series):
    m = Manifest(episodes={"ep1": EpisodeRecord(video_id="abcDEF12345")})
    s = states(series, m)["ep1"]
    assert s.status == "live_run_missing" and s.video_id == "abcDEF12345"


def test_explainer_only(home, series):
    d = home / "myrepo" / "series" / "cube-gs" / "ep1" / "video" / "20261027-100000"
    _write(d / "explainer.mp4")
    s = states(series)["ep1"]
    assert s.status == "explainer_only" and s.run is None and "re-render" in s.message


def test_explainer_pinned_becomes_the_run(home, series):
    d = home / "myrepo" / "series" / "cube-gs" / "ep1" / "video" / "20261027-100000"
    _write(d / "explainer.mp4")
    _write(d / "explainer.srt", SRT)
    m = Manifest(episodes={"ep1": EpisodeRecord(pin_run="20261027-100000")})
    s = states(series, m)["ep1"]
    assert s.status == "ready" and s.run.video == d / "explainer.mp4"
    assert s.run.srt == d / "explainer.srt"
    _write(d / "explainer.yaml", "video_id: abcDEF12345\n")
    s = states(series, m)["ep1"]
    assert s.status == "live" and s.video_id == "abcDEF12345"
    assert [e.stem for e in walker_entries([s])] == ["explainer"]


def test_series_story_counts_for_every_episode(home, series):
    run_dir(home, "ep1", "20261027-100000", srt=False)
    _write(series / "story.md", WORDS30)
    assert states(series)["ep1"].has_source
    _write(series / "story.md", "five words only here ok")
    s = states(series)["ep1"]
    assert not s.has_source and series / "story.md" in s.thin_sources


def test_odd_run_ids_warn(home, series):
    run_dir(home, "ep1", "a")
    run_dir(home, "ep1", "b")
    w = states(series)["ep1"].warnings
    assert len(w) == 1 and "a" in w[0] and "b" in w[0]


def test_single_source_uses_video_key(home, tmp_path):
    single = tmp_path / "repo2" / ".walker"
    _write(single / "walker.yaml", "format: walker/0.2\nproject: {name: X}\n")
    _write(home / "repo2" / "video" / "20261027-100000" / "repo2.mp4")
    (s,) = resolve(load_source(single), Manifest())
    assert s.key == "video" and s.position == 1 and s.status == "ready"


def test_walker_sync_run_vs_run_disagreement_exits_1_untouched(home, series, capsys):
    run_dir(home, "ep1", "20261027-100000", video_id="abcDEF12345")
    run_dir(home, "ep1", "20261028-100000", video_id="zzzDEF12345")
    run_dir(home, "ep2", "20261027-100000", video_id="qqqDEF12345")
    save_manifest(series, Manifest(repo="myrepo"))
    before = (series / "metatube.yaml").read_bytes()
    assert cli.main(["walker-sync", str(series)]) == 1
    assert "ep1" in capsys.readouterr().out
    assert (series / "metatube.yaml").read_bytes() == before


def short_dir(run, ep, video_id=None, numbers=(1,), sheet=None):
    d = run / "shorts"
    for k in numbers:
        name = f"cube-gs-{ep}-short" + ("" if k == 1 else f"-{k}")
        _write(d / f"{name}.mp4")
        _write(d / f"{name}.srt", SRT)
        if video_id and k == numbers[0]:
            _write(d / f"{name}.yaml", f"video_id: {video_id}\n")
    if sheet is not None:
        _write(d / "short.yaml", sheet)
    return d


SHEET = ("shorts:\n"
         "  - {title: One, hook: \"First hook\", why: \"stands alone\"}\n"
         "  - {title: Two, hook: \"Second hook\"}\n"
         "  - {title: Three, hook: \"Third hook\", why: \"third why\"}\n"
         "asked: 3\n")


def test_short_found_newest_unless_one_is_live(home, series):
    old = run_dir(home, "ep1", "20261027-100000")
    new = run_dir(home, "ep1", "20261028-100000")
    short_dir(old, "ep1")
    short_dir(new, "ep1")
    s = states(series)
    assert [x.run_id for x in s["ep1"].shorts] == ["20261028-100000"] and s["ep1"].shorts[0].srt is not None
    assert s["ep2"].shorts == []
    short_dir(old, "ep1", video_id="shortshort1")
    assert states(series)["ep1"].shorts[0].run_id == "20261027-100000"


def test_every_short_of_the_run_in_order_with_its_hook(home, series):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1, 2, 3), sheet=SHEET)
    shorts = states(series)["ep1"].shorts
    assert [(x.number, x.video.name, x.hook, x.why) for x in shorts] == [
        (1, "cube-gs-ep1-short.mp4", "First hook", "stands alone"),
        (2, "cube-gs-ep1-short-2.mp4", "Second hook", None),
        (3, "cube-gs-ep1-short-3.mp4", "Third hook", "third why")]
    assert all(x.run_id == "20261027-100000" for x in shorts)


def test_a_gap_keeps_numbers_and_a_broken_sheet_gives_no_hooks(home, series):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1, 3), sheet="shorts: [oops\n")
    shorts = states(series)["ep1"].shorts
    assert [(x.number, x.hook) for x in shorts] == [(1, None), (3, None)]


def test_no_sheet_gives_no_title_hook_or_why(home, series):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1, 2))
    assert [(x.title, x.hook, x.why) for x in states(series)["ep1"].shorts] == [(None, None, None)] * 2


def test_the_sheet_title_is_kept(home, series):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1,), sheet=SHEET)
    assert states(series)["ep1"].shorts[0].title == "One"


def test_a_live_second_short_keeps_its_run_and_says_a_newer_render_has_more(home, series):
    old = run_dir(home, "ep1", "20261027-100000")
    short_dir(old, "ep1", numbers=(1, 2))
    _write(old / "shorts" / "cube-gs-ep1-short-2.yaml", "video_id: shortshort2\n")
    short_dir(run_dir(home, "ep1", "20261028-100000"), "ep1", numbers=(1, 2, 3))
    s = states(series)["ep1"]
    assert [(x.run_id, x.number, x.video_id) for x in s.shorts] == [
        ("20261027-100000", 1, None), ("20261027-100000", 2, "shortshort2")]
    assert any("newer render 20261028-100000 has Shorts 1, 2, 3" in w for w in s.warnings)


def test_two_renders_with_live_shorts_are_said(home, series):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", video_id="shortshort1")
    short_dir(run_dir(home, "ep1", "20261028-100000"), "ep1", video_id="shortshort9")
    s = states(series)["ep1"]
    assert s.shorts[0].run_id == "20261028-100000"
    assert any("20261027-100000, 20261028-100000 all have Shorts on YouTube" in w for w in s.warnings)


def test_a_live_short_whose_file_is_gone_stays(home, series):
    d = short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1,))
    _write(d / "cube-gs-ep1-short-2.yaml", "video_id: shortshort2\n")  # Walker removed its .mp4 and .srt
    s = states(series)["ep1"]
    assert [(x.number, x.missing, x.video_id) for x in s.shorts] == [(1, False, None), (2, True, "shortshort2")]
    assert s.shorts[1].srt is None
    assert any("Short 2 is on YouTube (shortshort2) but its file is gone" in w for w in s.warnings)
    assert [e.stem for e in walker_entries([s])] == ["cube-gs-ep1", "cube-gs-ep1-short"]


def test_a_live_short_whose_file_is_gone_still_picks_its_run(home, series):
    old = run_dir(home, "ep1", "20261027-100000")
    _write(old / "shorts" / "cube-gs-ep1-short.yaml", "video_id: shortshort1\n")  # only the sidecar is left
    short_dir(run_dir(home, "ep1", "20261028-100000"), "ep1")
    shorts = states(series)["ep1"].shorts
    assert [(x.run_id, x.missing) for x in shorts] == [("20261027-100000", True)]


def test_only_numbers_1_to_5_count(home, series):
    d = short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1,))
    _write(d / "cube-gs-ep1-short-6.mp4")
    _write(d / "cube-gs-ep1-short-2.part.mp4")
    assert [x.number for x in states(series)["ep1"].shorts] == [1]


def test_walker_status_lists_shorts(home, series, capsys):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1, 2), sheet=SHEET)
    assert cli.main(["walker-status", str(series)]) == 0
    ep1 = next(e for e in json.loads(capsys.readouterr().out)["episodes"] if e["key"] == "ep1")
    assert [x["number"] for x in ep1["shorts"]] == [1, 2] and ep1["shorts"][1]["hook"] == "Second hook"
    assert "short" not in ep1


def test_walker_entries_include_every_short(home, series):
    short_dir(run_dir(home, "ep1", "20261027-100000"), "ep1", numbers=(1, 2))
    stems = [e.stem for e in walker_entries(list(states(series).values()))]
    assert stems == ["cube-gs-ep1", "cube-gs-ep1-short", "cube-gs-ep1-short-2"]
