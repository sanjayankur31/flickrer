from pathlib import Path

from platformdirs import PlatformDirs

_dirs = PlatformDirs("flickrer")
CONFIG_DIR = Path(_dirs.user_config_dir)
DATA_DIR = Path(_dirs.user_data_dir)
AUTH_PATH = CONFIG_DIR / "auth.json"
DB_PATH = DATA_DIR / "flickrer.db"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

VIEWER_CMD = "xdg-open"
