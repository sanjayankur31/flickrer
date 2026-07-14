import json
import logging
import warnings
from pathlib import Path

import flickr_api

from flickrer.config import AUTH_PATH

log = logging.getLogger(__name__)


def _creds_path() -> Path:
    return AUTH_PATH.parent / "flickr_creds.json"


def save_creds(api_key: str, api_secret: str) -> None:
    data = {"api_key": api_key, "api_secret": api_secret}
    _creds_path().write_text(json.dumps(data))


def load_creds() -> tuple[str, str] | None:
    try:
        data = json.loads(_creds_path().read_text())
        return data["api_key"], data["api_secret"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def has_token() -> bool:
    return AUTH_PATH.exists()


SIGNUP_URL = "https://www.flickr.com/services/"


def prompt_for_creds() -> tuple[str, str]:
    log.info("Get your API key here: %s", SIGNUP_URL)
    key = input("API key: ").strip()
    secret = input("API secret: ").strip()
    return key, secret


def authenticate(api_key: str | None = None, api_secret: str | None = None) -> None:
    if api_key is None or api_secret is None:
        api_key, api_secret = prompt_for_creds()

    flickr_api.set_keys(api_key=api_key, api_secret=api_secret)
    save_creds(api_key, api_secret)

    handler = flickr_api.auth.AuthHandler(callback="oob")
    url = handler.get_authorization_url("delete")
    log.info("Visit this URL to authorize:\n%s", url)
    verifier = input("Paste the verifier code: ").strip()
    handler.set_verifier(verifier)
    flickr_api.set_auth_handler(handler)

    token_data = json.dumps(handler.todict())
    AUTH_PATH.write_text(token_data)
    log.info("Authentication saved.")


def ensure_auth() -> bool:
    creds = load_creds()
    if creds is None:
        log.warning("No API credentials found. Run 'flickrer auth' first.")
        return False

    api_key, api_secret = creds
    flickr_api.set_keys(api_key=api_key, api_secret=api_secret)
    flickr_api.set_rate_limit(3600)

    if has_token():
        token_data = json.loads(AUTH_PATH.read_text())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            handler = flickr_api.auth.AuthHandler.fromdict(token_data)
        flickr_api.set_auth_handler(handler)
        return True

    log.warning("No OAuth token found. Run 'flickrer auth' first.")
    return False
