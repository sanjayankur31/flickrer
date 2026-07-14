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
    files = sorted(_walk_images(Path(directory)))
    if not files:
        log.warning("No image files found in %s", directory)
        return

    log.info("Found %d image files in %s", len(files), directory)

    if dry_run:
        log.info("[DRY RUN] Would upload %d files", len(files))
        return

    uploaded_ids: list[str] = []
    failed: list[str] = []

    start_time = int(time.time())

    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    )

    with progress:
        task = progress.add_task("Uploading...", total=len(files))

        for path in files:
            progress.update(task, description=f"Uploading {path.name}")

            try:
                photo = flickr_api.upload(
                    photo_file=str(path),
                    title=path.stem,
                    is_public=0,
                )
                uploaded_ids.append(photo.id)
                progress.update(task, advance=1)
            except Exception as e:
                log.warning("Failed to upload %s: %s", path.name, e)
                failed.append(str(path))
                progress.update(task, advance=1)

            time.sleep(_UPLOAD_DELAY)

    if uploaded_ids:
        log.info(
            "Refetching metadata for %d uploaded photos...",
            len(uploaded_ids),
        )
        fetch_photostream(username=user, after=start_time - 1)

    log.info(
        "Upload complete: %d uploaded, %d failed",
        len(uploaded_ids),
        len(failed),
    )


def _walk_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    return [p for p in directory.rglob("*") if p.suffix.lower() in _IMAGE_EXTENSIONS]
