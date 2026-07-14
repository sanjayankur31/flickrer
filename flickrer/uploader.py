import logging
import time
from pathlib import Path

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


def upload(directory: str, user: str, dry_run: bool = False) -> None:
    all_files = sorted(_walk_images(Path(directory)))
    if not all_files:
        log.warning("No image files found in %s", directory)
        return

    conn = get_conn()
    try:
        to_upload = _filter_pending(conn, all_files)
    finally:
        conn.close()

    if not to_upload:
        log.info("All files already uploaded (no new or modified files).")
        return

    skipped = len(all_files) - len(to_upload)
    log.info(
        "Found %d image files (%d new, %d already uploaded)",
        len(all_files),
        len(to_upload),
        skipped,
    )

    if dry_run:
        log.info("[DRY RUN] Would upload %d files", len(to_upload))
        return

    uploaded_ids: list[str] = []
    failed: list[str] = []
    start_time = int(time.time())
    interrupted = False

    conn = get_conn()
    try:
        progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        )

        with progress:
            task = progress.add_task("Uploading...", total=len(to_upload))

            for path in to_upload:
                progress.update(task, description=f"Uploading {path.name}")

                try:
                    photo = flickr_api.upload(
                        photo_file=str(path),
                        title=path.stem,
                        is_public=0,
                    )
                    uploaded_ids.append(photo.id)
                    record_upload(conn, str(path), photo.id, path.stat().st_mtime)
                    conn.commit()
                    progress.update(task, advance=1)
                except KeyboardInterrupt:
                    interrupted = True
                    break
                except Exception as e:
                    log.warning("Failed to upload %s: %s", path.name, e)
                    failed.append(str(path))
                    progress.update(task, advance=1)

                if not interrupted:
                    time.sleep(_UPLOAD_DELAY)
    finally:
        conn.close()

    if uploaded_ids:
        log.info(
            "Refetching metadata for %d uploaded photos...",
            len(uploaded_ids),
        )
        fetch_photostream(username=user, after=max(start_time - 1, 0))

    if interrupted:
        log.info(
            "Interrupted. Uploaded %d so far (%d pending, %d failed). "
            "Resume by running the same command again.",
            len(uploaded_ids),
            len(to_upload) - len(uploaded_ids) - len(failed),
            len(failed),
        )
    else:
        log.info(
            "Upload complete: %d uploaded, %d skipped, %d failed",
            len(uploaded_ids),
            skipped,
            len(failed),
        )


def _walk_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    return [p for p in directory.rglob("*") if p.suffix.lower() in _IMAGE_EXTENSIONS]


def _filter_pending(conn, files: list[Path]) -> list[Path]:
    pending = []
    for path in files:
        mtime = path.stat().st_mtime
        if not is_uploaded(conn, str(path), mtime):
            pending.append(path)
    return pending
