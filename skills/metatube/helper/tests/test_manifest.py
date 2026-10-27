from metatube_helper.manifest import (
    MANIFEST_NAME,
    Conflict,
    EpisodeRecord,
    Manifest,
    PlaylistRecord,
    load_manifest,
    save_manifest,
    sync_ids,
)


def test_round_trip_utf8(tmp_path):
    m = Manifest(
        repo="owner/repo",
        episodes={"ep1": EpisodeRecord(run_id="20261027-100000", video_id="AAAAAAAAAAA", blank_caption=True)},
        playlist=PlaylistRecord(title="Cube — café", description="d", privacy="unlisted", added=["AAAAAAAAAAA"]),
    )
    path = save_manifest(tmp_path, m)
    assert path.name == MANIFEST_NAME
    path.read_bytes().decode("utf-8")
    assert not (tmp_path / (MANIFEST_NAME + ".tmp")).exists()
    assert load_manifest(tmp_path) == m


def test_missing_manifest_is_empty(tmp_path):
    assert load_manifest(tmp_path) == Manifest()


def test_sync_copies_sidecar_id():
    m = Manifest(episodes={"ep1": EpisodeRecord()})
    out, conflicts = sync_ids(m, {"ep1": ("20261027-100000", "AAAAAAAAAAA")})
    assert out.episodes["ep1"].video_id == "AAAAAAAAAAA"
    assert out.episodes["ep1"].run_id == "20261027-100000"
    assert conflicts == []


def test_sync_conflict_leaves_record():
    m = Manifest(episodes={"ep1": EpisodeRecord(video_id="BBBBBBBBBBB", run_id="old")})
    out, conflicts = sync_ids(m, {"ep1": ("new", "AAAAAAAAAAA")})
    assert conflicts == [Conflict("ep1", "BBBBBBBBBBB", "AAAAAAAAAAA")]
    assert out.episodes["ep1"].video_id == "BBBBBBBBBBB"
    assert out.episodes["ep1"].run_id == "old"


def test_sync_equal_refreshes_run_id_and_adds_missing_episode():
    m = Manifest(episodes={"ep1": EpisodeRecord(video_id="AAAAAAAAAAA", run_id="old")})
    out, conflicts = sync_ids(m, {"ep1": ("new", "AAAAAAAAAAA"), "ep2": ("r2", "CCCCCCCCCCC")})
    assert conflicts == []
    assert out.episodes["ep1"].run_id == "new"
    assert out.episodes["ep2"].video_id == "CCCCCCCCCCC"
    assert m.episodes["ep1"].run_id == "old"  # input not mutated


def test_unknown_keys_ignored_on_load(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text(
        "repo: o/r\nfuture: 1\nepisodes:\n  ep1:\n    video_id: AAAAAAAAAAA\n    extra: x\n"
        "playlist:\n  title: T\n  description: D\n  privacy: public\n  zzz: 1\n",
        encoding="utf-8",
    )
    m = load_manifest(tmp_path)
    assert m.repo == "o/r"
    assert m.episodes["ep1"] == EpisodeRecord(video_id="AAAAAAAAAAA")
    assert m.playlist == PlaylistRecord(title="T", description="D", privacy="public")
