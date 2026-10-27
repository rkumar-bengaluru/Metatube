import pytest

from metatube_helper.sidecars import LiveSidecarError, load_sidecar, set_video_id, write_sidecar


def test_round_trip_utf8_and_comments(tmp_path):
    p = tmp_path / "ep.yaml"
    p.write_text('# keep me\ntitle: "Café — intro"\ncategory_id: "28"\n', encoding="utf-8")
    d = load_sidecar(p)
    d["description"] = 'Line 1\n\nÉtape — 2 `$HOME` "q"\n'
    write_sidecar(p, d)
    text = p.read_text(encoding="utf-8")
    assert "# keep me" in text and "Café — intro" in text
    assert load_sidecar(p)["description"] == 'Line 1\n\nÉtape — 2 `$HOME` "q"\n'


def test_empty_file_loads_as_empty_dict(tmp_path):
    p = tmp_path / "e.yaml"
    p.write_text("", encoding="utf-8")
    assert dict(load_sidecar(p)) == {}


def test_write_rejects_unknown_key(tmp_path):
    with pytest.raises(ValueError):
        write_sidecar(tmp_path / "a.yaml", {"title": "a", "foo": 1})


def test_write_cannot_change_or_drop_existing_video_id(tmp_path):
    p = tmp_path / "a.yaml"
    write_sidecar(p, {"title": "a", "category_id": "28", "video_id": "abcdefghijk"})
    with pytest.raises(LiveSidecarError):
        write_sidecar(p, {"title": "b", "category_id": "28"})
    with pytest.raises(LiveSidecarError):
        write_sidecar(p, {"title": "b", "category_id": "28", "video_id": "zzzzzzzzzzz"})
    write_sidecar(p, {"title": "b", "category_id": "28", "video_id": "abcdefghijk"})
    assert load_sidecar(p)["title"] == "b"


def test_set_video_id_idempotent_and_guarded(tmp_path):
    p = tmp_path / "a.yaml"
    write_sidecar(p, {"title": "a", "category_id": "28"})
    set_video_id(p, "abcdefghijk")
    set_video_id(p, "abcdefghijk")
    assert load_sidecar(p)["video_id"] == "abcdefghijk"
    with pytest.raises(LiveSidecarError):
        set_video_id(p, "zzzzzzzzzzz")


def test_replace_video_id_requires_expected_old(tmp_path):
    from metatube_helper.sidecars import replace_video_id
    p = tmp_path / "a.yaml"
    write_sidecar(p, {"title": "a", "category_id": "28", "video_id": "abcdefghijk"})
    with pytest.raises(LiveSidecarError):
        replace_video_id(p, "zzzzzzzzzzz", expected_old="yyyyyyyyyyy")
    replace_video_id(p, "zzzzzzzzzzz", expected_old="abcdefghijk")
    assert load_sidecar(p)["video_id"] == "zzzzzzzzzzz"
