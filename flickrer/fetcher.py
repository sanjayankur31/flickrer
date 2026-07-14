import logging

import flickr_api
from flickr_api import Walker

from flickrer.db import get_conn, upsert_exif, upsert_photo, init_db

log = logging.getLogger(__name__)


def fetch_photostream(username: str) -> None:
    init_db()
    user = flickr_api.Person.findByUserName(username)

    extras = "url_o,url_l,o_dims"
    total = 0
    exif_total = 0
    errors = 0

    conn = get_conn()
    try:
        for photo in Walker(user.getPhotos, per_page=500, extras=extras):
            photo_id = photo.id

            try:
                photo.getInfo()
            except Exception:
                log.warning("getInfo failed for %s, skipping", photo_id)
                errors += 1
                continue

            sizes = getattr(photo, "sizes", {}) or {}
            original = sizes.get("Original", {})
            large = sizes.get("Large", {}) or sizes.get("Medium 800", {})

            width = _int_or_none(original.get("width"))
            height = _int_or_none(original.get("height"))
            url_original = original.get("source") or getattr(photo, "url_o", None)
            url_large = large.get("source") or getattr(photo, "url_l", None)
            media = getattr(photo, "media", None)
            posted = getattr(photo, "posted", None)
            taken = getattr(photo, "taken", None)
            title = getattr(photo, "title", None)

            upsert_photo(
                conn,
                photo_id=photo_id,
                title=title,
                posted=posted,
                taken=taken,
                width=width,
                height=height,
                media=media,
                url_original=url_original,
                url_large=url_large,
            )

            try:
                exifs = photo.getExif()
                for exif_obj in exifs:
                    raw = exif_obj.raw if isinstance(exif_obj.raw, str | None) else None
                    upsert_exif(conn, photo_id, tag=exif_obj.tag, raw=raw)
                    exif_total += 1
            except Exception:
                log.debug("getExif failed for %s", photo_id)

            total += 1
            if total % 50 == 0:
                conn.commit()
                log.info("Fetched %d photos so far...", total)

        conn.commit()
    finally:
        conn.close()

    log.info(
        "Done. Fetched %d photos, %d EXIF entries, %d errors",
        total,
        exif_total,
        errors,
    )


def _int_or_none(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None
