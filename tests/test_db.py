from flickrer.db import (
    add_flag,
    add_review,
    count_flags,
    count_photos,
    get_photo,
    is_uploaded,
    iter_flags,
    photo_has_camera_exif,
    record_upload,
    set_content_length,
    upsert_exif,
    upsert_photo,
)


def test_init_creates_tables(conn):
    # All expected tables should exist after init.
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in tables]
    assert names == ["exif", "flags", "photos", "review", "uploads"]


class TestPhotos:
    def test_upsert_insert(self, conn):
        upsert_photo(conn, "p1", title="A", posted=1000, width=800, height=600)
        row = get_photo(conn, "p1")
        assert row["title"] == "A"
        assert row["posted"] == 1000
        assert row["width"] == 800
        assert row["height"] == 600

    def test_upsert_update(self, conn):
        upsert_photo(conn, "p1", title="A", posted=1000)
        upsert_photo(conn, "p1", title="B", posted=2000)
        row = get_photo(conn, "p1")
        assert row["title"] == "B"
        assert row["posted"] == 2000
        assert count_photos(conn) == 1

    def test_get_missing(self, conn):
        assert get_photo(conn, "nonexistent") is None

    def test_count(self, conn):
        assert count_photos(conn) == 0
        upsert_photo(conn, "p1")
        upsert_photo(conn, "p2")
        assert count_photos(conn) == 2

    def test_set_content_length(self, conn):
        upsert_photo(conn, "p1")
        set_content_length(conn, "p1", 12345)
        row = get_photo(conn, "p1")
        assert row["content_length"] == 12345


class TestExif:
    def test_upsert(self, conn):
        upsert_photo(conn, "p1")
        upsert_exif(conn, "p1", "Make", "Canon")
        upsert_exif(conn, "p1", "Model", "EOS R5")
        rows = conn.execute(
            "SELECT tag, raw FROM exif WHERE photo_id = ? ORDER BY tag", ("p1",)
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["tag"] == "Make"
        assert rows[0]["raw"] == "Canon"

    def test_has_camera_exif_true(self, conn):
        upsert_photo(conn, "p1")
        upsert_exif(conn, "p1", "Make", "Canon")
        upsert_exif(conn, "p1", "ISO", "400")
        assert photo_has_camera_exif(conn, "p1") is True

    def test_has_camera_exif_false(self, conn):
        upsert_photo(conn, "p1")
        assert photo_has_camera_exif(conn, "p1") is False

    def test_non_camera_tag_not_counted(self, conn):
        upsert_photo(conn, "p1")
        upsert_exif(conn, "p1", "Software", "Lightroom")
        assert photo_has_camera_exif(conn, "p1") is False


class TestFlags:
    def test_add_and_iter(self, conn):
        upsert_photo(conn, "p1", title="test")
        upsert_photo(conn, "p2", title="test")
        add_flag(conn, "p1", "duplicate", "same title", related_photo_id="p2")
        flags = list(iter_flags(conn))
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "duplicate"
        assert flags[0]["reason"] == "same title"

    def test_duplicate_ignored(self, conn):
        upsert_photo(conn, "p1")
        upsert_photo(conn, "p2")
        add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
        add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
        assert len(list(iter_flags(conn))) == 1

    def test_iter_flags_excludes_reviewed(self, conn):
        upsert_photo(conn, "p1", title="a")
        upsert_photo(conn, "p2", title="a")
        add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
        add_flag(conn, "p2", "duplicate", "dup", related_photo_id="p1")
        add_review(conn, "p1", "skip")
        remaining = list(iter_flags(conn))
        assert len(remaining) == 1
        assert remaining[0]["photo_id"] == "p2"

    def test_count_flags(self, conn):
        upsert_photo(conn, "p1")
        upsert_photo(conn, "p2")
        add_flag(conn, "p1", "duplicate", "dup", related_photo_id="p2")
        add_flag(conn, "p2", "duplicate", "dup", related_photo_id="p1")
        add_flag(conn, "p1", "no_camera_exif", "no camera tags")
        counts = count_flags(conn)
        assert counts["duplicate"] == 2
        assert counts["no_camera_exif"] == 1


class TestReview:
    def test_add_and_get(self, conn):
        upsert_photo(conn, "p1")
        add_review(conn, "p1", "delete")
        rows = conn.execute(
            "SELECT * FROM review WHERE photo_id = ?", ("p1",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["decision"] == "delete"

    def test_replace(self, conn):
        upsert_photo(conn, "p1")
        add_review(conn, "p1", "skip")
        add_review(conn, "p1", "delete")
        rows = conn.execute("SELECT * FROM review").fetchall()
        assert len(rows) == 1
        assert rows[0]["decision"] == "delete"


class TestUploads:
    def test_record_insert(self, conn):
        record_upload(conn, "/path/a.jpg", "p1", 1000.0)
        row = conn.execute(
            "SELECT * FROM uploads WHERE local_path = ?", ("/path/a.jpg",)
        ).fetchone()
        assert row["photo_id"] == "p1"
        assert row["mtime"] == 1000.0

    def test_is_uploaded_matches_mtime(self, conn):
        record_upload(conn, "/path/a.jpg", "p1", 1000.0)
        assert is_uploaded(conn, "/path/a.jpg", 1000.0) is True
        assert is_uploaded(conn, "/path/a.jpg", 2000.0) is False
        assert is_uploaded(conn, "/path/other.jpg", 1000.0) is False

    def test_record_replaces_mtime(self, conn):
        record_upload(conn, "/path/a.jpg", "p1", 1000.0)
        record_upload(conn, "/path/a.jpg", "p1", 2000.0)
        assert is_uploaded(conn, "/path/a.jpg", 2000.0) is True
        assert is_uploaded(conn, "/path/a.jpg", 1000.0) is False
