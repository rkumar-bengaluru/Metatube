import os
from pathlib import Path

import pytest

from metatube_helper import walker


def _write(p: Path, text: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


SERIES_YAML = (
    "format: walker/0.2\n"
    "series: {name: cube-gs, title: \"Cube: getting started\"}\n"
    "episodes: [ep1, ep2]\n"
    "project: {name: Cube, walked_tag: v1.8}\n"
)


def _series(tmp_path: Path, repo: str = "myrepo", folder: str = "cube") -> Path:
    s = tmp_path / repo / ".walker" / "series" / folder
    _write(s / "series.yaml", SERIES_YAML)
    _write(s / "ep1" / "walker.yaml", "format: walker/0.2\n")
    _write(s / "ep2" / "walker.yaml", "format: walker/0.2\n")
    return s


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "whome"
    monkeypatch.setenv("WALKER_HOME", str(h))
    return h


def test_detect_kinds(tmp_path):
    s = _series(tmp_path)
    assert walker.detect(s) == "series"
    assert walker.detect(s / "ep1") == "episode"
    single = tmp_path / "repo" / ".walker"
    _write(single / "walker.yaml", "format: walker/0.2\nproject: {name: X}\n")
    assert walker.detect(single) == "single"
    plain = tmp_path / "plain"
    _write(plain / "a.mp4")
    assert walker.detect(plain) == "plain"


def test_repo_name_from_dot_walker_path(tmp_path):
    s = _series(tmp_path)
    assert walker.load_source(s).repo_name == "myrepo"
    single = tmp_path / "myrepo2" / ".walker"
    _write(single / "walker.yaml", "format: walker/0.2\nproject: {name: X}\n")
    assert walker.load_source(single).repo_name == "myrepo2"
    other = tmp_path / "elsewhere" / "cube"
    _write(other / "series.yaml", SERIES_YAML)
    assert walker.load_source(other).repo_name is None
    assert walker.load_source(other, repo_name="given").repo_name == "given"


def test_series_name_not_folder_name(tmp_path, home):
    src = walker.load_source(_series(tmp_path))
    assert src.kind == "series"
    assert src.title == "Cube: getting started"
    assert src.episodes == ["ep1", "ep2"]
    assert walker.video_root(src, "ep1") == home / "myrepo" / "series" / "cube-gs" / "ep1" / "video"
    assert walker.expected_stem(src, "ep1") == "cube-gs-ep1"


def test_expected_stem_single(tmp_path):
    single = tmp_path / "myrepo" / ".walker"
    _write(single / "walker.yaml", "format: walker/0.2\nproject: {name: X, walked_tag: v1.2}\n")
    src = walker.load_source(single)
    assert src.title == "X"
    assert walker.expected_stem(src, None) == "myrepo-v1.2"
    _write(single / "walker.yaml", "format: walker/0.2\nproject: {name: X}\n")
    assert walker.expected_stem(walker.load_source(single), None) == "myrepo"
    assert walker.sanitize("a b/c") == "a-b-c"


def test_video_root_needs_repo_name(tmp_path, home):
    other = tmp_path / "elsewhere" / "cube"
    _write(other / "series.yaml", SERIES_YAML)
    with pytest.raises(ValueError, match="repo name unknown"):
        walker.video_root(walker.load_source(other), "ep1")


def test_walker_home_order(tmp_path, monkeypatch):
    fake = tmp_path / "user"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    monkeypatch.setenv("USERPROFILE", str(fake))
    monkeypatch.delenv("WALKER_HOME", raising=False)
    assert walker.walker_home() == fake / ".walker"
    _write(fake / ".walker" / "config.yaml", f"home: {tmp_path / 'cfg'}\n")
    assert walker.walker_home() == tmp_path / "cfg"
    monkeypatch.setenv("WALKER_HOME", str(tmp_path / "env"))
    assert walker.walker_home() == tmp_path / "env"


def test_find_runs_ignores_stray_and_explainer(tmp_path):
    root = tmp_path / "video"
    _write(root / "20261027-100000" / "cube-gs-ep1.mp4")
    _write(root / "20261027-100000" / "cube-gs-ep1.yaml", "video_id: abc123\n")
    _write(root / "20261027-110000" / "explainer.mp4")
    _write(root / "notes" / "readme.txt")
    cands, explainers = walker.find_runs(root, "cube-gs-ep1")
    assert [c.run_id for c in cands] == ["20261027-100000"]
    assert cands[0].video_id == "abc123"
    assert cands[0].sidecar is not None
    assert [p.name for p in explainers] == ["20261027-110000"]
    assert walker.find_runs(tmp_path / "nope", "x") == ([], [])


def test_choose_run_timestamp_ids(tmp_path):
    root = tmp_path / "video"
    a = _write(root / "20261027-100000" / "s.mp4")
    b = _write(root / "20261028-090000" / "s.mp4")
    os.utime(b, (1000, 1000))
    os.utime(a, (2000, 2000))
    cands, _ = walker.find_runs(root, "s")
    assert walker.choose_run(cands).run_id == "20261028-090000"
    assert walker.odd_run_ids(cands) == []
    assert walker.choose_run([]) is None


def test_choose_run_falls_back_to_mtime(tmp_path):
    root = tmp_path / "video"
    a = _write(root / "a" / "s.mp4")
    b = _write(root / "b" / "s.mp4")
    os.utime(a, (1000, 1000))
    os.utime(b, (2000, 2000))
    cands, _ = walker.find_runs(root, "s")
    assert walker.choose_run(cands).run_id == "b"
    assert sorted(walker.odd_run_ids(cands)) == ["a", "b"]
