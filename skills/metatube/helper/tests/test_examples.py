import shutil
from pathlib import Path

import pytest

from metatube_helper.discover import discover
from metatube_helper.schema import lint
from metatube_helper.sidecars import load_sidecar
from metatube_helper.ytstudio import run_ytstudio

EXAMPLES = Path(__file__).resolve().parents[4] / "examples"
FOLDERS = ["single-video", "series"]


def staged(tmp_path, name):
    """Copy an example folder and add an empty .mp4 per sidecar (videos aren't committed)."""
    dest = tmp_path / name
    shutil.copytree(EXAMPLES / name, dest)
    for sidecar in dest.glob("*.yaml"):
        sidecar.with_suffix(".mp4").write_bytes(b"")
    return dest


def all_sidecars():
    return sorted(EXAMPLES.glob("*/*.yaml"))


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
