"""IdleRPG Zero package."""

from .bot import IdleRPGBot, create_bot
from .config import Settings, load_settings
from .version import BOT_NAME, BOT_VERSION, __version__

__all__ = [
    "IdleRPGBot",
    "create_bot",
    "Settings",
    "load_settings",
    "BOT_NAME",
    "BOT_VERSION",
    "__version__",
]
