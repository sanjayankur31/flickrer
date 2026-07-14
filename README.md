# flickrer

Manage your Flickr photostream from the command line. Fetch metadata, find
duplicates and memes, review and delete photos, and upload new ones.

## Installation

Requires Python 3.12+. Untested on non-Linux systems.

```bash
git clone <repo> && cd flickrer
uv pip install -e .
```

## Setup

```bash
# Get an API key at https://www.flickr.com/services/
flickrer auth
```

This prompts for your API key + secret and guides you through OAuth
authorization (requires `delete` permission).

## Commands

```
flickrer auth      Set up API credentials and OAuth token
flickrer fetch     Download photostream metadata + EXIF into SQLite
flickrer analyze   Find duplicates and no-EXIF photos
flickrer review    Walk through flagged photos interactively
flickrer upload    Upload photos (private only, no duplicates)
flickrer status    Show database summary
```

### fetch

```bash
flickrer fetch sanjay_ankur
flickrer fetch sanjay_ankur --limit 50
flickrer fetch sanjay_ankur --after 1700000000 --before 1735689599
```

### analyze

```bash
flickrer analyze
```

Scans for:
- **Duplicates** -- same title + matching dimensions or close upload date
- **No-EXIF** -- photos missing camera EXIF tags (memes, screenshots, downloads)

File sizes are compared via HEAD requests for duplicate candidates only.

### review

```bash
flickrer review           # interactive walkthrough
flickrer review --dry-run # preview without deleting
```

Controls: `o` open in viewer, `d` delete, `s` skip, `q` quit.

### upload

```bash
flickrer upload --user sanjay_ankur ./photos
```

Walks the directory recursively, uploads image files as private photos.
Already-uploaded files (same path + modification time) are skipped.
Metadata is batch-refetched after all uploads complete.

Use `--date-from-mtime` to set the photo's taken date from the file's
modification time (useful for screenshots and downloads without EXIF).

## Development

```bash
uv pip install -e ".[dev]"
ruff format . && ruff check .
uv run pytest tests/ -v

---

This project was built with assistance from [opencode](https://opencode.ai).
It is intended for personal use only.
```
