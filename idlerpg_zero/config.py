"""Configuration helpers for IdleRPG Zero."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    """Runtime settings loaded from the environment."""

    token: str
    database_path: Path
    activity_text: str = "Leading idle adventures"
    pvp_season_reset: bool = True
    auction_listing_fee: int = 0
    repair_cost_percent: float = 0.2


def load_settings() -> Settings:
    """Load settings from environment variables.

    Raises:
        RuntimeError: If the Discord token is missing.
    """

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing DISCORD_TOKEN environment variable."
            " Create a bot token at https://discord.com/developers/applications"
        )

    db_path = Path(os.getenv("IDLERPG_DB_PATH", "idlerpg.sqlite3")).expanduser()
    activity = os.getenv("IDLERPG_ACTIVITY", "Leading idle adventures")
    seasonal_reset_value = os.getenv("IDLERPG_PVP_SEASON_RESET", "1").strip().lower()
    seasonal_reset = seasonal_reset_value not in {"0", "false", "no", "off"}

    try:
        listing_fee = int(os.getenv("IDLERPG_AUCTION_LISTING_FEE", "5"))
    except ValueError:
        listing_fee = 5

    listing_fee = max(0, listing_fee)

    try:
        repair_percent = float(os.getenv("IDLERPG_REPAIR_COST_PERCENT", "0.25"))
    except ValueError:
        repair_percent = 0.25

    repair_percent = min(1.0, max(0.0, repair_percent))

    return Settings(
        token=token,
        database_path=db_path,
        activity_text=activity,
        pvp_season_reset=seasonal_reset,
        auction_listing_fee=listing_fee,
        repair_cost_percent=repair_percent,
    )
