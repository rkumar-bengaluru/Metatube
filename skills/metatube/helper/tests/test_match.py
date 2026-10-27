from pathlib import Path

import pytest

from metatube_helper.discover import VideoEntry
from metatube_helper.match import ChannelVideo, match_videos, parse_video_ref


def entry(stem, video_id=None, ext=".mp4"):
    return VideoEntry(
        path=Path(stem + ext), stem=stem, sidecar=Path(stem + ".yaml"), video_id=video_id,
        notes=[], transcripts=[], slides=[], thumbnail=None,
    )


def cv(id, title):
    return ChannelVideo(id=id, title=title, privacy="private", published_at="2026-10-27T00:00:00Z")


def test_exact_title_match_case_insensitive():
    [m] = match_videos([entry("episode-01")], [cv("aaaaaaaaaaa", "Episode-01")])
    assert m.status == "matched" and m.video_id == "aaaaaaaaaaa"


def test_title_with_extension_matches():
    [m] = match_videos([entry("episode-01")], [cv("aaaaaaaaaaa", "episode-01.mp4")])
    assert m.status == "matched"


def test_duplicate_titles_ambiguous():
    [m] = match_videos([entry("episode-01")], [cv("aaaaaaaaaaa", "episode-01"), cv("bbbbbbbbbbb", "episode-01")])
    assert m.status == "ambiguous" and m.video_id is None and len(m.candidates) == 2


def test_claimed_video_excluded():
    a, b = entry("a", video_id="aaaaaaaaaaa"), entry("b")
    ma, mb = match_videos([a, b], [cv("aaaaaaaaaaa", "b")])
    assert ma.status == "preset" and ma.video_id == "aaaaaaaaaaa"
    assert mb.status == "missing"


def test_two_entries_same_candidate_both_ambiguous():
    ms = match_videos([entry("ep1", ext=".mp4"), entry("ep1", ext=".mov")], [cv("aaaaaaaaaaa", "ep1")])
    assert [m.status for m in ms] == ["ambiguous", "ambiguous"]


def test_entries_without_sidecar_are_skipped():
    e = entry("ep1")
    e.sidecar = None
    assert match_videos([e], [cv("aaaaaaaaaaa", "ep1")]) == []


@pytest.mark.parametrize(
    "ref",
    [
        "https://youtu.be/abcdefghijk",
        "https://www.youtube.com/watch?v=abcdefghijk&t=3",
        "https://studio.youtube.com/video/abcdefghijk/edit",
        "https://youtube.com/shorts/abcdefghijk",
        "abcdefghijk",
    ],
)
def test_parse_video_ref(ref):
    assert parse_video_ref(ref) == "abcdefghijk"


def test_parse_video_ref_rejects_garbage():
    with pytest.raises(ValueError):
        parse_video_ref("not a url")


@pytest.mark.parametrize("title", ["metatube day one test", "Metatube_Day_One_Test", "metatube  day-one test.mp4"])
def test_studio_title_with_spaces_for_hyphens_matches(title):
    [m] = match_videos([entry("metatube-day-one-test")], [cv("aaaaaaaaaaa", title)])
    assert m.status == "matched"
