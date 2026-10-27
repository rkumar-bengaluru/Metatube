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
    touch(single, "README.md", content=REAL_NOTES)
    assert discover(single).videos[0].has_source is True

    series = tmp_path / "series"
    series.mkdir()
    touch(series, "ep1.mp4", "ep2.mp4")
    touch(series, "README.md", content=REAL_NOTES)
    assert [e.has_source for e in discover(series).videos] == [False, False]


def test_readme_md_is_not_notes_for_stem_readme(tmp_path):
    touch(tmp_path, "README.mp4", "README.md")
    d = discover(tmp_path)
    assert d.videos[0].notes == [] and d.folder_readme == tmp_path / "README.md"


REAL_NOTES = "This video walks through installing the tool, configuring it, running the first job, " \
             "reading the logs, handling a failed run, and retrying it with backoff until it succeeds cleanly."


def test_empty_or_frontmatter_only_notes_are_thin(tmp_path):
    touch(tmp_path, "ep1.mp4", "ep2.mp4")
    touch(tmp_path, "ep1.md", content="")
    touch(tmp_path, "ep2.md", content='---\ndescription: x\n---\n\nUse the metatube skill to run the **generate** workflow.\n')
    d = discover(tmp_path)
    assert [v.has_source for v in d.videos] == [False, False]
    assert d.videos[0].thin_sources == [tmp_path / "ep1.md"]


def test_real_notes_count_as_source(tmp_path):
    touch(tmp_path, "ep1.mp4")
    touch(tmp_path, "ep1.md", content=REAL_NOTES)
    assert discover(tmp_path).videos[0].has_source is True


def test_transcript_with_text_counts_as_source(tmp_path):
    touch(tmp_path, "ep1.mp4")
    touch(tmp_path, "ep1.srt", content="1\n00:00:00,000 --> 00:00:05,000\nHello and welcome to the repo tour.\n")
    assert discover(tmp_path).videos[0].has_source is True


def test_thin_folder_readme_does_not_count(tmp_path):
    touch(tmp_path, "ep1.mp4")
    touch(tmp_path, "README.md", content="# hi\n")
    assert discover(tmp_path).videos[0].has_source is False
