from flickrer.fetcher import _int_or_none


class TestIntOrNone:
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
