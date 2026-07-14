import logging

import typer

from flickrer import auth as auth_mod
from flickrer import analyzer, fetcher, reviewer
from flickrer.db import count_flags, count_photos, get_conn, init_db

app = typer.Typer(
    name="flickrer",
    help="Clean up your Flickr photostream -- find duplicates, memes, and "
    "non-camera uploads.",
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
    after: int | None = typer.Option(
        None,
        "--after",
        help="Only photos uploaded after this Unix timestamp "
        "(e.g. 1700000000 for Nov 14 2023; use `date +%s` to get now)",
    ),
) -> None:
    """Fetch photostream metadata and EXIF into local SQLite database.

    Requires an authenticated session (run 'flickrer auth' first).
    """
    _check_auth()
    init_db()
    try:
        fetcher.fetch_photostream(username=user, limit=limit, after=after)
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
