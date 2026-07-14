import logging
import subprocess
import sys
import termios
import tty

import flickr_api

from flickrer.config import VIEWER_CMD
from flickrer.db import add_review, get_conn, iter_flags

log = logging.getLogger(__name__)


def _getch() -> str:
    fd = sys.stdin.fileno()
    attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)


def review(dry_run: bool = False) -> None:
    conn = get_conn()
    try:
        flags = list(iter_flags(conn))
        if not flags:
            log.info("No flags to review.")
            return

        log.info("Reviewing %d flagged photos (dry_run=%s)", len(flags), dry_run)

        for idx, row in enumerate(flags, 1):
            _show_photo(row, idx, len(flags), dry_run)
            if not _prompt(row, conn, dry_run):
                break
    finally:
        conn.close()


def _show_photo(row, idx: int, total: int, dry_run: bool) -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    title = row["title"] or "(no title)"
    taken = row["taken"] or "unknown"
    dims = f"{row['width'] or '?'}x{row['height'] or '?'}"
    flag_type = row["flag_type"]
    reason = row["reason"] or ""
    related = row["related_photo_id"] or ""

    mode = " [DRY RUN]" if dry_run else ""
    lines = [
        f"\n=== Review {idx}/{total}{mode} ===",
        f"  Photo ID:   {row['photo_id']}",
        f"  Title:      {title}",
        f"  Taken:      {taken}",
        f"  Dims:       {dims}",
        f"  Flag:       {flag_type}",
        f"  Reason:     {reason}",
    ]
    if related:
        lines.append(f"  Related:    {related}")

    lines.append("")
    lines.append("  [o] Open in viewer   [d] Delete   [s] Skip   [q] Quit")
    lines.append("")

    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()


def _prompt(row, conn, dry_run: bool) -> bool:
    while True:
        key = _getch().lower()

        if key == "o":
            _open_viewer(row)
            return True

        if key == "d":
            if dry_run:
                log.info("[DRY RUN] would delete photo %s", row["photo_id"])
            else:
                _delete_photo(row)
            add_review(conn, row["photo_id"], "delete")
            return True

        if key == "s":
            add_review(conn, row["photo_id"], "skip")
            return True

        if key == "q":
            conn.commit()
            return False


def _open_viewer(row) -> None:
    url = row["url_original"] or row["url_large"]
    if not url:
        log.warning("No URL available for photo %s", row["photo_id"])
        return
    try:
        subprocess.Popen(
            [VIEWER_CMD, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        log.warning("Failed to open viewer: %s", e)


def _delete_photo(row) -> None:
    try:
        photo = flickr_api.Photo(id=row["photo_id"])
        photo.delete()
        log.info("Deleted photo %s", row["photo_id"])
    except Exception as e:
        log.warning("Failed to delete photo %s: %s", row["photo_id"], e)
