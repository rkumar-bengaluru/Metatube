import json
import shutil
from pathlib import Path

import pytest

from metatube_helper import cli
from metatube_helper.discover import discover
from metatube_helper.manifest import load_manifest
from metatube_helper.playlists import lint_playlist
from metatube_helper.schema import lint
from metatube_helper.sidecars import load_sidecar
from metatube_helper.ytstudio import run_ytstudio

EXAMPLES = Path(__file__).resolve().parents[4] / "examples"
FOLDERS = ["single-video", "series"]
WALKER = EXAMPLES / "walker-series"


def staged(tmp_path, name):
    """Copy an example folder and add an empty .mp4 per sidecar (videos aren't committed)."""
    dest = tmp_path / name
    shutil.copytree(EXAMPLES / name, dest)
    for sidecar in dest.glob("*.yaml"):
        sidecar.with_suffix(".mp4").write_bytes(b"")
    return dest


def all_sidecars():
    """Sidecars of the flat examples; the Walker example keeps its sidecars in a fake Walker home."""
    return sorted(p for p in EXAMPLES.glob("*/*.yaml") if p.parent.name in FOLDERS)


def walker_sidecars():
    return sorted(WALKER.glob("_home/*/series/*/*/video/*/*.yaml"))


@pytest.fixture
def walker_copy(tmp_path, monkeypatch):
    """Copy the Walker example, point WALKER_HOME at its fake home, add an empty .mp4 per sidecar."""
    monkeypatch.setenv("METATUBE_CONFIG", str(tmp_path / "cfg" / "config.yaml"))
    dest = tmp_path / "walker-series"
    shutil.copytree(WALKER, dest)
    monkeypatch.setenv("WALKER_HOME", str(dest / "_home"))
    for sidecar in (dest / "_home").glob("*/series/*/*/video/*/*.yaml"):
        sidecar.with_suffix(".mp4").write_bytes(b"")
    return dest


def test_examples_exist():
    assert {p.parent.name for p in all_sidecars()} == set(FOLDERS)


@pytest.mark.parametrize("sidecar", all_sidecars(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_example_sidecars_lint_clean(sidecar):
    r = lint(load_sidecar(sidecar))
    assert r.ok and r.warnings == [], (r.errors, r.warnings)


def test_examples_contain_utf8_punctuation():
    text = "".join(p.read_text(encoding="utf-8") for p in all_sidecars())
    assert "—" in text and "é" in text


@pytest.mark.parametrize("name", FOLDERS)
def test_examples_discover_with_source(tmp_path, name):
    d = discover(staged(tmp_path, name))
    assert d.videos and all(v.has_source for v in d.videos) and d.fully_paired


@pytest.mark.skipif(shutil.which("ytstudio") is None, reason="ytstudio not installed")
@pytest.mark.parametrize("name", FOLDERS)
def test_ytstudio_dry_run_accepts_examples(tmp_path, name):
    folder = staged(tmp_path, name)
    r = run_ytstudio(["videos", "upload", str(folder)])
    output = r.stdout + r.stderr
    assert r.returncode == 0, output
    for sidecar in folder.glob("*.yaml"):
        title = load_sidecar(sidecar)["title"]
        assert title[:20] in output, (title, output)


def test_walker_example_status(walker_copy, capsys):
    code = cli.main(["walker-status", str(walker_copy), "--repo", "myrepo"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["kind"] == "series"
    eps = out["episodes"]
    assert [e["key"] for e in eps] == ["ep1-intro", "ep2-usage"]
    for e in eps:
        assert e["status"] == "ready", e
        assert e["transcript"] and e["has_source"] and not e["thin_sources"], e


def test_walker_example_sidecars_exist():
    assert len(walker_sidecars()) == 2


@pytest.mark.parametrize("sidecar", walker_sidecars(), ids=lambda p: p.name)
def test_walker_example_sidecars_lint_clean(sidecar):
    r = lint(load_sidecar(sidecar))
    assert r.ok and r.warnings == [], (r.errors, r.warnings)
    assert "video_id" not in load_sidecar(sidecar)


def test_walker_example_playlist_draft_lints():
    pl = load_manifest(WALKER).playlist
    assert pl is not None and pl.id is None
    assert lint_playlist(pl.title, pl.description, pl.privacy) == []
