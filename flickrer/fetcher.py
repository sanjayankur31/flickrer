import logging

import flickr_api
from flickr_api import Walker

from flickrer.db import (
    get_conn,
    init_db,
    iter_photos_missing_exif,
    iter_photos_outdated_exif,
    set_exif_fetched_at,
    upsert_exif,
    upsert_photo,
)

log = logging.getLogger(__name__)


def fetch_photostream(
    username: str,
    limit: int | None = None,
    after: int | None = None,
    before: int | None = None,
) -> None:
    """Fetch photo list metadata only (no EXIF)."""
    init_db()
    user = flickr_api.Person.findByUserName(username)

    extras = "url_o,url_l,o_dims,date_upload,date_taken,last_update"
    total = 0

    kwargs: dict = dict(per_page=500, extras=extras)
    if after is not None:
        kwargs["min_upload_date"] = after
    if before is not None:
        kwargs["max_upload_date"] = before

    walker = Walker(user.getPhotos, **kwargs)
    if limit is not None:
        walker = walker[:limit]

    conn = get_conn()
    try:
        for photo in walker:
            _save_photo(conn, photo)
            total += 1
            if total % 50 == 0:
                conn.commit()
                log.info("Fetched %d photos so far...", total)

        conn.commit()
    finally:
        conn.commit()
        conn.close()

    log.info("Done. Fetched %d photos.", total)


def fetch_exif_missing() -> None:
    """Fetch EXIF only for photos in the DB that are missing it."""
    init_db()
    conn = get_conn()
    try:
        photos = list(iter_photos_missing_exif(conn))
    finally:
        conn.close()

    if not photos:
        log.info("All photos already have EXIF data.")
        return

    log.info("Fetching EXIF for %d photos...", len(photos))
    _fetch_exif_for(photos)


def refresh_exif() -> None:
    """Re-fetch EXIF for photos whose lastupdate is newer than our last fetch."""
    init_db()
    conn = get_conn()
    try:
        photos = list(iter_photos_outdated_exif(conn))
    finally:
        conn.close()

    if not photos:
        log.info("No photos with outdated EXIF data.")
        return

    log.info("Refreshing EXIF for %d outdated photos...", len(photos))
    _fetch_exif_for(photos)


def _fetch_exif_for(photos: list) -> None:
    total = 0
    exif_total = 0

    conn = get_conn()
    try:
        for row in photos:
            photo_id = row["id"]
            try:
                photo = flickr_api.Photo(id=photo_id)
                exifs = photo.getExif()
                for exif_obj in exifs:
                    raw = exif_obj.raw if isinstance(exif_obj.raw, str | None) else None
                    upsert_exif(conn, photo_id, tag=exif_obj.tag, raw=raw)
                    exif_total += 1
                set_exif_fetched_at(conn, photo_id)
                total += 1
            except Exception:
                log.debug("getExif failed for %s", photo_id)

            if total % 50 == 0:
                conn.commit()
                log.info("Fetched EXIF for %d photos so far...", total)

        conn.commit()
    finally:
        conn.commit()
        conn.close()

    log.info("Done. Fetched EXIF for %d photos, %d EXIF entries.", total, exif_total)


def _save_photo(conn, photo) -> None:
    _d = photo.__dict__

    upsert_photo(
        conn,
        photo_id=photo.id,
        title=_d.get("title"),
        posted=_int_or_none(_d.get("dateupload")),
        taken=_d.get("datetaken"),
        width=_int_or_none(_d.get("width_o") or _d.get("width_l") or _d.get("o_width")),
        height=_int_or_none(
            _d.get("height_o") or _d.get("height_l") or _d.get("o_height")
        ),
        media=_d.get("media"),
        url_original=_d.get("url_o"),
        url_large=_d.get("url_l"),
        lastupdate=_int_or_none(_d.get("lastupdate")),
    )


def _int_or_none(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None
