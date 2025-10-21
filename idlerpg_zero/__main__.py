"""Console entrypoint for IdleRPG Zero."""

from __future__ import annotations

import logging
from importlib import import_module

from .config import load_settings

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
