"""SQLite database helpers for IdleRPG Zero."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union, cast

import aiosqlite

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
ANNIVERSARY_ITEM_NAME = "Anniversary Charm"
ACHIEVEMENT_FIRST_MARRIAGE = "first_marriage"
ACHIEVEMENT_LEVEL_50 = "level_50"
ACHIEVEMENT_QUEST_100 = "quest_100"
ACHIEVEMENT_RAID_10 = "raid_10"
LEVEL_MILESTONE = 50
QUEST_MILESTONE = 100
RAID_MILESTONE = 10
GUILD_ROLE_MASTER = "master"
GUILD_ROLE_OFFICER = "officer"
GUILD_ROLE_MEMBER = "member"
GUILD_ROLES = {GUILD_ROLE_MASTER, GUILD_ROLE_OFFICER, GUILD_ROLE_MEMBER}


_UNSET = object()


from .quests import QuestProgress


def guild_level_for_xp(xp: int) -> int:
    if xp <= 0:
        return 1
    return max(1, xp // 1000 + 1)


@dataclass(slots=True)
class ClassInfo:
    """Represents an available player class."""

    id: int
    name: str
    description: str
    base_hp: int
    base_attack: int
    base_defense: int
    ability_name: str
    ability_description: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "ClassInfo":
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            base_hp=row["base_hp"],
            base_attack=row["base_attack"],
            base_defense=row["base_defense"],
            ability_name=row["ability_name"],
            ability_description=row["ability_description"],
        )


@dataclass(slots=True)
class Player:
    """Represents a player's persistent state."""

    user_id: int
    level: int = 1
    xp: int = 0
    gold: int = 0
    hp: int = 100
    max_hp: int = 100
    energy: int = 100
    attack: int = 0
    defense: int = 0
    class_id: Optional[int] = None
    equipped_weapon_id: Optional[int] = None
    equipped_armor_id: Optional[int] = None
    attack_buff_percent: int = 0
    attack_buff_battles: int = 0
    defense_buff_percent: int = 0
    defense_buff_battles: int = 0
    quests_completed: int = 0
    raids_completed: int = 0
    pvp_wins: int = 0
    pvp_losses: int = 0
    pvp_season_wins: int = 0
    pvp_season_losses: int = 0
    equipped_title_id: Optional[int] = None
    last_quest_at: Optional[datetime] = None
    last_raid_at: Optional[datetime] = None
    last_work_at: Optional[datetime] = None
    last_rest_at: Optional[datetime] = None
    last_proposal_at: Optional[datetime] = None
    active_quest_id: Optional[str] = None
    active_quest_complete_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Player":
        keys = row.keys()
        return cls(
            user_id=row["user_id"],
            level=row["level"],
            xp=row["xp"],
            gold=row["gold"],
            hp=row["hp"],
            max_hp=row["max_hp"],
            energy=row["energy"],
            attack=row["attack"],
            defense=row["defense"],
            class_id=row["class_id"],
            equipped_weapon_id=row["equipped_weapon_id"],
            equipped_armor_id=row["equipped_armor_id"],
            attack_buff_percent=row["attack_buff_percent"],
            attack_buff_battles=row["attack_buff_battles"],
            defense_buff_percent=row["defense_buff_percent"],
            defense_buff_battles=row["defense_buff_battles"],
            quests_completed=row["quests_completed"] if "quests_completed" in keys else 0,
            raids_completed=row["raids_completed"] if "raids_completed" in keys else 0,
            pvp_wins=row["pvp_wins"] if "pvp_wins" in keys else 0,
            pvp_losses=row["pvp_losses"] if "pvp_losses" in keys else 0,
            pvp_season_wins=row["pvp_season_wins"] if "pvp_season_wins" in keys else 0,
            pvp_season_losses=row["pvp_season_losses"] if "pvp_season_losses" in keys else 0,
            equipped_title_id=row["equipped_title_id"] if "equipped_title_id" in keys else None,
            last_quest_at=_parse_time(row["last_quest_at"]),
            last_raid_at=_parse_time(row["last_raid_at"]) if "last_raid_at" in keys else None,
            last_work_at=_parse_time(row["last_work_at"]),
            last_rest_at=_parse_time(row["last_rest_at"]),
            last_proposal_at=_parse_time(row["last_proposal_at"]) if "last_proposal_at" in keys else None,
            active_quest_id=row["active_quest_id"] if "active_quest_id" in keys else None,
            active_quest_complete_at=_parse_time(row["active_quest_complete_at"]) if "active_quest_complete_at" in keys else None,
        )

    def as_db_tuple(self) -> Sequence[object]:
        return (
            self.level,
            self.xp,
            self.gold,
            self.hp,
            self.max_hp,
            self.energy,
            self.attack,
            self.defense,
            self.class_id,
            self.equipped_weapon_id,
            self.equipped_armor_id,
            self.attack_buff_percent,
            self.attack_buff_battles,
            self.defense_buff_percent,
            self.defense_buff_battles,
            self.quests_completed,
            self.raids_completed,
            self.equipped_title_id,
            _format_time(self.last_quest_at),
            _format_time(self.last_raid_at),
            _format_time(self.last_work_at),
            _format_time(self.last_rest_at),
            _format_time(self.last_proposal_at),
            self.active_quest_id,
            _format_time(self.active_quest_complete_at),
            self.user_id,
        )


@dataclass(slots=True)
class PlayerProfile:
    """Customization settings for a player's profile."""

    user_id: int
    avatar_url: Optional[str]
    banner_url: Optional[str]
    updated_at: Optional[datetime]

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "PlayerProfile":
        return cls(
            user_id=row["user_id"],
            avatar_url=row["avatar_url"],
            banner_url=row["banner_url"],
            updated_at=_parse_time(row["updated_at"]),
        )


@dataclass(slots=True)
class Weapon:
    id: int
    name: str
    damage: int
    durability: int
    price: int
    class_restriction: Optional[str]
    rarity: str
    is_generic: bool
    event_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Weapon":
        return cls(
            id=row["id"],
            name=row["name"],
            damage=row["damage"],
            durability=row["durability"],
            price=row["price"],
            class_restriction=row["class_restriction"],
            rarity=row["rarity"],
            is_generic=bool(row["is_generic"]),
            event_id=row["event_id"] if "event_id" in row.keys() else None,
        )


@dataclass(slots=True)
class Armor:
    id: int
    name: str
    defense_boost: int
    price: int
    rarity: str
    is_generic: bool

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Armor":
        return cls(
            id=row["id"],
            name=row["name"],
            defense_boost=row["defense_boost"],
            price=row["price"],
            rarity=row["rarity"],
            is_generic=bool(row["is_generic"]),
        )


@dataclass(slots=True)
class Item:
    id: int
    name: str
    effect_type: str
    effect_value: int
    price: int
    rarity: str
    effect_duration: int
    is_generic: bool
    event_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Item":
        return cls(
            id=row["id"],
            name=row["name"],
            effect_type=row["effect_type"],
            effect_value=row["effect_value"],
            price=row["price"],
            rarity=row["rarity"],
            effect_duration=row["effect_duration"],
            is_generic=bool(row["is_generic"]),
            event_id=row["event_id"] if "event_id" in row.keys() else None,
        )


@dataclass(slots=True)
class ShopRotationEntry:
    """Represents an item featured in the global shop rotation."""

    id: int
    item_type: str
    item_id: int
    rarity: str
    featured_at: datetime
    expires_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "ShopRotationEntry":
        return cls(
            id=row["id"],
            item_type=row["item_type"],
            item_id=row["item_id"],
            rarity=row["rarity"],
            featured_at=_parse_time(row["featured_at"]) or datetime.now(timezone.utc),
            expires_at=_parse_time(row["expires_at"]) or datetime.now(timezone.utc),
        )


@dataclass(slots=True)
class Achievement:
    id: int
    code: str
    name: str
    description: str
    title: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Achievement":
        return cls(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            description=row["description"],
            title=row["title"],
        )


@dataclass(slots=True)
class PlayerAchievementRecord:
    achievement: Achievement
    earned_at: datetime


@dataclass(slots=True)
class InventoryEntry:
    id: int
    user_id: int
    item_type: str
    item_id: int
    quantity: int
    current_durability: Optional[int]
    is_equipped: bool
    expires_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "InventoryEntry":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            item_type=row["item_type"],
            item_id=row["item_id"],
            quantity=row["quantity"],
            current_durability=row["current_durability"],
            is_equipped=bool(row["is_equipped"]),
            expires_at=_parse_time(row["expires_at"]) if "expires_at" in row.keys() else None,
        )


@dataclass(slots=True)
class AuctionListing:
    """Represents an item listed on the auction house."""

    id: int
    seller_id: int
    item_type: str
    item_id: int
    quantity: int
    current_durability: Optional[int]
    price: int
    created_at: datetime
    expires_at: datetime
    item_expires_at: Optional[datetime]

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "AuctionListing":
        return cls(
            id=row["id"],
            seller_id=row["seller_id"],
            item_type=row["item_type"],
            item_id=row["item_id"],
            quantity=row["quantity"],
            current_durability=row["current_durability"],
            price=row["price"],
            created_at=_parse_time(row["created_at"]) or datetime.now(timezone.utc),
            expires_at=_parse_time(row["expires_at"]) or datetime.now(timezone.utc),
            item_expires_at=_parse_time(row["item_expires_at"]) if "item_expires_at" in row.keys() else None,
        )


@dataclass(slots=True)
class ItemUseResult:
    item: Item
    healed: int = 0
    energy_restored: int = 0
    attack_buff: Optional[Tuple[int, int]] = None
    defense_buff: Optional[Tuple[int, int]] = None
    quantity_remaining: int = 0


@dataclass(slots=True)
class DurabilityChange:
    weapon: Weapon
    durability: int
    broken: bool


@dataclass(slots=True)
class Marriage:
    id: int
    player1_id: int
    player2_id: int
    date_married: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Marriage":
        return cls(
            id=row["id"],
            player1_id=row["player1_id"],
            player2_id=row["player2_id"],
            date_married=_parse_time(row["date_married"]),
        )

    def partner_id(self, user_id: int) -> Optional[int]:
        if user_id == self.player1_id:
            return self.player2_id
        if user_id == self.player2_id:
            return self.player1_id
        return None


@dataclass(slots=True)
class MarriageProposal:
    id: int
    proposer_id: int
    proposee_id: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "MarriageProposal":
        return cls(
            id=row["id"],
            proposer_id=row["proposer_id"],
            proposee_id=row["proposee_id"],
            created_at=_parse_time(row["created_at"]),
        )


@dataclass(slots=True)
class DivorceRequest:
    id: int
    marriage_id: int
    initiator_id: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "DivorceRequest":
        return cls(
            id=row["id"],
            marriage_id=row["marriage_id"],
            initiator_id=row["initiator_id"],
            created_at=_parse_time(row["created_at"]),
        )


@dataclass(slots=True)
class Guild:
    id: int
    name: str
    description: str
    xp: int
    level: int
    gold: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Guild":
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            xp=row["xp"],
            level=row["level"],
            gold=row["gold"],
            created_at=_parse_time(row["created_at"]),
        )


@dataclass(slots=True)
class GuildMember:
    player_id: int
    guild_id: int
    role: str
    joined_at: datetime
    last_quest_at: Optional[datetime]
    last_war_at: Optional[datetime]

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "GuildMember":
        return cls(
            player_id=row["player_id"],
            guild_id=row["guild_id"],
            role=row["role"],
            joined_at=_parse_time(row["joined_at"]),
            last_quest_at=_parse_time(row["last_quest_at"]),
            last_war_at=_parse_time(row["last_war_at"]),
        )


@dataclass(slots=True)
class GuildInvitation:
    guild_id: int
    player_id: int
    inviter_id: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "GuildInvitation":
        return cls(
            guild_id=row["guild_id"],
            player_id=row["player_id"],
            inviter_id=row["inviter_id"],
            created_at=_parse_time(row["created_at"]),
        )


@dataclass(slots=True)
class Material:
    id: int
    name: str
    rarity: str
    tier: int
    description: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Material":
        return cls(
            id=row["id"],
            name=row["name"],
            rarity=row["rarity"],
            tier=row["tier"],
            description=row["description"],
        )


@dataclass(slots=True)
class Event:
    """Represents a limited-time seasonal event."""

    id: int
    name: str
    description: str
    start_date: datetime
    end_date: datetime
    special_loot: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Event":
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            start_date=_parse_time(row["start_date"]) or datetime.now(timezone.utc),
            end_date=_parse_time(row["end_date"]) or datetime.now(timezone.utc),
            special_loot=row["special_loot"],
        )

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.start_date <= now <= self.end_date


@dataclass(slots=True)
class EventParticipant:
    """Tracks players who have joined an event."""

    event_id: int
    user_id: int
    joined_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "EventParticipant":
        return cls(
            event_id=row["event_id"],
            user_id=row["user_id"],
            joined_at=_parse_time(row["joined_at"]) or datetime.now(timezone.utc),
        )


@dataclass(slots=True)
class RaidBoss:
    """Template information for large scale raid bosses."""

    id: int
    name: str
    description: str
    max_hp: int
    attack: int
    xp_reward: int
    gold_reward: int
    rare_loot_chance: float
    rare_loot_rarity: Optional[str]
    item_reward_rarity: Optional[str]
    material_reward_rarity: Optional[str]
    event_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "RaidBoss":
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            max_hp=row["max_hp"],
            attack=row["attack"],
            xp_reward=row["xp_reward"],
            gold_reward=row["gold_reward"],
            rare_loot_chance=row["rare_loot_chance"],
            rare_loot_rarity=row["rare_loot_rarity"],
            item_reward_rarity=row["item_reward_rarity"],
            material_reward_rarity=row["material_reward_rarity"],
            event_id=row["event_id"] if "event_id" in row.keys() else None,
        )


@dataclass(slots=True)
class RaidInstance:
    """Represents an active or completed raid encounter."""

    id: int
    boss_id: int
    created_by: int
    current_hp: int
    status: str
    total_damage: int
    created_at: datetime
    completed_at: Optional[datetime]
    event_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "RaidInstance":
        return cls(
            id=row["id"],
            boss_id=row["boss_id"],
            created_by=row["created_by"],
            current_hp=row["current_hp"],
            status=row["status"],
            total_damage=row["total_damage"],
            created_at=_parse_time(row["created_at"]) or datetime.now(timezone.utc),
            completed_at=_parse_time(row["completed_at"]),
            event_id=row["event_id"] if "event_id" in row.keys() else None,
        )

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(slots=True)
class RaidParticipant:
    """Tracks total raid contribution for a player."""

    raid_id: int
    user_id: int
    damage_dealt: int
    last_attack_at: Optional[datetime]

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "RaidParticipant":
        return cls(
            raid_id=row["raid_id"],
            user_id=row["user_id"],
            damage_dealt=row["damage_dealt"],
            last_attack_at=_parse_time(row["last_attack_at"]),
        )


InventoryPayload = Union[Weapon, Armor, Item, Material]


