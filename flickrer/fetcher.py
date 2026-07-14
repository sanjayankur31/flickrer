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
    # FlickrObject.__getattr__ has a lazy-load "convenience": accessing
    # any attribute not yet in __dict__ calls photo.load() = getInfo() =
    # 1 API call. In a batch loop this silently triggers 1 extra API
    # call per photo. Mark loaded=True to disable this behavior --
    # all list-response data is already in __dict__ from the Walker.
    photo.__dict__["loaded"] = True

    upsert_photo(
        conn,
        photo_id=photo.id,
        title=getattr(photo, "title", None),
        posted=_int_or_none(getattr(photo, "dateupload", None)),
        taken=getattr(photo, "datetaken", None),
        width=_int_or_none(
            getattr(photo, "width_o", None)
            or getattr(photo, "width_l", None)
            or getattr(photo, "o_width", None)
        ),
        height=_int_or_none(
            getattr(photo, "height_o", None)
            or getattr(photo, "height_l", None)
            or getattr(photo, "o_height", None)
        ),
        media=getattr(photo, "media", None),
        url_original=getattr(photo, "url_o", None),
        url_large=getattr(photo, "url_l", None),
        lastupdate=_int_or_none(getattr(photo, "lastupdate", None)),
    )


def _int_or_none(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None
