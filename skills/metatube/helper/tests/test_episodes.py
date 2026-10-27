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
