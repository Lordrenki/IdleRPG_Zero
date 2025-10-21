"""Discord bot implementation for IdleRPG Zero."""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MethodType, SimpleNamespace
from typing import Dict, List, Optional, Sequence, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from .config import Settings
from .database import (
    AuctionListing,
    Achievement,
    Armor,
    Database,
    DivorceRequest,
    DurabilityChange,
    Guild,
    GuildMember,
    GUILD_ROLE_MASTER,
    GUILD_ROLE_MEMBER,
    GUILD_ROLE_OFFICER,
    InventoryEntry,
    InventoryPayload,
    Item,
    Material,
    Marriage,
    MarriageProposal,
    Player,
    RaidBoss,
    RaidInstance,
    RaidParticipant,
    ShopRotationEntry,
    Weapon,
)
from .embeds import (
    achievements_embed,
    class_info_embed,
    cooldown_embed,
    duel_result_embed,
    error_embed,
    event_info_embed,
    event_join_embed,
    guild_info_embed,
    guild_leaderboard_embed,
    heal_embed,
    leaderboard_embed,
    global_leaderboard_embed,
    PRIMARY_COLOR,
    SUCCESS_COLOR,
    profile_embed,
    quest_list_embed,
    quest_story_embed,
    raid_attack_embed,
    raid_join_embed,
    raid_leaderboard_embed,
    raid_spawn_embed,
    rest_embed,
    work_result_embed,
)
from .progression import (
    apply_xp_and_gold,
    can_quest,
    can_raid,
    can_rest,
    can_work,
    effective_attack,
    effective_defense,
    energy_ready,
    active_quest_remaining,
    heal_player,
    perform_quest,
    perform_work,
    rest_player,
    RAID_ENERGY_COST,
)
from .quests import (
    QuestDefinition,
    QuestMaterialReward,
    QuestProgress,
    all_quests,
    find_quest,
    random_adventure_quest,
    roll_random_encounter,
    search_quests,
)


CLASS_CHOICES = [
    app_commands.Choice(name="Warrior", value="1"),
    app_commands.Choice(name="Mage", value="2"),
    app_commands.Choice(name="Ranger", value="3"),
    app_commands.Choice(name="Rogue", value="4"),
    app_commands.Choice(name="Paladin", value="5"),
]

PROPOSAL_COOLDOWN = timedelta(hours=1)
COUPLE_XP_BONUS = 0.05
COUPLE_GOLD_BONUS = 0.05
ANNIVERSARY_DROP_CHANCE = 0.1
GUILD_QUEST_COOLDOWN = timedelta(hours=6)
GUILD_QUEST_ENERGY_COST = 30
GUILD_WAR_COOLDOWN = timedelta(hours=12)

log = logging.getLogger(__name__)


class IdleRPGBot(commands.Bot):
    """Discord bot with slash commands for the IdleRPG experience."""

    def __init__(self, *, database: Database, settings: Settings, intents: discord.Intents):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.database = database
        self.settings = settings

    async def setup_hook(self) -> None:
        await self.database.connect()
        try:
            await self.tree.sync()
        except discord.HTTPException as exc:
            log.warning('Failed to sync commands: %s', exc)
        log.info('Slash commands ready')

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)
        await self.change_presence(activity=discord.Game(name=self.settings.activity_text))

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            await self.database.close()


