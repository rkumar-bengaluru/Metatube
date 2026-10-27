from metatube_helper.schema import lint

TAGS8 = [f"t{i}" for i in range(8)]


def test_valid_minimal_sidecar_ok():
    r = lint({"title": "Intro to X", "category_id": "28", "tags": TAGS8})
    assert r.ok and r.warnings == []


def test_unknown_key_is_error():
    assert not lint({"title": "a", "category_id": "28", "summary": "x"}).ok


def test_missing_category_is_error():
    assert any("category_id" in e for e in lint({"title": "a"}).errors)


def test_title_over_100_error_over_70_warning():
    assert not lint({"title": "x" * 101, "category_id": "28"}).ok
    r = lint({"title": "x" * 71, "category_id": "28", "tags": TAGS8})
    assert r.ok and any("70" in w for w in r.warnings)


def test_tag_with_comma_is_error():
    assert not lint({"title": "a", "category_id": "28", "tags": ["a,b", *TAGS8]}).ok


def test_tags_total_over_500_chars_is_error():
    assert not lint({"title": "a", "category_id": "28", "tags": ["x" * 60] * 9}).ok


def test_tag_count_outside_8_15_is_warning():
    r = lint({"title": "a", "category_id": "28", "tags": ["a"]})
    assert r.ok and any("8" in w for w in r.warnings)


def test_publish_at_naive_or_past_is_error():
    assert not lint({"title": "a", "category_id": "28", "publish_at": "2030-01-01T10:00:00"}).ok
    assert not lint(
        {"title": "a", "category_id": "28", "publish_at": "2020-01-01T10:00:00+00:00"}
    ).ok


def test_publish_at_with_public_privacy_warns_forced_private():
    r = lint(
        {
            "title": "a",
            "category_id": "28",
            "privacy": "public",
            "publish_at": "2099-01-01T10:00:00+05:30",
            "tags": TAGS8,
        }
    )
    assert r.ok and any("private" in w for w in r.warnings)


def test_description_over_5000_bytes_is_error():
    assert not lint({"title": "a", "category_id": "28", "tags": TAGS8, "description": "é" * 2501}).ok


def test_angle_brackets_in_title_or_description_are_errors():
    assert not lint({"title": "a <b>", "category_id": "28", "tags": TAGS8}).ok
    assert not lint({"title": "a", "category_id": "28", "tags": TAGS8, "description": "x > y"}).ok


def test_tag_total_counts_commas_and_quotes_for_multiword_tags():
    # 9 tags x 52 chars = 468, + 8 separators + 2 quotes each for multi-word tags = 494 -> ok
    ok_tags = ["a" * 52] * 9
    assert lint({"title": "a", "category_id": "28", "tags": ok_tags}).ok
    multi = ["a b" + "c" * 49] * 9  # 52 chars each, quoted: 9*54 + 8 = 494 -> ok
    assert lint({"title": "a", "category_id": "28", "tags": multi}).ok
    over = ["a b" + "c" * 50] * 9  # 53 chars, quoted: 9*55 + 8 = 503 -> error
    assert not lint({"title": "a", "category_id": "28", "tags": over}).ok
