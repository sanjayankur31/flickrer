import logging
import urllib.request
from collections import defaultdict

from flickrer.db import (
    add_flag,
    get_conn,
    photo_has_camera_exif,
    set_content_length,
)

log = logging.getLogger(__name__)

_DUPLICATE_WINDOW_SECS = 3600  # 1 hour
_HEAD_TIMEOUT = 5


def analyze() -> None:
    conn = get_conn()
    try:
        dups = _find_duplicates(conn)
        log.info("Found %d duplicate pairs", dups)

        noexif = _find_no_exif(conn)
        log.info("Found %d no-EXIF photos", noexif)
    finally:
        conn.close()


def _fetch_content_length(url: str | None) -> int | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=_HEAD_TIMEOUT) as resp:
            size = resp.headers.get("Content-Length")
            return int(size) if size else None
    except Exception:
        log.debug("HEAD request failed for %s", url)
        return None


def _find_duplicates(conn) -> int:
    grouped: dict[str, list] = defaultdict(list)

    for row in conn.execute(
        "SELECT id, title, posted, taken, width, height, content_length, url_original "
        "FROM photos "
        "WHERE title IS NOT NULL AND title != '' "
        "ORDER BY LOWER(title), posted"
    ):
        grouped[row["title"].lower()].append(
            {
                "id": row["id"],
                "title": row["title"],
                "posted": row["posted"],
                "taken": row["taken"],
                "width": row["width"],
                "height": row["height"],
                "content_length": row["content_length"],
                "url_original": row["url_original"],
            }
        )

    count = 0
    for title_lower, photos in grouped.items():
        if len(photos) < 2:
            continue

        for i in range(len(photos)):
            for j in range(i + 1, len(photos)):
                a, b = photos[i], photos[j]
                reason = _duplicate_reason(conn, a, b)
                if reason is None:
                    continue

                add_flag(
                    conn,
                    photo_id=a["id"],
                    flag_type="duplicate",
                    reason=f"{b['title']}: {reason}",
                    related_photo_id=b["id"],
                )
                add_flag(
                    conn,
                    photo_id=b["id"],
                    flag_type="duplicate",
                    reason=f"{a['title']}: {reason}",
                    related_photo_id=a["id"],
                )
                count += 1

    conn.commit()
    return count


def _duplicate_reason(conn, a: dict, b: dict) -> str | None:
    reasons = []

    same_dims = (
        a["width"] is not None
        and b["width"] is not None
        and a["width"] == b["width"]
        and a["height"] == b["height"]
    )
    if same_dims:
        reasons.append("same dimensions")

    if a["posted"] is not None and b["posted"] is not None:
        if abs(a["posted"] - b["posted"]) <= _DUPLICATE_WINDOW_SECS:
            reasons.append("close upload date")

    if a["taken"] and b["taken"] and a["taken"] == b["taken"]:
        reasons.append("same taken date")

    if not reasons:
        return None

    size_a = a.get("content_length")
    size_b = b.get("content_length")

    if size_a is None:
        size_a = _fetch_content_length(a.get("url_original"))
        if size_a is not None:
            a["content_length"] = size_a
            set_content_length(conn, a["id"], size_a)

    if size_b is None:
        size_b = _fetch_content_length(b.get("url_original"))
        if size_b is not None:
            b["content_length"] = size_b
            set_content_length(conn, b["id"], size_b)

    if size_a is not None and size_b is not None and size_a == size_b:
        reasons.append("same file size")

    return ", ".join(reasons)


def _find_no_exif(conn) -> int:
    rows = list(conn.execute("SELECT id, title FROM photos"))
    count = 0

    for row in rows:
        if not photo_has_camera_exif(conn, row["id"]):
            add_flag(
                conn,
                photo_id=row["id"],
                flag_type="no_exif",
                reason="No camera EXIF data (could be meme, screenshot, or download)",
            )
            count += 1

    conn.commit()
    return count
