import dateutil.parser


def parse_timestamp(s: str) -> int:
    """Parse a date string or Unix timestamp.

    All-digit strings are treated as Unix timestamps for backward
    compatibility. Everything else is parsed via dateutil.
    """
    s = s.strip()
    if s.isdigit():
        return int(s)
    dt = dateutil.parser.parse(s)
    return int(dt.timestamp())
