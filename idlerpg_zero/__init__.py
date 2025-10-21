"""IdleRPG Zero package."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, List

from .config import Settings, load_settings
from .version import BOT_NAME, BOT_VERSION, __version__

if TYPE_CHECKING:  # pragma: no cover - only for static type checkers
    from .bot import IdleRPGBot, create_bot

__all__ = [
    "IdleRPGBot",
    "create_bot",
    "Settings",
    "load_settings",
    "BOT_NAME",
    "BOT_VERSION",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Lazily import heavy modules when their attributes are requested."""

    if name in {"IdleRPGBot", "create_bot"}:
        module = import_module(".bot", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(__all__)
