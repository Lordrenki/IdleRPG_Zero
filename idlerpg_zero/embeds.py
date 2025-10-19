"""Discord embed helpers for IdleRPG Zero."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Optional, Sequence, Tuple

import discord

from .database import (
    Achievement,
    Armor,
    ClassInfo,
    Event,
    Guild,
    GuildMember,
    InventoryEntry,
    Item,
    Marriage,
    Material,
    Player,
    PlayerAchievementRecord,
    PlayerProfile,
    RaidBoss,
    RaidInstance,
    RaidParticipant,
    Weapon,
)
from .progression import xp_to_next_level
from .quests import (
    QuestDefinition,
    QuestProgress,
    category_display_name,
    find_quest,
    summarize_rewards,
)

PRIMARY_COLOR = discord.Color.from_rgb(255, 170, 45)
ERROR_COLOR = discord.Color.red()
SUCCESS_COLOR = discord.Color.green()


def profile_embed(
    member: discord.abc.User,
    player: Player,
    player_class: Optional[ClassInfo] = None,
    weapon: Optional[Tuple[InventoryEntry, Weapon]] = None,
    armor: Optional[Tuple[InventoryEntry, Armor]] = None,
    title: Optional[Achievement] = None,
    guild: Optional[Guild] = None,
    guild_membership: Optional[GuildMember] = None,
    *,
    profile: Optional[PlayerProfile] = None,
    marriage: Optional[Marriage] = None,
    marriage_partner: Optional[str] = None,
    achievements: Optional[Sequence[PlayerAchievementRecord]] = None,
    guild_badge: Optional[str] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name}'s Adventure",
        color=PRIMARY_COLOR,
    )
    now = datetime.now(timezone.utc)
    avatar_url: Optional[str] = None
    if profile and profile.avatar_url:
        avatar_url = profile.avatar_url
    elif hasattr(member, "display_avatar"):
        avatar_url = member.display_avatar.url
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    if profile and profile.banner_url:
        embed.set_image(url=profile.banner_url)

    if player_class is not None:
        embed.add_field(name="Class", value=player_class.name, inline=True)
        embed.add_field(
            name="Ability",
            value=f"{player_class.ability_name}\n{player_class.ability_description}",
            inline=False,
        )

    embed.add_field(
        name="Level",
        value=f"{player.level} (XP {player.xp}/{xp_to_next_level(player.level)})",
        inline=True,
    )
    embed.add_field(
        name="Health",
        value=f"❤️ {player.hp}/{player.max_hp}",
        inline=True,
    )
    embed.add_field(
        name="Energy",
        value=f"⚡ {player.energy}/100",
        inline=True,
    )
    embed.add_field(name="Gold", value=f"💰 {player.gold}", inline=True)
    embed.add_field(name="Attack", value=f"🗡️ {player.attack}", inline=True)
    embed.add_field(name="Defense", value=f"🛡️ {player.defense}", inline=True)
    embed.add_field(
        name="PvP Record",
        value=f"⚔️ {player.pvp_wins}W-{player.pvp_losses}L",
        inline=True,
    )
    embed.add_field(
        name="Season PvP",
        value=f"🏆 {player.pvp_season_wins}W-{player.pvp_season_losses}L",
        inline=True,
    )
    marriage_value = "💍 Single"
    if marriage is not None:
        partner_display = marriage_partner or "Unknown partner"
        married_at = discord.utils.format_dt(marriage.date_married, style="R")
        marriage_value = f"💞 {partner_display}\nMarried {married_at}"
    embed.add_field(name="Marriage", value=marriage_value, inline=True)
    if title is not None:
        embed.add_field(name="Title", value=f"🏅 {title.title}", inline=True)
    if guild is not None and guild_membership is not None:
        embed.add_field(
            name="Guild",
            value=f"{guild.name} • Level {guild.level}",
            inline=True,
        )
        role_title = guild_membership.role.replace("_", " ").title()
        embed.add_field(name="Guild Rank", value=role_title, inline=True)
        embed.add_field(name="Guild Gold", value=f"🏛️ {guild.gold}", inline=True)
        if guild_badge:
            embed.add_field(name="Guild Badge", value=guild_badge, inline=True)
    if weapon is not None:
        weapon_entry, weapon_info = weapon
        durability = (
            f"Durability {weapon_entry.current_durability}/{weapon_info.durability}"
            if weapon_entry.current_durability is not None
            else ""
        )
        value = f"{weapon_info.name} • DMG {weapon_info.damage}"
        if durability:
            value += f"\n{durability}"
        embed.add_field(name="Equipped Weapon", value=value, inline=False)
    if armor is not None:
        _, armor_info = armor
        embed.add_field(
            name="Equipped Armor",
            value=f"{armor_info.name} • DEF +{armor_info.defense_boost}",
            inline=False,
        )
    if player.active_quest_id:
        quest = find_quest(player.active_quest_id)
        finish_at = player.active_quest_complete_at
        if quest is not None and finish_at is not None:
            remaining = finish_at - now
            if remaining > timedelta(0):
                remaining_text = _format_timedelta(remaining)
                finish_text = discord.utils.format_dt(finish_at, style="R")
                quest_value = (
                    f"On **{quest.name}**\n"
                    f"Time remaining: {remaining_text}\n"
                    f"Returns {finish_text}"
                )
            else:
                quest_value = (
                    f"Quest complete!\n"
                    f"Ready to finish **{quest.name}**."
                )
        else:
            quest_value = "Quest in progress"
        embed.add_field(name="Current Quest", value=quest_value, inline=False)
    if player.attack_buff_battles > 0 and player.attack_buff_percent > 0:
        embed.add_field(
            name="Attack Buff",
            value=f"+{player.attack_buff_percent}% for {player.attack_buff_battles} battles",
            inline=True,
        )
    if player.defense_buff_battles > 0 and player.defense_buff_percent > 0:
        embed.add_field(
            name="Defense Buff",
            value=f"+{player.defense_buff_percent}% for {player.defense_buff_battles} battles",
            inline=True,
        )
    if player.last_quest_at:
        embed.add_field(
            name="Last quest",
            value=discord.utils.format_dt(player.last_quest_at, style="R"),
            inline=True,
        )
    if player.last_work_at:
        embed.add_field(
            name="Last work",
            value=discord.utils.format_dt(player.last_work_at, style="R"),
            inline=True,
        )
    if achievements is not None:
        if achievements:
            lines = [
                f"🏅 {record.achievement.title} — {record.achievement.name}"
                for record in achievements
            ]
        else:
            lines = [
                "No achievements unlocked yet. Complete quests to earn more accolades!"
            ]
        embed.add_field(name="Achievements", value="\n".join(lines), inline=False)
    embed.set_footer(text="IdleRPG Zero • Slash commands for easy adventuring")
    return embed


def achievements_embed(
    member: discord.abc.User, achievements: Sequence[PlayerAchievementRecord]
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name}'s Achievements",
        color=PRIMARY_COLOR,
    )
    if hasattr(member, "display_avatar"):
        embed.set_thumbnail(url=member.display_avatar.url)
    if not achievements:
        embed.description = (
            "No achievements unlocked yet. Complete quests, raids, and milestones to earn badges!"
        )
        return embed

    for record in achievements:
        achievement = record.achievement
        earned = discord.utils.format_dt(record.earned_at, style="R")
        embed.add_field(
            name=f"{achievement.title} — {achievement.name}",
            value=f"{achievement.description}\nUnlocked {earned}.",
            inline=False,
        )
    return embed


def _format_material_rewards(materials: Sequence[Tuple[Material, int]]) -> str:
    lines = []
    for material, quantity in materials:
        rarity = material.rarity.title()
        lines.append(f"{quantity}× {material.name} ({rarity})")
    return "\n".join(lines)


def quest_result_embed(
    member: discord.abc.User,
    outcome,
    player: Player,
    materials: Optional[Sequence[Tuple[Material, int]]] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name} embarks on a quest!",
        description=f"🏅 Gained **{outcome.xp} XP** and **{outcome.gold} gold**!",
        color=SUCCESS_COLOR if outcome.leveled_up else PRIMARY_COLOR,
    )
    embed.add_field(name="Damage taken", value=f"💥 {outcome.damage}", inline=True)
    embed.add_field(name="Current HP", value=f"❤️ {player.hp}/{player.max_hp}", inline=True)
    embed.add_field(name="Energy", value=f"⚡ {player.energy}/100", inline=True)
    if outcome.leveled_up:
        embed.add_field(name="Level up!", value=f"Level {player.level}", inline=False)
    if materials:
        embed.add_field(
            name="Materials Found",
            value=_format_material_rewards(materials),
            inline=False,
        )
    embed.set_footer(text="Complete quests to grow stronger!")
    return embed


def quest_list_embed(
    member: discord.abc.User,
    quests: Sequence[QuestDefinition],
    progress: Mapping[str, QuestProgress],
    now: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name}'s Quest Board",
        description=(
            "Daily errands, weekly expeditions, and epic tales await."
        ),
        color=PRIMARY_COLOR,
    )
    categories: dict[str, list[str]] = {}
    for quest in quests:
        availability = quest.availability(progress.get(quest.id), now)
        if availability.locked:
            status = "🔒 Completed"
        elif availability.available:
            status = "✅ Ready"
        elif availability.cooldown_remaining:
            status = f"⏳ {_format_timedelta(availability.cooldown_remaining)}"
        else:
            status = "⏳ Recovering"
        reward_summary = summarize_rewards(quest)
        detail = (
            f"{quest.summary}\n"
            f"Duration {_format_timedelta(quest.duration)} • Energy {quest.energy_cost} • "
            f"Gold×{quest.gold_multiplier:.1f}\n"
            f"{reward_summary}\n{status}"
        )
        categories.setdefault(quest.category, []).append(f"**{quest.name}**\n{detail}")

    for category, entries in sorted(categories.items(), key=lambda item: item[0]):
        display = category_display_name(category)
        value = "\n\n".join(entries)
        embed.add_field(name=display, value=value, inline=False)

    embed.set_footer(text="Use /quest start <name> or /adventure to embark.")
    return embed


def quest_story_embed(
    member: discord.abc.User,
    quest: QuestDefinition,
    narrative: str,
    success_text: str,
    total_xp: int,
    total_gold: int,
    total_damage: int,
    player: Player,
    *,
    leveled_up: bool,
    encounter_text: Optional[str] = None,
    items: Optional[Sequence[Item]] = None,
    materials: Optional[Sequence[Tuple[Material, int]]] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name} completes {quest.name}!",
        description=f"{narrative}\n\n{success_text}",
        color=SUCCESS_COLOR if leveled_up else PRIMARY_COLOR,
    )
    embed.add_field(
        name="Rewards",
        value=f"🧠 {total_xp} XP\n💰 {total_gold} gold",
        inline=False,
    )
    embed.add_field(name="Damage taken", value=f"💥 {total_damage}", inline=True)
    embed.add_field(name="Current HP", value=f"❤️ {player.hp}/{player.max_hp}", inline=True)
    embed.add_field(name="Energy", value=f"⚡ {player.energy}/100", inline=True)
    if leveled_up:
        embed.add_field(name="Level Up!", value=f"Level {player.level}", inline=False)
    if encounter_text:
        embed.add_field(name="Random Encounter", value=encounter_text, inline=False)
    if items:
        embed.add_field(name="Items", value=_format_item_rewards(items), inline=False)
    if materials:
        embed.add_field(
            name="Materials",
            value=_format_material_rewards(materials),
            inline=False,
        )
    embed.set_footer(text="Check /quest list to track cooldowns and stories.")
    return embed


def raid_result_embed(
    member: discord.abc.User,
    outcome,
    player: Player,
    materials: Optional[Sequence[Tuple[Material, int]]] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name} leads a raid!",
        description=f"🏆 Gained **{outcome.xp} XP** and **{outcome.gold} gold**!",
        color=discord.Color.purple(),
    )
    embed.add_field(name="Damage taken", value=f"💥 {outcome.damage}", inline=True)
    embed.add_field(name="Current HP", value=f"❤️ {player.hp}/{player.max_hp}", inline=True)
    embed.add_field(name="Energy", value=f"⚡ {player.energy}/100", inline=True)
    if outcome.leveled_up:
        embed.add_field(name="Level up!", value=f"Level {player.level}", inline=False)
    if materials:
        embed.add_field(
            name="Raid Spoils",
            value=_format_material_rewards(materials),
            inline=False,
        )
    embed.set_footer(text="Raids demand teamwork and plenty of preparation!")
    return embed


def _format_item_rewards(items: Sequence[Item]) -> str:
    if not items:
        return "None"
    return ", ".join(f"**{item.name}**" for item in items)


def raid_spawn_embed(
    member: discord.abc.User, boss: RaidBoss, raid: RaidInstance
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name} calls for aid!",
        description=f"**{boss.name}** appears!\n{boss.description}",
        color=discord.Color.dark_teal(),
    )
    embed.add_field(
        name="Boss HP",
        value=f"💖 {raid.current_hp:,}/{boss.max_hp:,}",
        inline=True,
    )
    embed.add_field(name="Boss Power", value=f"⚔️ {boss.attack:,}", inline=True)
    embed.add_field(
        name="Raid Rewards",
        value=f"🏅 {boss.xp_reward:,} XP • 💰 {boss.gold_reward:,} gold",
        inline=False,
    )
    if boss.rare_loot_rarity:
        chance = int(round(boss.rare_loot_chance * 100))
        embed.add_field(
            name="Rare Loot",
            value=f"{boss.rare_loot_rarity.title()} drop — {chance}% chance",
            inline=True,
        )
    if boss.item_reward_rarity:
        embed.add_field(
            name="Guaranteed Loot",
            value=f"{boss.item_reward_rarity.title()} item",
            inline=True,
        )
    if boss.material_reward_rarity:
        embed.add_field(
            name="Crafting Materials",
            value=boss.material_reward_rarity.title(),
            inline=True,
        )
    embed.set_footer(text="Use /raid join and /raid attack to challenge the boss together!")
    return embed


def raid_join_embed(
    member: discord.abc.User,
    boss: RaidBoss,
    raid: RaidInstance,
    participant: RaidParticipant,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name} joins the raid!",
        description=f"The battle against **{boss.name}** intensifies.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Boss HP",
        value=f"💖 {raid.current_hp:,}/{boss.max_hp:,}",
        inline=True,
    )
    embed.add_field(
        name="Your Contribution",
        value=f"⚔️ {participant.damage_dealt:,} damage",
        inline=True,
    )
    status = "Active" if raid.is_active else "Completed"
    embed.add_field(name="Raid Status", value=status, inline=True)
    embed.set_footer(text="Use /raid attack to strike the boss!")
    return embed


def event_info_embed(
    event: Event,
    *,
    joined: bool,
    items: Sequence[Item],
    weapons: Sequence[Weapon],
    raid: Optional[RaidInstance] = None,
    raid_boss: Optional[RaidBoss] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=event.name,
        description=event.description,
        color=PRIMARY_COLOR,
    )
    embed.add_field(
        name="Event Window",
        value=(
            f"{discord.utils.format_dt(event.start_date, style='f')}"
            f" → {discord.utils.format_dt(event.end_date, style='f')}"
        ),
        inline=False,
    )
    status = "Active now!" if event.is_active else "Inactive"
    embed.add_field(name="Status", value=status, inline=True)
    participation = (
        "You are enlisted for this event."
        if joined
        else "Use /event join to participate and earn exclusive loot."
    )
    embed.add_field(name="Participation", value=participation, inline=True)
    if event.special_loot:
        embed.add_field(name="Special Loot", value=event.special_loot, inline=False)
    reward_lines = [
        f"🗡️ {weapon.name} ({weapon.rarity.title()})" for weapon in weapons
    ] + [
        f"🎁 {item.name} ({item.rarity.title()})" for item in items
    ]
    if reward_lines:
        embed.add_field(
            name="Exclusive Rewards",
            value="\n".join(reward_lines),
            inline=False,
        )
    if raid_boss is not None:
        if raid is not None and raid.is_active:
            raid_value = (
                f"**{raid_boss.name}** — HP {raid.current_hp:,}/{raid_boss.max_hp:,}"
            )
        elif raid is not None and not raid.is_active:
            raid_value = f"**{raid_boss.name}** — Defeated"
        else:
            raid_value = f"**{raid_boss.name}** — Awaiting challengers"
        embed.add_field(name="Event Raid", value=raid_value, inline=False)
    embed.set_footer(text="Event rewards expire when the event ends.")
    return embed


def event_join_embed(
    member: discord.abc.User,
    event: Event,
    *,
    rewards: Sequence[str],
    raid_boss: Optional[RaidBoss] = None,
    raid: Optional[RaidInstance] = None,
    joined_now: bool = True,
) -> discord.Embed:
    color = SUCCESS_COLOR if joined_now else PRIMARY_COLOR
    description = (
        f"{member.display_name} joins {event.name}!"
        if joined_now
        else f"{member.display_name} is ready for more of {event.name}!"
    )
    embed = discord.Embed(
        title="Event enlistment complete" if joined_now else "Event participation confirmed",
        description=description,
        color=color,
    )
    embed.add_field(
        name="Event Ends",
        value=discord.utils.format_dt(event.end_date, style="R"),
        inline=True,
    )
    embed.add_field(
        name="Status",
        value="Welcome to the festivities!" if joined_now else "Good to have you back!",
        inline=True,
    )
    if rewards:
        embed.add_field(name="Rewards", value="\n".join(rewards), inline=False)
    if raid_boss is not None:
        raid_value = raid_boss.name
        if raid is not None and raid.is_active:
            raid_value += f" — HP {raid.current_hp:,}/{raid_boss.max_hp:,}"
        elif raid is not None and not raid.is_active:
            raid_value += " — Defeated"
        embed.add_field(name="Event Raid", value=raid_value, inline=False)
    embed.set_footer(text="Use /event attack to challenge the event raid boss.")
    return embed


def raid_attack_embed(
    member: discord.abc.User,
    boss: RaidBoss,
    raid: RaidInstance,
    *,
    damage_dealt: int,
    damage_taken: int,
    player: Player,
    participant: RaidParticipant,
    raid_completed: bool = False,
    xp_reward: int = 0,
    gold_reward: int = 0,
    leveled_up: bool = False,
    loot_items: Sequence[Item] = (),
    rare_item: Optional[Item] = None,
    materials: Sequence[Tuple[Material, int]] = (),
) -> discord.Embed:
    color = discord.Color.purple() if not raid_completed else discord.Color.gold()
    embed = discord.Embed(
        title=f"{member.display_name} strikes {boss.name}!",
        color=color,
    )
    embed.add_field(name="Damage Dealt", value=f"⚔️ {damage_dealt:,}", inline=True)
    embed.add_field(
        name="Total Contribution",
        value=f"🏅 {participant.damage_dealt:,}",
        inline=True,
    )
    embed.add_field(
        name="Boss HP",
        value=f"💖 {raid.current_hp:,}/{boss.max_hp:,}",
        inline=True,
    )
    embed.add_field(name="Damage Taken", value=f"💥 {damage_taken:,}", inline=True)
    embed.add_field(
        name="Your HP",
        value=f"❤️ {player.hp:,}/{player.max_hp:,}",
        inline=True,
    )
    embed.add_field(name="Energy", value=f"⚡ {player.energy}/100", inline=True)

    if raid_completed:
        embed.add_field(name="Raid Status", value="✅ Boss defeated!", inline=False)
        embed.add_field(name="XP Reward", value=f"🏅 {xp_reward:,}", inline=True)
        embed.add_field(name="Gold Reward", value=f"💰 {gold_reward:,}", inline=True)
        if leveled_up:
            embed.add_field(name="Level Up!", value=f"Level {player.level}", inline=True)
        if rare_item is not None:
            embed.add_field(
                name="Rare Loot",
                value=f"🌟 {rare_item.name}",
                inline=False,
            )
        if loot_items:
            embed.add_field(
                name="Raid Loot",
                value=_format_item_rewards(list(loot_items)),
                inline=False,
            )
        if materials:
            embed.add_field(
                name="Crafting Materials",
                value=_format_material_rewards(materials),
                inline=False,
            )

    footer = "The raid continues!" if raid.is_active else "Celebrate your victory!"
    embed.set_footer(text=footer)
    return embed


def raid_leaderboard_embed(
    boss: RaidBoss,
    raid: RaidInstance,
    standings: Sequence[Tuple[str, int, float]],
) -> discord.Embed:
    status = "Active" if raid.is_active else "Completed"
    embed = discord.Embed(
        title=f"{boss.name} Raid Leaderboard",
        description=f"Status: **{status}**",
        color=discord.Color.dark_magenta(),
    )
    embed.add_field(
        name="Boss HP",
        value=f"💖 {raid.current_hp:,}/{boss.max_hp:,}",
        inline=True,
    )
    embed.add_field(
        name="Total Damage",
        value=f"⚔️ {raid.total_damage:,}",
        inline=True,
    )
    if standings:
        lines = [
            f"**{idx}.** {name} — {damage:,} dmg ({share:.1f}%)"
            for idx, (name, damage, share) in enumerate(standings, start=1)
        ]
        embed.add_field(name="Top Raiders", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Top Raiders", value="No damage dealt yet.", inline=False)
    embed.set_footer(text="Join with /raid join and attack with /raid attack!")
    return embed


def work_result_embed(member: discord.abc.User, outcome, player: Player) -> discord.Embed:
    embed = discord.Embed(
        title=f"{member.display_name} works hard",
        description=f"Earned 💰 **{outcome.gold} gold** and **{outcome.xp} XP**",
        color=PRIMARY_COLOR,
    )
    embed.add_field(name="Gold", value=f"💰 {player.gold}", inline=True)
    embed.add_field(name="Energy", value=f"⚡ {player.energy}/100", inline=True)
    embed.set_footer(text="Keep working between quests for steady rewards")
    return embed


def heal_embed(member: discord.abc.User, healed: int, cost: int, player: Player) -> discord.Embed:
    if healed <= 0:
        description = "You are already at full health or need more gold."
        color = ERROR_COLOR
    else:
        description = f"Restored **{healed} HP** for **{cost} gold**."
        color = SUCCESS_COLOR
    embed = discord.Embed(
        title=f"{member.display_name} visits the healer",
        description=description,
        color=color,
    )
    embed.add_field(name="Current HP", value=f"❤️ {player.hp}/{player.max_hp}", inline=True)
    embed.add_field(name="Gold", value=f"💰 {player.gold}", inline=True)
    return embed


def rest_embed(member: discord.abc.User, energy_gain: int, player: Player) -> discord.Embed:
    if energy_gain <= 0:
        description = "You are already full of energy."
        color = ERROR_COLOR
    else:
        description = f"Recovered **{energy_gain} energy** while resting."
        color = SUCCESS_COLOR
    embed = discord.Embed(
        title=f"{member.display_name} takes a short rest",
        description=description,
        color=color,
    )
    embed.add_field(name="Energy", value=f"⚡ {player.energy}/100", inline=True)
    embed.add_field(name="Health", value=f"❤️ {player.hp}/{player.max_hp}", inline=True)
    return embed


def leaderboard_embed(
    guild: Optional[discord.Guild],
    entries: Iterable[Tuple[Player, Optional[discord.abc.User], Optional[ClassInfo]]],
) -> discord.Embed:
    title = "IdleRPG Global Adventurer Rankings"
    if guild is not None:
        title += f" • Viewing from {guild.name}"
    embed = discord.Embed(
        title=title,
        color=PRIMARY_COLOR,
    )
    description_lines = []
    for index, (player, member, player_class) in enumerate(entries, start=1):
        display_name = member.display_name if member else f"Unknown ({player.user_id})"
        line = (
            f"**{index}. {display_name}** — Level {player.level}"
            f" • XP {player.xp}/{xp_to_next_level(player.level)}"
            f" • 💰 {player.gold}"
        )
        if player_class is not None:
            line += f" • {player_class.name}"
        description_lines.append(line)
    embed.description = "\n".join(description_lines) or "No adventurers yet."
    embed.set_footer(text="Climb the leaderboard by completing quests!")
    return embed


def duel_result_embed(
    challenger: discord.abc.User,
    opponent: discord.abc.User,
    *,
    winner: discord.abc.User,
    challenger_player: Player,
    opponent_player: Player,
    challenger_stats: Mapping[str, int],
    opponent_stats: Mapping[str, int],
    rounds: Sequence[Tuple[str, str, int, int]],
    season_start: Optional[datetime] = None,
    seasonal_reset_enabled: bool = True,
) -> discord.Embed:
    """Build an embed summarizing a PvP duel."""

    embed = discord.Embed(
        title=f"{challenger.display_name} vs. {opponent.display_name}",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Winner", value=f"🏆 {winner.display_name}", inline=False)

    if rounds:
        log_lines = [
            (
                f"**Round {index}.** {attacker} hits {defender} for {damage} damage"
                f" ({defender_hp} HP left)"
            )
            for index, (attacker, defender, damage, defender_hp) in enumerate(rounds, start=1)
        ]
        preview = log_lines[:15]
        if len(log_lines) > 15:
            preview.append(f"…and {len(log_lines) - 15} more turns.")
        embed.add_field(name="Battle Log", value="\n".join(preview), inline=False)
    else:
        embed.add_field(name="Battle Log", value="The duel was decided instantly.", inline=False)

    embed.add_field(
        name=f"{challenger.display_name} Stats",
        value=(
            f"Attack {challenger_stats.get('attack', 0)}\n"
            f"Defense {challenger_stats.get('defense', 0)}\n"
            f"Max HP {challenger_stats.get('max_hp', 0)}"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{opponent.display_name} Stats",
        value=(
            f"Attack {opponent_stats.get('attack', 0)}\n"
            f"Defense {opponent_stats.get('defense', 0)}\n"
            f"Max HP {opponent_stats.get('max_hp', 0)}"
        ),
        inline=True,
    )

    def _format_record(player: Player) -> str:
        total = f"{player.pvp_wins}W-{player.pvp_losses}L"
        seasonal = f"{player.pvp_season_wins}W-{player.pvp_season_losses}L"
        return f"Total {total} • Season {seasonal}"

    records = [
        f"{challenger.display_name}: {_format_record(challenger_player)}",
        f"{opponent.display_name}: {_format_record(opponent_player)}",
    ]
    embed.add_field(name="PvP Records", value="\n".join(records), inline=False)

    if season_start is not None:
        season_text = discord.utils.format_dt(season_start, style="D")
        if seasonal_reset_enabled:
            footer = f"Seasonal PvP reset began {season_text}"
        else:
            footer = f"PvP tracking since {season_text}"
        embed.set_footer(text=footer)
    else:
        embed.set_footer(text="PvP battles are recorded globally.")

    return embed


def global_leaderboard_embed(
    category: str,
    entries: Sequence[Tuple[Player, Optional[discord.abc.User]]],
    *,
    season_start: Optional[datetime] = None,
    seasonal_reset_enabled: bool = True,
) -> discord.Embed:
    category_key = category.lower()
    titles = {
        "xp": "Global XP Leaderboard",
        "gold": "Global Gold Leaderboard",
        "pvp_wins": "Global PvP Leaderboard",
    }
    embed = discord.Embed(title=titles.get(category_key, "Global Leaderboard"), color=PRIMARY_COLOR)

    lines: list[str] = []
    for index, (player, user) in enumerate(entries, start=1):
        if user is not None and hasattr(user, "display_name"):
            name = user.display_name  # type: ignore[attr-defined]
        elif user is not None:
            name = getattr(user, "name", f"Unknown ({player.user_id})")
        else:
            name = f"Unknown ({player.user_id})"

        if category_key == "xp":
            lines.append(
                f"**{index}. {name}** — Level {player.level}"
                f" • XP {player.xp}/{xp_to_next_level(player.level)}"
                f" • 💰 {player.gold}"
            )
        elif category_key == "gold":
            lines.append(f"**{index}. {name}** — 💰 {player.gold}")
        elif category_key == "pvp_wins":
            lines.append(
                f"**{index}. {name}** — ⚔️ {player.pvp_wins}W-{player.pvp_losses}L"
                f" (Season {player.pvp_season_wins}W-{player.pvp_season_losses}L)"
            )
        else:
            lines.append(f"**{index}. {name}** — Level {player.level}")

    embed.description = "\n".join(lines) if lines else "No ranked adventurers yet."

    if category_key == "pvp_wins" and season_start is not None:
        season_text = discord.utils.format_dt(season_start, style="D")
        if seasonal_reset_enabled:
            footer = f"Current PvP season began {season_text}."
        else:
            footer = f"PvP season tracking since {season_text}."
        embed.set_footer(text=footer)
    elif category_key == "pvp_wins":
        if seasonal_reset_enabled:
            embed.set_footer(text="PvP seasons reset monthly.")
        else:
            embed.set_footer(text="PvP win tracking is persistent.")
    else:
        embed.set_footer(text="Compete to climb the global ranks!")

    return embed


def guild_info_embed(
    guild: Guild,
    members: Sequence[Tuple[GuildMember, Optional[discord.abc.User]]],
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{guild.name} Guild Overview",
        description=guild.description or "No guild description provided.",
        color=PRIMARY_COLOR,
    )
    embed.add_field(
        name="Level",
        value=f"{guild.level} (XP {guild.xp})",
        inline=True,
    )
    embed.add_field(name="Treasury", value=f"🏛️ {guild.gold}", inline=True)
    embed.add_field(name="Members", value=str(len(members)), inline=True)
    roster_lines = []
    for member, discord_member in members:
        if discord_member is not None and hasattr(discord_member, "display_name"):
            name = discord_member.display_name  # type: ignore[attr-defined]
        elif discord_member is not None:
            name = getattr(discord_member, "name", f"Unknown ({member.player_id})")
        else:
            name = f"Unknown ({member.player_id})"
        role = member.role.replace("_", " ").title()
        roster_lines.append(f"**{name}** — {role}")
    embed.add_field(
        name="Roster",
        value="\n".join(roster_lines[:20]) or "No members yet.",
        inline=False,
    )
    embed.set_footer(text="Guilds grow stronger together through quests and wars!")
    return embed


def guild_leaderboard_embed(guilds: Sequence[Guild]) -> discord.Embed:
    embed = discord.Embed(
        title="Global Guild Rankings",
        color=PRIMARY_COLOR,
    )
    lines = []
    for index, guild in enumerate(guilds, start=1):
        lines.append(
            f"**{index}. {guild.name}** — Level {guild.level}"
            f" • XP {guild.xp} • 🏛️ {guild.gold}"
        )
    embed.description = "\n".join(lines) or "No guilds have been founded yet."
    embed.set_footer(text="Found a guild and climb the rankings together!")
    return embed


def class_info_embed(info: ClassInfo) -> discord.Embed:
    embed = discord.Embed(title=f"{info.name} Class Details", color=PRIMARY_COLOR)
    embed.add_field(name="Description", value=info.description, inline=False)
    embed.add_field(name="Base HP", value=str(info.base_hp), inline=True)
    embed.add_field(name="Base Attack", value=str(info.base_attack), inline=True)
    embed.add_field(name="Base Defense", value=str(info.base_defense), inline=True)
    embed.add_field(
        name=f"Ability — {info.ability_name}",
        value=info.ability_description,
        inline=False,
    )
    embed.set_footer(text="Choose wisely—your class defines your combat style!")
    return embed


def cooldown_embed(action: str, remaining: timedelta) -> discord.Embed:
    embed = discord.Embed(
        title=f"{action.title()} is on cooldown",
        description=(
            f"Please wait **{_format_timedelta(remaining)}** before using {action} again."
        ),
        color=ERROR_COLOR,
    )
    return embed


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(title="Something went wrong", description=message, color=ERROR_COLOR)


def _format_timedelta(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
