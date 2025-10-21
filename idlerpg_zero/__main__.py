"""Console entrypoint for IdleRPG Zero."""

from __future__ import annotations

import logging
import sys
from importlib import import_module
from pathlib import Path

try:
    from .config import load_settings
except ImportError as exc:  # pragma: no cover - script execution fallback
    # When executed as ``python path/to/__main__.py`` the package context is
    # missing, so retry the import with an absolute module path.
    module_name = getattr(exc, "name", None)
    should_retry = module_name in {
        f"{__package__}.config" if __package__ else "idlerpg_zero.config",
        "config",
    } or "attempted relative import" in str(exc).lower()
    if not should_retry:
        raise

    package_root = Path(__file__).resolve().parent
    parent = package_root.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))

    globals()["__package__"] = "idlerpg_zero"

    from idlerpg_zero.config import load_settings  # type: ignore

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _load_bot_factory():
    try:
        module = import_module(".bot", __package__)
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        missing = exc.name
        if missing in {f"{__package__}.bot", "discord"}:
            message = (
                "IdleRPG Zero's Discord bot component could not be imported. "
                "Install the project with its runtime dependencies (including "
                "'discord-py') before running the application."
            )
            log.error(message)
            raise SystemExit(1) from exc
        raise
    return module.create_bot


def main() -> None:
    settings = load_settings()
    create_bot = _load_bot_factory()
    bot = create_bot(settings)
    bot.run(settings.token)


if __name__ == "__main__":
    main()
