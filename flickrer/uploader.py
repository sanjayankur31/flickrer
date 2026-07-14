import logging
import re
import time
from datetime import datetime
from pathlib import Path

import exifread
import flickr_api
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from flickrer.db import get_conn, is_uploaded, record_upload
from flickrer.fetcher import fetch_photostream

log = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".tiff",
        ".tif",
        ".heic",
        ".heif",
    }
)

_UPLOAD_DELAY = 1.0

_DATE_PATTERNS = [
    re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})"),
    re.compile(r"(\d{2})(\d{2})(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})"),
]


def upload(directory: str, user: str, dry_run: bool = False) -> None:
    all_files = sorted(_walk_images(Path(directory)))
    if not all_files:
        log.warning("No image files found in %s", directory)
        return

    conn = get_conn()
    try:
        new_files, existing = _classify_files(conn, all_files)
    finally:
        conn.close()

    if not new_files and not existing:
        log.info("No files found in directory.")
        return

    skipped = len(existing)
    log.info(
        "Found %d image files (%d new, %d existing)",
        len(all_files),
        len(new_files),
        skipped,
    )

    if dry_run:
        log.info(
            "[DRY RUN] Would upload %d files, update %d existing",
            len(new_files),
            len(existing),
        )
        return

    uploaded_ids: list[str] = []
    failed: list[str] = []
    updated_ids: list[str] = []
    start_time = int(time.time())
    interrupted = False

    conn = get_conn()
    try:
        if new_files:
            _do_uploads(conn, new_files, uploaded_ids, failed, interrupted, start_time)

        if existing:
            _do_updates(conn, existing, updated_ids, interrupted)

    except KeyboardInterrupt:
        interrupted = True
    finally:
        conn.close()

    all_ids = uploaded_ids + updated_ids
    if all_ids:
        log.info(
            "Refetching metadata for %d photos...",
            len(all_ids),
        )
        fetch_photostream(username=user, after=max(start_time - 1, 0))

    if interrupted:
        remaining = len(new_files) - len(uploaded_ids) - len(failed)
        log.info(
            "Interrupted. Uploaded %d, updated %d (%d pending, %d failed). "
            "Resume by running the same command again.",
            len(uploaded_ids),
            len(updated_ids),
            remaining,
            len(failed),
        )
    else:
        log.info(
            "Complete: %d uploaded, %d updated, %d skipped, %d failed",
            len(uploaded_ids),
            len(updated_ids),
            skipped,
            len(failed),
        )


def _do_uploads(conn, paths, uploaded_ids, failed, interrupted, start_time):
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    )

    with progress:
        task = progress.add_task("Uploading...", total=len(paths))

        for path in paths:
            if interrupted:
                break

            progress.update(task, description=f"Uploading {path.name}")

            kwargs = dict(
                photo_file=str(path),
                title=path.stem,
                is_public=0,
            )

            date_taken = _guess_taken(path)
            if date_taken:
                kwargs["date_taken"] = date_taken

            try:
                photo = flickr_api.upload(**kwargs)
                uploaded_ids.append(photo.id)
                record_upload(conn, str(path), photo.id, path.stat().st_mtime)
                conn.commit()
                progress.update(task, advance=1)
            except Exception as e:
                log.warning("Failed to upload %s: %s", path.name, e)
                failed.append(str(path))
                progress.update(task, advance=1)

            time.sleep(_UPLOAD_DELAY)


def _do_updates(conn, paths, updated_ids, interrupted):
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    )

    lookups = {
        r["local_path"]: r["photo_id"]
        for r in conn.execute("SELECT local_path, photo_id FROM uploads").fetchall()
    }

    with progress:
        task = progress.add_task("Updating dates...", total=len(paths))

        for path in paths:
            if interrupted:
                break

            photo_id = lookups.get(str(path))
            if not photo_id:
                log.debug("No photo_id found for %s, skipping", path.name)
                progress.update(task, advance=1)
                continue

            date_taken = _guess_taken(path)
            if not date_taken:
                progress.update(task, advance=1)
                continue

            try:
                flickr_api.Photo(id=photo_id).setDates(date_taken=date_taken)
                updated_ids.append(photo_id)
                progress.update(task, description=f"Updated {path.name}")
            except Exception as e:
                log.warning("Failed to update date for %s: %s", path.name, e)
                progress.update(task, advance=1)

            time.sleep(_UPLOAD_DELAY)


def _guess_taken(path: Path) -> str | None:
    dt = _exif_date(path)
    if dt:
        return dt

    dt = _filename_date(path.stem)
    if dt:
        return dt

    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


def _exif_date(path: Path) -> str | None:
    try:
        with path.open("rb") as f:
            tags = exifread.process_file(f, details=False, builtin_types=True)
        raw = tags.get("EXIF DateTimeOriginal")
        if raw and isinstance(raw, str):
            parts = raw.replace(":", "-", 2).split(" ")
            if len(parts) == 2:
                return f"{parts[0]} {parts[1]}"
    except Exception:
        log.debug("Could not read EXIF from %s", path.name)
    return None


def _filename_date(stem: str) -> str | None:
    for pattern in _DATE_PATTERNS:
        m = pattern.search(stem)
        if not m:
            continue
        parts = [int(g) for g in m.groups()]

        if len(parts) == 6:
            y, mo, d, h, mi, s = parts
            if len(str(y)) != 4:
                y += 2000
        else:
            continue

        if not (
            1 <= mo <= 12
            and 1 <= d <= 31
            and 0 <= h <= 23
            and 0 <= mi <= 59
            and 0 <= s <= 59
        ):
            continue

        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"

    return None


def _walk_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    return [p for p in directory.rglob("*") if p.suffix.lower() in _IMAGE_EXTENSIONS]


def _classify_files(conn, files: list[Path]):
    new_files = []
    existing = []
    for path in files:
        mtime = path.stat().st_mtime
        if is_uploaded(conn, str(path), mtime):
            existing.append(path)
        else:
            new_files.append(path)
    return new_files, existing
