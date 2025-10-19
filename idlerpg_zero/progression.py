"""Core game mechanics for IdleRPG Zero."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
from typing import Optional, Tuple

from .database import Player

QUEST_COOLDOWN = timedelta(0)
WORK_COOLDOWN = timedelta(minutes=3)
REST_COOLDOWN = timedelta(minutes=10)
MIN_HEAL_COST = 15
HEAL_AMOUNT = 35
ENERGY_MAX = 100
RAID_COOLDOWN = timedelta(minutes=15)
RAID_ENERGY_COST = 40


@dataclass(slots=True)
class QuestOutcome:
    xp: int
    gold: int
    damage: int
    leveled_up: bool


@dataclass(slots=True)
class WorkOutcome:
    gold: int
    xp: int


@dataclass(slots=True)
class RaidOutcome:
    xp: int
    gold: int
    damage: int
    leveled_up: bool


@dataclass(slots=True)
class HealOutcome:
    healed: int
    cost: int


def xp_to_next_level(level: int) -> int:
    base = 100
    scale = 25 * level
    return base + scale


def apply_xp_and_gold(player: Player, xp: int, gold: int) -> bool:
    player.xp += xp
    leveled_up = False
    while player.xp >= xp_to_next_level(player.level):
        player.xp -= xp_to_next_level(player.level)
        player.level += 1
        player.max_hp += 10
        player.hp = player.max_hp
        player.energy = min(ENERGY_MAX, player.energy + 10)
        player.attack += 2
        player.defense += 1
        leveled_up = True
    player.gold += gold
    return leveled_up


def _effective_attack(player: Player, weapon_damage: int = 0) -> int:
    attack = player.attack + max(0, weapon_damage)
    if player.attack_buff_battles > 0 and player.attack_buff_percent > 0:
        attack = int(attack * (100 + player.attack_buff_percent) / 100)
    return max(0, attack)


def _effective_defense(player: Player, armor_defense: int = 0) -> int:
    defense = player.defense + max(0, armor_defense)
    if player.defense_buff_battles > 0 and player.defense_buff_percent > 0:
        defense = int(defense * (100 + player.defense_buff_percent) / 100)
    return max(0, defense)


def _consume_battle_buffs(player: Player) -> None:
    if player.attack_buff_battles > 0:
        player.attack_buff_battles -= 1
        if player.attack_buff_battles <= 0:
            player.attack_buff_percent = 0
    if player.defense_buff_battles > 0:
        player.defense_buff_battles -= 1
        if player.defense_buff_battles <= 0:
            player.defense_buff_percent = 0


def effective_attack(player: Player, weapon_damage: int = 0) -> int:
    """Public helper for computing a player's effective attack value."""

    return _effective_attack(player, weapon_damage)


def effective_defense(player: Player, armor_defense: int = 0) -> int:
    """Public helper for computing a player's effective defense value."""

    return _effective_defense(player, armor_defense)


