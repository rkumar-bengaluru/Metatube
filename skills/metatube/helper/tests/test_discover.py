from metatube_helper.discover import discover


def touch(folder, *names, content=""):
    for name in names:
        (folder / name).write_text(content, encoding="utf-8")


def test_pairs_supported_videos_and_sources(tmp_path):
    touch(tmp_path, "ep1.mp4", "ep1.md", "ep1.srt")
    touch(tmp_path, "ep1.yaml", content='title: a\ncategory_id: "28"\n')
    d = discover(tmp_path)
    [e] = d.videos
    assert e.stem == "ep1" and e.sidecar == tmp_path / "ep1.yaml"
    assert e.notes == [tmp_path / "ep1.md"] and e.transcripts == [tmp_path / "ep1.srt"]
    assert e.live is False and d.fully_paired is True


def test_flags_unsupported_and_ignores_other_files(tmp_path):
    touch(tmp_path, "a.avi", "b.txt")
    d = discover(tmp_path)
    assert d.unsupported == [tmp_path / "a.avi"] and d.videos == []


def test_live_detected_from_video_id(tmp_path):
    touch(tmp_path, "ep1.mov")
    touch(tmp_path, "ep1.yaml", content='title: a\ncategory_id: "28"\nvideo_id: abcdefghijk\n')
    [e] = discover(tmp_path).videos
    assert e.live is True and e.video_id == "abcdefghijk"


def test_orphan_sidecar_and_missing_sidecar_not_fully_paired(tmp_path):
    touch(tmp_path, "ep1.mp4", "old.yaml")
    d = discover(tmp_path)
    assert d.orphan_sidecars == [tmp_path / "old.yaml"]
    assert d.videos[0].sidecar is None and d.fully_paired is False


def test_has_source_rules(tmp_path):
    single = tmp_path / "single"
    single.mkdir()
    touch(single, "ep1.mp4")
    assert discover(single).videos[0].has_source is False
    touch(single, "README.md")
    assert discover(single).videos[0].has_source is True

    series = tmp_path / "series"
    series.mkdir()
    touch(series, "ep1.mp4", "ep2.mp4", "README.md")
    assert [e.has_source for e in discover(series).videos] == [False, False]


def test_readme_md_is_not_notes_for_stem_readme(tmp_path):
    touch(tmp_path, "README.mp4", "README.md")
    d = discover(tmp_path)
    assert d.videos[0].notes == [] and d.folder_readme == tmp_path / "README.md"