class Database:
    """High level SQLite wrapper used by the bot."""

    def __init__(self, path: Path):
        self.path = path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._connection is not None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._run_migrations()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _run_migrations(self) -> None:
        assert self._connection is not None
        await self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                title TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                base_hp INTEGER NOT NULL,
                base_attack INTEGER NOT NULL,
                base_defense INTEGER NOT NULL,
                ability_name TEXT NOT NULL,
                ability_description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 1,
                xp INTEGER NOT NULL DEFAULT 0,
                gold INTEGER NOT NULL DEFAULT 0,
                hp INTEGER NOT NULL DEFAULT 100,
                max_hp INTEGER NOT NULL DEFAULT 100,
                energy INTEGER NOT NULL DEFAULT 100,
                attack INTEGER NOT NULL DEFAULT 0,
                defense INTEGER NOT NULL DEFAULT 0,
                class_id INTEGER REFERENCES classes(id),
                equipped_weapon_id INTEGER REFERENCES player_inventory(id),
                equipped_armor_id INTEGER REFERENCES player_inventory(id),
                attack_buff_percent INTEGER NOT NULL DEFAULT 0,
                attack_buff_battles INTEGER NOT NULL DEFAULT 0,
                defense_buff_percent INTEGER NOT NULL DEFAULT 0,
                defense_buff_battles INTEGER NOT NULL DEFAULT 0,
                quests_completed INTEGER NOT NULL DEFAULT 0,
                raids_completed INTEGER NOT NULL DEFAULT 0,
                pvp_wins INTEGER NOT NULL DEFAULT 0,
                pvp_losses INTEGER NOT NULL DEFAULT 0,
                pvp_season_wins INTEGER NOT NULL DEFAULT 0,
                pvp_season_losses INTEGER NOT NULL DEFAULT 0,
                equipped_title_id INTEGER REFERENCES achievements(id),
                last_quest_at TEXT,
                last_raid_at TEXT,
                last_work_at TEXT,
                last_rest_at TEXT,
                last_proposal_at TEXT,
                active_quest_id TEXT,
                active_quest_complete_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS player_achievements (
                user_id INTEGER NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
                earned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                PRIMARY KEY(user_id, achievement_id)
            );

            CREATE TABLE IF NOT EXISTS player_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
                avatar_url TEXT,
                banner_url TEXT,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                special_loot TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weapons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                damage INTEGER NOT NULL,
                durability INTEGER NOT NULL,
                price INTEGER NOT NULL,
                class_restriction TEXT,
                rarity TEXT NOT NULL DEFAULT 'common',
                is_generic INTEGER NOT NULL DEFAULT 1,
                event_id INTEGER REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS armor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                defense_boost INTEGER NOT NULL,
                price INTEGER NOT NULL,
                rarity TEXT NOT NULL DEFAULT 'common',
                is_generic INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                rarity TEXT NOT NULL DEFAULT 'common',
                tier INTEGER NOT NULL DEFAULT 1,
                description TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                effect_type TEXT NOT NULL,
                effect_value INTEGER NOT NULL,
                price INTEGER NOT NULL,
                rarity TEXT NOT NULL DEFAULT 'common',
                effect_duration INTEGER NOT NULL DEFAULT 0,
                is_generic INTEGER NOT NULL DEFAULT 1,
                event_id INTEGER REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS shop_rotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL CHECK(item_type IN ('weapon','armor','item')),
                item_id INTEGER NOT NULL,
                rarity TEXT NOT NULL DEFAULT 'common',
                featured_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                expires_at TEXT NOT NULL,
                UNIQUE(item_type, item_id)
            );

            CREATE TABLE IF NOT EXISTS player_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL CHECK(item_type IN ('weapon','armor','item','material')),
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                current_durability INTEGER,
                is_equipped INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                expires_at TEXT,
                FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                item_type TEXT NOT NULL CHECK(item_type IN ('weapon','armor','item','material')),
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                current_durability INTEGER,
                price INTEGER NOT NULL CHECK(price > 0),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                expires_at TEXT NOT NULL,
                item_expires_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_listings_expires_at ON listings(expires_at);

            CREATE TABLE IF NOT EXISTS marriage_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposer_id INTEGER NOT NULL,
                proposee_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(proposer_id),
                UNIQUE(proposee_id),
                FOREIGN KEY(proposer_id) REFERENCES players(user_id) ON DELETE CASCADE,
                FOREIGN KEY(proposee_id) REFERENCES players(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS marriages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER NOT NULL,
                date_married TEXT NOT NULL,
                UNIQUE(player1_id),
                UNIQUE(player2_id),
                FOREIGN KEY(player1_id) REFERENCES players(user_id) ON DELETE CASCADE,
                FOREIGN KEY(player2_id) REFERENCES players(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS marriage_divorce_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marriage_id INTEGER NOT NULL UNIQUE,
                initiator_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                FOREIGN KEY(marriage_id) REFERENCES marriages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS guilds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                gold INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS guild_members (
                player_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('master','officer','member')),
                joined_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                last_quest_at TEXT,
                last_war_at TEXT,
                FOREIGN KEY(player_id) REFERENCES players(user_id) ON DELETE CASCADE,
                FOREIGN KEY(guild_id) REFERENCES guilds(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS guild_invitations (
                guild_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                inviter_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                PRIMARY KEY(guild_id, player_id),
                FOREIGN KEY(guild_id) REFERENCES guilds(id) ON DELETE CASCADE,
                FOREIGN KEY(player_id) REFERENCES players(user_id) ON DELETE CASCADE,
                FOREIGN KEY(inviter_id) REFERENCES players(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS raid_bosses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                max_hp INTEGER NOT NULL,
                attack INTEGER NOT NULL,
                xp_reward INTEGER NOT NULL,
                gold_reward INTEGER NOT NULL,
                rare_loot_chance REAL NOT NULL DEFAULT 0,
                rare_loot_rarity TEXT,
                item_reward_rarity TEXT,
                material_reward_rarity TEXT,
                event_id INTEGER REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS raid_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                boss_id INTEGER NOT NULL REFERENCES raid_bosses(id),
                created_by INTEGER NOT NULL REFERENCES players(user_id),
                current_hp INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed')),
                total_damage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                completed_at TEXT,
                event_id INTEGER REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS raid_participants (
                raid_id INTEGER NOT NULL REFERENCES raid_instances(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                damage_dealt INTEGER NOT NULL DEFAULT 0,
                last_attack_at TEXT,
                PRIMARY KEY(raid_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS event_participants (
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                joined_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                PRIMARY KEY(event_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_raid_instances_status ON raid_instances(status);
            CREATE INDEX IF NOT EXISTS idx_raid_participants_damage ON raid_participants(raid_id, damage_dealt DESC);
            CREATE INDEX IF NOT EXISTS idx_shop_rotation_expires_at ON shop_rotation(expires_at);
            """
        )

        await self._ensure_player_columns()
        await self._ensure_inventory_supports_materials()
        await self._ensure_event_columns()
        await self._ensure_player_quest_progress_table()
        await self._seed_default_achievements()
        await self._seed_default_classes()
        await self._seed_default_materials()
        await self._seed_default_shop()
        await self._seed_default_events()
        await self._seed_default_raid_bosses()
        await self._connection.commit()

    async def _ensure_player_columns(self) -> None:
        assert self._connection is not None
        cursor = await self._connection.execute("PRAGMA table_info(players)")
        columns = {row[1] for row in await cursor.fetchall()}
        await cursor.close()

        column_statements = {
            "attack": "ALTER TABLE players ADD COLUMN attack INTEGER NOT NULL DEFAULT 0",
            "defense": "ALTER TABLE players ADD COLUMN defense INTEGER NOT NULL DEFAULT 0",
            "class_id": "ALTER TABLE players ADD COLUMN class_id INTEGER REFERENCES classes(id)",
            "equipped_weapon_id": "ALTER TABLE players ADD COLUMN equipped_weapon_id INTEGER REFERENCES player_inventory(id)",
            "equipped_armor_id": "ALTER TABLE players ADD COLUMN equipped_armor_id INTEGER REFERENCES player_inventory(id)",
            "attack_buff_percent": "ALTER TABLE players ADD COLUMN attack_buff_percent INTEGER NOT NULL DEFAULT 0",
            "attack_buff_battles": "ALTER TABLE players ADD COLUMN attack_buff_battles INTEGER NOT NULL DEFAULT 0",
            "defense_buff_percent": "ALTER TABLE players ADD COLUMN defense_buff_percent INTEGER NOT NULL DEFAULT 0",
            "defense_buff_battles": "ALTER TABLE players ADD COLUMN defense_buff_battles INTEGER NOT NULL DEFAULT 0",
            "last_raid_at": "ALTER TABLE players ADD COLUMN last_raid_at TEXT",
            "last_proposal_at": "ALTER TABLE players ADD COLUMN last_proposal_at TEXT",
            "quests_completed": "ALTER TABLE players ADD COLUMN quests_completed INTEGER NOT NULL DEFAULT 0",
            "raids_completed": "ALTER TABLE players ADD COLUMN raids_completed INTEGER NOT NULL DEFAULT 0",
            "pvp_wins": "ALTER TABLE players ADD COLUMN pvp_wins INTEGER NOT NULL DEFAULT 0",
            "pvp_losses": "ALTER TABLE players ADD COLUMN pvp_losses INTEGER NOT NULL DEFAULT 0",
            "pvp_season_wins": "ALTER TABLE players ADD COLUMN pvp_season_wins INTEGER NOT NULL DEFAULT 0",
            "pvp_season_losses": "ALTER TABLE players ADD COLUMN pvp_season_losses INTEGER NOT NULL DEFAULT 0",
            "equipped_title_id": "ALTER TABLE players ADD COLUMN equipped_title_id INTEGER REFERENCES achievements(id)",
            "active_quest_id": "ALTER TABLE players ADD COLUMN active_quest_id TEXT",
            "active_quest_complete_at": "ALTER TABLE players ADD COLUMN active_quest_complete_at TEXT",
        }

        for column, statement in column_statements.items():
            if column not in columns:
                await self._connection.execute(statement)

    async def _ensure_inventory_supports_materials(self) -> None:
        assert self._connection is not None
        cursor = await self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'player_inventory'"
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return
        sql_definition = row["sql"]
        if sql_definition and "'material'" in sql_definition:
            return

        cursor = await self._connection.execute("PRAGMA table_info(player_inventory)")
        existing_columns = [column_row[1] for column_row in await cursor.fetchall()]
        await cursor.close()

        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS player_inventory_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL CHECK(item_type IN ('weapon','armor','item','material')),
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                current_durability INTEGER,
                is_equipped INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                expires_at TEXT,
                FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
            )
            """
        )
        select_clause = (
            "SELECT id, user_id, item_type, item_id, quantity, current_durability, "
            "is_equipped, created_at"
        )
        if "expires_at" in existing_columns:
            select_clause += ", expires_at"
        else:
            select_clause += ", NULL AS expires_at"
        select_clause += " FROM player_inventory"
        await self._connection.execute(
            f"""
            INSERT INTO player_inventory_new (
                id, user_id, item_type, item_id, quantity, current_durability, is_equipped, created_at, expires_at
            )
            {select_clause}
            """
        )
        await self._connection.execute("DROP TABLE player_inventory")
        await self._connection.execute(
            "ALTER TABLE player_inventory_new RENAME TO player_inventory"
        )

    async def _ensure_event_columns(self) -> None:
        assert self._connection is not None

        async def ensure(table: str, column: str, statement: str) -> None:
            cursor = await self._connection.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in await cursor.fetchall()}
            await cursor.close()
            if column not in columns:
                await self._connection.execute(statement)

        await ensure(
            "player_inventory",
            "expires_at",
            "ALTER TABLE player_inventory ADD COLUMN expires_at TEXT",
        )
        await ensure(
            "weapons",
            "event_id",
            "ALTER TABLE weapons ADD COLUMN event_id INTEGER REFERENCES events(id)",
        )
        await ensure(
            "items",
            "event_id",
            "ALTER TABLE items ADD COLUMN event_id INTEGER REFERENCES events(id)",
        )
        await ensure(
            "raid_bosses",
            "event_id",
            "ALTER TABLE raid_bosses ADD COLUMN event_id INTEGER REFERENCES events(id)",
        )
        await ensure(
            "raid_instances",
            "event_id",
            "ALTER TABLE raid_instances ADD COLUMN event_id INTEGER REFERENCES events(id)",
        )

    async def _ensure_player_quest_progress_table(self) -> None:
        assert self._connection is not None
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS player_quest_progress (
                user_id INTEGER NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                quest_id TEXT NOT NULL,
                last_completed_at TEXT,
                completions INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, quest_id)
            )
            """
        )

    async def _seed_default_achievements(self) -> None:
        assert self._connection is not None
        achievements = [
            (
                ACHIEVEMENT_FIRST_MARRIAGE,
                "Bonded Hearts",
                "Get married for the first time.",
                "The Beloved",
            ),
            (
                ACHIEVEMENT_LEVEL_50,
                "Seasoned Hero",
                "Reach level 50.",
                "Veteran Adventurer",
            ),
            (
                ACHIEVEMENT_QUEST_100,
                "Quest Centurion",
                "Complete 100 quests.",
                "Questing Legend",
            ),
            (
                ACHIEVEMENT_RAID_10,
                "Raid Conqueror",
                "Help defeat 10 raids.",
                "Raidbreaker",
            ),
        ]
        await self._connection.executemany(
            """
            INSERT INTO achievements (code, name, description, title)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                title = excluded.title
            """,
            achievements,
        )

    async def _seed_default_classes(self) -> None:
        assert self._connection is not None
        classes = [
            (
                1,
                "Warrior",
                "Strong melee fighter.",
                150,
                20,
                15,
                "Berserk Strike",
                "Deals double damage once per battle",
            ),
            (
                2,
                "Mage",
                "Master of elemental spells.",
                100,
                30,
                5,
                "Arcane Burst",
                "AOE damage",
            ),
            (
                3,
                "Ranger",
                "Balanced ranged attacker.",
                120,
                18,
                10,
                "Piercing Arrow",
                "Ignores defense",
            ),
            (
                4,
                "Rogue",
                "Agile and deadly.",
                110,
                25,
                8,
                "Shadowstep",
                "Guaranteed first strike",
            ),
            (
                5,
                "Paladin",
                "Defensive support.",
                140,
                15,
                20,
                "Holy Shield",
                "Reduces damage by 50% for 2 turns",
            ),
        ]

        await self._connection.executemany(
            """
            INSERT INTO classes (
                id, name, description, base_hp, base_attack, base_defense,
                ability_name, ability_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                base_hp = excluded.base_hp,
                base_attack = excluded.base_attack,
                base_defense = excluded.base_defense,
                ability_name = excluded.ability_name,
                ability_description = excluded.ability_description
            """,
            classes,
        )

    async def _seed_default_materials(self) -> None:
        assert self._connection is not None
        materials = [
            ("Iron Ore", "common", 1, "Sturdy ore used for basic forging."),
            ("Enchanted Bark", "uncommon", 2, "Mystic wood favored by skilled fletchers."),
            ("Runed Crystal", "rare", 3, "A crystal etched with dormant runes."),
            ("Drake Scale", "epic", 4, "A scale shed by ancient drakes."),
            ("Celestial Ember", "legendary", 5, "A fragment of starfire that never cools."),
        ]
        await self._connection.executemany(
            """
            INSERT INTO materials (name, rarity, tier, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                rarity = excluded.rarity,
                tier = excluded.tier,
                description = excluded.description
            """,
            materials,
        )

    async def _seed_default_shop(self) -> None:
        assert self._connection is not None
        weapons = [
            ("Iron Sword", 10, 100, 50, "Warrior", "uncommon"),
            ("Staff of Sparks", 14, 80, 70, "Mage", "rare"),
            ("Hunter Bow", 12, 90, 60, "Ranger", "uncommon"),
            ("Twin Daggers", 16, 70, 75, "Rogue", "rare"),
            ("Blessed Mace", 9, 110, 80, "Paladin", "rare"),
        ]
        await self._connection.executemany(
            """
            INSERT INTO weapons (name, damage, durability, price, class_restriction, rarity, is_generic)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                damage = excluded.damage,
                durability = excluded.durability,
                price = excluded.price,
                class_restriction = excluded.class_restriction,
                rarity = excluded.rarity,
                is_generic = 1
            """,
            weapons,
        )

        armors = [
            ("Copper Armor", 5, 100, "common"),
            ("Iron Armor", 10, 200, "uncommon"),
            ("Mythril Armor", 20, 500, "rare"),
        ]
        await self._connection.executemany(
            """
            INSERT INTO armor (name, defense_boost, price, rarity, is_generic)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                defense_boost = excluded.defense_boost,
                price = excluded.price,
                rarity = excluded.rarity,
                is_generic = 1
            """,
            armors,
        )

        items = [
            ("Healing Potion", "heal_hp", 50, 25, "common", 0),
            ("Greater Healing Potion", "heal_hp", 100, 50, "uncommon", 0),
            ("Mana Elixir", "restore_mana", 50, 30, "common", 0),
            ("Strength Tonic", "buff_attack", 10, 75, "rare", 3),
            ("Guard Brew", "buff_defense", 10, 75, "rare", 3),
            ("Sapphire Starmap", "vanity", 0, 4500, "epic", 0),
            ("Jeweled Phoenix Idol", "vanity", 0, 7500, "legendary", 0),
        ]
        await self._connection.executemany(
            """
            INSERT INTO items (name, effect_type, effect_value, price, rarity, effect_duration, is_generic)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                effect_type = excluded.effect_type,
                effect_value = excluded.effect_value,
                price = excluded.price,
                rarity = excluded.rarity,
                effect_duration = excluded.effect_duration,
                is_generic = 1
            """,
            items,
        )

        await self._connection.execute(
            """
            INSERT INTO items (name, effect_type, effect_value, price, rarity, effect_duration, is_generic)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(name) DO UPDATE SET
                effect_type = excluded.effect_type,
                effect_value = excluded.effect_value,
                price = excluded.price,
                rarity = excluded.rarity,
                effect_duration = excluded.effect_duration,
                is_generic = 0
            """,
            (ANNIVERSARY_ITEM_NAME, "heal_hp", 150, 0, "legendary", 0),
        )

    async def _seed_default_events(self) -> None:
        assert self._connection is not None
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=1)
        end = now + timedelta(days=14)
        start_str = _format_time(start)
        end_str = _format_time(end)
        event_name = "Haunting of Hollow's Eve"
        description = (
            "The Pumpkin King's minions spill into the realm, daring heroes to face the haunted raid."
        )
        special_loot = (
            "Exclusive Pumpkin Reaper weapon, Bewitched Candy consumables, and haunted raid cosmetics."
        )

        await self._connection.execute(
            """
            INSERT INTO events (name, description, start_date, end_date, special_loot)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                special_loot = excluded.special_loot
            """,
            (event_name, description, start_str, end_str, special_loot),
        )

        cursor = await self._connection.execute(
            "SELECT id FROM events WHERE name = ?",
            (event_name,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return
        event_id = row["id"]

        await self._connection.execute(
            """
            INSERT INTO weapons (
                name, damage, durability, price, class_restriction, rarity, is_generic, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(name) DO UPDATE SET
                damage = excluded.damage,
                durability = excluded.durability,
                price = excluded.price,
                class_restriction = excluded.class_restriction,
                rarity = excluded.rarity,
                is_generic = 0,
                event_id = excluded.event_id
            """,
            (
                "Pumpkin Reaper",
                42,
                120,
                0,
                None,
                "legendary",
                event_id,
            ),
        )

        await self._connection.execute(
            """
            INSERT INTO items (
                name, effect_type, effect_value, price, rarity, effect_duration, is_generic, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(name) DO UPDATE SET
                effect_type = excluded.effect_type,
                effect_value = excluded.effect_value,
                price = excluded.price,
                rarity = excluded.rarity,
                effect_duration = excluded.effect_duration,
                is_generic = 0,
                event_id = excluded.event_id
            """,
            (
                "Bewitched Candy",
                "buff_attack",
                15,
                0,
                "epic",
                3,
                event_id,
            ),
        )

        await self._connection.execute(
            """
            INSERT INTO items (
                name, effect_type, effect_value, price, rarity, effect_duration, is_generic, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(name) DO UPDATE SET
                effect_type = excluded.effect_type,
                effect_value = excluded.effect_value,
                price = excluded.price,
                rarity = excluded.rarity,
                effect_duration = excluded.effect_duration,
                is_generic = 0,
                event_id = excluded.event_id
            """,
            (
                "Haunted Collector's Relic",
                "vanity",
                0,
                9000,
                "legendary",
                0,
                event_id,
            ),
        )

        await self._connection.execute(
            """
            INSERT INTO raid_bosses (
                name, description, max_hp, attack, xp_reward, gold_reward,
                rare_loot_chance, rare_loot_rarity, item_reward_rarity, material_reward_rarity, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                max_hp = excluded.max_hp,
                attack = excluded.attack,
                xp_reward = excluded.xp_reward,
                gold_reward = excluded.gold_reward,
                rare_loot_chance = excluded.rare_loot_chance,
                rare_loot_rarity = excluded.rare_loot_rarity,
                item_reward_rarity = excluded.item_reward_rarity,
                material_reward_rarity = excluded.material_reward_rarity,
                event_id = excluded.event_id
            """,
            (
                "Pumpkin King",
                "A colossal gourd wreathed in eldritch flame that stalks the harvest moon.",
                9500,
                280,
                6000,
                5200,
                0.25,
                "legendary",
                "event",
                "legendary",
                event_id,
            ),
        )

    async def _seed_default_raid_bosses(self) -> None:
        assert self._connection is not None
        bosses = [
            (
                "Eternal Golem",
                "A towering construct forged from indestructible stone.",
                8500,
                220,
                4200,
                3600,
                0.12,
                "legendary",
                "epic",
                "epic",
            ),
            (
                "Abyssal Hydra",
                "Heads of void-touched serpents snap in every direction.",
                10000,
                260,
                5200,
                4400,
                0.16,
                "legendary",
                "rare",
                "rare",
            ),
            (
                "Celestial Wyrm",
                "An ancient dragon whose scales shimmer with starlight.",
                12500,
                300,
                6500,
                5200,
                0.2,
                "legendary",
                "legendary",
                "legendary",
            ),
        ]
        await self._connection.executemany(
            """
            INSERT INTO raid_bosses (
                name, description, max_hp, attack, xp_reward, gold_reward,
                rare_loot_chance, rare_loot_rarity, item_reward_rarity, material_reward_rarity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                max_hp = excluded.max_hp,
                attack = excluded.attack,
                xp_reward = excluded.xp_reward,
                gold_reward = excluded.gold_reward,
                rare_loot_chance = excluded.rare_loot_chance,
                rare_loot_rarity = excluded.rare_loot_rarity,
                item_reward_rarity = excluded.item_reward_rarity,
                material_reward_rarity = excluded.material_reward_rarity
            """,
            bosses,
        )

    async def get_metadata(self, key: str) -> Optional[str]:
        row = await self._fetchone(
            "SELECT value FROM metadata WHERE key = ?",
            (key,),
        )
        if row is None:
            return None
        return row["value"]

    async def set_metadata(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    async def create_player(self, guild_id: int, user_id: int, class_id: int) -> Player:
        class_info = await self.fetch_class_by_id(class_id)
        if class_info is None:
            raise ValueError(f"Class with id {class_id} does not exist")

        player = Player(
            user_id=user_id,
            hp=class_info.base_hp,
            max_hp=class_info.base_hp,
            attack=class_info.base_attack,
            defense=class_info.base_defense,
            class_id=class_info.id,
        )

        await self._execute(
            """
            INSERT INTO players (
                user_id, level, xp, gold, hp, max_hp, energy,
                attack, defense, class_id, quests_completed, raids_completed,
                pvp_wins, pvp_losses, pvp_season_wins, pvp_season_losses,
                equipped_title_id,
                last_quest_at, last_raid_at, last_work_at, last_rest_at,
                last_proposal_at,
                active_quest_id, active_quest_complete_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player.user_id,
                player.level,
                player.xp,
                player.gold,
                player.hp,
                player.max_hp,
                player.energy,
                player.attack,
                player.defense,
                player.class_id,
                player.quests_completed,
                player.raids_completed,
                player.pvp_wins,
                player.pvp_losses,
                player.pvp_season_wins,
                player.pvp_season_losses,
                player.equipped_title_id,
                _format_time(player.last_quest_at),
                _format_time(player.last_raid_at),
                _format_time(player.last_work_at),
                _format_time(player.last_rest_at),
                _format_time(player.last_proposal_at),
                player.active_quest_id,
                _format_time(player.active_quest_complete_at),
            ),
        )

        created = await self.fetch_player(guild_id, user_id)
        assert created is not None
        return created

    async def fetch_player(self, guild_id: int, user_id: int) -> Optional[Player]:
        row = await self._fetchone(
            "SELECT * FROM players WHERE user_id = ?",
            (user_id,),
        )
        if row is None:
            return None
        return Player.from_row(row)

    async def fetch_player_profile(self, user_id: int) -> Optional[PlayerProfile]:
        row = await self._fetchone(
            "SELECT * FROM player_profiles WHERE user_id = ?",
            (user_id,),
        )
        return PlayerProfile.from_row(row) if row else None

    async def set_player_profile(
        self,
        user_id: int,
        *,
        avatar_url: Union[Optional[str], object] = _UNSET,
        banner_url: Union[Optional[str], object] = _UNSET,
    ) -> PlayerProfile:
        await self.connect()
        existing = await self.fetch_player_profile(user_id)

        def _resolve(
            incoming: Union[Optional[str], object], current: Optional[str]
        ) -> Optional[str]:
            if incoming is _UNSET:
                return current
            return cast(Optional[str], incoming)

        avatar_value = _resolve(avatar_url, existing.avatar_url if existing else None)
        banner_value = _resolve(banner_url, existing.banner_url if existing else None)

        await self._execute(
            """
            INSERT INTO player_profiles (user_id, avatar_url, banner_url, updated_at)
            VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ON CONFLICT(user_id) DO UPDATE SET
                avatar_url = excluded.avatar_url,
                banner_url = excluded.banner_url,
                updated_at = excluded.updated_at
            """,
            (user_id, avatar_value, banner_value),
        )

        profile = await self.fetch_player_profile(user_id)
        assert profile is not None
        return profile

    async def delete_player_profile(self, user_id: int) -> None:
        await self._execute(
            "DELETE FROM player_profiles WHERE user_id = ?",
            (user_id,),
        )

    async def fetch_player_quest_progress(self, user_id: int) -> Dict[str, QuestProgress]:
        rows = await self._fetchall(
            """
            SELECT quest_id, last_completed_at, completions
            FROM player_quest_progress
            WHERE user_id = ?
            """,
            (user_id,),
        )
        progress: Dict[str, QuestProgress] = {}
        for row in rows:
            progress[row["quest_id"]] = QuestProgress(
                quest_id=row["quest_id"],
                last_completed_at=_parse_time(row["last_completed_at"]),
                completions=row["completions"],
            )
        return progress

    async def record_quest_completion(
        self, user_id: int, quest_id: str, completed_at: datetime
    ) -> QuestProgress:
        await self._execute(
            """
            INSERT INTO player_quest_progress (user_id, quest_id, last_completed_at, completions)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, quest_id) DO UPDATE SET
                last_completed_at = excluded.last_completed_at,
                completions = player_quest_progress.completions + 1
            """,
            (user_id, quest_id, _format_time(completed_at)),
        )
        row = await self._fetchone(
            """
            SELECT quest_id, last_completed_at, completions
            FROM player_quest_progress
            WHERE user_id = ? AND quest_id = ?
            """,
            (user_id, quest_id),
        )
        assert row is not None
        return QuestProgress(
            quest_id=row["quest_id"],
            last_completed_at=_parse_time(row["last_completed_at"]),
            completions=row["completions"],
        )

    async def fetch_class_by_id(self, class_id: int) -> Optional[ClassInfo]:
        row = await self._fetchone("SELECT * FROM classes WHERE id = ?", (class_id,))
        if row is None:
            return None
        return ClassInfo.from_row(row)

    async def fetch_class_by_name(self, class_name: str) -> Optional[ClassInfo]:
        row = await self._fetchone(
            "SELECT * FROM classes WHERE LOWER(name) = LOWER(?)",
            (class_name,),
        )
        if row is None:
            return None
        return ClassInfo.from_row(row)

    async def list_classes(self) -> Sequence[ClassInfo]:
        rows = await self._fetchall("SELECT * FROM classes ORDER BY id")
        return [ClassInfo.from_row(row) for row in rows]

    async def list_achievements(self) -> Sequence[Achievement]:
        rows = await self._fetchall("SELECT * FROM achievements ORDER BY id")
        return [Achievement.from_row(row) for row in rows]

    async def fetch_achievement_by_id(self, achievement_id: int) -> Optional[Achievement]:
        row = await self._fetchone(
            "SELECT * FROM achievements WHERE id = ?",
            (achievement_id,),
        )
        return Achievement.from_row(row) if row else None

    async def fetch_achievement_by_code(self, code: str) -> Optional[Achievement]:
        row = await self._fetchone(
            "SELECT * FROM achievements WHERE code = ?",
            (code,),
        )
        return Achievement.from_row(row) if row else None

    async def grant_achievement(
        self, user_id: int, achievement: Achievement
    ) -> Optional[Achievement]:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            cursor = await self._connection.execute(
                """
                INSERT INTO player_achievements (user_id, achievement_id)
                VALUES (?, ?)
                ON CONFLICT(user_id, achievement_id) DO NOTHING
                """,
                (user_id, achievement.id),
            )
            inserted = cursor.rowcount
            await cursor.close()
            await self._connection.commit()
        return achievement if inserted else None

    async def grant_achievement_by_code(
        self, user_id: int, code: str
    ) -> Optional[Achievement]:
        achievement = await self.fetch_achievement_by_code(code)
        if achievement is None:
            return None
        return await self.grant_achievement(user_id, achievement)

    async def list_player_achievements(
        self, user_id: int
    ) -> Sequence[PlayerAchievementRecord]:
        rows = await self._fetchall(
            """
            SELECT a.*, pa.earned_at
            FROM player_achievements pa
            JOIN achievements a ON pa.achievement_id = a.id
            WHERE pa.user_id = ?
            ORDER BY pa.earned_at ASC
            """,
            (user_id,),
        )
        records: List[PlayerAchievementRecord] = []
        for row in rows:
            achievement = Achievement.from_row(row)
            earned_at = _parse_time(row["earned_at"]) or datetime.now(timezone.utc)
            records.append(PlayerAchievementRecord(achievement=achievement, earned_at=earned_at))
        return records

    async def fetch_equipped_title(self, user_id: int) -> Optional[Achievement]:
        row = await self._fetchone(
            """
            SELECT a.*
            FROM players p
            JOIN achievements a ON p.equipped_title_id = a.id
            WHERE p.user_id = ?
            """,
            (user_id,),
        )
        return Achievement.from_row(row) if row else None

    async def set_equipped_title(
        self, user_id: int, achievement_id: Optional[int]
    ) -> None:
        if achievement_id is not None:
            row = await self._fetchone(
                """
                SELECT 1
                FROM player_achievements
                WHERE user_id = ? AND achievement_id = ?
                """,
                (user_id, achievement_id),
            )
            if row is None:
                raise ValueError("title_not_unlocked")
        await self._execute(
            """
            UPDATE players
            SET equipped_title_id = ?,
                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE user_id = ?
            """,
            (achievement_id, user_id),
        )

    async def clear_equipped_title(self, user_id: int) -> None:
        await self.set_equipped_title(user_id, None)

    async def evaluate_player_achievements(
        self,
        player: Player,
        *,
        check_level: bool = False,
        check_quests: bool = False,
        check_raids: bool = False,
    ) -> Sequence[Achievement]:
        unlocked: List[Achievement] = []
        if check_level and player.level >= LEVEL_MILESTONE:
            achievement = await self.grant_achievement_by_code(
                player.user_id, ACHIEVEMENT_LEVEL_50
            )
            if achievement is not None:
                unlocked.append(achievement)
        if check_quests and player.quests_completed >= QUEST_MILESTONE:
            achievement = await self.grant_achievement_by_code(
                player.user_id, ACHIEVEMENT_QUEST_100
            )
            if achievement is not None:
                unlocked.append(achievement)
        if check_raids and player.raids_completed >= RAID_MILESTONE:
            achievement = await self.grant_achievement_by_code(
                player.user_id, ACHIEVEMENT_RAID_10
            )
            if achievement is not None:
                unlocked.append(achievement)
        return unlocked

    async def update_player(self, player: Player) -> None:
        await self._execute(
            """
            UPDATE players
            SET level = ?, xp = ?, gold = ?, hp = ?, max_hp = ?, energy = ?,
                attack = ?, defense = ?, class_id = ?,
                equipped_weapon_id = ?, equipped_armor_id = ?,
                attack_buff_percent = ?, attack_buff_battles = ?,
                defense_buff_percent = ?, defense_buff_battles = ?,
                quests_completed = ?, raids_completed = ?, equipped_title_id = ?,
                last_quest_at = ?, last_raid_at = ?, last_work_at = ?, last_rest_at = ?,
                last_proposal_at = ?,
                active_quest_id = ?, active_quest_complete_at = ?,
                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE user_id = ?
            """,
            player.as_db_tuple(),
        )

    async def _maybe_reset_pvp_season(self, now: datetime, *, seasonal_reset: bool) -> None:
        await self.connect()
        assert self._connection is not None
        season_anchor = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        async with self._lock:
            cursor = await self._connection.execute(
                "SELECT value FROM metadata WHERE key = ?",
                ("pvp_season_start",),
            )
            row = await cursor.fetchone()
            await cursor.close()
            stored = _parse_time(row["value"]) if row is not None else None
            needs_commit = False
            if stored is None:
                await self._connection.execute(
                    """
                    INSERT INTO metadata (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("pvp_season_start", _format_time(season_anchor)),
                )
                stored = season_anchor
                needs_commit = True
            if seasonal_reset and (stored.year != now.year or stored.month != now.month):
                await self._connection.execute(
                    "UPDATE players SET pvp_season_wins = 0, pvp_season_losses = 0",
                )
                await self._connection.execute(
                    """
                    INSERT INTO metadata (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("pvp_season_start", _format_time(season_anchor)),
                )
                needs_commit = True
            if needs_commit:
                await self._connection.commit()

    async def get_pvp_season_start(self) -> Optional[datetime]:
        value = await self.get_metadata("pvp_season_start")
        if value is None:
            return None
        return _parse_time(value)

    async def record_duel_result(
        self,
        winner_id: int,
        loser_id: int,
        *,
        now: Optional[datetime] = None,
        seasonal_reset: bool = True,
    ) -> Tuple[Player, Player]:
        moment = now or datetime.now(timezone.utc)
        await self._maybe_reset_pvp_season(moment, seasonal_reset=seasonal_reset)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                winner_cursor = await self._connection.execute(
                    """
                    UPDATE players
                    SET pvp_wins = pvp_wins + 1,
                        pvp_season_wins = pvp_season_wins + 1,
                        updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (winner_id,),
                )
                winner_updated = winner_cursor.rowcount
                await winner_cursor.close()
                if winner_updated == 0:
                    raise ValueError("winner_not_found")

                loser_cursor = await self._connection.execute(
                    """
                    UPDATE players
                    SET pvp_losses = pvp_losses + 1,
                        pvp_season_losses = pvp_season_losses + 1,
                        updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (loser_id,),
                )
                loser_updated = loser_cursor.rowcount
                await loser_cursor.close()
                if loser_updated == 0:
                    raise ValueError("loser_not_found")

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        winner = await self.fetch_player(0, winner_id)
        loser = await self.fetch_player(0, loser_id)
        if winner is None or loser is None:
            raise ValueError("player_not_found")
        return winner, loser

    async def top_players(self, limit: int = 10) -> Iterable[Player]:
        rows = await self._fetchall(
            """
            SELECT * FROM players
            WHERE class_id IS NOT NULL
            ORDER BY level DESC, xp DESC, gold DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [Player.from_row(row) for row in rows]

    async def global_leaderboard(self, metric: str, limit: int = 10) -> Sequence[Player]:
        key = metric.lower()
        if key == "xp":
            order = "level DESC, xp DESC, gold DESC"
        elif key == "gold":
            order = "gold DESC, level DESC, xp DESC"
        elif key == "pvp_wins":
            order = "pvp_wins DESC, pvp_losses ASC, level DESC, xp DESC"
        else:
            raise ValueError("unknown_leaderboard_metric")

        rows = await self._fetchall(
            f"""
            SELECT * FROM players
            WHERE class_id IS NOT NULL
            ORDER BY {order}
            LIMIT ?
            """,
            (limit,),
        )
        return [Player.from_row(row) for row in rows]

    async def list_generic_weapons(self) -> Sequence[Weapon]:
        rows = await self._fetchall(
            "SELECT * FROM weapons WHERE is_generic = 1 AND event_id IS NULL ORDER BY price ASC, name ASC"
        )
        return [Weapon.from_row(row) for row in rows]

    async def list_generic_armor(self) -> Sequence[Armor]:
        rows = await self._fetchall(
            "SELECT * FROM armor WHERE is_generic = 1 ORDER BY price ASC, defense_boost DESC"
        )
        return [Armor.from_row(row) for row in rows]

    async def list_generic_items(self) -> Sequence[Item]:
        rows = await self._fetchall(
            "SELECT * FROM items WHERE is_generic = 1 AND event_id IS NULL ORDER BY price ASC, name ASC"
        )
        return [Item.from_row(row) for row in rows]

    async def list_shop_weapons(self) -> Sequence[Weapon]:
        rows = await self._fetchall(
            "SELECT * FROM weapons WHERE event_id IS NULL ORDER BY rarity DESC, price DESC, name ASC"
        )
        return [Weapon.from_row(row) for row in rows]

    async def list_shop_armor(self) -> Sequence[Armor]:
        rows = await self._fetchall(
            "SELECT * FROM armor ORDER BY rarity DESC, price DESC, name ASC"
        )
        return [Armor.from_row(row) for row in rows]

    async def list_shop_items(self) -> Sequence[Item]:
        rows = await self._fetchall(
            "SELECT * FROM items WHERE event_id IS NULL ORDER BY rarity DESC, price DESC, name ASC"
        )
        return [Item.from_row(row) for row in rows]

    async def fetch_weapon_by_name(self, name: str) -> Optional[Weapon]:
        row = await self._fetchone(
            "SELECT * FROM weapons WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return Weapon.from_row(row) if row else None

    async def fetch_weapon_by_id(self, weapon_id: int) -> Optional[Weapon]:
        row = await self._fetchone(
            "SELECT * FROM weapons WHERE id = ?",
            (weapon_id,),
        )
        return Weapon.from_row(row) if row else None

    async def fetch_armor_by_name(self, name: str) -> Optional[Armor]:
        row = await self._fetchone(
            "SELECT * FROM armor WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return Armor.from_row(row) if row else None

    async def fetch_armor_by_id(self, armor_id: int) -> Optional[Armor]:
        row = await self._fetchone(
            "SELECT * FROM armor WHERE id = ?",
            (armor_id,),
        )
        return Armor.from_row(row) if row else None

    async def fetch_item_by_name(self, name: str) -> Optional[Item]:
        row = await self._fetchone(
            "SELECT * FROM items WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return Item.from_row(row) if row else None

    async def fetch_item_by_id(self, item_id: int) -> Optional[Item]:
        row = await self._fetchone(
            "SELECT * FROM items WHERE id = ?",
            (item_id,),
        )
        return Item.from_row(row) if row else None

    async def list_items_by_rarity(
        self, rarity: str, *, generic_only: bool = False
    ) -> Sequence[Item]:
        query = "SELECT * FROM items WHERE LOWER(rarity) = LOWER(?) AND event_id IS NULL"
        if generic_only:
            query += " AND is_generic = 1"
        query += " ORDER BY price DESC, name ASC"
        rows = await self._fetchall(query, (rarity,))
        return [Item.from_row(row) for row in rows]

    async def get_active_shop_rotation_entries(self) -> Sequence[ShopRotationEntry]:
        now = datetime.now(timezone.utc)
        rows = await self._fetchall(
            """
            SELECT * FROM shop_rotation
            WHERE expires_at > ?
            ORDER BY expires_at ASC, rarity DESC
            """,
            (_format_time(now),),
        )
        return [ShopRotationEntry.from_row(row) for row in rows]

    async def replace_shop_rotation(
        self,
        entries: Sequence[Tuple[str, int, str]],
        *,
        featured_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        assert self._connection is not None
        featured = featured_at or datetime.now(timezone.utc)
        expiry = expires_at or (featured + timedelta(hours=24))
        featured_str = _format_time(featured) or ""
        expires_str = _format_time(expiry) or ""
        async with self._lock:
            await self._connection.execute("DELETE FROM shop_rotation")
            if entries:
                await self._connection.executemany(
                    """
                    INSERT INTO shop_rotation (item_type, item_id, rarity, featured_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item_type,
                            item_id,
                            rarity,
                            featured_str,
                            expires_str,
                        )
                        for item_type, item_id, rarity in entries
                    ],
                )
            await self._connection.commit()

    async def get_shop_rotation_expiry(self) -> Optional[datetime]:
        row = await self._fetchone(
            """
            SELECT MIN(expires_at) AS expires_at
            FROM shop_rotation
            WHERE expires_at > ?
            """,
            (_format_time(datetime.now(timezone.utc)),),
        )
        if row is None or row["expires_at"] is None:
            return None
        return _parse_time(row["expires_at"])

    async def get_active_shop_rotation_items(
        self,
    ) -> Sequence[Tuple[ShopRotationEntry, Union[Weapon, Armor, Item]]]:
        entries = await self.get_active_shop_rotation_entries()
        results: List[Tuple[ShopRotationEntry, Union[Weapon, Armor, Item]]] = []
        for entry in entries:
            if entry.item_type == "weapon":
                item = await self.fetch_weapon_by_id(entry.item_id)
            elif entry.item_type == "armor":
                item = await self.fetch_armor_by_id(entry.item_id)
            else:
                item = await self.fetch_item_by_id(entry.item_id)
            if item is None:
                continue
            results.append((entry, item))
        return results

    async def is_item_in_active_rotation(self, item_type: str, item_id: int) -> bool:
        row = await self._fetchone(
            """
            SELECT 1 FROM shop_rotation
            WHERE item_type = ? AND item_id = ? AND expires_at > ?
            LIMIT 1
            """,
            (item_type, item_id, _format_time(datetime.now(timezone.utc))),
        )
        return row is not None

    async def fetch_event(self, event_id: int) -> Optional[Event]:
        row = await self._fetchone(
            "SELECT * FROM events WHERE id = ?",
            (event_id,),
        )
        return Event.from_row(row) if row else None

    async def fetch_event_by_name(self, name: str) -> Optional[Event]:
        row = await self._fetchone(
            "SELECT * FROM events WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return Event.from_row(row) if row else None

    async def fetch_active_event(self) -> Optional[Event]:
        now = _format_time(datetime.now(timezone.utc))
        row = await self._fetchone(
            """
            SELECT * FROM events
            WHERE start_date <= ? AND end_date >= ?
            ORDER BY start_date ASC
            LIMIT 1
            """,
            (now, now),
        )
        return Event.from_row(row) if row else None

    async def list_event_weapons(self, event_id: int) -> Sequence[Weapon]:
        rows = await self._fetchall(
            "SELECT * FROM weapons WHERE event_id = ? ORDER BY price ASC, name ASC",
            (event_id,),
        )
        return [Weapon.from_row(row) for row in rows]

    async def list_event_items(self, event_id: int) -> Sequence[Item]:
        rows = await self._fetchall(
            "SELECT * FROM items WHERE event_id = ? ORDER BY price ASC, name ASC",
            (event_id,),
        )
        return [Item.from_row(row) for row in rows]

    async def fetch_event_participant(
        self, event_id: int, user_id: int
    ) -> Optional[EventParticipant]:
        row = await self._fetchone(
            "SELECT * FROM event_participants WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        )
        return EventParticipant.from_row(row) if row else None

    async def ensure_event_participant(self, event_id: int, user_id: int) -> bool:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    INSERT OR IGNORE INTO event_participants (event_id, user_id)
                    VALUES (?, ?)
                    """,
                    (event_id, user_id),
                )
                inserted = cursor.rowcount
                await cursor.close()
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise
        return inserted > 0

    async def fetch_material_by_id(self, material_id: int) -> Optional[Material]:
        row = await self._fetchone(
            "SELECT * FROM materials WHERE id = ?",
            (material_id,),
        )
        return Material.from_row(row) if row else None

    async def fetch_material_by_name(self, name: str) -> Optional[Material]:
        row = await self._fetchone(
            "SELECT * FROM materials WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return Material.from_row(row) if row else None

    async def list_materials_by_rarity(self, rarity: str) -> Sequence[Material]:
        rows = await self._fetchall(
            "SELECT * FROM materials WHERE LOWER(rarity) = LOWER(?)",
            (rarity,),
        )
        return [Material.from_row(row) for row in rows]

    async def list_materials(self) -> Sequence[Material]:
        rows = await self._fetchall("SELECT * FROM materials ORDER BY tier ASC")
        return [Material.from_row(row) for row in rows]

    async def list_raid_bosses(self) -> Sequence[RaidBoss]:
        rows = await self._fetchall(
            "SELECT * FROM raid_bosses WHERE event_id IS NULL ORDER BY max_hp ASC, name ASC"
        )
        return [RaidBoss.from_row(row) for row in rows]

    async def fetch_raid_boss_by_name(self, name: str) -> Optional[RaidBoss]:
        row = await self._fetchone(
            "SELECT * FROM raid_bosses WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return RaidBoss.from_row(row) if row else None

    async def fetch_raid_boss_by_id(self, boss_id: int) -> Optional[RaidBoss]:
        row = await self._fetchone(
            "SELECT * FROM raid_bosses WHERE id = ?",
            (boss_id,),
        )
        return RaidBoss.from_row(row) if row else None

    async def fetch_event_raid_boss(self, event_id: int) -> Optional[RaidBoss]:
        row = await self._fetchone(
            "SELECT * FROM raid_bosses WHERE event_id = ? LIMIT 1",
            (event_id,),
        )
        return RaidBoss.from_row(row) if row else None

    async def fetch_active_raid(self) -> Optional[RaidInstance]:
        row = await self._fetchone(
            """
            SELECT * FROM raid_instances
            WHERE status = 'active' AND event_id IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
        return RaidInstance.from_row(row) if row else None

    async def fetch_active_event_raid(self, event_id: int) -> Optional[RaidInstance]:
        row = await self._fetchone(
            """
            SELECT * FROM raid_instances
            WHERE status = 'active' AND event_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (event_id,),
        )
        return RaidInstance.from_row(row) if row else None

    async def fetch_most_recent_raid(self) -> Optional[RaidInstance]:
        row = await self._fetchone(
            """
            SELECT * FROM raid_instances
            WHERE event_id IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        return RaidInstance.from_row(row) if row else None

    async def fetch_raid_instance(self, raid_id: int) -> Optional[RaidInstance]:
        row = await self._fetchone(
            "SELECT * FROM raid_instances WHERE id = ?",
            (raid_id,),
        )
        return RaidInstance.from_row(row) if row else None

    async def ensure_raid_participant(self, raid_id: int, user_id: int) -> RaidParticipant:
        await self._execute(
            "INSERT OR IGNORE INTO raid_participants (raid_id, user_id, damage_dealt) VALUES (?, ?, 0)",
            (raid_id, user_id),
        )
        participant = await self.fetch_raid_participant(raid_id, user_id)
        if participant is None:
            raise ValueError("participant_not_created")
        return participant

    async def fetch_raid_participant(
        self, raid_id: int, user_id: int
    ) -> Optional[RaidParticipant]:
        row = await self._fetchone(
            "SELECT * FROM raid_participants WHERE raid_id = ? AND user_id = ?",
            (raid_id, user_id),
        )
        return RaidParticipant.from_row(row) if row else None

    async def list_raid_participants(self, raid_id: int) -> Sequence[RaidParticipant]:
        rows = await self._fetchall(
            """
            SELECT * FROM raid_participants
            WHERE raid_id = ?
            ORDER BY damage_dealt DESC, last_attack_at ASC
            """,
            (raid_id,),
        )
        return [RaidParticipant.from_row(row) for row in rows]

    async def create_raid_instance(
        self, boss_id: int, created_by: int, *, event_id: Optional[int] = None
    ) -> RaidInstance:
        boss = await self.fetch_raid_boss_by_id(boss_id)
        if boss is None:
            raise ValueError("boss_not_found")
        await self.connect()
        assert self._connection is not None
        event_value = event_id if event_id is not None else boss.event_id
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    INSERT INTO raid_instances (
                        boss_id, created_by, current_hp, status, total_damage, event_id
                    )
                    VALUES (?, ?, ?, 'active', 0, ?)
                    """,
                    (boss_id, created_by, boss.max_hp, event_value),
                )
                raid_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise
        raid = await self.fetch_raid_instance(raid_id)
        if raid is None:
            raise ValueError("raid_not_created")
        return raid

    async def record_raid_attack(
        self, raid_id: int, user_id: int, damage: int
    ) -> Tuple[RaidInstance, RaidParticipant, int]:
        inflicted = max(0, damage)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT current_hp, status, total_damage FROM raid_instances WHERE id = ?",
                    (raid_id,),
                )
                raid_row = await cursor.fetchone()
                await cursor.close()
                if raid_row is None:
                    raise ValueError("raid_not_found")
                if raid_row["status"] != "active":
                    raise ValueError("raid_not_active")
                remaining_hp = raid_row["current_hp"]
                inflicted = max(0, min(inflicted, remaining_hp))
                remaining_hp = max(0, remaining_hp - inflicted)
                total_damage = raid_row["total_damage"] + inflicted
                status = "completed" if remaining_hp <= 0 else "active"
                await self._connection.execute(
                    """
                    UPDATE raid_instances
                    SET current_hp = ?,
                        total_damage = ?,
                        status = ?,
                        completed_at = CASE
                            WHEN ? = 'completed' AND completed_at IS NULL THEN (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                            ELSE completed_at
                        END
                    WHERE id = ?
                    """,
                    (remaining_hp, total_damage, status, status, raid_id),
                )
                await self._connection.execute(
                    """
                    INSERT INTO raid_participants (raid_id, user_id, damage_dealt, last_attack_at)
                    VALUES (?, ?, ?, (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
                    ON CONFLICT(raid_id, user_id) DO UPDATE SET
                        damage_dealt = raid_participants.damage_dealt + excluded.damage_dealt,
                        last_attack_at = excluded.last_attack_at
                    """,
                    (raid_id, user_id, inflicted),
                )
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise
        raid = await self.fetch_raid_instance(raid_id)
        participant = await self.fetch_raid_participant(raid_id, user_id)
        if raid is None or participant is None:
            raise ValueError("raid_state_missing")
        return raid, participant, inflicted

    async def ensure_anniversary_item(self) -> Item:
        item = await self.fetch_item_by_name(ANNIVERSARY_ITEM_NAME)
        if item is None:
            item = await self.add_item(
                ANNIVERSARY_ITEM_NAME,
                effect_type="heal_hp",
                effect_value=150,
                price=0,
                rarity="legendary",
                effect_duration=0,
                is_generic=False,
            )
        return item

    async def add_weapon(
        self,
        name: str,
        damage: int,
        durability: int,
        price: int,
        class_restriction: Optional[str],
        rarity: str = "rare",
        is_generic: bool = False,
    ) -> Weapon:
        await self._execute(
            """
            INSERT INTO weapons (name, damage, durability, price, class_restriction, rarity, is_generic)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                damage = excluded.damage,
                durability = excluded.durability,
                price = excluded.price,
                class_restriction = excluded.class_restriction,
                rarity = excluded.rarity,
                is_generic = excluded.is_generic
            """,
            (
                name,
                damage,
                durability,
                price,
                class_restriction,
                rarity,
                1 if is_generic else 0,
            ),
        )
        weapon = await self.fetch_weapon_by_name(name)
        assert weapon is not None
        return weapon

    async def add_armor(
        self,
        name: str,
        defense_boost: int,
        price: int,
        rarity: str = "rare",
        is_generic: bool = False,
    ) -> Armor:
        await self._execute(
            """
            INSERT INTO armor (name, defense_boost, price, rarity, is_generic)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                defense_boost = excluded.defense_boost,
                price = excluded.price,
                rarity = excluded.rarity,
                is_generic = excluded.is_generic
            """,
            (name, defense_boost, price, rarity, 1 if is_generic else 0),
        )
        armor = await self.fetch_armor_by_name(name)
        assert armor is not None
        return armor

    async def add_material(
        self,
        name: str,
        rarity: str,
        tier: int,
        description: str,
    ) -> Material:
        await self._execute(
            """
            INSERT INTO materials (name, rarity, tier, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                rarity = excluded.rarity,
                tier = excluded.tier,
                description = excluded.description
            """,
            (name, rarity, tier, description),
        )
        material = await self.fetch_material_by_name(name)
        assert material is not None
        return material

    async def purge_expired_inventory(self, user_id: Optional[int] = None) -> int:
        await self.connect()
        assert self._connection is not None
        now = _format_time(datetime.now(timezone.utc))
        assert now is not None
        conditions = ["expires_at IS NOT NULL", "expires_at <= ?"]
        parameters: List[object] = [now]
        if user_id is not None:
            conditions.append("user_id = ?")
            parameters.append(user_id)
        where_clause = " AND ".join(conditions)

        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    f"SELECT id, user_id, item_type FROM player_inventory WHERE {where_clause}",
                    tuple(parameters),
                )
                rows = await cursor.fetchall()
                await cursor.close()

                for row in rows:
                    inventory_id = row["id"]
                    owner_id = row["user_id"]
                    item_type = row["item_type"]
                    await self._connection.execute(
                        "DELETE FROM player_inventory WHERE id = ?",
                        (inventory_id,),
                    )
                    if item_type == "weapon":
                        await self._connection.execute(
                            """
                            UPDATE players
                            SET equipped_weapon_id = CASE
                                    WHEN equipped_weapon_id = ? THEN NULL
                                    ELSE equipped_weapon_id
                                END,
                                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                            WHERE user_id = ?
                            """,
                            (inventory_id, owner_id),
                        )
                    elif item_type == "armor":
                        await self._connection.execute(
                            """
                            UPDATE players
                            SET equipped_armor_id = CASE
                                    WHEN equipped_armor_id = ? THEN NULL
                                    ELSE equipped_armor_id
                                END,
                                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                            WHERE user_id = ?
                            """,
                            (inventory_id, owner_id),
                        )

                await self._connection.commit()
                return len(rows)
            except Exception:
                await self._connection.rollback()
                raise

    async def grant_item_to_player(
        self,
        guild_id: int,
        user_id: int,
        item: Item,
        quantity: int = 1,
        *,
        expires_at: Optional[datetime] = None,
    ) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        expires_value = _format_time(expires_at)
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT 1 FROM players WHERE user_id = ?",
                    (user_id,),
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    """
                    SELECT id, quantity FROM player_inventory
                    WHERE user_id = ? AND item_type = 'item' AND item_id = ?
                        AND ((? IS NULL AND expires_at IS NULL) OR expires_at = ?)
                    """,
                    (user_id, item.id, expires_value, expires_value),
                )
                existing = await cursor.fetchone()
                await cursor.close()
                if existing is None:
                    cursor = await self._connection.execute(
                        """
                        INSERT INTO player_inventory (
                            user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                        ) VALUES (?, 'item', ?, ?, NULL, 0, ?)
                        """,
                        (user_id, item.id, max(1, quantity), expires_value),
                    )
                    inventory_id = cursor.lastrowid
                else:
                    inventory_id = existing["id"]
                    await self._connection.execute(
                        "UPDATE player_inventory SET quantity = quantity + ? WHERE id = ?",
                        (max(1, quantity), inventory_id),
                    )

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def grant_material_to_player(
        self, guild_id: int, user_id: int, material: Material, quantity: int = 1
    ) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT 1 FROM players WHERE user_id = ?",
                    (user_id,),
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    """
                    SELECT id, quantity FROM player_inventory
                    WHERE user_id = ? AND item_type = 'material' AND item_id = ?
                    """,
                    (user_id, material.id),
                )
                existing = await cursor.fetchone()
                await cursor.close()
                if existing is None:
                    cursor = await self._connection.execute(
                        """
                        INSERT INTO player_inventory (
                            user_id, item_type, item_id, quantity, current_durability, is_equipped
                        ) VALUES (?, 'material', ?, ?, NULL, 0)
                        """,
                        (user_id, material.id, max(1, quantity)),
                    )
                    inventory_id = cursor.lastrowid
                else:
                    inventory_id = existing["id"]
                    await self._connection.execute(
                        "UPDATE player_inventory SET quantity = quantity + ? WHERE id = ?",
                        (max(1, quantity), inventory_id),
                    )

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def grant_weapon_to_player(
        self,
        guild_id: int,
        user_id: int,
        weapon: Weapon,
        *,
        expires_at: Optional[datetime] = None,
    ) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        expires_value = _format_time(expires_at)
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT 1 FROM players WHERE user_id = ?",
                    (user_id,),
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    """
                    INSERT INTO player_inventory (
                        user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                    ) VALUES (?, 'weapon', ?, 1, ?, 0, ?)
                    """,
                    (user_id, weapon.id, weapon.durability, expires_value),
                )
                inventory_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def grant_armor_to_player(
        self,
        guild_id: int,
        user_id: int,
        armor: Armor,
        *,
        expires_at: Optional[datetime] = None,
    ) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        expires_value = _format_time(expires_at)
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT 1 FROM players WHERE user_id = ?",
                    (user_id,),
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    """
                    INSERT INTO player_inventory (
                        user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                    ) VALUES (?, 'armor', ?, 1, NULL, 0, ?)
                    """,
                    (user_id, armor.id, expires_value),
                )
                inventory_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def fetch_listing_by_id(self, listing_id: int) -> Optional[AuctionListing]:
        row = await self._fetchone("SELECT * FROM listings WHERE id = ?", (listing_id,))
        return AuctionListing.from_row(row) if row else None

    async def list_active_listings(
        self, page: int, page_size: int
    ) -> Tuple[int, Sequence[Tuple[AuctionListing, InventoryPayload]]]:
        await self.purge_expired_listings()
        now_value = _format_time(datetime.now(timezone.utc))
        total_row = await self._fetchone(
            "SELECT COUNT(*) AS count FROM listings WHERE expires_at > ?",
            (now_value,),
        )
        total = total_row["count"] if total_row else 0
        offset = max(0, (page - 1) * page_size)
        rows = await self._fetchall(
            """
            SELECT * FROM listings
            WHERE expires_at > ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (now_value, page_size, offset),
        )
        listings: List[Tuple[AuctionListing, InventoryPayload]] = []
        for row in rows:
            listing = AuctionListing.from_row(row)
            payload = await self._get_listing_payload(listing)
            if payload is None:
                continue
            listings.append((listing, payload))
        return total, listings

    async def create_listing(
        self,
        guild_id: int,
        seller_id: int,
        inventory_id: int,
        price: int,
        *,
        listing_fee: int = 0,
    ) -> AuctionListing:
        if price <= 0:
            raise ValueError("invalid_price")

        await self.purge_expired_inventory(seller_id)
        await self.purge_expired_listings()
        await self.connect()
        assert self._connection is not None

        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (seller_id,),
                )
                player_row = await cursor.fetchone()
                await cursor.close()
                if player_row is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    """
                    SELECT id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                    FROM player_inventory
                    WHERE id = ? AND user_id = ?
                    """,
                    (inventory_id, seller_id),
                )
                entry_row = await cursor.fetchone()
                await cursor.close()
                if entry_row is None:
                    raise ValueError("inventory_not_found")
                if entry_row["is_equipped"]:
                    raise ValueError("item_equipped")

                quantity = max(1, entry_row["quantity"])
                expires_at = datetime.now(timezone.utc) + timedelta(days=7)
                created_at = datetime.now(timezone.utc)

                if listing_fee > 0:
                    if player_row["gold"] < listing_fee:
                        raise ValueError("insufficient_gold")
                    await self._connection.execute(
                        """
                        UPDATE players
                        SET gold = gold - ?,
                            updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                        WHERE user_id = ?
                        """,
                        (listing_fee, seller_id),
                    )

                await self._connection.execute(
                    "DELETE FROM player_inventory WHERE id = ?",
                    (inventory_id,),
                )

                cursor = await self._connection.execute(
                    """
                    INSERT INTO listings (
                        seller_id, item_type, item_id, quantity, current_durability,
                        price, created_at, expires_at, item_expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        seller_id,
                        entry_row["item_type"],
                        entry_row["item_id"],
                        quantity,
                        entry_row["current_durability"],
                        price,
                        _format_time(created_at),
                        _format_time(expires_at),
                        entry_row["expires_at"],
                    ),
                )
                listing_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        listing = await self.fetch_listing_by_id(listing_id)
        assert listing is not None
        return listing

    async def buy_listing(
        self, guild_id: int, listing_id: int, buyer_id: int
    ) -> Tuple[AuctionListing, InventoryPayload, int]:
        await self.purge_expired_listings()
        await self.connect()
        assert self._connection is not None

        listing: Optional[AuctionListing] = None
        payload: Optional[InventoryPayload] = None
        tax_amount = 0

        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (buyer_id,),
                )
                buyer_row = await cursor.fetchone()
                await cursor.close()
                if buyer_row is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    "SELECT * FROM listings WHERE id = ?",
                    (listing_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    raise ValueError("listing_not_found")
                listing = AuctionListing.from_row(row)

                if listing.expires_at <= datetime.now(timezone.utc):
                    raise ValueError("listing_expired")
                if listing.seller_id == buyer_id:
                    raise ValueError("cannot_buy_own")

                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (listing.seller_id,),
                )
                seller_row = await cursor.fetchone()
                await cursor.close()
                if seller_row is None:
                    raise ValueError("seller_missing")

                if buyer_row["gold"] < listing.price:
                    raise ValueError("insufficient_gold")

                tax_amount = max(0, listing.price * 5 // 100)
                payout = listing.price - tax_amount

                await self._connection.execute(
                    """
                    UPDATE players
                    SET gold = gold - ?,
                        updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (listing.price, buyer_id),
                )

                if payout > 0:
                    await self._connection.execute(
                        """
                        UPDATE players
                        SET gold = gold + ?,
                            updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                        WHERE user_id = ?
                        """,
                        (payout, listing.seller_id),
                    )

                payload = await self._transfer_listing_item(buyer_id, listing)

                await self._connection.execute(
                    "DELETE FROM listings WHERE id = ?",
                    (listing.id,),
                )

                await self._connection.commit()
            except ValueError as exc:
                await self._connection.rollback()
                reason = str(exc)
                if reason == "listing_expired":
                    await self.purge_expired_listings()
                elif reason in {"seller_missing", "item_missing"} and listing is not None:
                    await self._execute(
                        "DELETE FROM listings WHERE id = ?",
                        (listing.id,),
                    )
                raise
            except Exception:
                await self._connection.rollback()
                raise

        if listing is None or payload is None:
            raise ValueError("listing_invalid")
        return listing, payload, tax_amount

    async def purge_expired_listings(self) -> int:
        await self.connect()
        assert self._connection is not None
        now_value = _format_time(datetime.now(timezone.utc))
        if now_value is None:
            return 0

        removed = 0
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT * FROM listings WHERE expires_at <= ?",
                    (now_value,),
                )
                rows = await cursor.fetchall()
                await cursor.close()

                for row in rows:
                    listing = AuctionListing.from_row(row)
                    try:
                        await self._transfer_listing_item(listing.seller_id, listing)
                    except (ValueError, aiosqlite.IntegrityError):
                        pass
                    await self._connection.execute(
                        "DELETE FROM listings WHERE id = ?",
                        (listing.id,),
                    )
                    removed += 1

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise
        return removed

    async def buy_weapon(self, guild_id: int, user_id: int, weapon: Weapon) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    raise ValueError("player_not_found")
                if row["gold"] < weapon.price:
                    raise ValueError("insufficient_gold")
                await self._connection.execute(
                    """
                    UPDATE players
                    SET gold = gold - ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (weapon.price, user_id),
                )
                cursor = await self._connection.execute(
                    """
                    INSERT INTO player_inventory (
                        user_id, item_type, item_id, quantity, current_durability, is_equipped
                    ) VALUES (?, 'weapon', ?, 1, ?, 0)
                    """,
                    (user_id, weapon.id, weapon.durability),
                )
                inventory_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def repair_weapon(
        self,
        guild_id: int,
        user_id: int,
        inventory_id: int,
        *,
        cost_percent: float,
    ) -> Tuple[InventoryEntry, Weapon, int]:
        await self.connect()
        assert self._connection is not None
        percent = min(1.0, max(0.0, cost_percent))

        weapon: Optional[Weapon] = None
        cost = 0

        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (user_id,),
                )
                player_row = await cursor.fetchone()
                await cursor.close()
                if player_row is None:
                    raise ValueError("player_not_found")

                cursor = await self._connection.execute(
                    """
                    SELECT
                        pi.id,
                        pi.current_durability,
                        w.id AS weapon_id,
                        w.name AS weapon_name,
                        w.damage AS weapon_damage,
                        w.durability AS weapon_durability,
                        w.price AS weapon_price,
                        w.class_restriction,
                        w.rarity AS weapon_rarity,
                        w.is_generic AS weapon_is_generic,
                        w.event_id AS weapon_event_id
                    FROM player_inventory AS pi
                    JOIN weapons AS w ON w.id = pi.item_id
                    WHERE pi.id = ? AND pi.user_id = ? AND pi.item_type = 'weapon'
                    LIMIT 1
                    """,
                    (inventory_id, user_id),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    raise ValueError("weapon_not_found")

                current = row["current_durability"]
                max_durability = row["weapon_durability"]
                if max_durability is None or max_durability <= 0:
                    raise ValueError("weapon_not_damaged")
                if current is None:
                    current = max_durability
                current = max(0, current)
                if current >= max_durability:
                    raise ValueError("weapon_not_damaged")

                missing = max_durability - current
                base_cost = row["weapon_price"] * percent
                cost = math.ceil(base_cost * (missing / max_durability))
                if (
                    cost <= 0
                    and missing > 0
                    and percent > 0
                    and row["weapon_price"] > 0
                ):
                    cost = 1
                cost = max(0, cost)
                if player_row["gold"] < cost:
                    raise ValueError("insufficient_gold")

                await self._connection.execute(
                    """
                    UPDATE players
                    SET gold = gold - ?,
                        updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (cost, user_id),
                )
                await self._connection.execute(
                    "UPDATE player_inventory SET current_durability = ? WHERE id = ?",
                    (max_durability, row["id"]),
                )

                weapon = Weapon(
                    id=row["weapon_id"],
                    name=row["weapon_name"],
                    damage=row["weapon_damage"],
                    durability=max_durability,
                    price=row["weapon_price"],
                    class_restriction=row["class_restriction"],
                    rarity=row["weapon_rarity"],
                    is_generic=bool(row["weapon_is_generic"]),
                    event_id=row["weapon_event_id"],
                )

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        if weapon is None:
            raise ValueError("weapon_not_found")

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        if entry is None:
            raise ValueError("weapon_not_found")
        return entry, weapon, cost

    async def fetch_marriage(self, guild_id: int, user_id: int) -> Optional[Marriage]:
        row = await self._fetchone(
            """
            SELECT * FROM marriages
            WHERE player1_id = ? OR player2_id = ?
            LIMIT 1
            """,
            (user_id, user_id),
        )
        return Marriage.from_row(row) if row else None

    async def fetch_marriage_by_id(self, marriage_id: int) -> Optional[Marriage]:
        row = await self._fetchone(
            "SELECT * FROM marriages WHERE id = ?",
            (marriage_id,),
        )
        return Marriage.from_row(row) if row else None

    async def fetch_proposal_for(
        self, guild_id: int, proposee_id: int
    ) -> Optional[MarriageProposal]:
        row = await self._fetchone(
            "SELECT * FROM marriage_proposals WHERE proposee_id = ?",
            (proposee_id,),
        )
        return MarriageProposal.from_row(row) if row else None

    async def fetch_proposal_from(
        self, guild_id: int, proposer_id: int
    ) -> Optional[MarriageProposal]:
        row = await self._fetchone(
            "SELECT * FROM marriage_proposals WHERE proposer_id = ?",
            (proposer_id,),
        )
        return MarriageProposal.from_row(row) if row else None

    async def fetch_proposal_between(
        self, guild_id: int, proposer_id: int, proposee_id: int
    ) -> Optional[MarriageProposal]:
        row = await self._fetchone(
            """
            SELECT * FROM marriage_proposals
            WHERE proposer_id = ? AND proposee_id = ?
            """,
            (proposer_id, proposee_id),
        )
        return MarriageProposal.from_row(row) if row else None

    async def delete_proposal(self, proposal_id: int) -> None:
        await self._execute(
            "DELETE FROM marriage_proposals WHERE id = ?",
            (proposal_id,),
        )

    async def delete_proposals_between(
        self, guild_id: int, player_a: int, player_b: int
    ) -> None:
        await self._execute(
            """
            DELETE FROM marriage_proposals
            WHERE (proposer_id = ? AND proposee_id = ?)
                OR (proposer_id = ? AND proposee_id = ?)
            """,
            (player_a, player_b, player_b, player_a),
        )

    async def create_proposal(
        self,
        guild_id: int,
        proposer_id: int,
        proposee_id: int,
        created_at: Optional[datetime] = None,
    ) -> MarriageProposal:
        created = created_at or datetime.now(timezone.utc)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    SELECT 1 FROM marriages
                    WHERE player1_id IN (?, ?) OR player2_id IN (?, ?)
                    )
                    LIMIT 1
                    """,
                    (proposer_id, proposee_id, proposer_id, proposee_id),
                )
                existing_marriage = await cursor.fetchone()
                await cursor.close()
                if existing_marriage is not None:
                    raise ValueError("already_married")

                cursor = await self._connection.execute(
                    """
                    SELECT 1 FROM marriage_proposals
                    WHERE proposer_id = ? OR proposee_id = ?
                    LIMIT 1
                    """,
                    (proposer_id, proposer_id),
                )
                proposer_pending = await cursor.fetchone()
                await cursor.close()
                if proposer_pending is not None:
                    raise ValueError("proposal_pending")

                cursor = await self._connection.execute(
                    """
                    SELECT 1 FROM marriage_proposals
                    WHERE proposer_id = ? OR proposee_id = ?
                    LIMIT 1
                    """,
                    (proposee_id, proposee_id),
                )
                proposee_pending = await cursor.fetchone()
                await cursor.close()
                if proposee_pending is not None:
                    raise ValueError("target_has_pending")

                cursor = await self._connection.execute(
                    """
                    INSERT INTO marriage_proposals (proposer_id, proposee_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (proposer_id, proposee_id, _format_time(created)),
                )
                proposal_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        proposal = await self.fetch_proposal_between(guild_id, proposer_id, proposee_id)
        assert proposal is not None
        return proposal

    async def create_marriage(
        self,
        guild_id: int,
        user_a: int,
        user_b: int,
        date_married: Optional[datetime] = None,
    ) -> Marriage:
        if user_a == user_b:
            raise ValueError("same_person")
        player1_id, player2_id = sorted((user_a, user_b))
        married_at = date_married or datetime.now(timezone.utc)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    SELECT 1 FROM marriages
                    WHERE player1_id IN (?, ?) OR player2_id IN (?, ?)
                    )
                    LIMIT 1
                    """,
                    (player1_id, player2_id, player1_id, player2_id),
                )
                existing = await cursor.fetchone()
                await cursor.close()
                if existing is not None:
                    raise ValueError("already_married")

                await self._connection.execute(
                    """
                    INSERT INTO marriages (player1_id, player2_id, date_married)
                    VALUES (?, ?, ?)
                    """,
                    (player1_id, player2_id, _format_time(married_at)),
                )

                await self._connection.execute(
                    """
                    DELETE FROM marriage_proposals
                    WHERE proposer_id IN (?, ?) OR proposee_id IN (?, ?)
                    )
                    """,
                    (player1_id, player2_id, player1_id, player2_id),
                )

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        marriage = await self.fetch_marriage(guild_id, player1_id)
        assert marriage is not None
        await self.grant_achievement_by_code(player1_id, ACHIEVEMENT_FIRST_MARRIAGE)
        await self.grant_achievement_by_code(player2_id, ACHIEVEMENT_FIRST_MARRIAGE)
        return marriage

    async def delete_marriage_by_id(self, marriage_id: int) -> None:
        await self._execute(
            "DELETE FROM marriages WHERE id = ?",
            (marriage_id,),
        )

    async def delete_marriage_for_player(self, guild_id: int, user_id: int) -> None:
        await self._execute(
            "DELETE FROM marriages WHERE player1_id = ? OR player2_id = ?",
            (user_id, user_id),
        )

    async def create_divorce_request(
        self,
        marriage_id: int,
        initiator_id: int,
        created_at: Optional[datetime] = None,
    ) -> DivorceRequest:
        created = created_at or datetime.now(timezone.utc)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    INSERT INTO marriage_divorce_requests (marriage_id, initiator_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (marriage_id, initiator_id, _format_time(created)),
                )
                request_id = cursor.lastrowid
                await self._connection.commit()
            except aiosqlite.IntegrityError:
                await self._connection.rollback()
                raise ValueError("divorce_pending")
            except Exception:
                await self._connection.rollback()
                raise

        row = await self._fetchone(
            "SELECT * FROM marriage_divorce_requests WHERE id = ?",
            (request_id,),
        )
        assert row is not None
        return DivorceRequest.from_row(row)

    async def fetch_divorce_request(self, marriage_id: int) -> Optional[DivorceRequest]:
        row = await self._fetchone(
            "SELECT * FROM marriage_divorce_requests WHERE marriage_id = ?",
            (marriage_id,),
        )
        return DivorceRequest.from_row(row) if row else None

    async def clear_divorce_request(self, marriage_id: int) -> None:
        await self._execute(
            "DELETE FROM marriage_divorce_requests WHERE marriage_id = ?",
            (marriage_id,),
        )

    async def create_guild(
        self, name: str, description: str, owner_id: int
    ) -> Guild:
        existing_membership = await self.fetch_guild_member(owner_id)
        if existing_membership is not None:
            raise ValueError("already_in_guild")

        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    INSERT INTO guilds (name, description)
                    VALUES (?, ?)
                    """,
                    (name, description),
                )
                guild_id = cursor.lastrowid
                await self._connection.execute(
                    """
                    INSERT INTO guild_members (player_id, guild_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (owner_id, guild_id, GUILD_ROLE_MASTER),
                )
                await self._connection.commit()
            except aiosqlite.IntegrityError as exc:
                await self._connection.rollback()
                if "UNIQUE" in str(exc).upper():
                    raise ValueError("guild_name_taken") from exc
                raise
            except Exception:
                await self._connection.rollback()
                raise

        guild = await self.fetch_guild_by_id(guild_id)
        assert guild is not None
        return guild

    async def fetch_guild_by_id(self, guild_id: int) -> Optional[Guild]:
        row = await self._fetchone(
            "SELECT * FROM guilds WHERE id = ?",
            (guild_id,),
        )
        return Guild.from_row(row) if row else None

    async def fetch_guild_by_name(self, name: str) -> Optional[Guild]:
        row = await self._fetchone(
            "SELECT * FROM guilds WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        return Guild.from_row(row) if row else None

    async def fetch_guild_member(self, player_id: int) -> Optional[GuildMember]:
        row = await self._fetchone(
            "SELECT * FROM guild_members WHERE player_id = ?",
            (player_id,),
        )
        return GuildMember.from_row(row) if row else None

    async def fetch_guild_for_player(self, player_id: int) -> Optional[Guild]:
        row = await self._fetchone(
            """
            SELECT g.* FROM guilds g
            JOIN guild_members gm ON gm.guild_id = g.id
            WHERE gm.player_id = ?
            """,
            (player_id,),
        )
        return Guild.from_row(row) if row else None

    async def list_guild_members(self, guild_id: int) -> Sequence[GuildMember]:
        rows = await self._fetchall(
            """
            SELECT * FROM guild_members
            WHERE guild_id = ?
            ORDER BY
                CASE role
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                joined_at ASC
            """,
            (guild_id, GUILD_ROLE_MASTER, GUILD_ROLE_OFFICER),
        )
        return [GuildMember.from_row(row) for row in rows]

    async def update_guild_member_role(
        self, guild_id: int, player_id: int, role: str
    ) -> GuildMember:
        role = role.lower()
        if role not in GUILD_ROLES:
            raise ValueError("invalid_role")
        await self._execute(
            """
            UPDATE guild_members
            SET role = ?
            WHERE guild_id = ? AND player_id = ?
            """,
            (role, guild_id, player_id),
        )
        membership = await self.fetch_guild_member(player_id)
        if membership is None:
            raise ValueError("not_member")
        return membership

    async def add_guild_member(
        self, guild_id: int, player_id: int, role: str = GUILD_ROLE_MEMBER
    ) -> GuildMember:
        if role not in GUILD_ROLES:
            raise ValueError("invalid_role")
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                await self._connection.execute(
                    """
                    INSERT INTO guild_members (player_id, guild_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (player_id, guild_id, role),
                )
                await self._connection.execute(
                    """
                    DELETE FROM guild_invitations
                    WHERE guild_id = ? AND player_id = ?
                    """,
                    (guild_id, player_id),
                )
                await self._connection.commit()
            except aiosqlite.IntegrityError:
                await self._connection.rollback()
                raise ValueError("already_member")
            except Exception:
                await self._connection.rollback()
                raise

        membership = await self.fetch_guild_member(player_id)
        assert membership is not None
        return membership

    async def remove_guild_member(self, guild_id: int, player_id: int) -> None:
        await self._execute(
            "DELETE FROM guild_members WHERE guild_id = ? AND player_id = ?",
            (guild_id, player_id),
        )

    async def guild_member_count(self, guild_id: int) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS count FROM guild_members WHERE guild_id = ?",
            (guild_id,),
        )
        return int(row["count"]) if row else 0

    async def delete_guild(self, guild_id: int) -> None:
        await self._execute("DELETE FROM guilds WHERE id = ?", (guild_id,))

    async def apply_guild_rewards(
        self, guild_id: int, *, xp: int = 0, gold: int = 0
    ) -> Guild:
        guild = await self.fetch_guild_by_id(guild_id)
        if guild is None:
            raise ValueError("guild_missing")
        guild.xp = max(0, guild.xp + max(0, xp))
        guild.gold = max(0, guild.gold + gold)
        guild.level = guild_level_for_xp(guild.xp)
        await self._execute(
            """
            UPDATE guilds
            SET xp = ?, gold = ?, level = ?,
                created_at = created_at
            WHERE id = ?
            """,
            (guild.xp, guild.gold, guild.level, guild_id),
        )
        return guild

    async def update_guild_gold(self, guild_id: int, *, gold: int) -> Guild:
        guild = await self.fetch_guild_by_id(guild_id)
        if guild is None:
            raise ValueError("guild_missing")
        guild.gold = max(0, gold)
        await self._execute(
            "UPDATE guilds SET gold = ? WHERE id = ?",
            (guild.gold, guild_id),
        )
        return guild

    async def create_guild_invitation(
        self, guild_id: int, player_id: int, inviter_id: int
    ) -> GuildInvitation:
        await self._execute(
            """
            INSERT INTO guild_invitations (guild_id, player_id, inviter_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, player_id) DO UPDATE SET
                inviter_id = excluded.inviter_id,
                created_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """,
            (guild_id, player_id, inviter_id),
        )
        invitation = await self.fetch_guild_invitation(guild_id, player_id)
        assert invitation is not None
        return invitation

    async def fetch_guild_invitation(
        self, guild_id: int, player_id: int
    ) -> Optional[GuildInvitation]:
        row = await self._fetchone(
            """
            SELECT * FROM guild_invitations
            WHERE guild_id = ? AND player_id = ?
            """,
            (guild_id, player_id),
        )
        return GuildInvitation.from_row(row) if row else None

    async def list_guild_invitations_for_player(
        self, player_id: int
    ) -> Sequence[GuildInvitation]:
        rows = await self._fetchall(
            "SELECT * FROM guild_invitations WHERE player_id = ? ORDER BY created_at DESC",
            (player_id,),
        )
        return [GuildInvitation.from_row(row) for row in rows]

    async def delete_guild_invitation(self, guild_id: int, player_id: int) -> None:
        await self._execute(
            "DELETE FROM guild_invitations WHERE guild_id = ? AND player_id = ?",
            (guild_id, player_id),
        )

    async def set_guild_member_activity(
        self,
        guild_id: int,
        player_id: int,
        *,
        last_quest_at: Optional[datetime] = None,
        last_war_at: Optional[datetime] = None,
    ) -> GuildMember:
        updates: List[str] = []
        params: List[object] = []
        if last_quest_at is not None:
            updates.append("last_quest_at = ?")
            params.append(_format_time(last_quest_at))
        if last_war_at is not None:
            updates.append("last_war_at = ?")
            params.append(_format_time(last_war_at))
        if not updates:
            membership = await self.fetch_guild_member(player_id)
            if membership is None:
                raise ValueError("not_member")
            return membership
        params.extend([guild_id, player_id])
        await self._execute(
            f"""
            UPDATE guild_members
            SET {', '.join(updates)}
            WHERE guild_id = ? AND player_id = ?
            """,
            tuple(params),
        )
        membership = await self.fetch_guild_member(player_id)
        if membership is None:
            raise ValueError("not_member")
        return membership

    async def guild_leaderboard(self, limit: int = 10) -> Sequence[Guild]:
        rows = await self._fetchall(
            """
            SELECT * FROM guilds
            ORDER BY level DESC, xp DESC, gold DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [Guild.from_row(row) for row in rows]

    async def set_last_proposal(
        self, guild_id: int, user_id: int, when: Optional[datetime]
    ) -> None:
        await self._execute(
            """
            UPDATE players
            SET last_proposal_at = ?,
                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE user_id = ?
            """,
            (_format_time(when), user_id),
        )

    async def buy_armor(self, guild_id: int, user_id: int, armor: Armor) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    raise ValueError("player_not_found")
                if row["gold"] < armor.price:
                    raise ValueError("insufficient_gold")
                await self._connection.execute(
                    """
                    UPDATE players
                    SET gold = gold - ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (armor.price, user_id),
                )
                cursor = await self._connection.execute(
                    """
                    INSERT INTO player_inventory (
                        user_id, item_type, item_id, quantity, current_durability, is_equipped
                    ) VALUES (?, 'armor', ?, 1, NULL, 0)
                    """,
                    (user_id, armor.id),
                )
                inventory_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def buy_item(self, guild_id: int, user_id: int, item: Item) -> InventoryEntry:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT gold FROM players WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    raise ValueError("player_not_found")
                if row["gold"] < item.price:
                    raise ValueError("insufficient_gold")
                await self._connection.execute(
                    """
                    UPDATE players
                    SET gold = gold - ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (item.price, user_id),
                )
                cursor = await self._connection.execute(
                    """
                    SELECT id FROM player_inventory
                    WHERE user_id = ? AND item_type = 'item' AND item_id = ? AND expires_at IS NULL
                    """,
                    (user_id, item.id),
                )
                existing = await cursor.fetchone()
                await cursor.close()
                if existing:
                    inventory_id = existing["id"]
                    await self._connection.execute(
                        "UPDATE player_inventory SET quantity = quantity + 1 WHERE id = ?",
                        (inventory_id,),
                    )
                else:
                    cursor = await self._connection.execute(
                        """
                        INSERT INTO player_inventory (
                            user_id, item_type, item_id, quantity, current_durability, is_equipped
                        ) VALUES (?, 'item', ?, 1, NULL, 0)
                        """,
                        (user_id, item.id),
                    )
                    inventory_id = cursor.lastrowid
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

        entry = await self.fetch_inventory_entry_by_id(inventory_id)
        assert entry is not None
        return entry

    async def fetch_inventory_entry_by_id(
        self, inventory_id: int
    ) -> Optional[InventoryEntry]:
        row = await self._fetchone(
            "SELECT * FROM player_inventory WHERE id = ?",
            (inventory_id,),
        )
        return InventoryEntry.from_row(row) if row else None

    async def fetch_player_inventory(
        self, guild_id: int, user_id: int
    ) -> Dict[str, Sequence[Tuple[InventoryEntry, InventoryPayload]]]:
        await self.purge_expired_inventory(user_id)
        weapons = []
        weapon_rows = await self._fetchall(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                w.id AS weapon_id,
                w.name AS weapon_name,
                w.damage AS weapon_damage,
                w.durability AS weapon_durability,
                w.price AS weapon_price,
                w.class_restriction,
                w.rarity AS weapon_rarity,
                w.is_generic AS weapon_is_generic,
                w.event_id AS weapon_event_id
            FROM player_inventory AS pi
            JOIN weapons AS w ON w.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'weapon'
            ORDER BY w.price ASC, w.name ASC
            """,
            (user_id,),
        )
        for row in weapon_rows:
            entry = InventoryEntry.from_row(row)
            weapon = Weapon(
                id=row["weapon_id"],
                name=row["weapon_name"],
                damage=row["weapon_damage"],
                durability=row["weapon_durability"],
                price=row["weapon_price"],
                class_restriction=row["class_restriction"],
                rarity=row["weapon_rarity"],
                is_generic=bool(row["weapon_is_generic"]),
                event_id=row["weapon_event_id"],
            )
            weapons.append((entry, weapon))

        armors = []
        armor_rows = await self._fetchall(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                a.id AS armor_id,
                a.name AS armor_name,
                a.defense_boost,
                a.price AS armor_price,
                a.rarity AS armor_rarity,
                a.is_generic AS armor_is_generic
            FROM player_inventory AS pi
            JOIN armor AS a ON a.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'armor'
            ORDER BY a.price ASC, a.defense_boost DESC
            """,
            (user_id,),
        )
        for row in armor_rows:
            entry = InventoryEntry.from_row(row)
            armor = Armor(
                id=row["armor_id"],
                name=row["armor_name"],
                defense_boost=row["defense_boost"],
                price=row["armor_price"],
                rarity=row["armor_rarity"],
                is_generic=bool(row["armor_is_generic"]),
            )
            armors.append((entry, armor))

        items = []
        item_rows = await self._fetchall(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                it.id AS item_id_real,
                it.name AS item_name,
                it.effect_type,
                it.effect_value,
                it.price AS item_price,
                it.rarity AS item_rarity,
                it.effect_duration,
                it.is_generic AS item_is_generic,
                it.event_id AS item_event_id
            FROM player_inventory AS pi
            JOIN items AS it ON it.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'item'
            ORDER BY it.price ASC, it.name ASC
            """,
            (user_id,),
        )
        for row in item_rows:
            entry = InventoryEntry.from_row(row)
            item = Item(
                id=row["item_id_real"],
                name=row["item_name"],
                effect_type=row["effect_type"],
                effect_value=row["effect_value"],
                price=row["item_price"],
                rarity=row["item_rarity"],
                effect_duration=row["effect_duration"],
                is_generic=bool(row["item_is_generic"]),
                event_id=row["item_event_id"],
            )
            items.append((entry, item))

        materials = []
        material_rows = await self._fetchall(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                m.id AS material_id,
                m.name AS material_name,
                m.rarity AS material_rarity,
                m.tier AS material_tier,
                m.description AS material_description
            FROM player_inventory AS pi
            JOIN materials AS m ON m.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'material'
            ORDER BY m.tier ASC, m.name ASC
            """,
            (user_id,),
        )
        for row in material_rows:
            entry = InventoryEntry.from_row(row)
            material = Material(
                id=row["material_id"],
                name=row["material_name"],
                rarity=row["material_rarity"],
                tier=row["material_tier"],
                description=row["material_description"],
            )
            materials.append((entry, material))

        return {"weapons": weapons, "armor": armors, "items": items, "materials": materials}

    async def fetch_weapon_entry_by_name(
        self, guild_id: int, user_id: int, name: str
    ) -> Optional[Tuple[InventoryEntry, Weapon]]:
        await self.purge_expired_inventory(user_id)
        row = await self._fetchone(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                w.id AS weapon_id,
                w.name AS weapon_name,
                w.damage AS weapon_damage,
                w.durability AS weapon_durability,
                w.price AS weapon_price,
                w.class_restriction,
                w.rarity AS weapon_rarity,
                w.is_generic AS weapon_is_generic,
                w.event_id AS weapon_event_id
            FROM player_inventory AS pi
            JOIN weapons AS w ON w.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'weapon' AND LOWER(w.name) = LOWER(?)
            LIMIT 1
            """,
            (user_id, name),
        )
        if row is None:
            return None
        entry = InventoryEntry.from_row(row)
        weapon = Weapon(
            id=row["weapon_id"],
            name=row["weapon_name"],
            damage=row["weapon_damage"],
            durability=row["weapon_durability"],
            price=row["weapon_price"],
            class_restriction=row["class_restriction"],
            rarity=row["weapon_rarity"],
            is_generic=bool(row["weapon_is_generic"]),
            event_id=row["weapon_event_id"],
        )
        return entry, weapon

    async def fetch_armor_entry_by_name(
        self, guild_id: int, user_id: int, name: str
    ) -> Optional[Tuple[InventoryEntry, Armor]]:
        await self.purge_expired_inventory(user_id)
        row = await self._fetchone(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                a.id AS armor_id,
                a.name AS armor_name,
                a.defense_boost,
                a.price AS armor_price,
                a.rarity AS armor_rarity,
                a.is_generic AS armor_is_generic
            FROM player_inventory AS pi
            JOIN armor AS a ON a.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'armor' AND LOWER(a.name) = LOWER(?)
            LIMIT 1
            """,
            (user_id, name),
        )
        if row is None:
            return None
        entry = InventoryEntry.from_row(row)
        armor = Armor(
            id=row["armor_id"],
            name=row["armor_name"],
            defense_boost=row["defense_boost"],
            price=row["armor_price"],
            rarity=row["armor_rarity"],
            is_generic=bool(row["armor_is_generic"]),
        )
        return entry, armor

    async def fetch_item_entry_by_name(
        self, guild_id: int, user_id: int, name: str
    ) -> Optional[Tuple[InventoryEntry, Item]]:
        await self.purge_expired_inventory(user_id)
        row = await self._fetchone(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                it.id AS item_id_real,
                it.name AS item_name,
                it.effect_type,
                it.effect_value,
                it.price AS item_price,
                it.rarity AS item_rarity,
                it.effect_duration,
                it.is_generic AS item_is_generic,
                it.event_id AS item_event_id
            FROM player_inventory AS pi
            JOIN items AS it ON it.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'item' AND LOWER(it.name) = LOWER(?)
            LIMIT 1
            """,
            (user_id, name),
        )
        if row is None:
            return None
        entry = InventoryEntry.from_row(row)
        item = Item(
            id=row["item_id_real"],
            name=row["item_name"],
            effect_type=row["effect_type"],
            effect_value=row["effect_value"],
            price=row["item_price"],
            rarity=row["item_rarity"],
            effect_duration=row["effect_duration"],
            is_generic=bool(row["item_is_generic"]),
            event_id=row["item_event_id"],
        )
        return entry, item

    async def fetch_material_entry_by_name(
        self, guild_id: int, user_id: int, name: str
    ) -> Optional[Tuple[InventoryEntry, Material]]:
        await self.purge_expired_inventory(user_id)
        row = await self._fetchone(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                m.id AS material_id,
                m.name AS material_name,
                m.rarity AS material_rarity,
                m.tier AS material_tier,
                m.description AS material_description
            FROM player_inventory AS pi
            JOIN materials AS m ON m.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'material' AND LOWER(m.name) = LOWER(?)
            LIMIT 1
            """,
            (user_id, name),
        )
        if row is None:
            return None
        entry = InventoryEntry.from_row(row)
        material = Material(
            id=row["material_id"],
            name=row["material_name"],
            rarity=row["material_rarity"],
            tier=row["material_tier"],
            description=row["material_description"],
        )
        return entry, material

    async def remove_inventory_quantity(
        self, guild_id: int, user_id: int, entry: InventoryEntry, quantity: int
    ) -> int:
        if quantity <= 0:
            raise ValueError("invalid_quantity")
        if entry.user_id != user_id:
            raise ValueError("wrong_owner")
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    SELECT quantity, is_equipped
                    FROM player_inventory
                    WHERE id = ? AND user_id = ?
                    """,
                    (entry.id, user_id),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    raise ValueError("entry_not_found")
                current_quantity = int(row["quantity"])
                if int(row["is_equipped"]) != 0:
                    raise ValueError("item_equipped")
                if current_quantity < quantity:
                    raise ValueError("insufficient_quantity")

                remaining = current_quantity - quantity
                if remaining > 0:
                    await self._connection.execute(
                        "UPDATE player_inventory SET quantity = ? WHERE id = ?",
                        (remaining, entry.id),
                    )
                else:
                    await self._connection.execute(
                        "DELETE FROM player_inventory WHERE id = ?",
                        (entry.id,),
                    )
                    if entry.item_type == "weapon":
                        await self._connection.execute(
                            """
                            UPDATE players
                            SET equipped_weapon_id = CASE
                                WHEN equipped_weapon_id = ? THEN NULL
                                ELSE equipped_weapon_id
                            END,
                                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                            WHERE user_id = ?
                            """,
                            (entry.id, user_id),
                        )
                    elif entry.item_type == "armor":
                        await self._connection.execute(
                            """
                            UPDATE players
                            SET equipped_armor_id = CASE
                                WHEN equipped_armor_id = ? THEN NULL
                                ELSE equipped_armor_id
                            END,
                                updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                            WHERE user_id = ?
                            """,
                            (entry.id, user_id),
                        )

                await self._connection.commit()
                return remaining
            except Exception:
                await self._connection.rollback()
                raise

    async def fetch_player_materials(
        self, guild_id: int, user_id: int
    ) -> Sequence[Tuple[InventoryEntry, Material]]:
        await self.purge_expired_inventory(user_id)
        rows = await self._fetchall(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                m.id AS material_id,
                m.name AS material_name,
                m.rarity AS material_rarity,
                m.tier AS material_tier,
                m.description AS material_description
            FROM player_inventory AS pi
            JOIN materials AS m ON m.id = pi.item_id
            WHERE pi.user_id = ? AND pi.item_type = 'material'
            ORDER BY m.tier ASC, m.name ASC
            """,
            (user_id,),
        )
        results: List[Tuple[InventoryEntry, Material]] = []
        for row in rows:
            entry = InventoryEntry.from_row(row)
            material = Material(
                id=row["material_id"],
                name=row["material_name"],
                rarity=row["material_rarity"],
                tier=row["material_tier"],
                description=row["material_description"],
            )
            results.append((entry, material))
        return results

    async def consume_materials(
        self, guild_id: int, user_id: int, material: Material, quantity: int
    ) -> None:
        if quantity <= 0:
            return
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    SELECT id, quantity FROM player_inventory
                    WHERE user_id = ? AND item_type = 'material' AND item_id = ?
                    """,
                    (user_id, material.id),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None or row["quantity"] < quantity:
                    raise ValueError("insufficient_materials")

                remaining = row["quantity"] - quantity
                if remaining > 0:
                    await self._connection.execute(
                        "UPDATE player_inventory SET quantity = ? WHERE id = ?",
                        (remaining, row["id"]),
                    )
                else:
                    await self._connection.execute(
                        "DELETE FROM player_inventory WHERE id = ?",
                        (row["id"],),
                    )

                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

    async def equip_weapon(
        self, guild_id: int, user_id: int, entry: InventoryEntry
    ) -> None:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                await self._connection.execute(
                    "UPDATE player_inventory SET is_equipped = 0 WHERE user_id = ? AND item_type = 'weapon'",
                    (user_id,),
                )
                await self._connection.execute(
                    "UPDATE player_inventory SET is_equipped = 1 WHERE id = ?",
                    (entry.id,),
                )
                await self._connection.execute(
                    """
                    UPDATE players
                    SET equipped_weapon_id = ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (entry.id, user_id),
                )
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

    async def equip_armor(
        self, guild_id: int, user_id: int, entry: InventoryEntry
    ) -> None:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                await self._connection.execute(
                    "UPDATE player_inventory SET is_equipped = 0 WHERE user_id = ? AND item_type = 'armor'",
                    (user_id,),
                )
                await self._connection.execute(
                    "UPDATE player_inventory SET is_equipped = 1 WHERE id = ?",
                    (entry.id,),
                )
                await self._connection.execute(
                    """
                    UPDATE players
                    SET equipped_armor_id = ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (entry.id, user_id),
                )
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

    async def unequip_weapon(self, guild_id: int, user_id: int) -> None:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                await self._connection.execute(
                    "UPDATE player_inventory SET is_equipped = 0 WHERE user_id = ? AND item_type = 'weapon'",
                    (user_id,),
                )
                await self._connection.execute(
                    """
                    UPDATE players
                    SET equipped_weapon_id = NULL, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

    async def unequip_armor(self, guild_id: int, user_id: int) -> None:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                await self._connection.execute(
                    "UPDATE player_inventory SET is_equipped = 0 WHERE user_id = ? AND item_type = 'armor'",
                    (user_id,),
                )
                await self._connection.execute(
                    """
                    UPDATE players
                    SET equipped_armor_id = NULL, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise

    async def fetch_equipped_weapon(
        self, guild_id: int, user_id: int
    ) -> Optional[Tuple[InventoryEntry, Weapon]]:
        await self.purge_expired_inventory(user_id)
        row = await self._fetchone(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                w.id AS weapon_id,
                w.name AS weapon_name,
                w.damage AS weapon_damage,
                w.durability AS weapon_durability,
                w.price AS weapon_price,
                w.class_restriction,
                w.rarity AS weapon_rarity,
                w.is_generic AS weapon_is_generic,
                w.event_id AS weapon_event_id
            FROM players AS p
            JOIN player_inventory AS pi ON pi.id = p.equipped_weapon_id
            JOIN weapons AS w ON w.id = pi.item_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        )
        if row is None:
            return None
        entry = InventoryEntry.from_row(row)
        weapon = Weapon(
            id=row["weapon_id"],
            name=row["weapon_name"],
            damage=row["weapon_damage"],
            durability=row["weapon_durability"],
            price=row["weapon_price"],
            class_restriction=row["class_restriction"],
            rarity=row["weapon_rarity"],
            is_generic=bool(row["weapon_is_generic"]),
            event_id=row["weapon_event_id"],
        )
        return entry, weapon

    async def fetch_equipped_armor(
        self, guild_id: int, user_id: int
    ) -> Optional[Tuple[InventoryEntry, Armor]]:
        await self.purge_expired_inventory(user_id)
        row = await self._fetchone(
            """
            SELECT
                pi.id,
                pi.user_id,
                pi.item_type,
                pi.item_id,
                pi.quantity,
                pi.current_durability,
                pi.is_equipped,
                pi.expires_at,
                a.id AS armor_id,
                a.name AS armor_name,
                a.defense_boost,
                a.price AS armor_price,
                a.rarity AS armor_rarity,
                a.is_generic AS armor_is_generic
            FROM players AS p
            JOIN player_inventory AS pi ON pi.id = p.equipped_armor_id
            JOIN armor AS a ON a.id = pi.item_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        )
        if row is None:
            return None
        entry = InventoryEntry.from_row(row)
        armor = Armor(
            id=row["armor_id"],
            name=row["armor_name"],
            defense_boost=row["defense_boost"],
            price=row["armor_price"],
            rarity=row["armor_rarity"],
            is_generic=bool(row["armor_is_generic"]),
        )
        return entry, armor

    async def reduce_equipped_weapon_durability(
        self, guild_id: int, user_id: int, amount: int
    ) -> Optional[DurabilityChange]:
        if amount <= 0:
            return None
        await self.purge_expired_inventory(user_id)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    """
                    SELECT
                        pi.id,
                        pi.current_durability,
                        w.id AS weapon_id,
                        w.name AS weapon_name,
                        w.damage AS weapon_damage,
                        w.durability AS weapon_durability,
                        w.price AS weapon_price,
                        w.class_restriction,
                        w.rarity AS weapon_rarity,
                        w.is_generic AS weapon_is_generic,
                        w.event_id AS weapon_event_id
                    FROM players AS p
                    JOIN player_inventory AS pi ON pi.id = p.equipped_weapon_id
                    JOIN weapons AS w ON w.id = pi.item_id
                    WHERE p.user_id = ?
                    """,
                    (user_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    await self._connection.rollback()
                    return None
                current = row["current_durability"]
                if current is None:
                    await self._connection.rollback()
                    return None
                new_durability = max(0, current - amount)
                weapon = Weapon(
                    id=row["weapon_id"],
                    name=row["weapon_name"],
                    damage=row["weapon_damage"],
                    durability=row["weapon_durability"],
                    price=row["weapon_price"],
                    class_restriction=row["class_restriction"],
                    rarity=row["weapon_rarity"],
                    is_generic=bool(row["weapon_is_generic"]),
                    event_id=row["weapon_event_id"],
                )
                if new_durability <= 0:
                    await self._connection.execute(
                        "DELETE FROM player_inventory WHERE id = ?",
                        (row["id"],),
                    )
                    await self._connection.execute(
                        """
                        UPDATE players
                        SET equipped_weapon_id = NULL, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                        WHERE user_id = ?
                        """,
                        (user_id,),
                    )
                    await self._connection.commit()
                    return DurabilityChange(weapon=weapon, durability=0, broken=True)
                await self._connection.execute(
                    "UPDATE player_inventory SET current_durability = ? WHERE id = ?",
                    (new_durability, row["id"]),
                )
                await self._connection.commit()
                return DurabilityChange(
                    weapon=weapon,
                    durability=new_durability,
                    broken=False,
                )
            except Exception:
                await self._connection.rollback()
                raise

    async def use_item(
        self, guild_id: int, user_id: int, entry: InventoryEntry, item: Item
    ) -> ItemUseResult:
        await self.purge_expired_inventory(user_id)
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                cursor = await self._connection.execute(
                    "SELECT * FROM players WHERE user_id = ?",
                    (user_id,),
                )
                player_row = await cursor.fetchone()
                await cursor.close()
                if player_row is None:
                    raise ValueError("player_not_found")
                player = Player.from_row(player_row)
                if entry.quantity <= 0:
                    raise ValueError("no_quantity")

                healed = 0
                energy = 0
                attack_buff: Optional[Tuple[int, int]] = None
                defense_buff: Optional[Tuple[int, int]] = None

                if item.effect_type == "heal_hp":
                    missing = max(0, player.max_hp - player.hp)
                    if missing <= 0:
                        raise ValueError("no_effect")
                    healed = min(item.effect_value, missing)
                    player.hp += healed
                elif item.effect_type == "restore_mana":
                    missing = max(0, 100 - player.energy)
                    if missing <= 0:
                        raise ValueError("no_effect")
                    energy = min(item.effect_value, missing)
                    player.energy += energy
                elif item.effect_type == "buff_attack":
                    duration = item.effect_duration or 3
                    player.attack_buff_percent = item.effect_value
                    player.attack_buff_battles = duration
                    attack_buff = (item.effect_value, duration)
                elif item.effect_type == "buff_defense":
                    duration = item.effect_duration or 3
                    player.defense_buff_percent = item.effect_value
                    player.defense_buff_battles = duration
                    defense_buff = (item.effect_value, duration)

                if healed == 0 and energy == 0 and attack_buff is None and defense_buff is None:
                    # Still consume the item if it is a buff type
                    pass

                if entry.quantity > 1:
                    await self._connection.execute(
                        "UPDATE player_inventory SET quantity = quantity - 1 WHERE id = ?",
                        (entry.id,),
                    )
                    remaining = entry.quantity - 1
                else:
                    await self._connection.execute(
                        "DELETE FROM player_inventory WHERE id = ?",
                        (entry.id,),
                    )
                    remaining = 0

                await self._connection.execute(
                    """
                    UPDATE players
                    SET hp = ?, energy = ?, attack_buff_percent = ?, attack_buff_battles = ?,
                        defense_buff_percent = ?, defense_buff_battles = ?,
                        updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    WHERE user_id = ?
                    """,
                    (
                        player.hp,
                        player.energy,
                        player.attack_buff_percent,
                        player.attack_buff_battles,
                        player.defense_buff_percent,
                        player.defense_buff_battles,
                        user_id,
                    ),
                )

                await self._connection.commit()
                return ItemUseResult(
                    item=item,
                    healed=healed,
                    energy_restored=energy,
                    attack_buff=attack_buff,
                    defense_buff=defense_buff,
                    quantity_remaining=remaining,
                )
            except Exception:
                await self._connection.rollback()
                raise

    async def _get_listing_payload(
        self, listing: AuctionListing
    ) -> Optional[InventoryPayload]:
        if listing.item_type == "weapon":
            return await self.fetch_weapon_by_id(listing.item_id)
        if listing.item_type == "armor":
            return await self.fetch_armor_by_id(listing.item_id)
        if listing.item_type == "item":
            return await self.fetch_item_by_id(listing.item_id)
        if listing.item_type == "material":
            return await self.fetch_material_by_id(listing.item_id)
        return None

    async def _transfer_listing_item(
        self, user_id: int, listing: AuctionListing
    ) -> InventoryPayload:
        assert self._connection is not None

        expires_value = _format_time(listing.item_expires_at)
        quantity = max(1, listing.quantity)

        if listing.item_type == "weapon":
            cursor = await self._connection.execute(
                "SELECT * FROM weapons WHERE id = ?",
                (listing.item_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                raise ValueError("item_missing")
            payload = Weapon.from_row(row)
            durability = (
                listing.current_durability
                if listing.current_durability is not None
                else payload.durability
            )
            await self._connection.execute(
                """
                INSERT INTO player_inventory (
                    user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                ) VALUES (?, 'weapon', ?, 1, ?, 0, ?)
                """,
                (user_id, payload.id, max(0, durability), expires_value),
            )
            return payload

        if listing.item_type == "armor":
            cursor = await self._connection.execute(
                "SELECT * FROM armor WHERE id = ?",
                (listing.item_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                raise ValueError("item_missing")
            payload = Armor.from_row(row)
            await self._connection.execute(
                """
                INSERT INTO player_inventory (
                    user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                ) VALUES (?, 'armor', ?, 1, NULL, 0, ?)
                """,
                (user_id, payload.id, expires_value),
            )
            return payload

        if listing.item_type == "item":
            cursor = await self._connection.execute(
                "SELECT * FROM items WHERE id = ?",
                (listing.item_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                raise ValueError("item_missing")
            payload = Item.from_row(row)
            cursor = await self._connection.execute(
                """
                SELECT id FROM player_inventory
                WHERE user_id = ? AND item_type = 'item' AND item_id = ?
                    AND ((? IS NULL AND expires_at IS NULL) OR expires_at = ?)
                """,
                (user_id, payload.id, expires_value, expires_value),
            )
            existing = await cursor.fetchone()
            await cursor.close()
            if existing is None:
                await self._connection.execute(
                    """
                    INSERT INTO player_inventory (
                        user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                    ) VALUES (?, 'item', ?, ?, NULL, 0, ?)
                    """,
                    (user_id, payload.id, quantity, expires_value),
                )
            else:
                await self._connection.execute(
                    "UPDATE player_inventory SET quantity = quantity + ? WHERE id = ?",
                    (quantity, existing["id"]),
                )
            return payload

        if listing.item_type == "material":
            cursor = await self._connection.execute(
                "SELECT * FROM materials WHERE id = ?",
                (listing.item_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                raise ValueError("item_missing")
            payload = Material.from_row(row)
            cursor = await self._connection.execute(
                """
                SELECT id FROM player_inventory
                WHERE user_id = ? AND item_type = 'material' AND item_id = ?
                """,
                (user_id, payload.id),
            )
            existing = await cursor.fetchone()
            await cursor.close()
            if existing is None:
                await self._connection.execute(
                    """
                    INSERT INTO player_inventory (
                        user_id, item_type, item_id, quantity, current_durability, is_equipped, expires_at
                    ) VALUES (?, 'material', ?, ?, NULL, 0, NULL)
                    """,
                    (user_id, payload.id, quantity),
                )
            else:
                await self._connection.execute(
                    "UPDATE player_inventory SET quantity = quantity + ? WHERE id = ?",
                    (quantity, existing["id"]),
                )
            return payload

        raise ValueError("item_missing")

    async def _execute(self, query: str, parameters: Sequence[object] = ()) -> None:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute(query, parameters)
            await self._connection.commit()

    async def _fetchone(
        self, query: str, parameters: Sequence[object] = ()
    ) -> Optional[aiosqlite.Row]:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            cursor = await self._connection.execute(query, parameters)
            row = await cursor.fetchone()
            await cursor.close()
            return row

    async def _fetchall(
        self, query: str, parameters: Sequence[object] = ()
    ) -> Sequence[aiosqlite.Row]:
        await self.connect()
        assert self._connection is not None
        async with self._lock:
            cursor = await self._connection.execute(query, parameters)
            rows = await cursor.fetchall()
            await cursor.close()
            return rows


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.strptime(value, ISO_FORMAT).replace(tzinfo=timezone.utc)


def _format_time(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).strftime(ISO_FORMAT)