def perform_quest(
    player: Player,
    weapon_damage: int = 0,
    armor_defense: int = 0,
    *,
    xp_multiplier: float = 1.0,
    gold_multiplier: float = 1.0,
    energy_cost: int = 20,
) -> QuestOutcome:
    effective_attack = _effective_attack(player, weapon_damage)
    effective_defense = _effective_defense(player, armor_defense)
    xp_gain = random.randint(40, 70) + max(0, effective_attack // 2)
    gold_gain = random.randint(20, 45)
    base_damage = random.randint(5, 25)
    damage_reduction = effective_defense // 2
    damage = max(1, base_damage - damage_reduction)
    xp_reward = int(max(0, round(xp_gain * max(0.0, xp_multiplier))))
    gold_reward = int(max(0, round(gold_gain * max(0.0, gold_multiplier))))
    leveled_up = apply_xp_and_gold(player, xp_reward, gold_reward)
    player.hp = max(1, player.hp - damage)
    player.energy = max(0, player.energy - max(0, energy_cost))
    player.last_quest_at = datetime.now(timezone.utc)
    _consume_battle_buffs(player)
    return QuestOutcome(xp=xp_reward, gold=gold_reward, damage=damage, leveled_up=leveled_up)


def perform_raid(
    player: Player,
    weapon_damage: int = 0,
    armor_defense: int = 0,
    *,
    xp_multiplier: float = 1.0,
    gold_multiplier: float = 1.0,
) -> RaidOutcome:
    effective_attack = _effective_attack(player, weapon_damage)
    effective_defense = _effective_defense(player, armor_defense)
    xp_gain = random.randint(90, 140) + max(0, effective_attack)
    gold_gain = random.randint(75, 150)
    base_damage = random.randint(25, 55)
    damage_reduction = int(effective_defense * 0.75)
    damage = max(5, base_damage - damage_reduction)
    xp_reward = int(max(0, round(xp_gain * max(0.0, xp_multiplier))))
    gold_reward = int(max(0, round(gold_gain * max(0.0, gold_multiplier))))
    leveled_up = apply_xp_and_gold(player, xp_reward, gold_reward)
    player.hp = max(1, player.hp - damage)
    player.energy = max(0, player.energy - RAID_ENERGY_COST)
    player.last_raid_at = datetime.now(timezone.utc)
    _consume_battle_buffs(player)
    return RaidOutcome(xp=xp_reward, gold=gold_reward, damage=damage, leveled_up=leveled_up)


def perform_work(player: Player, weapon_damage: int = 0) -> WorkOutcome:
    effective_attack = _effective_attack(player, weapon_damage)
    gold_gain = random.randint(15, 30)
    xp_gain = random.randint(10, 20) + max(0, effective_attack // 4)
    apply_xp_and_gold(player, xp_gain, gold_gain)
    player.energy = max(0, player.energy - 10)
    player.last_work_at = datetime.now(timezone.utc)
    return WorkOutcome(gold=gold_gain, xp=xp_gain)


def heal_player(player: Player) -> HealOutcome:
    missing_hp = player.max_hp - player.hp
    if missing_hp <= 0:
        return HealOutcome(healed=0, cost=0)

    cost = max(MIN_HEAL_COST, missing_hp // 2)
    if player.gold < cost:
        return HealOutcome(healed=0, cost=0)

    heal_amount = min(HEAL_AMOUNT + player.level * 2, missing_hp)
    player.gold -= cost
    player.hp += heal_amount
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    return HealOutcome(healed=heal_amount, cost=cost)


def regenerate_energy(player: Player) -> int:
    if player.energy >= ENERGY_MAX:
        return 0
    gained = min(ENERGY_MAX - player.energy, 15)
    player.energy += gained
    return gained


def can_quest(player: Player, now: datetime) -> Tuple[bool, timedelta]:
    if player.active_quest_id is not None:
        if player.active_quest_complete_at is None:
            return False, QUEST_COOLDOWN
        remaining = player.active_quest_complete_at - now
        if remaining > timedelta(0):
            return False, remaining

    if player.last_quest_at is None:
        return True, timedelta(0)
    elapsed = now - player.last_quest_at
    if elapsed >= QUEST_COOLDOWN:
        return True, timedelta(0)
    return False, QUEST_COOLDOWN - elapsed


def active_quest_remaining(player: Player, now: datetime) -> Optional[timedelta]:
    if player.active_quest_id is None or player.active_quest_complete_at is None:
        return None
    remaining = player.active_quest_complete_at - now
    if remaining <= timedelta(0):
        return timedelta(0)
    return remaining


def can_raid(player: Player, now: datetime) -> Tuple[bool, timedelta]:
    if player.last_raid_at is None:
        return True, timedelta(0)
    elapsed = now - player.last_raid_at
    if elapsed >= RAID_COOLDOWN:
        return True, timedelta(0)
    return False, RAID_COOLDOWN - elapsed


def can_work(player: Player, now: datetime) -> Tuple[bool, timedelta]:
    if player.last_work_at is None:
        return True, timedelta(0)
    elapsed = now - player.last_work_at
    if elapsed >= WORK_COOLDOWN:
        return True, timedelta(0)
    return False, WORK_COOLDOWN - elapsed




def can_rest(player: Player, now: datetime) -> Tuple[bool, timedelta]:
    if player.last_rest_at is None:
        return True, timedelta(0)
    elapsed = now - player.last_rest_at
    if elapsed >= REST_COOLDOWN:
        return True, timedelta(0)
    return False, REST_COOLDOWN - elapsed


def rest_player(player: Player) -> int:
    energy_gain = regenerate_energy(player)
    player.last_rest_at = datetime.now(timezone.utc)
    return energy_gain

def energy_ready(player: Player, required: int) -> bool:
    return player.energy >= required
