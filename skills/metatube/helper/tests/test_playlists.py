from metatube_helper.episodes import EpisodeState
from metatube_helper.manifest import Manifest, PlaylistRecord
from metatube_helper.playlists import flag_items, insert_position, lint_playlist, plan_adds
from metatube_helper.ytstudio import PlaylistItem


def items(*vids):
    return [PlaylistItem(v, f"title {v}", i) for i, v in enumerate(vids)]


def state(key, position, status="live", video_id=None):
    return EpisodeState(key, position, status, None, None, video_id, [], None, [])


def test_insert_position():
    order = ["a", "b", "c"]
    assert insert_position(order, "b", items("a", "x", "c")) == 2
    assert insert_position(order, "b", []) == 0
    assert insert_position(order, "a", items("c")) == 0
    assert insert_position(order, "c", items("a", "b")) == 2
    assert insert_position(order, "b", items("a")) == 1


def test_plan_adds_skips_present_and_orders():
    states = [state("ep1", 1, video_id="a"), state("ep2", 2, video_id="b"),
              state("ep3", 3, status="not_rendered"), state("ep4", 4, video_id="d"),
              state("ep5", 5, status="live_run_missing", video_id="e")]
    plan = plan_adds(states, Manifest(), items("b"))
    # a goes before b; d and e go after b, each position counting the adds before it
    assert plan == [("ep1", "a", 0), ("ep4", "d", 2), ("ep5", "e", 3)]


def test_plan_adds_does_not_readd_what_owner_removed():
    m = Manifest(playlist=PlaylistRecord("t", "d", "public", id="PL1", added=["a"]))
    plan = plan_adds([state("ep1", 1, video_id="a"), state("ep2", 2, video_id="b")], m, [])
    assert plan == [("ep2", "b", 0)]


def test_plan_adds_skips_disagreement():
    plan = plan_adds([state("ep1", 1, status="disagreement", video_id="a")], Manifest(), [])
    assert plan == []


def test_flag_items():
    its = [PlaylistItem("a", "anything", 0), PlaylistItem("z", "Cube GS: part 9", 1),
           PlaylistItem("y", "Cooking pasta", 2)]
    flagged = flag_items(its, {"a"}, "cube gs")
    assert [i.video_id for i in flagged] == ["y"]


def test_lint_playlist():
    assert lint_playlist("Cube GS", "A series.", "public") == []
    errors = lint_playlist("", "x" * 5001, "secret")
    assert len(errors) == 3
    assert lint_playlist("t" * 151, "", "private")
    assert lint_playlist("a <b>", "", "unlisted")
    assert lint_playlist("ok", "has > sign", "unlisted")
    assert lint_playlist("   ", "", "public")
