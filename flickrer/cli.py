import logging

import typer

from flickrer import auth as auth_mod
from flickrer import analyzer, fetcher, reviewer, uploader
from flickrer.db import count_flags, count_photos, get_conn, init_db
from flickrer.utils import parse_timestamp

app = typer.Typer(
    name="flickrer",
    help="Manage your Flickr photostream -- auth, fetch metadata, "
    "find duplicates and memes, review and delete, upload photos.",
    no_args_is_help=True,
)

_log = logging.getLogger("flickrer")


def _check_auth() -> None:
    if not auth_mod.ensure_auth():
        raise typer.Exit(code=1)


@app.command()
def auth() -> None:
    """Set up Flickr API credentials and OAuth token.

    You need a Flickr API key first. Get one at:

        https://www.flickr.com/services/

    This command will prompt for your API key + secret, then guide
    you through OAuth authorization (requires 'delete' permission).
    """
    try:
        auth_mod.authenticate()
    except Exception as e:
        _log.error("Auth failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def fetch(
    user: str = typer.Argument(
        ...,
        help="Flickr username (not email) to fetch photos from",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-n",
        help="Stop after fetching N photos (for testing)",
    ),
    after: str | None = typer.Option(
        None,
        "--after",
        help="Only photos uploaded after this date. Accepts dateutil-"
        "parsable formats (e.g. '2025-01-15', 'Jan 15 2025', "
        "'2025-01-15 14:30:00') or a Unix timestamp (e.g. 1736899200)",
    ),
    before: str | None = typer.Option(
        None,
        "--before",
        help="Only photos uploaded before this date. Same formats as --after.",
    ),
    exif: bool = typer.Option(
        False,
        "--exif",
        help="Fetch EXIF data for photos in the DB that are missing it "
        "(skip the photo list walk, resumes from where you left off)",
    ),
    refresh_exif: bool = typer.Option(
        False,
        "--refresh-exif",
        help="Re-fetch EXIF for ALL photos, even if already present "
        "(useful if metadata was updated on Flickr)",
    ),
) -> None:
    """Fetch photostream metadata into local SQLite database.

    Without flags: fetches photo list only (fast). Use --exif to
    fill in EXIF data for photos missing it, or --refresh-exif to
    force a full re-fetch of all EXIF data.

    Requires an authenticated session (run 'flickrer auth' first).
    """
    _check_auth()
    init_db()
    try:
        if exif:
            fetcher.fetch_exif_missing()
        elif refresh_exif:
            fetcher.refresh_exif()
        else:
            after_ts = parse_timestamp(after) if after else None
            before_ts = parse_timestamp(before) if before else None
            fetcher.fetch_photostream(
                username=user, limit=limit, after=after_ts, before=before_ts
            )
    except Exception as e:
        _log.error("Fetch failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def analyze() -> None:
    """Scan local database for duplicate photos and no-EXIF uploads.

    Flags are written to the database and reviewed with 'flickrer review'.
    """
    init_db()
    try:
        analyzer.analyze()
    except Exception as e:
        _log.error("Analysis failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def review(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate review actions without deleting from Flickr",
    ),
) -> None:
    """Walk through flagged photos interactively.

    Controls:
        o   Open photo in system image viewer
        d   Delete photo from Flickr
        s   Skip photo
        q   Quit review session

    Use --dry-run to see what would be deleted without making changes.
    """
    _check_auth()
    init_db()
    try:
        reviewer.review(dry_run=dry_run)
    except Exception as e:
        _log.error("Review failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def upload(
    directory: str = typer.Argument(
        ...,
        help="Directory of image files to upload",
    ),
    user: str = typer.Option(
        ...,
        "--user",
        help="Flickr username (required for metadata refresh after upload)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate upload without sending to Flickr",
    ),
) -> None:
    """Upload image files to your Flickr account (private only).

    Automatically determines each photo's taken date: uses EXIF
    DateTimeOriginal if available, otherwise tries to parse the
    filename (e.g. YYYYMMDD_HHMMSS), and falls back to file
    modification time.

    For already-uploaded files (same path + modification time),
    instead of re-uploading, the taken date is corrected on Flickr
    via the API. This allows fixing dates from previous web uploads
    without re-uploading the actual file.

    Metadata is batch-refetched after all uploads complete.
    """
    _check_auth()
    init_db()
    try:
        uploader.upload(directory=directory, user=user, dry_run=dry_run)
    except Exception as e:
        _log.error("Upload failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def status() -> None:
    """Show summary of local database contents."""
    init_db()
    conn = get_conn()
    try:
        photos = count_photos(conn)
        flags = count_flags(conn)
        flag_total = sum(flags.values()) if flags else 0

        _log.info("Photos: %d", photos)
        for ftype, cnt in sorted(flags.items()):
            _log.info("  %s: %d", ftype, cnt)
        if flag_total:
            _log.info(
                "Run 'flickrer review' to review %d flagged photos",
                flag_total,
            )
    finally:
        conn.close()
