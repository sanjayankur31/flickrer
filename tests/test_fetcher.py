from unittest.mock import patch

import flickr_api

from flickrer.fetcher import _int_or_none, _save_photo


class TestIntOrNone:
    # _int_or_none converts string digit values to int, returning None for
    # missing or malformed input (used for Flickr API fields like posted,
    # width, height, lastupdate).

    def test_valid_int_string(self):
        assert _int_or_none("500") == 500

    def test_none(self):
        assert _int_or_none(None) is None

    def test_invalid_string(self):
        assert _int_or_none("abc") is None

    def test_empty_string(self):
        assert _int_or_none("") is None

    def test_negative(self):
        assert _int_or_none("-10") == -10

    def test_float_string(self):
        assert _int_or_none("12.5") is None


class TestSavePhoto:
    # _save_photo extracts relevant fields from a Photo object returned by
    # the Walker and upserts them into the DB. It marks loaded=True to
    # prevent FlickrObject.__getattr__ from triggering a getInfo() API call
    # when accessing missing attributes (the Walker already populated
    # __dict__ from the paginated list response).

    def test_full_photo(self, conn):
        # A Photo with all extras should store every field in the DB.
        photo = flickr_api.Photo(
            id="p1",
            title="Sunset",
            dateupload="1700000000",
            datetaken="2024-01-15 14:30:00",
            width_o="1920",
            height_o="1080",
            media="photo",
            url_o="https://example.com/original.jpg",
            url_l="https://example.com/large.jpg",
            lastupdate="1700000100",
        )
        _save_photo(conn, photo)
        row = conn.execute("SELECT * FROM photos WHERE id = 'p1'").fetchone()
        assert row["title"] == "Sunset"
        assert row["posted"] == 1700000000
        assert row["taken"] == "2024-01-15 14:30:00"
        assert row["width"] == 1920
        assert row["height"] == 1080
        assert row["media"] == "photo"
        assert row["url_original"] == "https://example.com/original.jpg"
        assert row["url_large"] == "https://example.com/large.jpg"
        assert row["lastupdate"] == 1700000100

    def test_minimal_photo_no_crash(self, conn):
        # A Photo with only an id (no extras) should save without error and
        # set missing fields to None -- no lazy-loaded getInfo() call.
        photo = flickr_api.Photo(id="p1")
        _save_photo(conn, photo)
        row = conn.execute("SELECT * FROM photos WHERE id = 'p1'").fetchone()
        assert row["title"] is None
        assert row["posted"] is None
        assert row["taken"] is None
        assert row["width"] is None
        assert row["height"] is None
        assert row["media"] is None
        assert row["url_original"] is None
        assert row["url_large"] is None
        assert row["lastupdate"] is None

    def test_width_fallback_order(self, conn):
        # width_o is preferred, then width_l, then o_width from o_dims.
        photo = flickr_api.Photo(id="p1", width_o="800", width_l="1024", o_width="600")
        _save_photo(conn, photo)
        row = conn.execute("SELECT * FROM photos WHERE id = 'p1'").fetchone()
        assert row["width"] == 800

    def test_height_large_fallback(self, conn):
        # When height_o is absent, height_l is used.
        photo = flickr_api.Photo(id="p1", height_l="768")
        _save_photo(conn, photo)
        row = conn.execute("SELECT * FROM photos WHERE id = 'p1'").fetchone()
        assert row["height"] == 768

    def test_height_o_dims_fallback(self, conn):
        # When both width_o and width_l are absent, o_height from o_dims is
        # used as a last resort.
        photo = flickr_api.Photo(id="p1", o_height="600")
        _save_photo(conn, photo)
        row = conn.execute("SELECT * FROM photos WHERE id = 'p1'").fetchone()
        assert row["height"] == 600

    def test_loaded_flag_prevents_getinfo_call(self, conn):
        # Verifies that _save_photo does NOT trigger photo.load() (=getInfo()
        # API call) by marking loaded=True before accessing any attributes.
        with patch.object(flickr_api.Photo, "load") as mock_load:
            photo = flickr_api.Photo(id="p1")
            _save_photo(conn, photo)
            mock_load.assert_not_called()
