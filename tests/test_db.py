from flickrer.db import (
    add_flag,
    add_review,
    count_flags,
    count_photos,
    get_photo,
    iter_flags,
    photo_has_camera_exif,
    set_content_length,
    upsert_exif,
    upsert_photo,
)


def test_init_creates_tables(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in tables]
    assert names == ["exif", "flags", "photos", "review"]


def test_upsert_photo_insert(conn):
    upsert_photo(conn, "p1", title="A", posted=1000, width=800, height=600)
    row = get_photo(conn, "p1")
    assert row["title"] == "A"
    assert row["posted"] == 1000
    assert row["width"] == 800
    assert row["height"] == 600


def test_upsert_photo_update(conn):
    upsert_photo(conn, "p1", title="A", posted=1000)
    upsert_photo(conn, "p1", title="B", posted=2000)
    row = get_photo(conn, "p1")
    assert row["title"] == "B"
    assert row["posted"] == 2000
    assert count_photos(conn) == 1


def test_get_photo_missing(conn):
    assert get_photo(conn, "nonexistent") is None


def test_count_photos(conn):
    assert count_photos(conn) == 0
    upsert_photo(conn, "p1")
    upsert_photo(conn, "p2")
    assert count_photos(conn) == 2


def test_set_content_length(conn):
    upsert_photo(conn, "p1")
    set_content_length(conn, "p1", 12345)
    row = get_photo(conn, "p1")
    assert row["content_length"] == 12345


def test_upsert_exif(conn):
    upsert_photo(conn, "p1")
    upsert_exif(conn, "p1", "Make", "Canon")
    upsert_exif(conn, "p1", "Model", "EOS R5")
    rows = conn.execute(
        "SELECT tag, raw FROM exif WHERE photo_id = ? ORDER BY tag", ("p1",)
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["tag"] == "Make"
    assert rows[0]["raw"] == "Canon"


def test_photo_has_camera_exif_true(conn):
    upsert_photo(conn, "p1")
    upsert_exif(conn, "p1", "Make", "Canon")
    upsert_exif(conn, "p1", "ISO", "400")
    assert photo_has_camera_exif(conn, "p1") is True


def test_photo_has_camera_exif_false(conn):
    upsert_photo(conn, "p1")
    assert photo_has_camera_exif(conn, "p1") is False


def test_photo_has_camera_exif_non_camera_tag(conn):
    upsert_photo(conn, "p1")
    upsert_exif(conn, "p1", "Software", "Lightroom")
    assert photo_has_camera_exif(conn, "p1") is False


def test_add_flag(conn):
    upsert_photo(conn, "p1", title="test")
    upsert_photo(conn, "p2", title="test")
    add_flag(conn, "p1", "duplicate", "same title", related_photo_id="p2")
    flags = list(iter_flags(conn))
    assert len(flags) == 1
    assert flags[0]["flag_type"] == "duplicate"
    assert flags[0]["reason"] == "same title"


def test_add_flag_duplicate_ignored(conn):
    upsert_photo(conn, "p1")
    upsert_photo(conn, "p2")
    add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
    add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
    assert len(list(iter_flags(conn))) == 1


def test_iter_flags_excludes_reviewed(conn):
    upsert_photo(conn, "p1", title="a")
    upsert_photo(conn, "p2", title="a")
    add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
    add_flag(conn, "p2", "duplicate", "dup", related_photo_id="p1")
    add_review(conn, "p1", "skip")
    remaining = list(iter_flags(conn))
    assert len(remaining) == 1
    assert remaining[0]["photo_id"] == "p2"


def test_add_review_and_get(conn):
    upsert_photo(conn, "p1")
    add_review(conn, "p1", "delete")
    rows = conn.execute("SELECT * FROM review WHERE photo_id = ?", ("p1",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["decision"] == "delete"


def test_add_review_replace(conn):
    upsert_photo(conn, "p1")
    add_review(conn, "p1", "skip")
    add_review(conn, "p1", "delete")
    rows = conn.execute("SELECT * FROM review").fetchall()
    assert len(rows) == 1
    assert rows[0]["decision"] == "delete"


def test_count_flags(conn):
    upsert_photo(conn, "p1")
    upsert_photo(conn, "p2")
    add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
    add_flag(conn, "p2", "duplicate", "dup", related_photo_id="p1")
    add_flag(conn, "p1", "no_exif", "no exif")
    counts = count_flags(conn)
    assert counts["duplicate"] == 2
    assert counts["no_exif"] == 1
