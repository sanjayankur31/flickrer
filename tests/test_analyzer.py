from flickrer.analyzer import _duplicate_reason, _find_no_exif
from flickrer.db import upsert_exif, upsert_photo


def _photo(
    pid: str,
    title: str = "",
    posted: int | None = None,
    taken: str | None = None,
    width: int | None = None,
    height: int | None = None,
    content_length: int | None = None,
):
    return {
        "id": pid,
        "title": title,
        "posted": posted,
        "taken": taken,
        "width": width,
        "height": height,
        "content_length": content_length,
        "url_original": None,
    }


class TestDuplicateReason:
    def test_no_match(self, conn):
        a = _photo("1", "sunset", posted=0, width=800)
        b = _photo("2", "beach", posted=7200, width=1024)
        assert _duplicate_reason(conn, a, b) is None

    def test_same_dimensions(self, conn):
        a = _photo("1", "photo", width=1920, height=1080)
        b = _photo("2", "photo", width=1920, height=1080)
        reason = _duplicate_reason(conn, a, b)
        assert reason is not None
        assert "same dimensions" in reason

    def test_close_upload_date(self, conn):
        a = _photo("1", "pic", posted=1000)
        b = _photo("2", "pic", posted=2000)
        reason = _duplicate_reason(conn, a, b)
        assert reason is not None
        # 1000s diff is within 1h window
        assert "close upload date" in reason

    def test_far_upload_date(self, conn):
        a = _photo("1", "pic", posted=0)
        b = _photo("2", "pic", posted=7200)
        reason = _duplicate_reason(conn, a, b)
        assert reason is None

    def test_same_taken_date(self, conn):
        a = _photo("1", "pic", taken="2024-01-01")
        b = _photo("2", "pic", taken="2024-01-01")
        reason = _duplicate_reason(conn, a, b)
        assert reason is not None
        assert "same taken date" in reason

    def test_all_signals(self, conn):
        a = _photo("1", "dup", posted=1000, taken="2024-01-01", width=800, height=600)
        b = _photo("2", "dup", posted=1200, taken="2024-01-01", width=800, height=600)
        reason = _duplicate_reason(conn, a, b)
        assert reason is not None
        assert "same dimensions" in reason
        assert "close upload date" in reason
        assert "same taken date" in reason

    def test_same_file_size(self, conn):
        upsert_photo(conn, "1")
        upsert_photo(conn, "2")
        a = _photo("1", "dup", posted=1000, width=800, height=600, content_length=5000)
        b = _photo("2", "dup", posted=1200, width=800, height=600, content_length=5000)
        reason = _duplicate_reason(conn, a, b)
        assert "same file size" in reason

    def test_different_file_size(self, conn):
        upsert_photo(conn, "1")
        upsert_photo(conn, "2")
        a = _photo("1", "dup", posted=1000, width=800, height=600, content_length=5000)
        b = _photo("2", "dup", posted=1200, width=800, height=600, content_length=6000)
        reason = _duplicate_reason(conn, a, b)
        assert reason is not None
        assert "same file size" not in reason


class TestFindNoExif:
    def test_no_exif_flagged(self, conn):
        upsert_photo(conn, "p1")
        count = _find_no_exif(conn)
        assert count == 1
        flags = conn.execute(
            "SELECT * FROM flags WHERE flag_type = 'no_exif'"
        ).fetchall()
        assert len(flags) == 1
        assert flags[0]["photo_id"] == "p1"

    def test_camera_exif_not_flagged(self, conn):
        upsert_photo(conn, "p1")
        upsert_exif(conn, "p1", "Make", "Canon")
        upsert_exif(conn, "p1", "ISO", "400")
        count = _find_no_exif(conn)
        assert count == 0

    def test_non_camera_exif_flagged(self, conn):
        upsert_photo(conn, "p1")
        upsert_exif(conn, "p1", "Software", "Lightroom")
        count = _find_no_exif(conn)
        assert count == 1

    def test_mixed_photos(self, conn):
        upsert_photo(conn, "p1")
        upsert_exif(conn, "p1", "Make", "Nikon")
        upsert_photo(conn, "p2")
        count = _find_no_exif(conn)
        assert count == 1