def create_bot(settings: Settings) -> IdleRPGBot:
    intents = discord.Intents.default()
    intents.members = True
    database = Database(settings.database_path)
    bot = IdleRPGBot(database=database, settings=settings, intents=intents)

    PAGE_SIZE = 5

    MATERIAL_DROP_CONFIG = {
        "quest": {
            "chance": 0.7,
            "rolls": (1, 1),
            "quantity": (1, 2),
            "weights": (
                ("common", 0.55),
                ("uncommon", 0.3),
                ("rare", 0.12),
                ("epic", 0.03),
            ),
        },
        "raid": {
            "chance": 0.95,
            "rolls": (2, 3),
            "quantity": (1, 3),
            "weights": (
                ("uncommon", 0.4),
                ("rare", 0.35),
                ("epic", 0.2),
                ("legendary", 0.05),
            ),
        },
    }

    CRAFTING_RECIPES = {
        "common": {
            "tier": 1,
            "materials": 4,
            "success": 0.85,
            "weapon_damage": (12, 16),
            "weapon_durability": (80, 120),
            "armor_defense": (6, 10),
            "price": (90, 150),
        },
        "uncommon": {
            "tier": 2,
            "materials": 6,
            "success": 0.75,
            "weapon_damage": (18, 24),
            "weapon_durability": (110, 150),
            "armor_defense": (11, 17),
            "price": (160, 230),
        },
        "rare": {
            "tier": 3,
            "materials": 8,
            "success": 0.6,
            "weapon_damage": (24, 32),
            "weapon_durability": (150, 200),
            "armor_defense": (18, 26),
            "price": (240, 340),
        },
        "epic": {
            "tier": 4,
            "materials": 10,
            "success": 0.45,
            "weapon_damage": (32, 44),
            "weapon_durability": (190, 240),
            "armor_defense": (27, 36),
            "price": (360, 520),
        },
        "legendary": {
            "tier": 5,
            "materials": 12,
            "success": 0.3,
            "weapon_damage": (42, 58),
            "weapon_durability": (230, 300),
            "armor_defense": (38, 50),
            "price": (520, 700),
        },
    }

    RARITY_CHOICES = [
        app_commands.Choice(name="Common", value="common"),
        app_commands.Choice(name="Uncommon", value="uncommon"),
        app_commands.Choice(name="Rare", value="rare"),
        app_commands.Choice(name="Epic", value="epic"),
        app_commands.Choice(name="Legendary", value="legendary"),
    ]

    SHOP_ROTATION_DURATION = timedelta(hours=24)
    SHOP_ROTATION_COUNTS: Dict[str, int] = {
        "weapon": 3,
        "armor": 2,
        "item": 3,
    }
    SHOP_ROTATION_RARITY_WEIGHTS: Dict[str, Sequence[Tuple[str, float]]] = {
        "weapon": (("common", 0.55), ("rare", 0.3), ("epic", 0.15)),
        "armor": (("common", 0.6), ("rare", 0.28), ("epic", 0.12)),
        "item": (("common", 0.5), ("rare", 0.35), ("epic", 0.15)),
    }
    SHOP_ROTATION_CATEGORY_LABELS = {
        "weapon": "Weapons",
        "armor": "Armor",
        "item": "Potions & Trinkets",
    }

    def paginate_collections(
        collections: Sequence[Sequence], page: int, page_size: int = PAGE_SIZE
    ) -> Tuple[int, int, Sequence[Sequence]]:
        page_size = max(1, page_size)
        totals = [len(collection) for collection in collections]
        max_pages = max([math.ceil(total / page_size) for total in totals if total] or [1])
        page = max(1, min(page, max_pages))
        start = (page - 1) * page_size
        end = start + page_size
        sliced = [collection[start:end] for collection in collections]
        return page, max_pages, sliced

    def format_weapon(weapon: Weapon) -> str:
        restriction = f" (Class: {weapon.class_restriction})" if weapon.class_restriction else ""
        return (
            f"**{weapon.name}** — DMG {weapon.damage} • DUR {weapon.durability}"
            f" • 💰 {weapon.price}{restriction}"
        )

    def format_armor(armor: Armor) -> str:
        return f"**{armor.name}** — DEF +{armor.defense_boost} • 💰 {armor.price}"

    def describe_item_effect(item: Item) -> str:
        if item.effect_type == "heal_hp":
            return f"Restores {item.effect_value} HP"
        if item.effect_type == "restore_mana":
            return f"Restores {item.effect_value} energy"
        if item.effect_type == "buff_attack":
            duration = item.effect_duration or 3
            return f"+{item.effect_value}% attack for {duration} battles"
        if item.effect_type == "buff_defense":
            duration = item.effect_duration or 3
            return f"+{item.effect_value}% defense for {duration} battles"
        if item.effect_type == "vanity":
            return "Luxury collectible (no gameplay effect)"
        return "Consumable"

    def format_item(item: Item) -> str:
        return (
            f"**{item.name}** — {describe_item_effect(item)}"
            f" • 💰 {item.price}"
        )

    def rarity_label(rarity: str) -> str:
        return rarity.replace("_", " ").title()

    def format_rotation_weapon(entry: ShopRotationEntry, weapon: Weapon) -> str:
        restriction = f" • Class: {weapon.class_restriction}" if weapon.class_restriction else ""
        return (
            f"**{weapon.name}** [{rarity_label(entry.rarity)}] — DMG {weapon.damage}"
            f" • DUR {weapon.durability} • 💰 {weapon.price}{restriction}"
        )

    def format_rotation_armor(entry: ShopRotationEntry, armor: Armor) -> str:
        return (
            f"**{armor.name}** [{rarity_label(entry.rarity)}] — DEF +{armor.defense_boost}"
            f" • 💰 {armor.price}"
        )

    def format_rotation_item(entry: ShopRotationEntry, item: Item) -> str:
        return (
            f"**{item.name}** [{rarity_label(entry.rarity)}] — {describe_item_effect(item)}"
            f" • 💰 {item.price}"
        )

    AUCTION_TYPE_LABELS = {
        "weapon": "Weapon",
        "armor": "Armor",
        "item": "Consumable",
        "material": "Material",
    }

    def auction_listing_detail(listing: AuctionListing, payload: InventoryPayload) -> str:
        if isinstance(payload, Weapon):
            current = (
                listing.current_durability
                if listing.current_durability is not None
                else payload.durability
            )
            durability_text = (
                f"DUR {current}/{payload.durability}"
                if listing.current_durability is not None
                else f"DUR {payload.durability}"
            )
            return f"DMG {payload.damage} • {durability_text}"
        if isinstance(payload, Armor):
            return f"DEF +{payload.defense_boost}"
        if isinstance(payload, Item):
            return describe_item_effect(payload)
        assert isinstance(payload, Material)
        return f"Tier {payload.tier} • {payload.rarity.title()}"

    def format_auction_listing_entry(
        listing: AuctionListing, payload: InventoryPayload
    ) -> str:
        type_label = AUCTION_TYPE_LABELS.get(
            listing.item_type, listing.item_type.title()
        )
        name = getattr(payload, "name", "Unknown Item")
        quantity_suffix = (
            f" ×{listing.quantity}"
            if listing.quantity > 1 and listing.item_type in {"item", "material"}
            else ""
        )
        header = f"**ID {listing.id} — {name}{quantity_suffix}** ({type_label})"
        expires_text = discord.utils.format_dt(listing.expires_at, style="R")
        detail = auction_listing_detail(listing, payload)
        info_line = (
            f"{detail}\nPrice: 💰 {listing.price} • Seller: <@{listing.seller_id}>"
            f" • Expires {expires_text}"
        )
        return f"{header}\n{info_line}"

    async def generate_shop_rotation() -> Sequence[Tuple[str, int, str]]:
        rotation: List[Tuple[str, int, str]] = []
        pools = {
            "weapon": list(await bot.database.list_shop_weapons()),
            "armor": list(await bot.database.list_shop_armor()),
            "item": list(await bot.database.list_shop_items()),
        }

        for item_type, items in pools.items():
            if not items:
                continue
            desired = SHOP_ROTATION_COUNTS.get(item_type, 0)
            if desired <= 0:
                continue
            chosen_ids: set[int] = set()
            weights = SHOP_ROTATION_RARITY_WEIGHTS.get(item_type, ())
            for _ in range(desired):
                available = [item for item in items if item.id not in chosen_ids]
                if not available:
                    break
                rarity_choice = weighted_choice(weights) if weights else None
                if rarity_choice is not None:
                    candidates = [
                        item
                        for item in available
                        if item.rarity.lower() == rarity_choice
                    ]
                else:
                    candidates = []
                if not candidates:
                    candidates = available
                selected = random.choice(candidates)
                chosen_ids.add(selected.id)
                rotation.append((item_type, selected.id, selected.rarity.lower()))
        return rotation

    async def ensure_shop_rotation(force: bool = False) -> Sequence[ShopRotationEntry]:
        now = datetime.now(timezone.utc)
        existing = await bot.database.get_active_shop_rotation_entries()
        if not force and existing:
            expiry = min(entry.expires_at for entry in existing)
            categories_ok = True
            for category, count in SHOP_ROTATION_COUNTS.items():
                if count <= 0:
                    continue
                if any(entry.item_type == category for entry in existing):
                    continue
                categories_ok = False
                break
            if expiry > now and categories_ok:
                return existing

        rotation = await generate_shop_rotation()
        await bot.database.replace_shop_rotation(
            rotation,
            featured_at=now,
            expires_at=now + SHOP_ROTATION_DURATION,
        )
        return await bot.database.get_active_shop_rotation_entries()

    async def shop_rotation_scheduler() -> None:
        try:
            while True:
                try:
                    await ensure_shop_rotation()
                    expiry = await bot.database.get_shop_rotation_expiry()
                    if expiry is None:
                        sleep_seconds = SHOP_ROTATION_DURATION.total_seconds()
                    else:
                        sleep_seconds = max(
                            60.0,
                            (expiry - datetime.now(timezone.utc)).total_seconds(),
                        )
                except Exception:
                    log.exception("Failed to refresh shop rotation")
                    sleep_seconds = 3600.0
                await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            pass

    async def start_shop_rotation_scheduler() -> None:
        await ensure_shop_rotation()
        task = getattr(bot, "shop_rotation_task", None)
        if task is not None and not task.done():
            return
        bot.shop_rotation_task = bot.loop.create_task(shop_rotation_scheduler())

    async def restart_shop_rotation_scheduler() -> None:
        task = getattr(bot, "shop_rotation_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            bot.shop_rotation_task = None
        await start_shop_rotation_scheduler()

    bot.shop_rotation_task: Optional[asyncio.Task] = None

    original_setup_hook = bot.setup_hook

    async def setup_hook_with_rotation(self: IdleRPGBot) -> None:
        await original_setup_hook()
        await start_shop_rotation_scheduler()

    bot.setup_hook = MethodType(setup_hook_with_rotation, bot)

    original_close = bot.close

    async def close_with_rotation(self: IdleRPGBot) -> None:
        task = getattr(self, "shop_rotation_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.shop_rotation_task = None
        await original_close()

    bot.close = MethodType(close_with_rotation, bot)

    def format_inventory_weapon(entry: Tuple[InventoryEntry, Weapon]) -> str:
        inv, weapon = entry
        durability = (
            f"Durability {inv.current_durability}/{weapon.durability}"
            if inv.current_durability is not None
            else ""
        )
        status = " (Equipped)" if inv.is_equipped else ""
        parts = [f"**{weapon.name}** — DMG {weapon.damage}"]
        if durability:
            parts.append(durability)
        if inv.expires_at:
            parts.append(
                f"Expires {discord.utils.format_dt(inv.expires_at, style='R')}"
            )
        return " • ".join(parts) + status

    def format_inventory_armor(entry: Tuple[InventoryEntry, Armor]) -> str:
        inv, armor = entry
        status = " (Equipped)" if inv.is_equipped else ""
        expiry = (
            f" — expires {discord.utils.format_dt(inv.expires_at, style='R')}"
            if inv.expires_at
            else ""
        )
        return f"**{armor.name}** — DEF +{armor.defense_boost}{status}{expiry}"

    def format_inventory_item(entry: Tuple[InventoryEntry, Item]) -> str:
        inv, item = entry
        effect = describe_item_effect(item)
        expiry = (
            f" — expires {discord.utils.format_dt(inv.expires_at, style='R')}"
            if inv.expires_at
            else ""
        )
        return f"**{item.name}** ×{inv.quantity} — {effect}{expiry}"

    def format_inventory_material(entry: Tuple[InventoryEntry, Material]) -> str:
        inv, material = entry
        rarity = material.rarity.title()
        expiry = (
            f" — expires {discord.utils.format_dt(inv.expires_at, style='R')}"
            if inv.expires_at
            else ""
        )
        return (
            f"**{material.name}** ×{inv.quantity} — {rarity} (Tier {material.tier})"
            f"{expiry}"
        )

    def weighted_choice(weights: Sequence[Tuple[str, float]]) -> str:
        total = sum(weight for _, weight in weights)
        roll = random.random() * total
        cumulative = 0.0
        for value, weight in weights:
            cumulative += weight
            if roll <= cumulative:
                return value
        return weights[-1][0]

    async def roll_material_rewards(
        source: str, guild_id: int, user_id: int
    ) -> Sequence[Tuple[Material, int]]:
        config = MATERIAL_DROP_CONFIG.get(source)
        if config is None:
            return []
        if random.random() > config["chance"]:
            return []

        rolls = random.randint(config["rolls"][0], config["rolls"][1])
        material_cache: dict[str, Sequence[Material]] = {}
        fallback_materials: Optional[Sequence[Material]] = None
        rewards: list[Tuple[Material, int]] = []

        async def get_materials_for_rarity(rarity: str) -> Sequence[Material]:
            if rarity not in material_cache:
                material_cache[rarity] = await bot.database.list_materials_by_rarity(rarity)
            return material_cache[rarity]

        for _ in range(rolls):
            rarity = weighted_choice(config["weights"])
            materials = list(await get_materials_for_rarity(rarity))
            if not materials:
                if fallback_materials is None:
                    fallback_materials = await bot.database.list_materials()
                materials = list(fallback_materials or [])
            if not materials:
                continue
            material = random.choice(materials)
            quantity = random.randint(config["quantity"][0], config["quantity"][1])
            await bot.database.grant_material_to_player(guild_id, user_id, material, quantity)
            rewards.append((material, quantity))
        return rewards

    async def gather_crafting_materials(
        guild_id: int, user_id: int, required_tier: int, required_quantity: int
    ) -> Optional[Sequence[Tuple[Material, int]]]:
        inventory = await bot.database.fetch_player_materials(guild_id, user_id)
        eligible = [
            (material, entry.quantity)
            for entry, material in sorted(
                inventory, key=lambda pair: (pair[1].tier, pair[0].id)
            )
            if material.tier >= required_tier
        ]
        total = sum(quantity for _, quantity in eligible)
        if total < required_quantity:
            return None

        remaining = required_quantity
        selections: list[Tuple[Material, int]] = []
        for material, quantity in eligible:
            take = min(quantity, remaining)
            if take > 0:
                selections.append((material, take))
                remaining -= take
            if remaining <= 0:
                break
        return selections

    def summarize_materials(materials: Sequence[Tuple[Material, int]]) -> str:
        if not materials:
            return "None"
        return ", ".join(f"{quantity}× {material.name}" for material, quantity in materials)

    def merge_material_rewards(
        *collections: Optional[Sequence[Tuple[Material, int]]]
    ) -> List[Tuple[Material, int]]:
        combined: Dict[int, Tuple[Material, int]] = {}
        for group in collections:
            if not group:
                continue
            for material, quantity in group:
                existing = combined.get(material.id)
                if existing:
                    combined[material.id] = (material, existing[1] + quantity)
                else:
                    combined[material.id] = (material, quantity)
        return list(combined.values())

    async def grant_material_reward(
        reward: QuestMaterialReward, guild_id: int, user_id: int
    ) -> Optional[Tuple[Material, int]]:
        materials = list(await bot.database.list_materials_by_rarity(reward.rarity))
        if not materials:
            materials = list(await bot.database.list_materials())
        if not materials:
            return None
        material = random.choice(materials)
        quantity = random.randint(reward.quantity[0], reward.quantity[1])
        await bot.database.grant_material_to_player(guild_id, user_id, material, quantity)
        return material, quantity

    async def grant_items_by_name(
        names: Sequence[str], guild_id: int, user_id: int
    ) -> List[Item]:
        awarded: List[Item] = []
        for name in names:
            item = await bot.database.fetch_item_by_name(name)
            if item is None:
                log.warning("Quest reward item '%s' not found in database", name)
                continue
            await bot.database.grant_item_to_player(guild_id, user_id, item, 1)
            awarded.append(item)
        return awarded

    def short_timedelta(delta: timedelta) -> str:
        seconds = int(delta.total_seconds())
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        parts: List[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)

    def quest_block_embed(
        player: Player,
        quest: Optional[QuestDefinition],
        remaining: Optional[timedelta],
        *,
        subject: str = "You",
    ) -> discord.Embed:
        quest_name = quest.name if quest else "your quest"
        verb = "are" if subject.lower() == "you" else "is"
        description: List[str] = [f"{subject} {verb} already adventuring on **{quest_name}**."]
        if remaining is not None:
            if remaining > timedelta(0):
                description.append(f"Time remaining: **{short_timedelta(remaining)}**.")
            else:
                description.append(
                    f"**{quest_name}** is ready to complete. Use /quest status to claim rewards."
                )
        if player.active_quest_complete_at:
            description.append(
                f"Return {discord.utils.format_dt(player.active_quest_complete_at, style='R')}"
            )
        description.append("Use /quest status to check your progress.")
        return discord.Embed(
            title="Quest in progress",
            description="\n".join(description),
            color=discord.Color.orange(),
        )

    async def complete_active_quest(
        interaction: discord.Interaction,
        player: Player,
        quest: QuestDefinition,
        *,
        progress_map: Optional[Dict[str, QuestProgress]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Quests require a guild context."), ephemeral=True
            )
            return

        completion_time = now or datetime.now(timezone.utc)
        if progress_map is None:
            progress_lookup = await bot.database.fetch_player_quest_progress(
                interaction.user.id
            )
        else:
            progress_lookup = progress_map

        marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        weapon_data = await bot.database.fetch_equipped_weapon(guild.id, interaction.user.id)
        armor_data = await bot.database.fetch_equipped_armor(guild.id, interaction.user.id)
        weapon_damage = weapon_data[1].damage if weapon_data else 0
        armor_defense = armor_data[1].defense_boost if armor_data else 0

        outcome = perform_quest(
            player,
            weapon_damage=weapon_damage,
            armor_defense=armor_defense,
            xp_multiplier=quest.xp_multiplier,
            gold_multiplier=quest.gold_multiplier,
            energy_cost=quest.energy_cost,
        )
        total_xp = outcome.xp
        total_gold = outcome.gold
        total_damage = outcome.damage
        leveled_up = outcome.leveled_up

        quest_items: List[Item] = []
        quest_materials: List[Tuple[Material, int]] = []

        if quest.rewards.xp or quest.rewards.gold:
            leveled_reward = apply_xp_and_gold(player, quest.rewards.xp, quest.rewards.gold)
            total_xp += quest.rewards.xp
            total_gold += quest.rewards.gold
            leveled_up = leveled_up or leveled_reward

        if quest.rewards.item_names:
            quest_items.extend(
                await grant_items_by_name(quest.rewards.item_names, guild.id, interaction.user.id)
            )

        for material_reward in quest.rewards.materials:
            granted = await grant_material_reward(material_reward, guild.id, interaction.user.id)
            if granted:
                quest_materials.append(granted)

        encounter_text: Optional[str] = None
        encounter_items: List[Item] = []
        encounter_materials: List[Tuple[Material, int]] = []
        encounter = roll_random_encounter()
        if encounter is not None:
            encounter_data, encounter_outcome = encounter
            encounter_text = f"**{encounter_data.prompt}**\n{encounter_outcome.text}"
            if encounter_outcome.damage:
                player.hp = max(1, player.hp - encounter_outcome.damage)
                total_damage += encounter_outcome.damage
            if encounter_outcome.xp or encounter_outcome.gold:
                leveled_encounter = apply_xp_and_gold(
                    player, encounter_outcome.xp, encounter_outcome.gold
                )
                total_xp += encounter_outcome.xp
                total_gold += encounter_outcome.gold
                leveled_up = leveled_up or leveled_encounter
            if encounter_outcome.item_names:
                encounter_items.extend(
                    await grant_items_by_name(
                        encounter_outcome.item_names, guild.id, interaction.user.id
                    )
                )
            for material_reward in encounter_outcome.materials:
                granted = await grant_material_reward(
                    material_reward, guild.id, interaction.user.id
                )
                if granted:
                    encounter_materials.append(granted)

        random_materials = await roll_material_rewards("quest", guild.id, interaction.user.id)
        materials_found = merge_material_rewards(
            random_materials, quest_materials, encounter_materials
        )
        items_found = quest_items + encounter_items

        player.quests_completed += 1
        player.active_quest_id = None
        player.active_quest_complete_at = None
        await bot.database.update_player(player)
        new_progress = await bot.database.record_quest_completion(
            interaction.user.id, quest.id, completion_time
        )
        progress_lookup[quest.id] = new_progress

        unlocked_achievements = await bot.database.evaluate_player_achievements(
            player,
            check_level=True,
            check_quests=True,
        )
        achievement_lines = format_achievement_lines(interaction.user, unlocked_achievements)

        durability_change: Optional[DurabilityChange] = None
        if weapon_data is not None:
            durability_change = await bot.database.reduce_equipped_weapon_durability(
                guild.id, interaction.user.id, 1
            )
            if durability_change and durability_change.broken:
                player.equipped_weapon_id = None

        embed = quest_story_embed(
            interaction.user,
            quest,
            quest.narrative,
            quest.success_text,
            total_xp,
            total_gold,
            total_damage,
            player,
            leveled_up=leveled_up,
            encounter_text=encounter_text,
            items=items_found if items_found else None,
            materials=materials_found if materials_found else None,
        )

        await interaction.response.send_message(embed=embed)

        if durability_change is not None:
            if durability_change.broken:
                await interaction.followup.send(
                    content=(
                        f"⚠️ Your {durability_change.weapon.name} shattered during the battle and has been removed."
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    content=(
                        f"Your {durability_change.weapon.name} now has {durability_change.durability} durability remaining."
                    ),
                    ephemeral=True,
                )

        anniversary_message = await maybe_award_anniversary_item(guild, interaction.user, marriage)
        if anniversary_message:
            await interaction.followup.send(
                content=anniversary_message,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )
        if achievement_lines:
            await interaction.followup.send(
                "\n".join(achievement_lines),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )

    @dataclass(slots=True)
    class RaidRewardSummary:
        xp: int
        gold: int
        leveled_up: bool
        loot: List[Item]
        rare_item: Optional[Item]
        materials: List[Tuple[Material, int]]
        achievements: Sequence[Achievement]

    async def execute_quest(
        interaction: discord.Interaction,
        quest: QuestDefinition,
        *,
        progress_map: Optional[Dict[str, QuestProgress]] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Quests require a guild context."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Create your character with /create before embarking on quests."
                ),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)

        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                if remaining_active is None:
                    remaining_active = timedelta(0)
                if remaining_active <= timedelta(0):
                    await complete_active_quest(
                        interaction,
                        player,
                        active_quest,
                        progress_map=progress_map,
                        now=now,
                    )
                    return
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return

        ready, remaining = can_quest(player, now)
        if not ready:
            await interaction.response.send_message(
                embed=cooldown_embed("quest", remaining), ephemeral=True
            )
            return
        if player.hp <= 10:
            await interaction.response.send_message(
                embed=error_embed("You are too wounded. Visit /heal before the next quest."),
                ephemeral=True,
            )
            return
        if not energy_ready(player, quest.energy_cost):
            await interaction.response.send_message(
                embed=error_embed(
                    f"You need at least {quest.energy_cost} energy. Try /rest or /work."
                ),
                ephemeral=True,
            )
            return

        if progress_map is None:
            progress_lookup = await bot.database.fetch_player_quest_progress(
                interaction.user.id
            )
        else:
            progress_lookup = progress_map
        progress_entry = progress_lookup.get(quest.id)
        availability = quest.availability(progress_entry, now)
        if availability.locked:
            await interaction.response.send_message(
                embed=error_embed("You have already completed this story quest."),
                ephemeral=True,
            )
            return
        if not availability.available:
            if availability.cooldown_remaining is not None:
                await interaction.response.send_message(
                    embed=cooldown_embed(quest.name, availability.cooldown_remaining),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=error_embed("This quest is not available yet."),
                    ephemeral=True,
                )
            return

        completion_at = now + quest.duration
        player.active_quest_id = quest.id
        player.active_quest_complete_at = completion_at
        await bot.database.update_player(player)

        duration_text = short_timedelta(quest.duration)
        return_text = discord.utils.format_dt(completion_at, style="R")
        description = (
            f"{quest.summary}\n\n"
            f"⏳ Duration: **{duration_text}**\n"
            f"📅 Returns {return_text}\n"
            "Use /quest status to track your progress."
        )
        embed = discord.Embed(
            title=f"{interaction.user.display_name} sets out on {quest.name}!",
            description=description,
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Quests resolve automatically once the timer ends.")
        embed.add_field(
            name="Energy Requirement",
            value=f"{quest.energy_cost} energy",
            inline=True,
        )
        embed.add_field(
            name="XP Multiplier",
            value=f"×{quest.xp_multiplier:.1f}",
            inline=True,
        )
        embed.add_field(
            name="Gold Multiplier",
            value=f"×{quest.gold_multiplier:.1f}",
            inline=True,
        )

        await interaction.response.send_message(embed=embed)

    def format_achievement_lines(
        member: discord.abc.User, achievements: Sequence[Achievement]
    ) -> List[str]:
        lines: List[str] = []
        mention = getattr(member, "mention", None)
        if mention is None and hasattr(member, "id"):
            mention = f"<@{getattr(member, 'id')}>"
        if mention is None:
            mention = str(member)
        for achievement in achievements:
            lines.append(
                f"🏆 {mention} unlocked **{achievement.name}** — *{achievement.title}*."
                f" {achievement.description}"
            )
        return lines

    def effective_raid_attack(player: Player, weapon_damage: int = 0) -> int:
        attack = player.attack + max(0, weapon_damage)
        if player.attack_buff_battles > 0 and player.attack_buff_percent > 0:
            attack = int(attack * (100 + player.attack_buff_percent) / 100)
        return max(0, attack)

    def effective_raid_defense(player: Player, armor_defense: int = 0) -> int:
        defense = player.defense + max(0, armor_defense)
        if player.defense_buff_battles > 0 and player.defense_buff_percent > 0:
            defense = int(defense * (100 + player.defense_buff_percent) / 100)
        return max(0, defense)

    def consume_battle_buffs(player: Player) -> None:
        if player.attack_buff_battles > 0:
            player.attack_buff_battles -= 1
            if player.attack_buff_battles <= 0:
                player.attack_buff_percent = 0
        if player.defense_buff_battles > 0:
            player.defense_buff_battles -= 1
            if player.defense_buff_battles <= 0:
                player.defense_buff_percent = 0

    def calculate_player_raid_damage(player: Player, weapon_damage: int = 0) -> int:
        effective = effective_raid_attack(player, weapon_damage)
        base = max(12, int(effective * 0.55))
        variance = max(8, int(effective * 0.45))
        return random.randint(base, base + variance)

    def calculate_boss_retaliation(
        boss: RaidBoss, player: Player, armor_defense: int = 0
    ) -> int:
        base = random.randint(int(boss.attack * 0.65), int(boss.attack * 1.15))
        mitigation = int(effective_raid_defense(player, armor_defense) * 0.6)
        return max(6, base - mitigation)

    async def choose_item_by_rarity(
        rarity: Optional[str], *, event_id: Optional[int] = None
    ) -> Optional[Item]:
        if not rarity:
            return None
        rarity_key = rarity.lower()
        items: List[Item] = []
        if event_id is not None:
            event_items = list(await bot.database.list_event_items(event_id))
            if rarity_key == "event":
                items = event_items
            else:
                items = [item for item in event_items if item.rarity.lower() == rarity_key]
            if not items:
                items = event_items
        if not items:
            items = list(await bot.database.list_items_by_rarity(rarity, generic_only=False))
        if not items:
            items = list(await bot.database.list_items_by_rarity(rarity, generic_only=True))
        if not items:
            return None
        return random.choice(items)

    async def choose_material_by_rarity(rarity: Optional[str]) -> Optional[Material]:
        if not rarity:
            return None
        materials = list(await bot.database.list_materials_by_rarity(rarity))
        if not materials:
            return None
        return random.choice(materials)

    async def finalize_raid_rewards(
        raid: RaidInstance, boss: RaidBoss, guild: discord.Guild
    ) -> Dict[int, RaidRewardSummary]:
        participants = await bot.database.list_raid_participants(raid.id)
        total_damage = sum(participant.damage_dealt for participant in participants)
        if total_damage <= 0:
            total_damage = max(1, raid.total_damage)
        total_damage = max(1, total_damage)
        summaries: Dict[int, RaidRewardSummary] = {}

        for participant in participants:
            if participant.damage_dealt <= 0:
                continue
            share = participant.damage_dealt / total_damage
            xp_reward = max(10, int(round(boss.xp_reward * share)))
            gold_reward = max(10, int(round(boss.gold_reward * share)))
            player = await bot.database.fetch_player(guild.id, participant.user_id)
            if player is None:
                continue

            leveled_up = apply_xp_and_gold(player, xp_reward, gold_reward)
            loot_items: List[Item] = []
            rare_item: Optional[Item] = None
            material_rewards: List[Tuple[Material, int]] = []

            guaranteed_item = await choose_item_by_rarity(
                boss.item_reward_rarity, event_id=boss.event_id
            )
            if guaranteed_item is not None:
                await bot.database.grant_item_to_player(
                    guild.id, participant.user_id, guaranteed_item
                )
                loot_items.append(guaranteed_item)

            if boss.rare_loot_chance > 0 and boss.rare_loot_rarity:
                if random.random() <= boss.rare_loot_chance:
                    candidate = await choose_item_by_rarity(
                        boss.rare_loot_rarity, event_id=boss.event_id
                    )
                    if candidate is not None:
                        await bot.database.grant_item_to_player(
                            guild.id, participant.user_id, candidate
                        )
                        rare_item = candidate

            chosen_material = await choose_material_by_rarity(boss.material_reward_rarity)
            if chosen_material is not None:
                quantity = random.randint(1, 3)
                await bot.database.grant_material_to_player(
                    guild.id, participant.user_id, chosen_material, quantity
                )
                material_rewards.append((chosen_material, quantity))

            extra_materials = await roll_material_rewards(
                "raid", guild.id, participant.user_id
            )
            if extra_materials:
                material_rewards.extend(extra_materials)

            player.raids_completed += 1
            await bot.database.update_player(player)
            achievements = await bot.database.evaluate_player_achievements(
                player,
                check_level=True,
                check_raids=True,
            )
            summaries[participant.user_id] = RaidRewardSummary(
                xp=xp_reward,
                gold=gold_reward,
                leveled_up=leveled_up,
                loot=loot_items,
                rare_item=rare_item,
                materials=material_rewards,
                achievements=achievements,
            )

        return summaries

    def get_spouse_member(
        guild: discord.Guild, marriage: Marriage, user_id: int
    ) -> Optional[discord.Member]:
        partner_id = marriage.partner_id(user_id)
        if partner_id is None:
            return None
        return guild.get_member(partner_id)

    async def maybe_award_anniversary_item(
        guild: discord.Guild, member: discord.abc.User, marriage: Optional[Marriage]
    ) -> Optional[str]:
        if marriage is None:
            return None
        now = datetime.now(timezone.utc)
        anniversary = marriage.date_married.astimezone(timezone.utc)
        if anniversary.month != now.month or anniversary.day != now.day:
            return None
        if random.random() > ANNIVERSARY_DROP_CHANCE:
            return None
        item = await bot.database.ensure_anniversary_item()
        await bot.database.grant_item_to_player(guild.id, member.id, item)
        return (
            f"🎁 {member.mention} receives an **{item.name}** to celebrate the anniversary"
            " of their marriage!"
        )

    async def get_player_guild(user_id: int) -> Tuple[Optional[Guild], Optional[GuildMember]]:
        membership = await bot.database.fetch_guild_member(user_id)
        if membership is None:
            return None, None
        guild = await bot.database.fetch_guild_by_id(membership.guild_id)
        return guild, membership

    async def build_profile_embed_for(
        guild: discord.Guild, member: discord.Member, player: Player
    ) -> discord.Embed:
        player_class = (
            await bot.database.fetch_class_by_id(player.class_id)
            if player.class_id is not None
            else None
        )
        weapon = await bot.database.fetch_equipped_weapon(guild.id, member.id)
        armor = await bot.database.fetch_equipped_armor(guild.id, member.id)
        guild_info, membership = await get_player_guild(member.id)
        title = await bot.database.fetch_equipped_title(member.id)
        profile_settings = await bot.database.fetch_player_profile(member.id)
        marriage = await bot.database.fetch_marriage(guild.id, member.id)
        achievements = await bot.database.list_player_achievements(member.id)

        partner_display: Optional[str] = None
        if marriage is not None:
            partner_id = marriage.partner_id(member.id)
            if partner_id is not None:
                partner_member = guild.get_member(partner_id)
                partner_user: Optional[discord.abc.User] = partner_member
                if partner_user is None:
                    partner_user = bot.get_user(partner_id)
                if partner_user is None:
                    try:
                        partner_user = await bot.fetch_user(partner_id)
                    except discord.HTTPException:
                        partner_user = None
                if partner_user is not None:
                    partner_display = (
                        partner_user.mention
                        if hasattr(partner_user, "mention")
                        else getattr(partner_user, "display_name", partner_user.name)
                    )
                elif partner_id is not None:
                    partner_display = f"<@{partner_id}>"

        badge_icon_map = {
            GUILD_ROLE_MASTER: "👑",
            GUILD_ROLE_OFFICER: "🛡️",
            GUILD_ROLE_MEMBER: "⚔️",
        }
        guild_badge: Optional[str] = None
        if membership is not None:
            icon = badge_icon_map.get(membership.role, "🏰")
            role_title = membership.role.replace("_", " ").title()
            guild_badge = f"{icon} {role_title}"

        recent_achievements = list(reversed(achievements[-3:])) if achievements else []

        return profile_embed(
            member,
            player,
            player_class,
            weapon,
            armor,
            title=title,
            guild=guild_info,
            guild_membership=membership,
            profile=profile_settings,
            marriage=marriage,
            marriage_partner=partner_display,
            achievements=recent_achievements,
            guild_badge=guild_badge,
        )

    def build_duel_stats(
        player: Player,
        weapon: Optional[Tuple[InventoryEntry, Weapon]],
        armor: Optional[Tuple[InventoryEntry, Armor]],
    ) -> Dict[str, int]:
        weapon_damage = weapon[1].damage if weapon else 0
        armor_defense = armor[1].defense_boost if armor else 0
        return {
            "attack": effective_attack(player, weapon_damage),
            "defense": effective_defense(player, armor_defense),
            "max_hp": player.max_hp,
            "weapon_damage": weapon_damage,
            "armor_defense": armor_defense,
        }

    async def build_guild_roster(
        guild_id: int, context_guild: Optional[discord.Guild]
    ) -> Sequence[Tuple[GuildMember, Optional[discord.abc.User]]]:
        roster: list[Tuple[GuildMember, Optional[discord.abc.User]]] = []
        members = await bot.database.list_guild_members(guild_id)
        for entry in members:
            user_obj: Optional[discord.abc.User] = None
            if context_guild is not None:
                user_obj = context_guild.get_member(entry.player_id)
            if user_obj is None:
                user_obj = bot.get_user(entry.player_id)
            roster.append((entry, user_obj))
        return roster

    guild_group = app_commands.Group(name="guild", description="Manage your IdleRPG guild")
    bot.tree.add_command(guild_group)

    global_group = app_commands.Group(
        name="global", description="View worldwide IdleRPG standings"
    )
    bot.tree.add_command(global_group)

    @bot.tree.command(name="start", description="Join the IdleRPG adventure")
    async def start(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("This command can only be used in a server."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("You don't have a character yet. Use /create to begin."),
                ephemeral=True,
            )
            return

        embed = await build_profile_embed_for(interaction.guild, interaction.user, player)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @guild_group.command(name="create", description="Create a new guild")
    @app_commands.describe(name="Name of your guild", description="Optional short description")
    async def guild_create(
        interaction: discord.Interaction, name: str, description: Optional[str] = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Guilds can only be managed from inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before founding a guild."),
                ephemeral=True,
            )
            return

        existing_guild, _ = await get_player_guild(interaction.user.id)
        if existing_guild is not None:
            await interaction.response.send_message(
                embed=error_embed("You are already a member of a guild."),
                ephemeral=True,
            )
            return

        guild_name = name.strip()
        if len(guild_name) < 3 or len(guild_name) > 32:
            await interaction.response.send_message(
                embed=error_embed("Guild names must be between 3 and 32 characters."),
                ephemeral=True,
            )
            return

        description_text = (description or "").strip()
        try:
            guild = await bot.database.create_guild(
                guild_name, description_text, interaction.user.id
            )
        except ValueError as exc:
            if str(exc) == "guild_name_taken":
                await interaction.response.send_message(
                    embed=error_embed("That guild name is already taken."), ephemeral=True
                )
                return
            raise

        roster = await build_guild_roster(guild.id, interaction.guild)
        embed = guild_info_embed(guild, roster)
        await interaction.response.send_message(
            content=f"{interaction.user.mention} founded **{guild.name}**!",
            embed=embed,
        )

    @guild_group.command(name="invite", description="Invite an adventurer to your guild")
    @app_commands.describe(member="Who should join your guild")
    async def guild_invite(
        interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Guild invitations must be sent from inside a server."),
                ephemeral=True,
            )
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("You can't invite yourself."), ephemeral=True
            )
            return

        guild, membership = await get_player_guild(interaction.user.id)
        if guild is None or membership is None:
            await interaction.response.send_message(
                embed=error_embed("You need to be in a guild to invite others."),
                ephemeral=True,
            )
            return

        if membership.role not in {GUILD_ROLE_MASTER, GUILD_ROLE_OFFICER}:
            await interaction.response.send_message(
                embed=error_embed("Only guild masters or officers can invite players."),
                ephemeral=True,
            )
            return

        target_player = await bot.database.fetch_player(interaction.guild.id, member.id)
        if target_player is None:
            await interaction.response.send_message(
                embed=error_embed("That adventurer needs to create a character first."),
                ephemeral=True,
            )
            return

        target_guild, _ = await get_player_guild(member.id)
        if target_guild is not None:
            await interaction.response.send_message(
                embed=error_embed("That adventurer already belongs to a guild."),
                ephemeral=True,
            )
            return

        await bot.database.create_guild_invitation(guild.id, member.id, interaction.user.id)
        await interaction.response.send_message(
            content=(
                f"{member.mention}, you have been invited to join **{guild.name}**!"
                " Use /guild join to accept."
            )
        )

    @guild_group.command(name="join", description="Join a guild you've been invited to")
    @app_commands.describe(name="Name of the guild you wish to join")
    async def guild_join(
        interaction: discord.Interaction, name: Optional[str] = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Guild membership can only be managed inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before joining a guild."),
                ephemeral=True,
            )
            return

        current_guild, _ = await get_player_guild(interaction.user.id)
        if current_guild is not None:
            await interaction.response.send_message(
                embed=error_embed("You are already part of a guild."), ephemeral=True
            )
            return

        invitations = await bot.database.list_guild_invitations_for_player(interaction.user.id)
        target_guild: Optional[Guild] = None
        if name:
            target_guild = await bot.database.fetch_guild_by_name(name)
            if target_guild is None:
                await interaction.response.send_message(
                    embed=error_embed("No guild with that name exists."), ephemeral=True
                )
                return
            invite = await bot.database.fetch_guild_invitation(target_guild.id, interaction.user.id)
            if invite is None:
                await interaction.response.send_message(
                    embed=error_embed("You do not have an invitation to that guild."),
                    ephemeral=True,
                )
                return
        else:
            if not invitations:
                await interaction.response.send_message(
                    embed=error_embed("You have no pending guild invitations."),
                    ephemeral=True,
                )
                return
            if len(invitations) > 1:
                guild_names = []
                for invite in invitations:
                    guild_info = await bot.database.fetch_guild_by_id(invite.guild_id)
                    if guild_info is not None:
                        guild_names.append(guild_info.name)
                await interaction.response.send_message(
                    embed=error_embed(
                        "You have invites to multiple guilds. Use /guild join name:<guild name>."
                        f" Pending: {', '.join(guild_names) if guild_names else 'Unknown'}"
                    ),
                    ephemeral=True,
                )
                return
            target_invite = invitations[0]
            target_guild = await bot.database.fetch_guild_by_id(target_invite.guild_id)

        if target_guild is None:
            await interaction.response.send_message(
                embed=error_embed("Unable to find the guild for your invitation."),
                ephemeral=True,
            )
            return

        await bot.database.add_guild_member(target_guild.id, interaction.user.id)
        roster = await build_guild_roster(target_guild.id, interaction.guild)
        embed = guild_info_embed(target_guild, roster)
        await interaction.response.send_message(
            content=f"{interaction.user.mention} joined **{target_guild.name}**!",
            embed=embed,
        )

    @guild_group.command(name="leave", description="Leave your current guild")
    async def guild_leave(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Guild membership can only be changed from within a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before leaving a guild."),
                ephemeral=True,
            )
            return

        guild, membership = await get_player_guild(interaction.user.id)
        if guild is None or membership is None:
            await interaction.response.send_message(
                embed=error_embed("You are not currently in a guild."), ephemeral=True
            )
            return

        members = await bot.database.list_guild_members(guild.id)
        if membership.role == GUILD_ROLE_MASTER and len(members) > 1:
            successor = None
            for entry in members:
                if entry.player_id == interaction.user.id:
                    continue
                if entry.role in {GUILD_ROLE_OFFICER, GUILD_ROLE_MEMBER}:
                    successor = entry
                    if entry.role == GUILD_ROLE_OFFICER:
                        break
            if successor is not None:
                await bot.database.update_guild_member_role(
                    guild.id, successor.player_id, GUILD_ROLE_MASTER
                )

        await bot.database.remove_guild_member(guild.id, interaction.user.id)
        remaining = await bot.database.guild_member_count(guild.id)
        if remaining == 0:
            await bot.database.delete_guild(guild.id)
            await interaction.response.send_message(
                content=(
                    f"{interaction.user.mention} has left **{guild.name}**. "
                    "With no members remaining, the guild disbands."
                )
            )
        else:
            await interaction.response.send_message(
                content=f"{interaction.user.mention} has left **{guild.name}**."
            )

    @guild_group.command(name="donate", description="Donate gold to your guild's treasury")
    @app_commands.describe(amount="How much gold to donate")
    async def guild_donate(
        interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1_000_000]
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Donations can only be made from within a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before donating."),
                ephemeral=True,
            )
            return

        guild, membership = await get_player_guild(interaction.user.id)
        if guild is None or membership is None:
            await interaction.response.send_message(
                embed=error_embed("You must belong to a guild to donate."),
                ephemeral=True,
            )
            return

        if player.gold < amount:
            await interaction.response.send_message(
                embed=error_embed("You don't have enough gold for that donation."),
                ephemeral=True,
            )
            return

        player.gold -= amount
        await bot.database.update_player(player)
        guild_state = await bot.database.apply_guild_rewards(guild.id, gold=amount)
        await interaction.response.send_message(
            content=(
                f"{interaction.user.mention} donated 💰 {amount} gold to **{guild_state.name}**."
                f" The treasury now holds 🏛️ {guild_state.gold}."
            )
        )

    @guild_group.command(name="info", description="Display information about a guild")
    @app_commands.describe(name="Optional guild name to inspect")
    async def guild_info_command(
        interaction: discord.Interaction, name: Optional[str] = None
    ) -> None:
        target_guild: Optional[Guild]
        if name:
            target_guild = await bot.database.fetch_guild_by_name(name)
            if target_guild is None:
                await interaction.response.send_message(
                    embed=error_embed("No guild with that name exists."), ephemeral=True
                )
                return
        else:
            target_guild, _ = await get_player_guild(interaction.user.id)
            if target_guild is None:
                await interaction.response.send_message(
                    embed=error_embed("Join a guild or provide a name to view."),
                    ephemeral=True,
                )
                return

        roster = await build_guild_roster(target_guild.id, interaction.guild)
        embed = guild_info_embed(target_guild, roster)
        await interaction.response.send_message(embed=embed, ephemeral=name is not None)

    @guild_group.command(name="leaderboard", description="Show the top guilds")
    async def guild_leaderboard_command(interaction: discord.Interaction) -> None:
        guilds = await bot.database.guild_leaderboard()
        embed = guild_leaderboard_embed(guilds)
        await interaction.response.send_message(embed=embed)

    @guild_group.command(name="quest", description="Embark on a guild quest")
    async def guild_quest(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Guild quests can only be started inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before running guild quests."),
                ephemeral=True,
            )
            return

        guild, membership = await get_player_guild(interaction.user.id)
        if guild is None or membership is None:
            await interaction.response.send_message(
                embed=error_embed("Join a guild before attempting a guild quest."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return
        if membership.last_quest_at is not None:
            remaining = GUILD_QUEST_COOLDOWN - (now - membership.last_quest_at)
            if remaining > timedelta(0):
                await interaction.response.send_message(
                    embed=cooldown_embed("Guild quest", remaining), ephemeral=True
                )
                return

        if player.energy < GUILD_QUEST_ENERGY_COST:
            await interaction.response.send_message(
                embed=error_embed("You need more energy to lead a guild quest."),
                ephemeral=True,
            )
            return

        guild_xp = random.randint(120, 220)
        guild_gold = random.randint(80, 160)
        personal_xp = guild_xp // 4
        personal_gold = guild_gold // 4

        leveled_up = apply_xp_and_gold(player, personal_xp, personal_gold)
        player.energy = max(0, player.energy - GUILD_QUEST_ENERGY_COST)
        await bot.database.update_player(player)
        unlocked_achievements = await bot.database.evaluate_player_achievements(
            player,
            check_level=True,
        )
        achievement_lines = format_achievement_lines(interaction.user, unlocked_achievements)
        updated_guild = await bot.database.apply_guild_rewards(
            guild.id, xp=guild_xp, gold=guild_gold
        )
        await bot.database.set_guild_member_activity(
            guild.id, interaction.user.id, last_quest_at=now
        )

        embed = discord.Embed(
            title=f"{interaction.user.display_name} leads a guild quest!",
            description=(
                f"**{updated_guild.name}** earns **{guild_xp} XP** and **{guild_gold} gold**.\n"
                f"You also gain {personal_xp} XP and {personal_gold} gold."
            ),
            color=PRIMARY_COLOR,
        )
        embed.add_field(
            name="Guild Level",
            value=f"{updated_guild.level} (XP {updated_guild.xp})",
            inline=True,
        )
        embed.add_field(
            name="Guild Treasury",
            value=f"🏛️ {updated_guild.gold}",
            inline=True,
        )
        if leveled_up:
            embed.add_field(name="Level Up!", value=f"Level {player.level}", inline=False)
        await interaction.response.send_message(embed=embed)
        if achievement_lines:
            await interaction.followup.send(
                "\n".join(achievement_lines),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )

    @guild_group.command(name="war", description="Challenge another guild to a friendly war")
    @app_commands.describe(target="Name of the guild you want to challenge")
    async def guild_war(interaction: discord.Interaction, target: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Guild wars can only be initiated from a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before starting wars."),
                ephemeral=True,
            )
            return

        guild, membership = await get_player_guild(interaction.user.id)
        if guild is None or membership is None:
            await interaction.response.send_message(
                embed=error_embed("Join a guild before challenging others."),
                ephemeral=True,
            )
            return

        if membership.role not in {GUILD_ROLE_MASTER, GUILD_ROLE_OFFICER}:
            await interaction.response.send_message(
                embed=error_embed("Only guild masters or officers may initiate wars."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if membership.last_war_at is not None:
            remaining = GUILD_WAR_COOLDOWN - (now - membership.last_war_at)
            if remaining > timedelta(0):
                await interaction.response.send_message(
                    embed=cooldown_embed("Guild war", remaining), ephemeral=True
                )
                return

        target_guild = await bot.database.fetch_guild_by_name(target)
        if target_guild is None:
            await interaction.response.send_message(
                embed=error_embed("That guild does not exist."), ephemeral=True
            )
            return

        if target_guild.id == guild.id:
            await interaction.response.send_message(
                embed=error_embed("You cannot challenge your own guild."),
                ephemeral=True,
            )
            return

        own_members = await bot.database.list_guild_members(guild.id)
        opponent_members = await bot.database.list_guild_members(target_guild.id)
        if not opponent_members:
            await interaction.response.send_message(
                embed=error_embed("The target guild has no members yet."), ephemeral=True
            )
            return

        own_score = guild.level * random.randint(1, 6) + len(own_members) * 10
        opponent_score = target_guild.level * random.randint(1, 6) + len(opponent_members) * 10

        if own_score == opponent_score:
            own_score += random.randint(1, 6)
            opponent_score += random.randint(1, 6)

        if own_score > opponent_score:
            winner = guild
            loser = target_guild
            result_text = f"**{guild.name}** triumphs over **{target_guild.name}**!"
        else:
            winner = target_guild
            loser = guild
            result_text = f"**{target_guild.name}** wins the friendly war!"

        xp_reward = random.randint(200, 350)
        gold_reward = random.randint(150, 250)
        await bot.database.apply_guild_rewards(winner.id, xp=xp_reward, gold=gold_reward)
        consolation = max(50, xp_reward // 4)
        await bot.database.apply_guild_rewards(loser.id, xp=consolation, gold=gold_reward // 4)
        await bot.database.set_guild_member_activity(
            guild.id, interaction.user.id, last_war_at=now
        )

        embed = discord.Embed(
            title="Friendly Guild War",
            description=result_text,
            color=PRIMARY_COLOR,
        )
        embed.add_field(
            name="Winner Rewards",
            value=f"XP +{xp_reward} • 🏛️ +{gold_reward}",
            inline=True,
        )
        embed.add_field(
            name="Participants",
            value=f"{guild.name} ({len(own_members)} adventurers) vs. {target_guild.name} ({len(opponent_members)})",
            inline=False,
        )
        embed.add_field(
            name="Consolation",
            value=f"{loser.name} receives {consolation} XP and {gold_reward // 4} gold",
            inline=True,
        )
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="duel", description="Challenge another adventurer to a PvP duel")
    @app_commands.describe(opponent="Adventurer to challenge")
    async def duel_command(
        interaction: discord.Interaction, opponent: discord.Member
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("PvP duels can only be started inside a server."),
                ephemeral=True,
            )
            return

        if opponent.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("You cannot duel yourself."),
                ephemeral=True,
            )
            return

        if opponent.bot:
            await interaction.response.send_message(
                embed=error_embed("Bots are not eligible for PvP."),
                ephemeral=True,
            )
            return

        challenger = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if challenger is None or challenger.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("You need an active character to duel."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if challenger.active_quest_id:
            active_quest = find_quest(challenger.active_quest_id)
            remaining_active = active_quest_remaining(challenger, now)
            if active_quest is None:
                challenger.active_quest_id = None
                challenger.active_quest_complete_at = None
                await bot.database.update_player(challenger)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(challenger, active_quest, remaining_active),
                    ephemeral=True,
                )
                return

        opponent_player = await bot.database.fetch_player(interaction.guild.id, opponent.id)
        if opponent_player is None or opponent_player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("That adventurer hasn't created a character yet."),
                ephemeral=True,
            )
            return

        opponent_subject = opponent.mention if hasattr(opponent, "mention") else opponent.display_name
        if opponent_player.active_quest_id:
            active_quest = find_quest(opponent_player.active_quest_id)
            remaining_active = active_quest_remaining(opponent_player, now)
            if active_quest is None:
                opponent_player.active_quest_id = None
                opponent_player.active_quest_complete_at = None
                await bot.database.update_player(opponent_player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(
                        opponent_player, active_quest, remaining_active, subject=opponent_subject
                    ),
                    ephemeral=True,
                )
                return

        challenger_weapon = await bot.database.fetch_equipped_weapon(
            interaction.guild.id, interaction.user.id
        )
        challenger_armor = await bot.database.fetch_equipped_armor(
            interaction.guild.id, interaction.user.id
        )
        opponent_weapon = await bot.database.fetch_equipped_weapon(
            interaction.guild.id, opponent.id
        )
        opponent_armor = await bot.database.fetch_equipped_armor(
            interaction.guild.id, opponent.id
        )

        challenger_stats = build_duel_stats(challenger, challenger_weapon, challenger_armor)
        opponent_stats = build_duel_stats(opponent_player, opponent_weapon, opponent_armor)

        participants = [
            (interaction.user, challenger_stats, challenger),
            (opponent, opponent_stats, opponent_player),
        ]
        hp = {
            interaction.user.id: challenger_stats["max_hp"],
            opponent.id: opponent_stats["max_hp"],
        }

        rounds: List[Tuple[str, str, int, int]] = []
        attacker_index = 0
        winner_user: discord.abc.User
        loser_user: discord.abc.User
        for _ in range(100):
            attacker_user, attacker_stats, _ = participants[attacker_index]
            defender_user, defender_stats, _ = participants[1 - attacker_index]
            attack_power = attacker_stats["attack"]
            defense_power = defender_stats["defense"]
            variance = max(1, attack_power // 5)
            damage_roll = attack_power + random.randint(-variance, variance)
            mitigation = max(0, defense_power // 4)
            damage = max(1, damage_roll - mitigation)
            hp[defender_user.id] = max(0, hp[defender_user.id] - damage)
            rounds.append(
                (
                    attacker_user.display_name,
                    defender_user.display_name,
                    damage,
                    hp[defender_user.id],
                )
            )
            if hp[defender_user.id] <= 0:
                winner_user = attacker_user
                loser_user = defender_user
                break
            attacker_index = 1 - attacker_index
        else:
            if hp[interaction.user.id] >= hp[opponent.id]:
                winner_user, loser_user = interaction.user, opponent
            else:
                winner_user, loser_user = opponent, interaction.user

        winner_player = challenger if winner_user.id == challenger.user_id else opponent_player
        loser_player = opponent_player if winner_player is challenger else challenger

        updated_winner, updated_loser = await bot.database.record_duel_result(
            winner_player.user_id,
            loser_player.user_id,
            now=datetime.now(timezone.utc),
            seasonal_reset=bot.settings.pvp_season_reset,
        )

        updated_map = {
            updated_winner.user_id: updated_winner,
            updated_loser.user_id: updated_loser,
        }
        challenger_after = updated_map.get(challenger.user_id, challenger)
        opponent_after = updated_map.get(opponent_player.user_id, opponent_player)
        season_start = await bot.database.get_pvp_season_start()

        embed = duel_result_embed(
            interaction.user,
            opponent,
            winner=winner_user,
            challenger_player=challenger_after,
            opponent_player=opponent_after,
            challenger_stats=challenger_stats,
            opponent_stats=opponent_stats,
            rounds=rounds,
            season_start=season_start,
            seasonal_reset_enabled=bot.settings.pvp_season_reset,
        )

        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="profile", description="Show your IdleRPG profile")
    @app_commands.describe(member="Member to inspect")
    async def profile(
        interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Profiles are only available in servers."), ephemeral=True
            )
            return

        target = member or interaction.user
        player = await bot.database.fetch_player(interaction.guild.id, target.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "That adventurer hasn't created a character yet. Ask them to use /create."
                ),
                ephemeral=True,
            )
            return

        embed = await build_profile_embed_for(interaction.guild, target, player)
        await interaction.response.send_message(embed=embed, ephemeral=member is not None)

    profile_config_group = app_commands.Group(
        name="profileconfig", description="Customize your IdleRPG profile"
    )
    bot.tree.add_command(profile_config_group)

    def _validate_image_url(url: str) -> bool:
        return url.lower().startswith("http://") or url.lower().startswith("https://")

    @profile_config_group.command(
        name="avatar", description="Set or reset the avatar shown on your profile"
    )
    @app_commands.describe(
        url="Direct image URL to use for your IdleRPG avatar",
        reset="Reset to use your Discord avatar instead",
    )
    async def profileconfig_avatar(
        interaction: discord.Interaction,
        url: Optional[str] = None,
        reset: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Profile customization can only be used inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before editing your profile."),
                ephemeral=True,
            )
            return

        avatar_value: Optional[str]
        if reset:
            avatar_value = None
        else:
            if url is None or not url.strip():
                await interaction.response.send_message(
                    embed=error_embed("Provide an image URL or enable reset to clear your avatar."),
                    ephemeral=True,
                )
                return
            cleaned = url.strip()
            if not _validate_image_url(cleaned):
                await interaction.response.send_message(
                    embed=error_embed("Avatar URLs must start with http:// or https://."),
                    ephemeral=True,
                )
                return
            avatar_value = cleaned

        await bot.database.set_player_profile(interaction.user.id, avatar_url=avatar_value)
        embed = await build_profile_embed_for(guild, interaction.user, player)
        message = (
            "Your IdleRPG avatar now uses the custom image."
            if avatar_value
            else "Your IdleRPG avatar has been reset to your Discord avatar."
        )
        await interaction.response.send_message(content=message, embed=embed, ephemeral=True)

    @profile_config_group.command(
        name="banner", description="Set or reset the banner shown on your profile"
    )
    @app_commands.describe(
        url="Direct image URL to use for your IdleRPG banner",
        reset="Reset to remove your custom banner",
    )
    async def profileconfig_banner(
        interaction: discord.Interaction,
        url: Optional[str] = None,
        reset: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Profile customization can only be used inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before editing your profile."),
                ephemeral=True,
            )
            return

        banner_value: Optional[str]
        if reset:
            banner_value = None
        else:
            if url is None or not url.strip():
                await interaction.response.send_message(
                    embed=error_embed("Provide an image URL or enable reset to clear your banner."),
                    ephemeral=True,
                )
                return
            cleaned = url.strip()
            if not _validate_image_url(cleaned):
                await interaction.response.send_message(
                    embed=error_embed("Banner URLs must start with http:// or https://."),
                    ephemeral=True,
                )
                return
            banner_value = cleaned

        await bot.database.set_player_profile(interaction.user.id, banner_url=banner_value)
        embed = await build_profile_embed_for(guild, interaction.user, player)
        message = (
            "Your IdleRPG banner now uses the custom image."
            if banner_value
            else "Your IdleRPG banner has been cleared."
        )
        await interaction.response.send_message(content=message, embed=embed, ephemeral=True)

    @profile_config_group.command(
        name="reset", description="Clear your custom profile avatar and banner"
    )
    async def profileconfig_reset(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Profile customization can only be used inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before editing your profile."),
                ephemeral=True,
            )
            return

        await bot.database.set_player_profile(
            interaction.user.id, avatar_url=None, banner_url=None
        )
        embed = await build_profile_embed_for(guild, interaction.user, player)
        await interaction.response.send_message(
            content="Your IdleRPG profile customizations have been cleared.",
            embed=embed,
            ephemeral=True,
        )

    @bot.tree.command(name="achievements", description="Show your unlocked achievements")
    @app_commands.describe(member="Member to inspect")
    async def achievements_command(
        interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Achievements can only be viewed inside a server."),
                ephemeral=True,
            )
            return

        target = member or interaction.user
        player = await bot.database.fetch_player(interaction.guild.id, target.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "That adventurer hasn't unlocked achievements yet. They need an active character first."
                ),
                ephemeral=True,
            )
            return

        records = await bot.database.list_player_achievements(target.id)
        embed = achievements_embed(target, records)
        await interaction.response.send_message(embed=embed, ephemeral=member is not None)

    async def autocomplete_title(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        records = await bot.database.list_player_achievements(interaction.user.id)
        term = current.lower()
        choices: List[app_commands.Choice[str]] = []
        for record in records:
            achievement = record.achievement
            label = f"{achievement.title} ({achievement.name})"
            if not term or term in label.lower():
                display = label if len(label) <= 100 else f"{label[:97]}..."
                choices.append(app_commands.Choice(name=display, value=str(achievement.id)))
            if len(choices) >= 25:
                break
        return choices

    title_group = app_commands.Group(
        name="title", description="Manage the titles you've earned"
    )
    bot.tree.add_command(title_group)

    @title_group.command(name="equip", description="Equip an achievement title")
    @app_commands.describe(title="Achievement title to display on your profile")
    @app_commands.autocomplete(title=autocomplete_title)
    async def equip_title_command(interaction: discord.Interaction, title: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Titles can only be managed inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before equipping a title."),
                ephemeral=True,
            )
            return

        try:
            achievement_id = int(title)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Select a title from the list of unlocked achievements."),
                ephemeral=True,
            )
            return

        achievement = await bot.database.fetch_achievement_by_id(achievement_id)
        if achievement is None:
            await interaction.response.send_message(
                embed=error_embed("That title could not be found."),
                ephemeral=True,
            )
            return

        try:
            await bot.database.set_equipped_title(interaction.user.id, achievement.id)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("You haven't unlocked that title yet."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Equipped the title *{achievement.title}*.",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    @title_group.command(name="clear", description="Remove your equipped title")
    async def clear_title_command(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Titles can only be managed inside a server."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before clearing a title."),
                ephemeral=True,
            )
            return

        await bot.database.clear_equipped_title(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                description="Your title has been cleared.",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="create", description="Create your IdleRPG character")
    @app_commands.describe(character_class="Choose your starting class")
    @app_commands.choices(character_class=CLASS_CHOICES)
    async def create(
        interaction: discord.Interaction, character_class: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Character creation must happen in a server."),
                ephemeral=True,
            )
            return

        existing = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if existing is not None and existing.class_id is not None:
            await interaction.response.send_message(
                embed=error_embed(
                    "You have already chosen a class. Contact an admin if you need a reset."
                ),
                ephemeral=True,
            )
            return

        class_info = await bot.database.fetch_class_by_id(int(character_class.value))
        if class_info is None:
            await interaction.response.send_message(
                embed=error_embed("That class is unavailable. Please pick another."),
                ephemeral=True,
            )
            return

        if existing is None:
            player = await bot.database.create_player(
                interaction.guild.id, interaction.user.id, class_info.id
            )
        else:
            existing.hp = class_info.base_hp
            existing.max_hp = class_info.base_hp
            existing.attack = class_info.base_attack
            existing.defense = class_info.base_defense
            existing.class_id = class_info.id
            existing.level = 1
            existing.xp = 0
            existing.gold = 0
            existing.energy = 100
            existing.last_quest_at = None
            existing.last_work_at = None
            existing.last_rest_at = None
            player = existing
            await bot.database.update_player(player)

        embed = await build_profile_embed_for(interaction.guild, interaction.user, player)
        await interaction.response.send_message(
            content=(
                "Welcome to IdleRPG Zero! Your class determines your stats and abilities—"
                "prepare for adventure!"
            ),
            embed=embed,
            ephemeral=True,
        )

    @bot.tree.command(name="propose", description="Propose marriage to another adventurer")
    @app_commands.describe(member="The adventurer you want to propose to")
    async def propose(interaction: discord.Interaction, member: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Marriage proposals must happen inside a guild."),
                ephemeral=True,
            )
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("You cannot propose to yourself."), ephemeral=True
            )
            return

        if member.bot:
            await interaction.response.send_message(
                embed=error_embed("Bots cannot accept proposals."), ephemeral=True
            )
            return

        proposer = await bot.database.fetch_player(guild.id, interaction.user.id)
        target = await bot.database.fetch_player(guild.id, member.id)
        if proposer is None or proposer.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before proposing."),
                ephemeral=True,
            )
            return
        if target is None or target.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("That adventurer needs a character before they can be proposed to."),
                ephemeral=True,
            )
            return

        existing_marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        if existing_marriage is not None:
            await interaction.response.send_message(
                embed=error_embed("You are already married. Consider /marriageinfo or /divorce."),
                ephemeral=True,
            )
            return

        target_marriage = await bot.database.fetch_marriage(guild.id, member.id)
        if target_marriage is not None:
            await interaction.response.send_message(
                embed=error_embed("That adventurer is already married."), ephemeral=True
            )
            return

        existing_proposal = await bot.database.fetch_proposal_from(guild.id, interaction.user.id)
        if existing_proposal is not None:
            await interaction.response.send_message(
                embed=error_embed("You already have a pending proposal."),
                ephemeral=True,
            )
            return

        target_pending = await bot.database.fetch_proposal_for(guild.id, member.id)
        if target_pending is not None:
            await interaction.response.send_message(
                embed=error_embed("They already have a pending proposal to respond to."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if proposer.last_proposal_at is not None and now - proposer.last_proposal_at < PROPOSAL_COOLDOWN:
            remaining = PROPOSAL_COOLDOWN - (now - proposer.last_proposal_at)
            minutes = max(1, int(remaining.total_seconds() // 60))
            await interaction.response.send_message(
                embed=error_embed(
                    f"You must wait about {minutes} more minute(s) before proposing again."
                ),
                ephemeral=True,
            )
            return

        try:
            await bot.database.create_proposal(guild.id, interaction.user.id, member.id, created_at=now)
        except ValueError as exc:
            reason = str(exc)
            if reason == "already_married":
                message = "One of you is already married."
            elif reason == "proposal_pending":
                message = "You already have a pending proposal."
            elif reason == "target_has_pending":
                message = "They already have a pending proposal awaiting a response."
            else:
                message = "The proposal could not be recorded. Please try again shortly."
            await interaction.response.send_message(embed=error_embed(message), ephemeral=True)
            return

        proposer.last_proposal_at = now
        await bot.database.set_last_proposal(guild.id, interaction.user.id, now)

        embed = discord.Embed(
            title="A heartfelt proposal!",
            description=(
                f"{interaction.user.mention} has proposed to {member.mention}!\n"
                "Use **/acceptproposal** to celebrate your union."
            ),
            color=discord.Color.magenta(),
        )
        embed.set_footer(text="Love is in the air—respond before someone else does!")
        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )

    @bot.tree.command(name="acceptproposal", description="Accept a pending marriage proposal")
    async def acceptproposal(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("You need to be in a guild to accept a proposal."),
                ephemeral=True,
            )
            return

        proposal = await bot.database.fetch_proposal_for(guild.id, interaction.user.id)
        if proposal is None:
            await interaction.response.send_message(
                embed=error_embed("You do not have any pending proposals."),
                ephemeral=True,
            )
            return

        proposer_member = guild.get_member(proposal.proposer_id)
        proposer_player = await bot.database.fetch_player(guild.id, proposal.proposer_id)
        proposee_player = await bot.database.fetch_player(guild.id, proposal.proposee_id)
        if proposer_player is None or proposer_player.class_id is None:
            await bot.database.delete_proposal(proposal.id)
            await interaction.response.send_message(
                embed=error_embed("The proposer no longer has a valid character."),
                ephemeral=True,
            )
            return
        if proposee_player is None or proposee_player.class_id is None:
            await bot.database.delete_proposal(proposal.id)
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before accepting."),
                ephemeral=True,
            )
            return

        existing_marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        if existing_marriage is not None:
            await bot.database.delete_proposal(proposal.id)
            await interaction.response.send_message(
                embed=error_embed("You are already married."), ephemeral=True
            )
            return

        proposer_marriage = await bot.database.fetch_marriage(guild.id, proposal.proposer_id)
        if proposer_marriage is not None:
            await bot.database.delete_proposal(proposal.id)
            await interaction.response.send_message(
                embed=error_embed("The proposer is already married."), ephemeral=True
            )
            return

        try:
            marriage = await bot.database.create_marriage(
                guild.id, proposal.proposer_id, proposal.proposee_id
            )
        except ValueError as exc:
            await interaction.response.send_message(
                embed=error_embed("The marriage could not be recorded." if str(exc) != "already_married" else "One of you is already married."),
                ephemeral=True,
            )
            return

        spouse_member = get_spouse_member(guild, marriage, interaction.user.id)
        xp_bonus = int(COUPLE_XP_BONUS * 100)
        gold_bonus = int(COUPLE_GOLD_BONUS * 100)
        proposer_after = await bot.database.list_player_achievements(proposal.proposer_id)
        proposee_after = await bot.database.list_player_achievements(proposal.proposee_id)
        proposer_new = [
            record.achievement
            for record in proposer_after
            if record.achievement.code not in proposer_before
        ]
        proposee_new = [
            record.achievement
            for record in proposee_after
            if record.achievement.code not in proposee_before
        ]
        proposer_target = proposer_member or bot.get_user(proposal.proposer_id)
        if proposer_target is None:
            proposer_target = SimpleNamespace(
                mention=f"<@{proposal.proposer_id}>", id=proposal.proposer_id
            )
        achievement_lines: List[str] = []
        if proposer_new:
            achievement_lines.extend(
                format_achievement_lines(proposer_target, proposer_new)
            )
        if proposee_new:
            achievement_lines.extend(
                format_achievement_lines(interaction.user, proposee_new)
            )
        embed = discord.Embed(
            title="A joyous celebration!",
            description=(
                f"{interaction.user.mention} and {proposer_member.mention if proposer_member else f'<@{proposal.proposer_id}>'} "
                "are now married!"
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Adventure Bonus",
            value=(
                f"Earn +{xp_bonus}% XP and +{gold_bonus}% gold when using /couplequest together."
            ),
            inline=False,
        )
        embed.set_footer(text="May your quests be filled with joy and loot!")
        allowed_users = [interaction.user]
        if proposer_member is not None:
            allowed_users.append(proposer_member)
        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=allowed_users),
        )
        if achievement_lines:
            await interaction.followup.send(
                "\n".join(achievement_lines),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=allowed_users),
            )

    @bot.tree.command(name="marriageinfo", description="Show marriage details")
    @app_commands.describe(member="Member to inspect")
    async def marriageinfo(
        interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Marriage details are only available inside guilds."),
                ephemeral=True,
            )
            return

        target = member or interaction.user
        marriage = await bot.database.fetch_marriage(guild.id, target.id)
        if marriage is None:
            message = (
                "You are not currently married." if target.id == interaction.user.id else "That adventurer is not married."
            )
            await interaction.response.send_message(embed=error_embed(message), ephemeral=True)
            return

        spouse_member = get_spouse_member(guild, marriage, target.id)
        spouse_name = (
            spouse_member.mention if spouse_member else f"<@{marriage.partner_id(target.id)}>"
        )
        xp_bonus = int(COUPLE_XP_BONUS * 100)
        gold_bonus = int(COUPLE_GOLD_BONUS * 100)
        embed = discord.Embed(title="Marriage Information", color=discord.Color.blurple())
        embed.add_field(
            name="Partners",
            value=f"{target.mention} ❤ {spouse_name}",
            inline=False,
        )
        embed.add_field(
            name="Date Married",
            value=discord.utils.format_dt(marriage.date_married, style="F"),
            inline=False,
        )
        embed.add_field(
            name="Party Bonus",
            value=(
                f"+{xp_bonus}% XP and +{gold_bonus}% gold while adventuring together with /couplequest."
            ),
            inline=False,
        )

        divorce_request = await bot.database.fetch_divorce_request(marriage.id)
        if divorce_request is not None:
            initiator = guild.get_member(divorce_request.initiator_id)
            initiator_name = (
                initiator.mention if initiator else f"<@{divorce_request.initiator_id}>"
            )
            embed.add_field(
                name="Pending Divorce",
                value=(
                    f"Started by {initiator_name}"
                    f" {discord.utils.format_dt(divorce_request.created_at, style='R')}"
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=member is None or member.id == interaction.user.id,
        )

    @bot.tree.command(name="divorce", description="End a marriage")
    @app_commands.describe(
        member="Member whose marriage should be ended (admin override)",
        force="Force the divorce without requiring both confirmations",
    )
    async def divorce(
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        force: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Divorces can only be processed inside a guild."),
                ephemeral=True,
            )
            return

        if force:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    embed=error_embed("Only administrators can force a divorce."),
                    ephemeral=True,
                )
                return
            target_member = member or interaction.user
            marriage = await bot.database.fetch_marriage(guild.id, target_member.id)
            if marriage is None:
                await interaction.response.send_message(
                    embed=error_embed("No marriage found to dissolve."),
                    ephemeral=True,
                )
                return
            spouse_member = get_spouse_member(guild, marriage, target_member.id)
            await bot.database.delete_marriage_by_id(marriage.id)
            allowed_users = [target_member]
            if spouse_member is not None:
                allowed_users.append(spouse_member)
            embed = discord.Embed(
                title="Marriage dissolved",
                description=(
                    f"An administrator has dissolved the marriage between {target_member.mention}"
                    f" and {spouse_member.mention if spouse_member else f'<@{marriage.partner_id(target_member.id)}>'}."
                ),
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=allowed_users),
            )
            return

        marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        if marriage is None:
            await interaction.response.send_message(
                embed=error_embed("You are not married."),
                ephemeral=True,
            )
            return

        spouse_member = get_spouse_member(guild, marriage, interaction.user.id)
        divorce_request = await bot.database.fetch_divorce_request(marriage.id)
        if divorce_request is None:
            try:
                divorce_request = await bot.database.create_divorce_request(
                    marriage.id, interaction.user.id
                )
            except ValueError:
                divorce_request = await bot.database.fetch_divorce_request(marriage.id)
            notice = (
                f"Divorce requested. {spouse_member.mention if spouse_member else 'Your spouse'}"
                " must also use /divorce to finalize it."
            )
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Divorce pending",
                    description=notice,
                    color=discord.Color.orange(),
                ),
                ephemeral=True,
            )
            if spouse_member is not None:
                await interaction.followup.send(
                    content=(
                        f"{spouse_member.mention}, {interaction.user.mention} has requested a divorce."
                        " Use /divorce to confirm."
                    ),
                    allowed_mentions=discord.AllowedMentions(users=[spouse_member, interaction.user]),
                )
            return

        if divorce_request.initiator_id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Waiting for your spouse to confirm the divorce."),
                ephemeral=True,
            )
            return

        await bot.database.delete_marriage_by_id(marriage.id)
        embed = discord.Embed(
            title="Marriage ended",
            description=(
                f"{interaction.user.mention} and {spouse_member.mention if spouse_member else f'<@{marriage.partner_id(interaction.user.id)}>'}"
                " have agreed to part ways."
            ),
            color=discord.Color.orange(),
        )
        allowed = [interaction.user]
        if spouse_member is not None:
            allowed.append(spouse_member)
        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=allowed),
        )

    @bot.tree.command(name="classinfo", description="Show details about a class")
    @app_commands.describe(class_name="Name of the class to inspect")
    async def classinfo(interaction: discord.Interaction, class_name: str) -> None:
        info = await bot.database.fetch_class_by_name(class_name)
        if info is None and class_name.isdigit():
            info = await bot.database.fetch_class_by_id(int(class_name))
        if info is None:
            available = ", ".join(choice.name for choice in CLASS_CHOICES)
            await interaction.response.send_message(
                embed=error_embed(f"Class not found. Choose from: {available}."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(embed=class_info_embed(info), ephemeral=True)

    @bot.tree.command(name="gold", description="Show your current gold balance")
    async def gold(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Gold balances are tied to guild characters."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create to start earning gold."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            content=f"💰 You currently have **{player.gold} gold**.", ephemeral=True
        )

    @bot.tree.command(name="gift", description="Send gold or items to another adventurer")
    @app_commands.describe(
        member="The adventurer receiving your gift",
        gold="Amount of gold to send",
        item_name="Name of the item, material, weapon, or armor to gift",
        quantity="How many to send when gifting stackable items",
    )
    async def gift(
        interaction: discord.Interaction,
        member: discord.Member,
        gold: Optional[int] = None,
        item_name: Optional[str] = None,
        quantity: Optional[int] = 1,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Gifts can only be exchanged inside a guild."),
                ephemeral=True,
            )
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("You cannot gift yourself."),
                ephemeral=True,
            )
            return
        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before gifting."),
                ephemeral=True,
            )
            return
        recipient = await bot.database.fetch_player(guild.id, member.id)
        if recipient is None or recipient.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("That adventurer hasn't created a character yet."),
                ephemeral=True,
            )
            return
        if (gold is None and item_name is None) or (gold is not None and item_name is not None):
            await interaction.response.send_message(
                embed=error_embed("Specify either a gold amount or an item to gift."),
                ephemeral=True,
            )
            return

        if gold is not None:
            amount = gold
            if amount <= 0:
                await interaction.response.send_message(
                    embed=error_embed("Gifted gold must be a positive amount."),
                    ephemeral=True,
                )
                return
            if player.gold < amount:
                await interaction.response.send_message(
                    embed=error_embed("You don't have enough gold for that gift."),
                    ephemeral=True,
                )
                return
            player.gold -= amount
            recipient.gold += amount
            await bot.database.update_player(player)
            await bot.database.update_player(recipient)
            embed = discord.Embed(
                title="Gift Sent!",
                description=(
                    f"{interaction.user.mention} sent **{amount} gold** to {member.mention}."
                ),
                color=SUCCESS_COLOR,
            )
            await interaction.response.send_message(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user, member]),
            )
            return

        assert item_name is not None
        item_query = item_name.strip()
        if not item_query:
            await interaction.response.send_message(
                embed=error_embed("Provide the name of the item you want to gift."),
                ephemeral=True,
            )
            return
        amount_to_give = quantity if quantity is not None else 1
        if amount_to_give <= 0:
            await interaction.response.send_message(
                embed=error_embed("Gift quantity must be at least one."),
                ephemeral=True,
            )
            return

        fetchers = (
            bot.database.fetch_item_entry_by_name,
            bot.database.fetch_material_entry_by_name,
            bot.database.fetch_weapon_entry_by_name,
            bot.database.fetch_armor_entry_by_name,
        )
        entry_payload: Optional[Tuple[InventoryEntry, InventoryPayload]] = None
        for fetcher in fetchers:
            entry_payload = await fetcher(guild.id, interaction.user.id, item_query)
            if entry_payload is not None:
                break
        if entry_payload is None:
            await interaction.response.send_message(
                embed=error_embed("You don't have that item to gift."),
                ephemeral=True,
            )
            return
        entry, payload = entry_payload
        if entry.item_type in {"weapon", "armor"} and amount_to_give != 1:
            await interaction.response.send_message(
                embed=error_embed("Weapons and armor can only be gifted one at a time."),
                ephemeral=True,
            )
            return
        try:
            await bot.database.remove_inventory_quantity(guild.id, interaction.user.id, entry, amount_to_give)
        except ValueError as exc:
            reason = str(exc)
            if reason == "item_equipped":
                message = "Unequip that item before gifting it."
            elif reason in {"insufficient_quantity", "entry_not_found"}:
                message = "You don't have enough quantity of that item."
            else:
                message = "Unable to gift that item right now."
            await interaction.response.send_message(
                embed=error_embed(message),
                ephemeral=True,
            )
            return

        if entry.item_type == "item":
            assert isinstance(payload, Item)
            await bot.database.grant_item_to_player(guild.id, member.id, payload, amount_to_give)
            item_label = payload.name
        elif entry.item_type == "material":
            assert isinstance(payload, Material)
            await bot.database.grant_material_to_player(guild.id, member.id, payload, amount_to_give)
            item_label = payload.name
        elif entry.item_type == "weapon":
            assert isinstance(payload, Weapon)
            await bot.database.grant_weapon_to_player(guild.id, member.id, payload)
            item_label = payload.name
        else:
            assert isinstance(payload, Armor)
            await bot.database.grant_armor_to_player(guild.id, member.id, payload)
            item_label = payload.name

        quantity_text = f"x{amount_to_give} " if entry.item_type in {"item", "material"} and amount_to_give > 1 else ""
        embed = discord.Embed(
            title="Gift Sent!",
            description=(
                f"{interaction.user.mention} gifted {quantity_text}**{item_label}** to {member.mention}."
            ),
            color=SUCCESS_COLOR,
        )
        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user, member]),
        )

    @bot.tree.command(name="gamble", description="Wager gold for a chance at extra winnings")
    @app_commands.describe(amount="Gold amount to wager")
    async def gamble(interaction: discord.Interaction, amount: int) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("You can only gamble inside a guild."),
                ephemeral=True,
            )
            return
        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before gambling."),
                ephemeral=True,
            )
            return
        wager = max(0, amount)
        if wager <= 0:
            await interaction.response.send_message(
                embed=error_embed("Your wager must be greater than zero."),
                ephemeral=True,
            )
            return
        if player.gold < wager:
            await interaction.response.send_message(
                embed=error_embed("You don't have enough gold for that wager."),
                ephemeral=True,
            )
            return

        roll = random.random()
        if roll >= 0.95:
            winnings = wager * 3
            player.gold += winnings
            result_text = f"Jackpot! You won **{winnings}** gold."
        elif roll >= 0.55:
            winnings = wager
            player.gold += winnings
            result_text = f"You won **{winnings}** gold."
        else:
            player.gold -= wager
            result_text = f"Bad luck! You lost **{wager}** gold."

        await bot.database.update_player(player)
        embed = discord.Embed(
            title="Gamble Results",
            description=result_text,
            color=SUCCESS_COLOR if "won" in result_text.lower() else discord.Color.red(),
        )
        embed.set_footer(text=f"Current balance: {player.gold} gold")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="roll", description="Roll a die for bragging rights or wagers")
    @app_commands.describe(
        sides="Number of sides on the die (2-1000)",
        bet="Optional gold bet to stake on the roll",
    )
    async def roll(
        interaction: discord.Interaction,
        sides: Optional[int] = 100,
        bet: Optional[int] = 0,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Dice rolling is only available inside a guild."),
                ephemeral=True,
            )
            return
        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create a character with /create to roll dice."),
                ephemeral=True,
            )
            return
        total_sides = sides or 100
        total_sides = max(2, min(1000, total_sides))
        wager = max(0, bet or 0)
        if wager > 0 and player.gold < wager:
            await interaction.response.send_message(
                embed=error_embed("You don't have enough gold for that bet."),
                ephemeral=True,
            )
            return

        result = random.randint(1, total_sides)
        net_change = 0
        if wager > 0:
            high_threshold = math.ceil(total_sides * 0.75)
            low_threshold = max(1, math.floor(total_sides * 0.25))
            if result == total_sides:
                net_change = wager * 2
            elif result >= high_threshold:
                net_change = wager
            elif result <= low_threshold:
                net_change = -wager
            elif result == 1:
                net_change = -(wager * 2)
            if net_change > 0:
                player.gold += net_change
            elif net_change < 0:
                player.gold += net_change  # net_change is negative
                if player.gold < 0:
                    player.gold = 0
        outcome_lines = [
            f"🎲 Rolled a **{result}** on a d{total_sides}.",
        ]
        if wager > 0:
            if net_change > 0:
                outcome_lines.append(f"You won **{net_change}** gold!")
            elif net_change < 0:
                outcome_lines.append(f"You lost **{abs(net_change)}** gold.")
            else:
                outcome_lines.append("No gold changed hands this time.")
        await bot.database.update_player(player)
        embed = discord.Embed(
            title="Dice Roll",
            description="\n".join(outcome_lines),
            color=SUCCESS_COLOR if net_change >= 0 else discord.Color.red(),
        )
        if wager > 0:
            embed.set_footer(text=f"Current balance: {player.gold} gold")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="flip", description="Flip a coin and test your luck")
    @app_commands.describe(
        call="Your call: heads or tails",
        bet="Optional gold bet to stake on the flip",
    )
    async def flip(
        interaction: discord.Interaction,
        call: Optional[str] = None,
        bet: Optional[int] = 0,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Coin flips are only available inside a guild."),
                ephemeral=True,
            )
            return
        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create a character with /create to flip coins."),
                ephemeral=True,
            )
            return
        wager = max(0, bet or 0)
        call_normalized = call.lower().strip() if call else ""
        if wager > 0:
            if player.gold < wager:
                await interaction.response.send_message(
                    embed=error_embed("You don't have enough gold for that bet."),
                    ephemeral=True,
                )
                return
            if call_normalized not in {"heads", "tails"}:
                await interaction.response.send_message(
                    embed=error_embed("Call heads or tails when placing a bet."),
                    ephemeral=True,
                )
                return
        result = random.choice(["heads", "tails"])
        win = wager > 0 and call_normalized == result
        lose = wager > 0 and call_normalized and call_normalized != result
        if win:
            player.gold += wager
        elif lose:
            player.gold -= wager
            if player.gold < 0:
                player.gold = 0
        await bot.database.update_player(player)

        outcome_lines = [f"🪙 The coin landed on **{result.title()}**."]
        if wager > 0:
            if win:
                outcome_lines.append(f"You won **{wager}** gold!")
            else:
                outcome_lines.append(f"You lost **{wager}** gold.")
        embed = discord.Embed(
            title="Coin Flip",
            description="\n".join(outcome_lines),
            color=SUCCESS_COLOR if win or wager == 0 else discord.Color.red(),
        )
        if wager > 0:
            embed.set_footer(text=f"Current balance: {player.gold} gold")
        await interaction.response.send_message(embed=embed)

    shop_group = app_commands.Group(name="shop", description="Browse the IdleRPG shop")

    @shop_group.command(name="view", description="List available shop inventory")
    @app_commands.describe(page="Page number to view")
    async def shop_view(interaction: discord.Interaction, page: Optional[int] = 1) -> None:
        page_number = page or 1
        await ensure_shop_rotation()
        rotation_entries = await bot.database.get_active_shop_rotation_items()
        rotation_by_category: Dict[str, List[str]] = {key: [] for key in SHOP_ROTATION_CATEGORY_LABELS}
        for entry, item in rotation_entries:
            if entry.item_type == "weapon" and isinstance(item, Weapon):
                rotation_by_category["weapon"].append(
                    format_rotation_weapon(entry, item)
                )
            elif entry.item_type == "armor" and isinstance(item, Armor):
                rotation_by_category["armor"].append(
                    format_rotation_armor(entry, item)
                )
            elif entry.item_type == "item" and isinstance(item, Item):
                rotation_by_category["item"].append(
                    format_rotation_item(entry, item)
                )
        rotation_expiry = await bot.database.get_shop_rotation_expiry()
        weapons = list(await bot.database.list_generic_weapons())
        armor = list(await bot.database.list_generic_armor())
        items = list(await bot.database.list_generic_items())
        page_number, total_pages, paginated = paginate_collections(
            [weapons, armor, items], page_number, PAGE_SIZE
        )
        weapons_page, armor_page, items_page = paginated
        embed = discord.Embed(
            title="Adventurer's Shop",
            description="Quality gear for every class.",
            color=discord.Color.gold(),
        )
        for item_type, label in SHOP_ROTATION_CATEGORY_LABELS.items():
            entries = rotation_by_category.get(item_type) or []
            if entries:
                embed.add_field(
                    name=f"Daily Deals — {label}",
                    value="\n".join(entries),
                    inline=False,
                )
        if weapons_page:
            embed.add_field(
                name="Weapons",
                value="\n".join(format_weapon(w) for w in weapons_page),
                inline=False,
            )
        if armor_page:
            embed.add_field(
                name="Armor",
                value="\n".join(format_armor(a) for a in armor_page),
                inline=False,
            )
        if items_page:
            embed.add_field(
                name="Consumables",
                value="\n".join(format_item(i) for i in items_page),
                inline=False,
            )
        if not weapons_page and not armor_page and not items_page:
            embed.description = "The shop has no stock at the moment."
        footer_parts: List[str] = []
        if rotation_expiry is not None:
            footer_parts.append(
                f"Daily deals refresh {discord.utils.format_dt(rotation_expiry, style='R')}"
            )
        footer_parts.append(f"Page {page_number} of {total_pages}")
        embed.set_footer(text=" • ".join(footer_parts))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @shop_group.command(name="refresh", description="Force refresh of the daily shop rotation")
    async def shop_refresh(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Daily deals can only be refreshed from within a guild."),
                ephemeral=True,
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed("Only administrators can refresh the daily deals."),
                ephemeral=True,
            )
            return

        await ensure_shop_rotation(force=True)
        await restart_shop_rotation_scheduler()
        rotation_entries = await bot.database.get_active_shop_rotation_items()
        rotation_expiry = await bot.database.get_shop_rotation_expiry()
        embed = discord.Embed(
            title="Daily deals refreshed!",
            color=discord.Color.gold(),
        )
        sections_added = False
        for item_type, label in SHOP_ROTATION_CATEGORY_LABELS.items():
            lines: List[str] = []
            for entry, item in rotation_entries:
                if entry.item_type != item_type:
                    continue
                if item_type == "weapon" and isinstance(item, Weapon):
                    lines.append(format_rotation_weapon(entry, item))
                elif item_type == "armor" and isinstance(item, Armor):
                    lines.append(format_rotation_armor(entry, item))
                elif item_type == "item" and isinstance(item, Item):
                    lines.append(format_rotation_item(entry, item))
            if lines:
                sections_added = True
                embed.add_field(name=f"Daily Deals — {label}", value="\n".join(lines), inline=False)
        if not sections_added:
            embed.description = "No eligible items were found for today's rotation."
        if rotation_expiry is not None:
            embed.set_footer(
                text=f"Refreshes again {discord.utils.format_dt(rotation_expiry, style='R')}"
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @shop_group.command(name="buy", description="Purchase an item from the shop")
    @app_commands.describe(item="Name of the weapon, armor, or consumable to buy")
    async def shop_buy(interaction: discord.Interaction, item: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Purchases must be made from within a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character first using /create."),
                ephemeral=True,
            )
            return

        weapon = await bot.database.fetch_weapon_by_name(item)
        armor_item = None
        consumable = None
        if weapon is None:
            armor_item = await bot.database.fetch_armor_by_name(item)
            if armor_item is None:
                consumable = await bot.database.fetch_item_by_name(item)
                if consumable is None:
                    await interaction.response.send_message(
                        embed=error_embed("That item is not sold in the shop."),
                        ephemeral=True,
                    )
                    return

        player_class = (
            await bot.database.fetch_class_by_id(player.class_id)
            if player.class_id is not None
            else None
        )

        async def ensure_available(item_type: str, obj: object) -> bool:
            is_generic = bool(getattr(obj, "is_generic", False))
            event_id = getattr(obj, "event_id", None)
            if is_generic or event_id is not None:
                return True
            return await bot.database.is_item_in_active_rotation(item_type, getattr(obj, "id"))

        try:
            if weapon is not None:
                if not await ensure_available("weapon", weapon):
                    await interaction.response.send_message(
                        embed=error_embed("That weapon is not currently featured in the daily deals."),
                        ephemeral=True,
                    )
                    return
                if weapon.class_restriction and (
                    player_class is None
                    or weapon.class_restriction.lower() != player_class.name.lower()
                ):
                    await interaction.response.send_message(
                        embed=error_embed(
                            "Your class cannot wield that weapon. Choose something compatible."
                        ),
                        ephemeral=True,
                    )
                    return
                await bot.database.buy_weapon(interaction.guild.id, interaction.user.id, weapon)
                purchased_name = weapon.name
                price = weapon.price
            elif armor_item is not None:
                if not await ensure_available("armor", armor_item):
                    await interaction.response.send_message(
                        embed=error_embed("That armor is not currently featured in the daily deals."),
                        ephemeral=True,
                    )
                    return
                await bot.database.buy_armor(interaction.guild.id, interaction.user.id, armor_item)
                purchased_name = armor_item.name
                price = armor_item.price
            else:
                assert consumable is not None
                if not await ensure_available("item", consumable):
                    await interaction.response.send_message(
                        embed=error_embed("That consumable is not currently featured in the daily deals."),
                        ephemeral=True,
                    )
                    return
                await bot.database.buy_item(interaction.guild.id, interaction.user.id, consumable)
                purchased_name = consumable.name
                price = consumable.price
        except ValueError as exc:
            reason = str(exc)
            if reason == "insufficient_gold":
                message = "You don't have enough gold for that purchase."
            elif reason == "player_not_found":
                message = "Your character could not be found. Try /create again."
            else:
                message = "The purchase could not be completed."
            await interaction.response.send_message(embed=error_embed(message), ephemeral=True)
            return

        updated = await bot.database.fetch_player(interaction.guild.id, interaction.user.id)
        remaining = updated.gold if updated else player.gold - price
        embed = discord.Embed(
            title="Purchase successful!",
            description=f"You bought **{purchased_name}** for **{price} gold**.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Gold remaining", value=f"💰 {remaining}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    bot.tree.add_command(shop_group)

    auction_group = app_commands.Group(
        name="auction", description="Trade items with other adventurers"
    )

    @auction_group.command(name="list", description="List an item for sale")
    @app_commands.describe(
        item="Name of the item to list from your inventory",
        price="Listing price in gold",
    )
    async def auction_list_command(
        interaction: discord.Interaction, item: str, price: int
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Auctions are only available inside guilds."),
                ephemeral=True,
            )
            return

        item_name = item.strip()
        if not item_name:
            await interaction.response.send_message(
                embed=error_embed("Provide the name of the item you want to list."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("You need a character before you can use the auction house. Try /start."),
                ephemeral=True,
            )
            return

        if price <= 0:
            await interaction.response.send_message(
                embed=error_embed("Listing price must be at least 1 gold."),
                ephemeral=True,
            )
            return

        entry_payload: Optional[Tuple[InventoryEntry, InventoryPayload]] = None
        weapon_entry = await bot.database.fetch_weapon_entry_by_name(
            guild.id, interaction.user.id, item_name
        )
        if weapon_entry is not None:
            entry_payload = weapon_entry
        else:
            armor_entry = await bot.database.fetch_armor_entry_by_name(
                guild.id, interaction.user.id, item_name
            )
            if armor_entry is not None:
                entry_payload = armor_entry
            else:
                consumable_entry = await bot.database.fetch_item_entry_by_name(
                    guild.id, interaction.user.id, item_name
                )
                if consumable_entry is not None:
                    entry_payload = consumable_entry
                else:
                    material_entry = await bot.database.fetch_material_entry_by_name(
                        guild.id, interaction.user.id, item_name
                    )
                    if material_entry is not None:
                        entry_payload = material_entry

        if entry_payload is None:
            await interaction.response.send_message(
                embed=error_embed("That item is not in your inventory."),
                ephemeral=True,
            )
            return

        entry, payload = entry_payload

        try:
            listing = await bot.database.create_listing(
                guild.id,
                interaction.user.id,
                entry.id,
                price,
                listing_fee=bot.settings.auction_listing_fee,
            )
        except ValueError as exc:
            reason = str(exc)
            if reason == "invalid_price":
                message = "Listing price must be at least 1 gold."
            elif reason == "inventory_not_found":
                message = "That item could not be found in your inventory."
            elif reason == "item_equipped":
                message = "Unequip the item before listing it on the auction house."
            elif reason == "insufficient_gold":
                message = "You don't have enough gold to pay the listing fee."
            elif reason == "no_quantity":
                message = "You don't have any of that item available to list."
            else:
                message = "The listing could not be created."
            await interaction.response.send_message(
                embed=error_embed(message),
                ephemeral=True,
            )
            return

        updated_player = await bot.database.fetch_player(guild.id, interaction.user.id)
        balance = updated_player.gold if updated_player else player.gold

        embed = discord.Embed(
            title="Auction listing created!",
            description=format_auction_listing_entry(listing, payload),
            color=SUCCESS_COLOR,
        )
        if bot.settings.auction_listing_fee > 0:
            embed.add_field(
                name="Listing fee",
                value=f"💰 {bot.settings.auction_listing_fee}",
                inline=True,
            )
        embed.add_field(name="Gold remaining", value=f"💰 {balance}", inline=True)
        embed.set_footer(text="A 5% sales tax is applied when listings are sold.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @auction_group.command(name="browse", description="Browse active auction listings")
    @app_commands.describe(page="Page number to view")
    async def auction_browse_command(
        interaction: discord.Interaction, page: Optional[int] = 1
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Auctions are only available inside guilds."),
                ephemeral=True,
            )
            return

        page_number = max(1, page or 1)
        total, results = await bot.database.list_active_listings(page_number, PAGE_SIZE)
        listings = list(results)
        if not listings and total > 0 and page_number > 1:
            last_page = max(1, math.ceil(total / PAGE_SIZE))
            total, results = await bot.database.list_active_listings(last_page, PAGE_SIZE)
            listings = list(results)
            page_number = last_page

        total_pages = max(1, math.ceil(total / PAGE_SIZE)) if total > 0 else 1
        embed = discord.Embed(title="Auction House", color=discord.Color.blurple())
        if listings:
            embed.description = "\n\n".join(
                format_auction_listing_entry(listing, payload)
                for listing, payload in listings
            )
        else:
            embed.description = "No active listings right now. Check back later!"
        embed.set_footer(
            text=f"Page {page_number} of {total_pages} • 5% sales tax on successful sales"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @auction_group.command(name="buy", description="Buy an item from the auction house")
    @app_commands.describe(listing_id="ID of the listing to purchase")
    async def auction_buy_command(
        interaction: discord.Interaction, listing_id: int
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Auctions are only available inside guilds."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                embed=error_embed("You need a character before you can buy from the auction house."),
                ephemeral=True,
            )
            return

        try:
            listing, payload, tax_amount = await bot.database.buy_listing(
                guild.id, listing_id, interaction.user.id
            )
        except ValueError as exc:
            reason = str(exc)
            if reason == "listing_not_found":
                message = "No listing with that ID exists."
            elif reason == "listing_expired":
                message = "That listing has already expired."
            elif reason == "cannot_buy_own":
                message = "You cannot buy your own listing."
            elif reason == "insufficient_gold":
                message = "You don't have enough gold for that purchase."
            elif reason == "seller_missing":
                message = "The seller is no longer available. The listing has been removed."
            elif reason == "item_missing":
                message = "The listed item is no longer available. The listing has been removed."
            elif reason == "player_not_found":
                message = "You need a character before you can buy from the auction house."
            else:
                message = "The purchase could not be completed."
            await interaction.response.send_message(
                embed=error_embed(message),
                ephemeral=True,
            )
            return

        updated_player = await bot.database.fetch_player(guild.id, interaction.user.id)
        balance = updated_player.gold if updated_player else player.gold - listing.price
        payout = listing.price - tax_amount

        embed = discord.Embed(
            title="Auction purchase successful!",
            description=format_auction_listing_entry(listing, payload),
            color=SUCCESS_COLOR,
        )
        embed.add_field(name="Sales tax removed", value=f"💰 {tax_amount}", inline=True)
        embed.add_field(name="Seller payout", value=f"💰 {payout}", inline=True)
        embed.add_field(name="Gold remaining", value=f"💰 {balance}", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    bot.tree.add_command(auction_group)

    craft_group = app_commands.Group(
        name="craft", description="Forge new weapons and armor from gathered materials"
    )
    bot.tree.add_command(craft_group)

    @craft_group.command(name="weapon", description="Forge a new weapon using materials")
    @app_commands.describe(
        name="Name for the crafted weapon",
        rarity="Desired rarity tier",
        class_restriction="Optional class restriction for the weapon",
        to_shop="Add the crafted weapon to the public shop instead of your inventory",
    )
    @app_commands.choices(rarity=RARITY_CHOICES)
    async def craft_weapon_command(
        interaction: discord.Interaction,
        name: str,
        rarity: app_commands.Choice[str],
        class_restriction: Optional[str] = None,
        to_shop: Optional[bool] = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Crafting must be done inside a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before crafting."),
                ephemeral=True,
            )
            return

        recipe = CRAFTING_RECIPES[rarity.value]
        materials_needed = await gather_crafting_materials(
            guild.id, interaction.user.id, recipe["tier"], recipe["materials"]
        )
        if materials_needed is None:
            await interaction.response.send_message(
                embed=error_embed(
                    (
                        f"You need {recipe['materials']} materials of tier {recipe['tier']} or higher"
                        " to craft this weapon. Run more quests and raids!"
                    )
                ),
                ephemeral=True,
            )
            return

        success_chance = recipe["success"]
        for material, quantity in materials_needed:
            await bot.database.consume_materials(guild.id, interaction.user.id, material, quantity)

        succeeded = random.random() <= success_chance
        embed: discord.Embed
        summary = summarize_materials(materials_needed)
        success_percent = int(success_chance * 100)
        rarity_title = rarity.name

        if succeeded:
            damage = random.randint(*recipe["weapon_damage"])
            durability = random.randint(*recipe["weapon_durability"])
            price = random.randint(*recipe["price"])
            weapon = await bot.database.add_weapon(
                name=name,
                damage=damage,
                durability=durability,
                price=price,
                class_restriction=class_restriction,
                rarity=rarity.value,
                is_generic=bool(to_shop),
            )
            if not to_shop:
                await bot.database.grant_weapon_to_player(guild.id, interaction.user.id, weapon)
            result_text = (
                "Added to the public shop." if to_shop else "Added to your inventory."
            )
            embed = discord.Embed(
                title="Weapon Forged!",
                description=(
                    f"Successfully forged **{weapon.name}** ({rarity_title}). {result_text}"
                ),
                color=discord.Color.gold(),
            )
            embed.add_field(
                name="Weapon Stats",
                value=f"DMG {damage} • DUR {durability} • Price {price} gold",
                inline=False,
            )
            if class_restriction:
                embed.add_field(
                    name="Class Restriction",
                    value=class_restriction,
                    inline=False,
                )
            embed.add_field(name="Materials Used", value=summary, inline=False)
            embed.add_field(name="Success Chance", value=f"{success_percent}%", inline=True)
        else:
            embed = discord.Embed(
                title="Crafting Failed",
                description=(
                    "The forge sputtered and the weapon failed to take shape. Better luck next time!"
                ),
                color=discord.Color.red(),
            )
            embed.add_field(name="Materials Lost", value=summary, inline=False)
            embed.add_field(name="Success Chance", value=f"{success_percent}%", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @craft_group.command(name="armor", description="Forge new armor using materials")
    @app_commands.describe(
        name="Name for the crafted armor",
        rarity="Desired rarity tier",
        to_shop="Add the crafted armor to the public shop instead of your inventory",
    )
    @app_commands.choices(rarity=RARITY_CHOICES)
    async def craft_armor_command(
        interaction: discord.Interaction,
        name: str,
        rarity: app_commands.Choice[str],
        to_shop: Optional[bool] = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Crafting must be done inside a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before crafting."),
                ephemeral=True,
            )
            return

        recipe = CRAFTING_RECIPES[rarity.value]
        materials_needed = await gather_crafting_materials(
            guild.id, interaction.user.id, recipe["tier"], recipe["materials"]
        )
        if materials_needed is None:
            await interaction.response.send_message(
                embed=error_embed(
                    (
                        f"You need {recipe['materials']} materials of tier {recipe['tier']} or higher"
                        " to craft this armor. Run more quests and raids!"
                    )
                ),
                ephemeral=True,
            )
            return

        success_chance = recipe["success"]
        for material, quantity in materials_needed:
            await bot.database.consume_materials(guild.id, interaction.user.id, material, quantity)

        succeeded = random.random() <= success_chance
        summary = summarize_materials(materials_needed)
        success_percent = int(success_chance * 100)
        rarity_title = rarity.name

        if succeeded:
            defense = random.randint(*recipe["armor_defense"])
            price = random.randint(*recipe["price"])
            armor_piece = await bot.database.add_armor(
                name=name,
                defense_boost=defense,
                price=price,
                rarity=rarity.value,
                is_generic=bool(to_shop),
            )
            if not to_shop:
                await bot.database.grant_armor_to_player(guild.id, interaction.user.id, armor_piece)
            result_text = (
                "Added to the public shop." if to_shop else "Added to your inventory."
            )
            embed = discord.Embed(
                title="Armor Forged!",
                description=(
                    f"Successfully forged **{armor_piece.name}** ({rarity_title}). {result_text}"
                ),
                color=discord.Color.gold(),
            )
            embed.add_field(
                name="Armor Stats",
                value=f"DEF +{defense} • Price {price} gold",
                inline=False,
            )
            embed.add_field(name="Materials Used", value=summary, inline=False)
            embed.add_field(name="Success Chance", value=f"{success_percent}%", inline=True)
        else:
            embed = discord.Embed(
                title="Crafting Failed",
                description=(
                    "The smith's hammer slips and the armor shatters. The materials are lost."
                ),
                color=discord.Color.red(),
            )
            embed.add_field(name="Materials Lost", value=summary, inline=False)
            embed.add_field(name="Success Chance", value=f"{success_percent}%", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    quest_group = app_commands.Group(
        name="quest", description="Browse and embark on quests"
    )

    @quest_group.command(name="status", description="Check your current quest timer")
    async def quest_status(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Quests require a guild context."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Create your character with /create before checking quest status."
                ),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)

        if not player.active_quest_id:
            embed = discord.Embed(
                title="No active quest",
                description="You are not currently on a quest. Use /quest start to begin one.",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        quest_def = find_quest(player.active_quest_id)
        if quest_def is None:
            player.active_quest_id = None
            player.active_quest_complete_at = None
            await bot.database.update_player(player)
            await interaction.response.send_message(
                embed=error_embed(
                    "Your previous quest is no longer available and has been cleared."
                ),
                ephemeral=True,
            )
            return

        remaining = active_quest_remaining(player, now)
        if remaining is None:
            remaining = timedelta(0)
        if remaining <= timedelta(0):
            progress_map = await bot.database.fetch_player_quest_progress(interaction.user.id)
            await complete_active_quest(
                interaction,
                player,
                quest_def,
                progress_map=progress_map,
                now=now,
            )
            return

        finish_at = player.active_quest_complete_at
        finish_text = (
            discord.utils.format_dt(finish_at, style="R") if finish_at is not None else "Unknown"
        )
        embed = discord.Embed(
            title=f"{quest_def.name} in progress",
            description=(
                f"Time remaining: **{short_timedelta(remaining)}**\n"
                f"Expected completion: {finish_text}"
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Summary", value=quest_def.summary, inline=False)
        embed.set_footer(text="Quests resolve automatically once the timer ends.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @quest_group.command(name="list", description="View all quest options and cooldowns")
    async def quest_list(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Quests require a guild context."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Create your character with /create before browsing quests."
                ),
                ephemeral=True,
            )
            return

        progress_map = await bot.database.fetch_player_quest_progress(interaction.user.id)
        now = datetime.now(timezone.utc)
        embed = quest_list_embed(interaction.user, all_quests(), progress_map, now)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @quest_group.command(name="start", description="Begin a named quest")
    @app_commands.describe(quest="Quest name to embark upon")
    async def quest_start(interaction: discord.Interaction, quest: str) -> None:
        quest_def = find_quest(quest)
        if quest_def is None:
            await interaction.response.send_message(
                embed=error_embed("Quest not found. Use /quest list to review options."),
                ephemeral=True,
            )
            return

        progress_map = await bot.database.fetch_player_quest_progress(interaction.user.id)
        await execute_quest(interaction, quest_def, progress_map=progress_map)

    @quest_start.autocomplete("quest")
    async def quest_start_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        quests = search_quests(current)
        progress_map = await bot.database.fetch_player_quest_progress(interaction.user.id)
        now = datetime.now(timezone.utc)
        choices: List[app_commands.Choice[str]] = []
        for quest_def in quests:
            availability = quest_def.availability(progress_map.get(quest_def.id), now)
            if availability.locked:
                status = "Completed"
            elif availability.available:
                status = "Ready"
            elif availability.cooldown_remaining is not None:
                status = f"Cooldown {short_timedelta(availability.cooldown_remaining)}"
            else:
                status = "Unavailable"
            choices.append(
                app_commands.Choice(name=f"{quest_def.name} ({status})", value=quest_def.id)
            )
            if len(choices) >= 25:
                break
        return choices

    bot.tree.add_command(quest_group)

    @bot.tree.command(name="adventure", description="Embark on a random quest adventure")
    async def adventure(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Adventures require a guild context."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before adventuring."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return
        ready, remaining = can_quest(player, now)
        if not ready:
            await interaction.response.send_message(
                embed=cooldown_embed("quest", remaining), ephemeral=True
            )
            return
        if player.hp <= 10:
            await interaction.response.send_message(
                embed=error_embed("You are too wounded. Visit /heal before your next adventure."),
                ephemeral=True,
            )
            return

        progress_map = await bot.database.fetch_player_quest_progress(interaction.user.id)
        duration_minutes = random.randint(5, 30)
        quest_choice = random_adventure_quest(timedelta(minutes=duration_minutes))
        await execute_quest(interaction, quest_choice, progress_map=progress_map)

    async def autocomplete_raid_boss(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        bosses = await bot.database.list_raid_bosses()
        term = current.lower()
        choices: List[app_commands.Choice[str]] = []
        for boss in bosses:
            if not term or term in boss.name.lower():
                choices.append(app_commands.Choice(name=boss.name, value=str(boss.id)))
            if len(choices) >= 25:
                break
        return choices

    event_group = app_commands.Group(
        name="event", description="Limited-time seasonal adventures"
    )
    bot.tree.add_command(event_group)

    @event_group.command(name="info", description="View the current seasonal event")
    async def event_info(interaction: discord.Interaction) -> None:
        event = await bot.database.fetch_active_event()
        if event is None:
            await interaction.response.send_message(
                embed=error_embed("There is no active event right now."),
                ephemeral=True,
            )
            return

        await bot.database.purge_expired_inventory(interaction.user.id)
        items = await bot.database.list_event_items(event.id)
        weapons = await bot.database.list_event_weapons(event.id)
        raid_boss = await bot.database.fetch_event_raid_boss(event.id)
        raid_instance = None
        if raid_boss is not None:
            raid_instance = await bot.database.fetch_active_event_raid(event.id)
        participant = await bot.database.fetch_event_participant(
            event.id, interaction.user.id
        )
        embed = event_info_embed(
            event,
            joined=participant is not None,
            items=items,
            weapons=weapons,
            raid=raid_instance,
            raid_boss=raid_boss,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @event_group.command(name="join", description="Join the current seasonal event")
    async def event_join(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Events must be joined from within a guild."),
                ephemeral=True,
            )
            return

        event = await bot.database.fetch_active_event()
        if event is None:
            await interaction.response.send_message(
                embed=error_embed("There is no active event to join right now."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before joining events."),
                ephemeral=True,
            )
            return

        await bot.database.purge_expired_inventory(interaction.user.id)
        newly_joined = await bot.database.ensure_event_participant(
            event.id, interaction.user.id
        )
        items = await bot.database.list_event_items(event.id)
        weapons = await bot.database.list_event_weapons(event.id)
        reward_lines: List[str] = []
        expiry_text = discord.utils.format_dt(event.end_date, style="R")
        if newly_joined:
            for weapon in weapons:
                await bot.database.grant_weapon_to_player(
                    guild.id,
                    interaction.user.id,
                    weapon,
                    expires_at=event.end_date,
                )
                reward_lines.append(f"🗡️ {weapon.name} — expires {expiry_text}")
            for item in items:
                await bot.database.grant_item_to_player(
                    guild.id,
                    interaction.user.id,
                    item,
                    3,
                    expires_at=event.end_date,
                )
                reward_lines.append(f"🎁 {item.name} ×3 — expires {expiry_text}")
            if not reward_lines:
                reward_lines.append("Registered for the event! Rewards will drop from the raid boss.")
        else:
            reward_lines.append(
                "You are already enlisted in this event. Rally your allies for the raid!"
            )

        raid_boss = await bot.database.fetch_event_raid_boss(event.id)
        raid_instance = None
        participant: Optional[RaidParticipant] = None
        if raid_boss is not None:
            raid_instance = await bot.database.fetch_active_event_raid(event.id)
            if raid_instance is None or not raid_instance.is_active:
                raid_instance = await bot.database.create_raid_instance(
                    raid_boss.id, interaction.user.id, event_id=event.id
                )
            participant = await bot.database.ensure_raid_participant(
                raid_instance.id, interaction.user.id
            )

        embed = event_join_embed(
            interaction.user,
            event,
            rewards=reward_lines,
            raid_boss=raid_boss,
            raid=raid_instance,
            joined_now=newly_joined,
        )
        embeds = [embed]
        if raid_boss is not None and raid_instance is not None and participant is not None:
            embeds.append(raid_join_embed(interaction.user, raid_boss, raid_instance, participant))
        await interaction.response.send_message(embeds=embeds)

    @event_group.command(name="attack", description="Strike the event raid boss")
    async def event_attack(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Event raids must be attempted from within a guild."),
                ephemeral=True,
            )
            return

        event = await bot.database.fetch_active_event()
        if event is None:
            await interaction.response.send_message(
                embed=error_embed("There is no active event raid to attack."),
                ephemeral=True,
            )
            return

        raid_instance = await bot.database.fetch_active_event_raid(event.id)
        if raid_instance is None or not raid_instance.is_active:
            await interaction.response.send_message(
                embed=error_embed(
                    "The event raid is not active. Use /event join to summon the boss."
                ),
                ephemeral=True,
            )
            return

        boss = await bot.database.fetch_raid_boss_by_id(raid_instance.boss_id)
        if boss is None:
            await interaction.response.send_message(
                embed=error_embed("The event raid boss data is missing."),
                ephemeral=True,
            )
            return

        participant = await bot.database.fetch_event_participant(event.id, interaction.user.id)
        if participant is None:
            await interaction.response.send_message(
                embed=error_embed("Join the event first with /event join."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before joining events."),
                ephemeral=True,
            )
            return

        raid_participant = await bot.database.fetch_raid_participant(
            raid_instance.id, interaction.user.id
        )
        if raid_participant is None:
            await interaction.response.send_message(
                embed=error_embed("Join the event raid with /event join before attacking."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return
        ready, remaining = can_raid(player, now)
        if not ready:
            await interaction.response.send_message(
                embed=cooldown_embed("raid", remaining), ephemeral=True
            )
            return
        if player.hp <= 0:
            await interaction.response.send_message(
                embed=error_embed("You are too wounded to continue fighting."),
                ephemeral=True,
            )
            return
        if not energy_ready(player, RAID_ENERGY_COST):
            await interaction.response.send_message(
                embed=error_embed(
                    f"You need at least {RAID_ENERGY_COST} energy to strike. Try /rest or /work."
                ),
                ephemeral=True,
            )
            return

        marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        weapon_data = await bot.database.fetch_equipped_weapon(guild.id, interaction.user.id)
        armor_data = await bot.database.fetch_equipped_armor(guild.id, interaction.user.id)
        weapon_damage = weapon_data[1].damage if weapon_data else 0
        armor_defense = armor_data[1].defense_boost if armor_data else 0

        player_damage = calculate_player_raid_damage(player, weapon_damage)
        boss_damage = calculate_boss_retaliation(boss, player, armor_defense)
        player.hp = max(0, player.hp - boss_damage)
        player.energy = max(0, player.energy - RAID_ENERGY_COST)
        player.last_raid_at = now
        consume_battle_buffs(player)

        await bot.database.update_player(player)

        durability_change: Optional[DurabilityChange] = None
        if weapon_data is not None:
            durability_change = await bot.database.reduce_equipped_weapon_durability(
                guild.id, interaction.user.id, 2
            )
            if durability_change and durability_change.broken:
                player.equipped_weapon_id = None

        updated_raid, updated_participant, inflicted = await bot.database.record_raid_attack(
            raid_instance.id, interaction.user.id, player_damage
        )
        raid_completed = not updated_raid.is_active

        reward_summaries: Dict[int, RaidRewardSummary] = {}
        if raid_completed:
            reward_summaries = await finalize_raid_rewards(updated_raid, boss, guild)

        summary = reward_summaries.get(interaction.user.id)
        materials = summary.materials if summary else []
        loot_items = summary.loot if summary else []
        rare_item = summary.rare_item if summary else None
        xp_reward = summary.xp if summary else 0
        gold_reward = summary.gold if summary else 0
        leveled_up = summary.leveled_up if summary else False
        achievement_lines: List[str] = []
        if summary:
            achievement_lines = format_achievement_lines(
                interaction.user, summary.achievements
            )

        if summary:
            refreshed_player = await bot.database.fetch_player(guild.id, interaction.user.id)
            if refreshed_player is not None:
                player = refreshed_player

        embed = raid_attack_embed(
            interaction.user,
            boss,
            updated_raid,
            damage_dealt=inflicted,
            damage_taken=boss_damage,
            player=player,
            participant=updated_participant,
            raid_completed=raid_completed,
            xp_reward=xp_reward,
            gold_reward=gold_reward,
            leveled_up=leveled_up,
            loot_items=loot_items,
            rare_item=rare_item,
            materials=materials,
        )
        await interaction.response.send_message(embed=embed)

        if durability_change is not None:
            if durability_change.broken:
                await interaction.followup.send(
                    content=(
                        f"⚠️ Your {durability_change.weapon.name} shattered during the battle and has been removed."
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    content=(
                        f"Your {durability_change.weapon.name} now has"
                        f" {durability_change.durability} durability remaining."
                    ),
                    ephemeral=True,
                )

        anniversary_message = await maybe_award_anniversary_item(guild, interaction.user, marriage)
        if anniversary_message:
            await interaction.followup.send(
                content=anniversary_message,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )
        if achievement_lines:
            await interaction.followup.send(
                "\n".join(achievement_lines),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )

    raid_group = app_commands.Group(
        name="raid", description="Coordinate global multiplayer raid battles"
    )
    bot.tree.add_command(raid_group)

    @raid_group.command(name="create", description="Summon a powerful raid boss")
    @app_commands.describe(boss="Select a raid boss to challenge")
    @app_commands.autocomplete(boss=autocomplete_raid_boss)
    async def raid_create(interaction: discord.Interaction, boss: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Raids must be attempted from within a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before starting raids."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return

        active_raid = await bot.database.fetch_active_raid()
        if active_raid is not None and active_raid.is_active:
            await interaction.response.send_message(
                embed=error_embed("A raid is already underway. Defeat the current boss first!"),
                ephemeral=True,
            )
            return

        boss_obj: Optional[RaidBoss] = None
        try:
            boss_id = int(boss)
            boss_obj = await bot.database.fetch_raid_boss_by_id(boss_id)
        except ValueError:
            boss_obj = await bot.database.fetch_raid_boss_by_name(boss)

        if boss_obj is None:
            await interaction.response.send_message(
                embed=error_embed("That raid boss could not be found."),
                ephemeral=True,
            )
            return
        if boss_obj.event_id is not None:
            await interaction.response.send_message(
                embed=error_embed(
                    "That boss can only be challenged through its event. Use /event join."
                ),
                ephemeral=True,
            )
            return

        raid_instance = await bot.database.create_raid_instance(boss_obj.id, interaction.user.id)
        await bot.database.ensure_raid_participant(raid_instance.id, interaction.user.id)

        embed = raid_spawn_embed(interaction.user, boss_obj, raid_instance)
        await interaction.response.send_message(embed=embed)

    @raid_group.command(name="join", description="Join the ongoing raid")
    async def raid_join(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Raids must be attempted from within a guild."), ephemeral=True
            )
            return

        raid_instance = await bot.database.fetch_active_raid()
        if raid_instance is None or not raid_instance.is_active:
            await interaction.response.send_message(
                embed=error_embed("There is no active raid right now. Start one with /raid create."),
                ephemeral=True,
            )
            return

        boss = await bot.database.fetch_raid_boss_by_id(raid_instance.boss_id)
        if boss is None:
            await interaction.response.send_message(
                embed=error_embed("The raid boss data is missing. Please try again later."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before joining raids."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return

        participant = await bot.database.ensure_raid_participant(
            raid_instance.id, interaction.user.id
        )
        embed = raid_join_embed(interaction.user, boss, raid_instance, participant)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @raid_group.command(name="attack", description="Strike the raid boss with your party")
    async def raid_attack(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Raids must be attempted from within a guild."), ephemeral=True
            )
            return

        raid_instance = await bot.database.fetch_active_raid()
        if raid_instance is None or not raid_instance.is_active:
            await interaction.response.send_message(
                embed=error_embed("There is no active raid right now. Start one with /raid create."),
                ephemeral=True,
            )
            return

        boss = await bot.database.fetch_raid_boss_by_id(raid_instance.boss_id)
        if boss is None:
            await interaction.response.send_message(
                embed=error_embed("The raid boss data is missing. Please try again later."),
                ephemeral=True,
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before joining raids."),
                ephemeral=True,
            )
            return

        participant = await bot.database.fetch_raid_participant(
            raid_instance.id, interaction.user.id
        )
        if participant is None:
            await interaction.response.send_message(
                embed=error_embed("Join the raid with /raid join before attacking."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return
        ready, remaining = can_raid(player, now)
        if not ready:
            await interaction.response.send_message(
                embed=cooldown_embed("raid", remaining), ephemeral=True
            )
            return

        if player.hp <= 0:
            await interaction.response.send_message(
                embed=error_embed("You have fallen in battle. Heal up before striking again."),
                ephemeral=True,
            )
            return

        if not energy_ready(player, RAID_ENERGY_COST):
            await interaction.response.send_message(
                embed=error_embed(
                    f"You need at least {RAID_ENERGY_COST} energy to attack. Try /rest or /work."
                ),
                ephemeral=True,
            )
            return

        marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        weapon_data = await bot.database.fetch_equipped_weapon(guild.id, interaction.user.id)
        armor_data = await bot.database.fetch_equipped_armor(guild.id, interaction.user.id)
        weapon_damage = weapon_data[1].damage if weapon_data else 0
        armor_defense = armor_data[1].defense_boost if armor_data else 0

        player_damage = calculate_player_raid_damage(player, weapon_damage)
        boss_damage = calculate_boss_retaliation(boss, player, armor_defense)
        player.hp = max(0, player.hp - boss_damage)
        player.energy = max(0, player.energy - RAID_ENERGY_COST)
        player.last_raid_at = now
        consume_battle_buffs(player)

        await bot.database.update_player(player)

        durability_change: Optional[DurabilityChange] = None
        if weapon_data is not None:
            durability_change = await bot.database.reduce_equipped_weapon_durability(
                guild.id, interaction.user.id, 2
            )
            if durability_change and durability_change.broken:
                player.equipped_weapon_id = None

        updated_raid, updated_participant, inflicted = await bot.database.record_raid_attack(
            raid_instance.id, interaction.user.id, player_damage
        )
        raid_completed = not updated_raid.is_active

        reward_summaries: Dict[int, RaidRewardSummary] = {}
        if raid_completed:
            reward_summaries = await finalize_raid_rewards(updated_raid, boss, guild)

        summary = reward_summaries.get(interaction.user.id)
        materials = summary.materials if summary else []
        loot_items = summary.loot if summary else []
        rare_item = summary.rare_item if summary else None
        xp_reward = summary.xp if summary else 0
        gold_reward = summary.gold if summary else 0
        leveled_up = summary.leveled_up if summary else False
        achievement_lines: List[str] = []
        if summary:
            achievement_lines = format_achievement_lines(
                interaction.user, summary.achievements
            )

        if summary:
            refreshed_player = await bot.database.fetch_player(guild.id, interaction.user.id)
            if refreshed_player is not None:
                player = refreshed_player

        embed = raid_attack_embed(
            interaction.user,
            boss,
            updated_raid,
            damage_dealt=inflicted,
            damage_taken=boss_damage,
            player=player,
            participant=updated_participant,
            raid_completed=raid_completed,
            xp_reward=xp_reward,
            gold_reward=gold_reward,
            leveled_up=leveled_up,
            loot_items=loot_items,
            rare_item=rare_item,
            materials=materials,
        )
        await interaction.response.send_message(embed=embed)

        if durability_change is not None:
            if durability_change.broken:
                await interaction.followup.send(
                    content=(
                        f"⚠️ Your {durability_change.weapon.name} shattered during the battle and has been removed."
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    content=(
                        f"Your {durability_change.weapon.name} now has"
                        f" {durability_change.durability} durability remaining."
                    ),
                    ephemeral=True,
                )

        anniversary_message = await maybe_award_anniversary_item(guild, interaction.user, marriage)
        if anniversary_message:
            await interaction.followup.send(
                content=anniversary_message,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )
        if achievement_lines:
            await interaction.followup.send(
                "\n".join(achievement_lines),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )

    @raid_group.command(name="leaderboard", description="Show raid damage rankings")
    async def raid_leaderboard(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Raid leaderboards can only be viewed in a guild."),
                ephemeral=True,
            )
            return

        raid_instance = await bot.database.fetch_active_raid()
        if raid_instance is None:
            raid_instance = await bot.database.fetch_most_recent_raid()

        if raid_instance is None:
            await interaction.response.send_message(
                embed=error_embed("No raids have been recorded yet."),
                ephemeral=True,
            )
            return

        boss = await bot.database.fetch_raid_boss_by_id(raid_instance.boss_id)
        if boss is None:
            await interaction.response.send_message(
                embed=error_embed("The raid boss data is missing."),
                ephemeral=True,
            )
            return

        participants = await bot.database.list_raid_participants(raid_instance.id)
        total_damage = max(1, raid_instance.total_damage)
        standings: List[Tuple[str, int, float]] = []
        for participant in participants[:10]:
            member = guild.get_member(participant.user_id)
            name = member.display_name if member else f"<@{participant.user_id}>"
            share = (participant.damage_dealt / total_damage) * 100
            standings.append((name, participant.damage_dealt, share))

        embed = raid_leaderboard_embed(boss, raid_instance, standings)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="couplequest", description="Embark on a special quest with your spouse")
    async def couplequest(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Couple quests require a shared guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before adventuring."),
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if player.active_quest_id:
            active_quest = find_quest(player.active_quest_id)
            remaining_active = active_quest_remaining(player, now)
            if active_quest is None:
                player.active_quest_id = None
                player.active_quest_complete_at = None
                await bot.database.update_player(player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(player, active_quest, remaining_active),
                    ephemeral=True,
                )
                return

        marriage = await bot.database.fetch_marriage(guild.id, interaction.user.id)
        if marriage is None:
            await interaction.response.send_message(
                embed=error_embed("You must be married to use /couplequest."),
                ephemeral=True,
            )
            return

        spouse_id = marriage.partner_id(interaction.user.id)
        if spouse_id is None:
            await interaction.response.send_message(
                embed=error_embed("Your spouse could not be determined."),
                ephemeral=True,
            )
            return

        spouse_member = guild.get_member(spouse_id)
        if spouse_member is None:
            await interaction.response.send_message(
                embed=error_embed("Your spouse must be in this guild to adventure together."),
                ephemeral=True,
            )
            return

        spouse_player = await bot.database.fetch_player(guild.id, spouse_id)
        if spouse_player is None or spouse_player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Your spouse needs an active character before questing."),
                ephemeral=True,
            )
            return

        spouse_subject = (
            spouse_member.mention if hasattr(spouse_member, "mention") else spouse_member.display_name
        )
        if spouse_player.active_quest_id:
            active_quest = find_quest(spouse_player.active_quest_id)
            remaining_active = active_quest_remaining(spouse_player, now)
            if active_quest is None:
                spouse_player.active_quest_id = None
                spouse_player.active_quest_complete_at = None
                await bot.database.update_player(spouse_player)
            else:
                await interaction.response.send_message(
                    embed=quest_block_embed(
                        spouse_player, active_quest, remaining_active, subject=spouse_subject
                    ),
                    ephemeral=True,
                )
                return

        proposer_before = {
            record.achievement.code
            for record in await bot.database.list_player_achievements(proposal.proposer_id)
        }
        proposee_before = {
            record.achievement.code
            for record in await bot.database.list_player_achievements(proposal.proposee_id)
        }

        ready_self, remaining_self = can_quest(player, now)
        if not ready_self:
            await interaction.response.send_message(
                embed=cooldown_embed("quest", remaining_self), ephemeral=True
            )
            return

        ready_spouse, remaining_spouse = can_quest(spouse_player, now)
        if not ready_spouse:
            embed = cooldown_embed("quest", remaining_spouse)
            embed.description = (
                f"Your spouse is still resting. They can quest again in **"
                f"{embed.description.split('**')[1]}**." if "**" in embed.description else embed.description
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if player.hp <= 10:
            await interaction.response.send_message(
                embed=error_embed("You are too injured for a couple quest."),
                ephemeral=True,
            )
            return

        if spouse_player.hp <= 10:
            await interaction.response.send_message(
                embed=error_embed("Your spouse is too injured to travel."),
                ephemeral=True,
            )
            return

        if not energy_ready(player, 20):
            await interaction.response.send_message(
                embed=error_embed("You need at least 20 energy. Try /rest or /work."),
                ephemeral=True,
            )
            return

        if not energy_ready(spouse_player, 20):
            await interaction.response.send_message(
                embed=error_embed("Your spouse needs at least 20 energy before adventuring."),
                ephemeral=True,
            )
            return

        weapon_self = await bot.database.fetch_equipped_weapon(guild.id, interaction.user.id)
        armor_self = await bot.database.fetch_equipped_armor(guild.id, interaction.user.id)
        weapon_spouse = await bot.database.fetch_equipped_weapon(guild.id, spouse_id)
        armor_spouse = await bot.database.fetch_equipped_armor(guild.id, spouse_id)

        outcome_self = perform_quest(
            player,
            weapon_damage=weapon_self[1].damage if weapon_self else 0,
            armor_defense=armor_self[1].defense_boost if armor_self else 0,
            xp_multiplier=1.0 + COUPLE_XP_BONUS,
            gold_multiplier=1.0 + COUPLE_GOLD_BONUS,
        )
        outcome_spouse = perform_quest(
            spouse_player,
            weapon_damage=weapon_spouse[1].damage if weapon_spouse else 0,
            armor_defense=armor_spouse[1].defense_boost if armor_spouse else 0,
            xp_multiplier=1.0 + COUPLE_XP_BONUS,
            gold_multiplier=1.0 + COUPLE_GOLD_BONUS,
        )

        player.quests_completed += 1
        spouse_player.quests_completed += 1
        await bot.database.update_player(player)
        await bot.database.update_player(spouse_player)
        achievements_self = await bot.database.evaluate_player_achievements(
            player,
            check_level=True,
            check_quests=True,
        )
        achievements_spouse = await bot.database.evaluate_player_achievements(
            spouse_player,
            check_level=True,
            check_quests=True,
        )

        loot_self = await roll_material_rewards("quest", guild.id, interaction.user.id)
        loot_spouse = await roll_material_rewards("quest", guild.id, spouse_id)

        durability_change_self: Optional[DurabilityChange] = None
        durability_change_spouse: Optional[DurabilityChange] = None
        if weapon_self is not None:
            durability_change_self = await bot.database.reduce_equipped_weapon_durability(
                guild.id, interaction.user.id, 1
            )
            if durability_change_self and durability_change_self.broken:
                player.equipped_weapon_id = None
        if weapon_spouse is not None:
            durability_change_spouse = await bot.database.reduce_equipped_weapon_durability(
                guild.id, spouse_id, 1
            )
            if durability_change_spouse and durability_change_spouse.broken:
                spouse_player.equipped_weapon_id = None

        xp_bonus = int(COUPLE_XP_BONUS * 100)
        gold_bonus = int(COUPLE_GOLD_BONUS * 100)
        embed = discord.Embed(
            title="Couple quest complete!",
            description=(
                f"{interaction.user.mention} and {spouse_member.mention} return from their adventure together."
            ),
            color=discord.Color.purple(),
        )
        embed.add_field(
            name=interaction.user.display_name,
            value=(
                f"XP +{outcome_self.xp}\n"
                f"Gold +{outcome_self.gold}\n"
                f"Damage taken {outcome_self.damage}"
                + (
                    f"\nMaterials: {summarize_materials(loot_self)}"
                    if loot_self
                    else ""
                )
            ),
            inline=True,
        )
        embed.add_field(
            name=spouse_member.display_name,
            value=(
                f"XP +{outcome_spouse.xp}\n"
                f"Gold +{outcome_spouse.gold}\n"
                f"Damage taken {outcome_spouse.damage}"
                + (
                    f"\nMaterials: {summarize_materials(loot_spouse)}"
                    if loot_spouse
                    else ""
                )
            ),
            inline=True,
        )
        embed.add_field(
            name="Party bonus",
            value=f"+{xp_bonus}% XP and +{gold_bonus}% gold applied for adventuring together.",
            inline=False,
        )
        if outcome_self.leveled_up:
            embed.add_field(
                name=f"{interaction.user.display_name} leveled up!",
                value=f"Now level {player.level}",
                inline=False,
            )
        if outcome_spouse.leveled_up:
            embed.add_field(
                name=f"{spouse_member.display_name} leveled up!",
                value=f"Now level {spouse_player.level}",
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user, spouse_member]),
        )

        notifications = []
        if achievements_self:
            notifications.extend(
                format_achievement_lines(interaction.user, achievements_self)
            )
        if achievements_spouse:
            notifications.extend(
                format_achievement_lines(spouse_member, achievements_spouse)
            )
        if durability_change_self is not None:
            if durability_change_self.broken:
                notifications.append(
                    f"⚠️ {interaction.user.mention}'s {durability_change_self.weapon.name} has broken."
                )
            else:
                notifications.append(
                    f"{interaction.user.mention}'s {durability_change_self.weapon.name} now has"
                    f" {durability_change_self.durability} durability."
                )
        if durability_change_spouse is not None:
            if durability_change_spouse.broken:
                notifications.append(
                    f"⚠️ {spouse_member.mention}'s {durability_change_spouse.weapon.name} has broken."
                )
            else:
                notifications.append(
                    f"{spouse_member.mention}'s {durability_change_spouse.weapon.name} now has"
                    f" {durability_change_spouse.durability} durability."
                )

        anniversary_self = await maybe_award_anniversary_item(guild, interaction.user, marriage)
        if anniversary_self:
            notifications.append(anniversary_self)
        anniversary_spouse = await maybe_award_anniversary_item(guild, spouse_member, marriage)
        if anniversary_spouse:
            notifications.append(anniversary_spouse)

        if notifications:
            await interaction.followup.send(
                "\n".join(notifications),
                allowed_mentions=discord.AllowedMentions(users=[interaction.user, spouse_member]),
            )

    @bot.tree.command(name="work", description="Do some work for steady rewards")
    async def work(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Work can only be done inside a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("You need a class before you can work. Use /create first."),
                ephemeral=True,
            )
            return
        now = datetime.now(timezone.utc)
        ready, remaining = can_work(player, now)
        if not ready:
            await interaction.response.send_message(
                embed=cooldown_embed("work", remaining), ephemeral=True
            )
            return
        if not energy_ready(player, 10):
            await interaction.response.send_message(
                embed=error_embed("You need at least 10 energy to work. Try /rest."),
                ephemeral=True,
            )
            return

        weapon_data = await bot.database.fetch_equipped_weapon(guild.id, interaction.user.id)
        weapon_damage = weapon_data[1].damage if weapon_data else 0
        outcome = perform_work(player, weapon_damage=weapon_damage)
        await bot.database.update_player(player)
        unlocked_achievements = await bot.database.evaluate_player_achievements(
            player,
            check_level=True,
        )
        achievement_lines = format_achievement_lines(interaction.user, unlocked_achievements)
        embed = work_result_embed(interaction.user, outcome, player)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if achievement_lines:
            await interaction.followup.send(
                "\n".join(achievement_lines),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )

    @bot.tree.command(name="inventory", description="View your items, weapons, and armor")
    @app_commands.describe(page="Page number to view")
    async def inventory(interaction: discord.Interaction, page: Optional[int] = 1) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Inventories are only available in guilds."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create a character with /create first."),
                ephemeral=True,
            )
            return

        inventory_data = await bot.database.fetch_player_inventory(guild.id, interaction.user.id)
        weapons = list(inventory_data["weapons"])
        armors = list(inventory_data["armor"])
        items = list(inventory_data["items"])
        materials = list(inventory_data["materials"])
        page_number = page or 1
        page_number, total_pages, paginated = paginate_collections(
            [weapons, armors, items, materials], page_number, PAGE_SIZE
        )
        weapons_page, armors_page, items_page, materials_page = paginated

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Inventory",
            color=discord.Color.blurple(),
        )
        if weapons_page:
            embed.add_field(
                name="Weapons",
                value="\n".join(format_inventory_weapon(w) for w in weapons_page),
                inline=False,
            )
        if armors_page:
            embed.add_field(
                name="Armor",
                value="\n".join(format_inventory_armor(a) for a in armors_page),
                inline=False,
            )
        if items_page:
            embed.add_field(
                name="Consumables",
                value="\n".join(format_inventory_item(i) for i in items_page),
                inline=False,
            )
        if materials_page:
            embed.add_field(
                name="Materials",
                value="\n".join(format_inventory_material(m) for m in materials_page),
                inline=False,
            )
        if (
            not weapons_page
            and not armors_page
            and not items_page
            and not materials_page
        ):
            embed.description = (
                "Your inventory is empty. Visit the shop, complete quests, or lead raids for loot!"
            )
        embed.set_footer(text=f"Page {page_number} of {total_pages}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="repair", description="Repair a damaged weapon for gold")
    @app_commands.describe(weapon="Name of the weapon to repair")
    async def repair_command(
        interaction: discord.Interaction, weapon: Optional[str] = None
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Repairs are only available inside a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before visiting the smith."),
                ephemeral=True,
            )
            return

        inventory = await bot.database.fetch_player_inventory(guild.id, interaction.user.id)
        weapons: List[Tuple[InventoryEntry, Weapon]] = list(inventory["weapons"])
        weapon_name = weapon.strip() if weapon else ""

        chosen: Optional[Tuple[InventoryEntry, Weapon]] = None
        if weapon_name:
            for entry, info in weapons:
                if info.name.lower() == weapon_name.lower():
                    current = (
                        entry.current_durability
                        if entry.current_durability is not None
                        else info.durability
                    )
                    if current >= info.durability:
                        await interaction.response.send_message(
                            embed=error_embed("That weapon is already at full durability."),
                            ephemeral=True,
                        )
                        return
                    chosen = (entry, info)
                    break
            if chosen is None:
                await interaction.response.send_message(
                    embed=error_embed("That weapon could not be found in your inventory."),
                    ephemeral=True,
                )
                return
        else:
            damaged = [
                (entry, info)
                for entry, info in weapons
                if entry.current_durability is not None
                and entry.current_durability < info.durability
            ]
            if not damaged:
                await interaction.response.send_message(
                    embed=error_embed("All of your weapons are already pristine."),
                    ephemeral=True,
                )
                return
            if len(damaged) > 1:
                suggestions = ", ".join(info.name for _, info in damaged[:5])
                if len(damaged) > 5:
                    suggestions += ", ..."
                await interaction.response.send_message(
                    embed=error_embed(
                        "You have multiple damaged weapons. Specify one to repair."
                        f" ({suggestions})"
                    ),
                    ephemeral=True,
                )
                return
            chosen = damaged[0]

        entry, info = chosen
        try:
            updated_entry, weapon_info, cost = await bot.database.repair_weapon(
                guild.id,
                interaction.user.id,
                entry.id,
                cost_percent=bot.settings.repair_cost_percent,
            )
        except ValueError as exc:
            reason = str(exc)
            if reason == "insufficient_gold":
                message = "You don't have enough gold to pay for that repair."
            elif reason == "weapon_not_damaged":
                message = "That weapon is already at full durability."
            elif reason in {"player_not_found", "weapon_not_found"}:
                message = "Your weapon could not be repaired right now. Try again later."
            else:
                message = "The smith can't repair that weapon right now."
            await interaction.response.send_message(
                embed=error_embed(message),
                ephemeral=True,
            )
            return

        updated_player = await bot.database.fetch_player(guild.id, interaction.user.id)
        durability = (
            updated_entry.current_durability
            if updated_entry.current_durability is not None
            else weapon_info.durability
        )
        percent = int(bot.settings.repair_cost_percent * 100)
        if cost > 0:
            description = (
                f"Restored **{weapon_info.name}** to full durability for **{cost} gold**."
            )
        else:
            description = f"{weapon_info.name} was restored to full durability."

        embed = discord.Embed(
            title="Weapon repaired!",
            description=description,
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Durability",
            value=f"{durability}/{weapon_info.durability}",
            inline=True,
        )
        if updated_player is not None:
            embed.add_field(
                name="Gold remaining",
                value=f"💰 {updated_player.gold}",
                inline=True,
            )
        if percent > 0:
            embed.set_footer(
                text=(
                    f"Repairs cost {percent}% of a weapon's base value scaled by damage."
                )
            )
        else:
            embed.set_footer(text="Repairs scale with the damage your weapon has taken.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    equip_group = app_commands.Group(name="equip", description="Equip your weapons or armor")

    @equip_group.command(name="weapon", description="Equip a weapon from your inventory")
    @app_commands.describe(name="Name of the weapon to equip")
    async def equip_weapon_command(interaction: discord.Interaction, name: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Equipping gear requires a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create a character with /create before equipping gear."),
                ephemeral=True,
            )
            return

        entry = await bot.database.fetch_weapon_entry_by_name(guild.id, interaction.user.id, name)
        if entry is None:
            await interaction.response.send_message(
                embed=error_embed("You do not own that weapon."), ephemeral=True
            )
            return

        inv_entry, weapon = entry
        if inv_entry.current_durability is not None and inv_entry.current_durability <= 0:
            await interaction.response.send_message(
                embed=error_embed("That weapon is broken. Purchase or craft a new one."),
                ephemeral=True,
            )
            return

        player_class = await bot.database.fetch_class_by_id(player.class_id)
        if (
            weapon.class_restriction
            and player_class is not None
            and weapon.class_restriction.lower() != player_class.name.lower()
        ):
            await interaction.response.send_message(
                embed=error_embed("Your class cannot equip that weapon."), ephemeral=True
            )
            return

        await bot.database.equip_weapon(guild.id, interaction.user.id, inv_entry)
        player.equipped_weapon_id = inv_entry.id
        durability = (
            f"Durability {inv_entry.current_durability}/{weapon.durability}"
            if inv_entry.current_durability is not None
            else ""
        )
        description = f"Equipped **{weapon.name}**."
        if durability:
            description += f" ({durability})"
        await interaction.response.send_message(
            embed=discord.Embed(description=description, color=discord.Color.green()),
            ephemeral=True,
        )

    @equip_group.command(name="armor", description="Equip armor from your inventory")
    @app_commands.describe(name="Name of the armor to equip")
    async def equip_armor_command(interaction: discord.Interaction, name: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Equipping gear requires a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create a character with /create before equipping gear."),
                ephemeral=True,
            )
            return

        entry = await bot.database.fetch_armor_entry_by_name(guild.id, interaction.user.id, name)
        if entry is None:
            await interaction.response.send_message(
                embed=error_embed("You do not own that armor set."), ephemeral=True
            )
            return

        inv_entry, armor_piece = entry
        await bot.database.equip_armor(guild.id, interaction.user.id, inv_entry)
        player.equipped_armor_id = inv_entry.id
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Equipped **{armor_piece.name}** (DEF +{armor_piece.defense_boost}).",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    bot.tree.add_command(equip_group)

    @bot.tree.command(name="use", description="Use a consumable item from your inventory")
    @app_commands.describe(item="Name of the item to use")
    async def use_item_command(interaction: discord.Interaction, item: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Consumables can only be used in guilds."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create a character with /create before using items."),
                ephemeral=True,
            )
            return

        entry = await bot.database.fetch_item_entry_by_name(guild.id, interaction.user.id, item)
        if entry is None:
            await interaction.response.send_message(
                embed=error_embed("You don't have that item."), ephemeral=True
            )
            return

        inv_entry, item_info = entry
        if item_info.effect_type == "vanity":
            await interaction.response.send_message(
                embed=error_embed("That item is a luxury collectible and cannot be used."),
                ephemeral=True,
            )
            return
        try:
            result = await bot.database.use_item(guild.id, interaction.user.id, inv_entry, item_info)
        except ValueError as exc:
            reason = str(exc)
            if reason == "player_not_found":
                message = "Your character could not be found."
            elif reason == "no_quantity":
                message = "You have none of that item left."
            elif reason == "no_effect":
                message = "That item has no effect right now. Try again later."
            else:
                message = "That item could not be used right now."
            await interaction.response.send_message(embed=error_embed(message), ephemeral=True)
            return

        updated_player = await bot.database.fetch_player(guild.id, interaction.user.id)
        embed = discord.Embed(
            title=f"Used {result.item.name}",
            color=discord.Color.green(),
        )
        if result.healed:
            embed.add_field(name="Healing", value=f"Restored {result.healed} HP", inline=False)
        if result.energy_restored:
            embed.add_field(
                name="Energy",
                value=f"Recovered {result.energy_restored} energy",
                inline=False,
            )
        if result.attack_buff is not None:
            percent, battles = result.attack_buff
            embed.add_field(
                name="Attack Buff",
                value=f"+{percent}% attack for {battles} battles",
                inline=False,
            )
        if result.defense_buff is not None:
            percent, battles = result.defense_buff
            embed.add_field(
                name="Defense Buff",
                value=f"+{percent}% defense for {battles} battles",
                inline=False,
            )
        embed.add_field(
            name="Quantity Remaining",
            value=str(result.quantity_remaining),
            inline=False,
        )
        if updated_player is not None:
            embed.add_field(
                name="Current Stats",
                value=(
                    f"HP: {updated_player.hp}/{updated_player.max_hp}\n"
                    f"Energy: {updated_player.energy}/100"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="heal", description="Spend gold to restore health")
    async def heal(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Healing is only available inside a guild."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Adventurers need a class before visiting the healer. Use /create."),
                ephemeral=True,
            )
            return
        outcome = heal_player(player)
        await bot.database.update_player(player)
        embed = heal_embed(interaction.user, outcome.healed, outcome.cost, player)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="rest", description="Recover some energy between quests")
    async def rest(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Resting is only available in guilds."), ephemeral=True
            )
            return

        player = await bot.database.fetch_player(guild.id, interaction.user.id)
        if player is None or player.class_id is None:
            await interaction.response.send_message(
                embed=error_embed("Create your character with /create before resting."),
                ephemeral=True,
            )
            return
        now = datetime.now(timezone.utc)
        ready, remaining = can_rest(player, now)
        if not ready:
            await interaction.response.send_message(
                embed=cooldown_embed("rest", remaining), ephemeral=True
            )
            return

        energy_gain = rest_player(player)
        await bot.database.update_player(player)
        embed = rest_embed(interaction.user, energy_gain, player)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="leaderboard", description="Show the top adventurers everywhere")
    async def leaderboard(interaction: discord.Interaction) -> None:
        guild = interaction.guild

        players = await bot.database.top_players()
        members = []
        for player in players:
            member: Optional[discord.abc.User]
            if guild is not None:
                resolved_member = guild.get_member(player.user_id)
                if resolved_member is None:
                    try:
                        resolved_member = await guild.fetch_member(player.user_id)
                    except discord.HTTPException:
                        resolved_member = None
                member = resolved_member
            else:
                member = bot.get_user(player.user_id)
                if member is None:
                    try:
                        member = await bot.fetch_user(player.user_id)
                    except discord.HTTPException:
                        member = None
            player_class = (
                await bot.database.fetch_class_by_id(player.class_id)
                if player.class_id is not None
                else None
            )
            members.append((player, member, player_class))

        embed = leaderboard_embed(guild, members)
        await interaction.response.send_message(embed=embed)

    @global_group.command(name="leaderboard", description="View global IdleRPG rankings")
    @app_commands.describe(category="Which leaderboard to display")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="XP", value="xp"),
            app_commands.Choice(name="Gold", value="gold"),
            app_commands.Choice(name="PvP Wins", value="pvp_wins"),
        ]
    )
    async def global_leaderboard_command(
        interaction: discord.Interaction, category: app_commands.Choice[str]
    ) -> None:
        records = await bot.database.global_leaderboard(category.value)
        entries: List[Tuple[Player, Optional[discord.abc.User]]] = []
        for player in records:
            user_obj: Optional[discord.abc.User] = bot.get_user(player.user_id)
            if user_obj is None:
                try:
                    user_obj = await bot.fetch_user(player.user_id)
                except discord.HTTPException:
                    user_obj = None
            entries.append((player, user_obj))

        season_start: Optional[datetime] = None
        if category.value == "pvp_wins":
            season_start = await bot.database.get_pvp_season_start()

        embed = global_leaderboard_embed(
            category.value,
            entries,
            season_start=season_start,
            seasonal_reset_enabled=bot.settings.pvp_season_reset,
        )
        await interaction.response.send_message(embed=embed)

    async def on_app_command_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        log.exception("Command error: %s", error)
        if interaction.response.is_done():
            await interaction.followup.send(embed=error_embed(str(error)), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=error_embed("An unexpected error occurred."), ephemeral=True
            )

    bot.tree.on_error = on_app_command_error

    return bot
