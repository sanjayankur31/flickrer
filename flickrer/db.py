import sqlite3
import time
from collections.abc import Generator

from flickrer.config import DB_PATH

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS photos (
    id             TEXT PRIMARY KEY,
    title          TEXT,
    posted         INTEGER,
    taken          TEXT,
    width          INTEGER,
    height         INTEGER,
    content_length INTEGER,
    media          TEXT,
    url_original   TEXT,
    url_large      TEXT,
    lastupdate     INTEGER,
    exif_fetched_at INTEGER
);

CREATE TABLE IF NOT EXISTS exif (
    photo_id TEXT NOT NULL REFERENCES photos(id),
    tag      TEXT NOT NULL,
    raw      TEXT,
    UNIQUE(photo_id, tag)
);

CREATE TABLE IF NOT EXISTS flags (
    photo_id         TEXT NOT NULL REFERENCES photos(id),
    flag_type        TEXT NOT NULL,
    reason           TEXT,
    related_photo_id TEXT,
    created_at       INTEGER NOT NULL,
    UNIQUE(photo_id, flag_type, related_photo_id)
);

CREATE TABLE IF NOT EXISTS review (
    photo_id   TEXT NOT NULL REFERENCES photos(id) UNIQUE,
    decision   TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS uploads (
    local_path   TEXT PRIMARY KEY,
    photo_id     TEXT NOT NULL,
    mtime        REAL NOT NULL,
    synced_date  TEXT,
    uploaded_at  INTEGER NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_CREATE_TABLES)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(uploads)")}
    if "synced_date" not in existing:
        conn.execute("ALTER TABLE uploads ADD COLUMN synced_date TEXT")
    photo_cols = {r["name"] for r in conn.execute("PRAGMA table_info(photos)")}
    if "lastupdate" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN lastupdate INTEGER")
    if "exif_fetched_at" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN exif_fetched_at INTEGER")


# --- photos ---


def upsert_photo(
    conn: sqlite3.Connection,
    photo_id: str,
    title: str | None = None,
    posted: int | None = None,
    taken: str | None = None,
    width: int | None = None,
    height: int | None = None,
    media: str | None = None,
    url_original: str | None = None,
    url_large: str | None = None,
    lastupdate: int | None = None,
) -> None:
    conn.execute(
        """INSERT INTO photos (id, title, posted, taken, width, height, media, url_original, url_large, lastupdate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               title=excluded.title,
               posted=excluded.posted,
               taken=excluded.taken,
               width=excluded.width,
               height=excluded.height,
               media=excluded.media,
               url_original=excluded.url_original,
               url_large=excluded.url_large,
               lastupdate=excluded.lastupdate""",
        (
            photo_id,
            title,
            posted,
            taken,
            width,
            height,
            media,
            url_original,
            url_large,
            lastupdate,
        ),
    )


def get_photo(conn: sqlite3.Connection, photo_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()


def set_content_length(conn: sqlite3.Connection, photo_id: str, size: int) -> None:
    conn.execute("UPDATE photos SET content_length = ? WHERE id = ?", (size, photo_id))


def iter_photos(conn: sqlite3.Connection) -> Generator[sqlite3.Row, None, None]:
    yield from conn.execute("SELECT * FROM photos ORDER BY posted")


def count_photos(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]


def set_exif_fetched_at(conn: sqlite3.Connection, photo_id: str) -> None:
    conn.execute(
        "UPDATE photos SET exif_fetched_at = ? WHERE id = ?",
        (int(time.time()), photo_id),
    )


def iter_photos_missing_exif(
    conn: sqlite3.Connection,
) -> Generator[sqlite3.Row, None, None]:
    yield from conn.execute(
        "SELECT id FROM photos "
        "WHERE NOT EXISTS (SELECT 1 FROM exif WHERE photo_id = photos.id)"
    )


def iter_photos_outdated_exif(
    conn: sqlite3.Connection,
) -> Generator[sqlite3.Row, None, None]:
    yield from conn.execute(
        "SELECT id FROM photos "
        "WHERE lastupdate IS NOT NULL "
        "AND (exif_fetched_at IS NULL OR lastupdate > exif_fetched_at)"
    )


# --- exif ---


def upsert_exif(
    conn: sqlite3.Connection, photo_id: str, tag: str, raw: str | None
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO exif (photo_id, tag, raw) VALUES (?, ?, ?)",
        (photo_id, tag, raw),
    )


def get_photo_exif(conn: sqlite3.Connection, photo_id: str) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM exif WHERE photo_id = ?", (photo_id,)))


def photo_has_camera_exif(conn: sqlite3.Connection, photo_id: str) -> bool:
    camera_tags = {"Make", "Model", "FNumber", "ExposureTime", "ISO", "FocalLength"}
    rows = conn.execute(
        "SELECT tag FROM exif WHERE photo_id = ? AND tag IN ("
        + ",".join("?" for _ in camera_tags)
        + ")",
        (photo_id, *camera_tags),
    )
    return rows.fetchone() is not None


# --- flags ---


def add_flag(
    conn: sqlite3.Connection,
    photo_id: str,
    flag_type: str,
    reason: str,
    related_photo_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO flags (photo_id, flag_type, reason, related_photo_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (photo_id, flag_type, reason, related_photo_id, int(time.time())),
    )


def iter_flags(
    conn: sqlite3.Connection, exclude_reviewed: bool = True
) -> Generator[sqlite3.Row, None, None]:
    query = (
        "SELECT f.*, p.title, p.taken, p.posted, p.width, p.height, p.url_original, p.url_large "
        "FROM flags f JOIN photos p ON p.id = f.photo_id "
    )
    if exclude_reviewed:
        query += (
            "LEFT JOIN review r ON r.photo_id = f.photo_id WHERE r.photo_id IS NULL "
        )
    query += "ORDER BY f.flag_type, f.created_at"
    yield from conn.execute(query)


def count_flags(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT flag_type, COUNT(*) as cnt FROM flags GROUP BY flag_type"
    )
    return {r["flag_type"]: r["cnt"] for r in rows}


# --- review ---


def add_review(conn: sqlite3.Connection, photo_id: str, decision: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO review (photo_id, decision, created_at) VALUES (?, ?, ?)",
        (photo_id, decision, int(time.time())),
    )


def get_review(conn: sqlite3.Connection, photo_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM review WHERE photo_id = ?", (photo_id,)
    ).fetchone()


# --- uploads ---


def record_upload(
    conn: sqlite3.Connection,
    local_path: str,
    photo_id: str,
    mtime: float,
    synced_date: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO uploads (local_path, photo_id, mtime, synced_date, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (local_path, photo_id, mtime, synced_date, int(time.time())),
    )


def is_uploaded(conn: sqlite3.Connection, local_path: str, mtime: float) -> bool:
    row = conn.execute(
        "SELECT 1 FROM uploads WHERE local_path = ? AND mtime = ?",
        (local_path, mtime),
    ).fetchone()
    return row is not None


def is_uploaded_any(conn: sqlite3.Connection, local_path: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM uploads WHERE local_path = ?", (local_path,)
    ).fetchone()
    return row is not None


def get_upload(conn: sqlite3.Connection, local_path: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM uploads WHERE local_path = ?", (local_path,)
    ).fetchone()


def update_upload_sync(
    conn: sqlite3.Connection,
    local_path: str,
    synced_date: str | None,
    mtime: float | None = None,
) -> None:
    if mtime is not None:
        conn.execute(
            "UPDATE uploads SET synced_date = ?, mtime = ? WHERE local_path = ?",
            (synced_date, mtime, local_path),
        )
    else:
        conn.execute(
            "UPDATE uploads SET synced_date = ? WHERE local_path = ?",
            (synced_date, local_path),
        )
