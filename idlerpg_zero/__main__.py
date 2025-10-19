"""Console entrypoint for IdleRPG Zero."""

from __future__ import annotations

import logging

from .bot import create_bot
from .config import load_settings

logging.basicConfig(level=logging.INFO)


def main() -> None:
    settings = load_settings()
    bot = create_bot(settings)
    bot.run(settings.token)


if __name__ == "__main__":
    main()
