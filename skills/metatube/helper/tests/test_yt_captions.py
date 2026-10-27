import pytest

from metatube_helper import yt_captions


def test_one_cue_srt_exact():
    assert yt_captions.ONE_CUE_SRT == "1\n00:00:00,000 --> 00:00:01,000\n.\n"


def test_parse_args():
    a = yt_captions.parse_args(["insert", "abc", "--language", "en"])
    assert (a.command, a.video_id, a.language) == ("insert", "abc", "en")
    assert yt_captions.parse_args(["list", "abc"]).command == "list"


def test_insert_requires_language():
    with pytest.raises(SystemExit):
        yt_captions.parse_args(["insert", "abc"])
