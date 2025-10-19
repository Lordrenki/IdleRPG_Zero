"""Quest definitions and random encounters for IdleRPG Zero."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import random
from typing import Iterable, Mapping, Optional, Sequence, Tuple


QuestCategory = str


@dataclass(slots=True)
class QuestMaterialReward:
    """Configuration for a material reward granted by a quest."""

    rarity: str
    quantity: Tuple[int, int] = (1, 1)


@dataclass(slots=True)
class QuestReward:
    """Additional rewards provided by a quest beyond the base outcome."""

    xp: int = 0
    gold: int = 0
    item_names: Sequence[str] = field(default_factory=tuple)
    materials: Sequence[QuestMaterialReward] = field(default_factory=tuple)


@dataclass(slots=True)
class QuestDefinition:
    """Structured definition of a quest available to players."""

    id: str
    name: str
    summary: str
    narrative: str
    success_text: str
    category: QuestCategory
    cooldown: Optional[timedelta]
    xp_multiplier: float = 1.0
    gold_multiplier: float = 1.0
    energy_cost: int = 20
    rewards: QuestReward = field(default_factory=QuestReward)
    repeatable: bool = True

    def availability(
        self, progress: Optional["QuestProgress"], now: datetime
    ) -> "QuestAvailability":
        if not self.repeatable and progress and progress.completions > 0:
            return QuestAvailability(available=False, cooldown_remaining=None, locked=True)
        if self.cooldown is None or progress is None or progress.last_completed_at is None:
            return QuestAvailability(available=True, cooldown_remaining=None, locked=False)
        elapsed = now - progress.last_completed_at
        if elapsed >= self.cooldown:
            return QuestAvailability(available=True, cooldown_remaining=None, locked=False)
        return QuestAvailability(
            available=False,
            cooldown_remaining=self.cooldown - elapsed,
            locked=False,
        )


@dataclass(slots=True)
class QuestProgress:
    """Snapshot of a player's progress for a specific quest."""

    quest_id: str
    last_completed_at: Optional[datetime]
    completions: int


@dataclass(slots=True)
class QuestAvailability:
    """Represents whether a quest can currently be attempted."""

    available: bool
    cooldown_remaining: Optional[timedelta]
    locked: bool


@dataclass(slots=True)
class EncounterOutcome:
    """Possible result from a random encounter event."""

    text: str
    weight: float = 1.0
    xp: int = 0
    gold: int = 0
    item_names: Sequence[str] = field(default_factory=tuple)
    materials: Sequence[QuestMaterialReward] = field(default_factory=tuple)
    damage: int = 0


@dataclass(slots=True)
class RandomEncounter:
    """Represents a random event that can trigger during a quest."""

    id: str
    prompt: str
    outcomes: Sequence[EncounterOutcome]
    weight: float = 1.0

    def roll(self) -> EncounterOutcome:
        total = sum(outcome.weight for outcome in self.outcomes)
        roll = random.random() * total
        cumulative = 0.0
        for outcome in self.outcomes:
            cumulative += outcome.weight
            if roll <= cumulative:
                return outcome
        return self.outcomes[-1]


def _quest(
    *,
    id: str,
    name: str,
    summary: str,
    narrative: str,
    success_text: str,
    category: QuestCategory,
    cooldown: Optional[timedelta],
    xp_multiplier: float = 1.0,
    gold_multiplier: float = 1.0,
    energy_cost: int = 20,
    rewards: Optional[QuestReward] = None,
    repeatable: bool = True,
) -> QuestDefinition:
    return QuestDefinition(
        id=id,
        name=name,
        summary=summary,
        narrative=narrative,
        success_text=success_text,
        category=category,
        cooldown=cooldown,
        xp_multiplier=xp_multiplier,
        gold_multiplier=gold_multiplier,
        energy_cost=energy_cost,
        rewards=rewards or QuestReward(),
        repeatable=repeatable,
    )


QUESTS: Sequence[QuestDefinition] = (
    _quest(
        id="daily_forest_patrol",
        name="Forest Patrol",
        summary="Sweep the Whispering Woods for mischievous sprites.",
        narrative=(
            "You follow deer trails through the Whispering Woods, driving off sprites"
            " that have been stealing lantern light from nearby villages."
        ),
        success_text="The grateful villagers gift you bundles of wildberries and coin.",
        category="daily",
        cooldown=timedelta(hours=24),
        xp_multiplier=1.1,
        gold_multiplier=1.15,
        rewards=QuestReward(
            materials=(QuestMaterialReward("common", (1, 2)),),
        ),
    ),
    _quest(
        id="daily_market_guard",
        name="Market Guard",
        summary="Stand watch over the bustling Skyport bazaar.",
        narrative=(
            "Merchant airships crowd the Skyport and tempers flare as traders jostle"
            " for space. Your steady gaze keeps the peace and settles disputes."
        ),
        success_text="Honest vendors slip you extra coin for the calm you provided.",
        category="daily",
        cooldown=timedelta(hours=24),
        xp_multiplier=1.05,
        gold_multiplier=1.25,
        rewards=QuestReward(
            gold=35,
        ),
    ),
    _quest(
        id="daily_herbalist_rescue",
        name="Herbalist's Aid",
        summary="Gather moonpetal blooms before the night frost takes them.",
        narrative=(
            "Anxious herbalists lead you to terraces bathed in moonlight. You fend"
            " off hungry fae and harvest the glowing moonpetal blossoms in time."
        ),
        success_text="The coven brews a restorative tonic in your honour.",
        category="daily",
        cooldown=timedelta(hours=24),
        xp_multiplier=1.2,
        gold_multiplier=1.05,
        rewards=QuestReward(
            item_names=("Healing Potion",),
        ),
    ),
    _quest(
        id="weekly_ruins_delver",
        name="Sunken Ruins Delve",
        summary="Explore flooded ruins beneath the crystal lake.",
        narrative=(
            "Ancient wards flicker as you descend into the lake's drowned sanctum."
            " You recover relics while dodging rune traps and spectral guardians."
        ),
        success_text="A recovered reliquary pulses with lost knowledge and wealth.",
        category="weekly",
        cooldown=timedelta(days=7),
        xp_multiplier=1.4,
        gold_multiplier=1.3,
        energy_cost=25,
        rewards=QuestReward(
            xp=75,
            item_names=("Mana Elixir",),
            materials=(QuestMaterialReward("uncommon", (1, 2)),),
        ),
    ),
    _quest(
        id="weekly_dragon_watch",
        name="Dragon Watch",
        summary="Scout the Stormpeaks for awakening drakes.",
        narrative=(
            "You brave icy winds atop the Stormpeaks, mapping nests and warding"
            " townsfolk against restless drakelings stirring from slumber."
        ),
        success_text="Your reports earn royal favour and a cache of rare scales.",
        category="weekly",
        cooldown=timedelta(days=7),
        xp_multiplier=1.35,
        gold_multiplier=1.4,
        energy_cost=30,
        rewards=QuestReward(
            gold=120,
            materials=(QuestMaterialReward("rare", (1, 1)),),
        ),
    ),
    _quest(
        id="story_crystal_awakening",
        name="Crystal Awakening",
        summary="Unravel the mystery of the slumbering auric crystal.",
        narrative=(
            "A dormant auric crystal hums beneath the capital. You decipher forgotten"
            " sigils, channeling your own power to reawaken its protective ward."
        ),
        success_text="The city erupts in celebration as the shield flares back to life.",
        category="story",
        cooldown=None,
        xp_multiplier=1.5,
        gold_multiplier=1.5,
        energy_cost=30,
        rewards=QuestReward(
            xp=150,
            item_names=("Strength Tonic",),
            materials=(QuestMaterialReward("epic", (1, 1)),),
        ),
        repeatable=False,
    ),
    _quest(
        id="story_shadow_pact",
        name="Shadow Pact",
        summary="Confront the Veiled Court and break their pact with night spirits.",
        narrative=(
            "In catacombs of living shadow you negotiate with ancient spirits, severing"
            " a pact that has drained the realm's warmth for generations."
        ),
        success_text="The spirits bow to your resolve, granting a boon before dispersing.",
        category="story",
        cooldown=None,
        xp_multiplier=1.45,
        gold_multiplier=1.6,
        energy_cost=35,
        rewards=QuestReward(
            gold=200,
            item_names=("Greater Healing Potion",),
            materials=(QuestMaterialReward("legendary", (1, 1)),),
        ),
        repeatable=False,
    ),
)


RANDOM_ENCOUNTERS: Sequence[RandomEncounter] = (
    RandomEncounter(
        id="wandering_bard",
        prompt="A wandering bard challenges you to a duel of stories.",
        weight=1.0,
        outcomes=(
            EncounterOutcome(
                text="You trade tales late into the night, inspiring each other to new heights.",
                xp=45,
                gold=20,
                weight=2.0,
            ),
            EncounterOutcome(
                text="The bard gifts you a melody etched into a silver charm.",
                item_names=("Mana Elixir",),
                xp=20,
            ),
            EncounterOutcome(
                text="Your story falters and the bard's playful mockery stings your pride.",
                damage=10,
                xp=10,
            ),
        ),
    ),
    RandomEncounter(
        id="lost_traveler",
        prompt="You spot a lost traveler waving frantically from a ravine.",
        weight=0.9,
        outcomes=(
            EncounterOutcome(
                text="You rig a rope bridge and guide them to safety. Grateful, they share provisions.",
                gold=40,
                xp=25,
            ),
            EncounterOutcome(
                text="Bandits ambush while you assist, but you drive them off with minor scrapes.",
                damage=12,
                materials=(QuestMaterialReward("common", (1, 1)),),
                xp=15,
            ),
            EncounterOutcome(
                text="The traveler is a scholar who pays you with a rare alchemical draught.",
                item_names=("Healing Potion",),
                xp=30,
            ),
        ),
    ),
    RandomEncounter(
        id="rune_cache",
        prompt="Faint glyphs reveal a hidden cache buried beneath mossy stones.",
        weight=0.8,
        outcomes=(
            EncounterOutcome(
                text="You decipher the sequence and claim glittering materials.",
                materials=(QuestMaterialReward("uncommon", (1, 2)),),
                xp=20,
            ),
            EncounterOutcome(
                text="A rune misfires, releasing a concussive blast that rattles your armor.",
                damage=15,
                xp=10,
            ),
            EncounterOutcome(
                text="The cache hides a battle standard imbued with protective wards.",
                item_names=("Guard Brew",),
                xp=35,
            ),
        ),
    ),
)


def all_quests() -> Sequence[QuestDefinition]:
    return QUESTS


def quests_by_category() -> Mapping[QuestCategory, Sequence[QuestDefinition]]:
    categories: dict[QuestCategory, list[QuestDefinition]] = {}
    for quest in QUESTS:
        categories.setdefault(quest.category, []).append(quest)
    for quest_list in categories.values():
        quest_list.sort(key=lambda q: q.name)
    return categories


def find_quest(identifier: str) -> Optional[QuestDefinition]:
    lowered = identifier.lower()
    for quest in QUESTS:
        if quest.id == lowered or quest.name.lower() == lowered:
            return quest
    return None


def search_quests(term: str) -> Sequence[QuestDefinition]:
    lowered = term.lower()
    results = [
        quest
        for quest in QUESTS
        if not term or lowered in quest.name.lower() or lowered in quest.summary.lower()
    ]
    results.sort(key=lambda q: q.name)
    return results[:25]


def category_display_name(category: QuestCategory) -> str:
    if category == "daily":
        return "Daily Quests"
    if category == "weekly":
        return "Weekly Quests"
    if category == "story":
        return "Story Quests"
    return category.title()


def roll_random_encounter() -> Optional[Tuple[RandomEncounter, EncounterOutcome]]:
    if not RANDOM_ENCOUNTERS:
        return None
    # 60% chance to trigger an encounter
    if random.random() > 0.6:
        return None
    total_weight = sum(encounter.weight for encounter in RANDOM_ENCOUNTERS)
    roll = random.random() * total_weight
    cumulative = 0.0
    for encounter in RANDOM_ENCOUNTERS:
        cumulative += encounter.weight
        if roll <= cumulative:
            return encounter, encounter.roll()
    encounter = RANDOM_ENCOUNTERS[-1]
    return encounter, encounter.roll()


def summarize_rewards(quest: QuestDefinition) -> str:
    parts: list[str] = []
    if quest.rewards.xp:
        parts.append(f"+{quest.rewards.xp} XP")
    if quest.rewards.gold:
        parts.append(f"+{quest.rewards.gold} gold")
    if quest.rewards.item_names:
        parts.append(
            "Items: " + ", ".join(f"{name}" for name in quest.rewards.item_names)
        )
    if quest.rewards.materials:
        mats = ", ".join(
            f"{reward.quantity[0]}–{reward.quantity[1]}× {reward.rarity.title()} material"
            if reward.quantity[0] != reward.quantity[1]
            else f"{reward.quantity[0]}× {reward.rarity.title()} material"
            for reward in quest.rewards.materials
        )
        parts.append(f"Materials: {mats}")
    return "; ".join(parts) if parts else "Bonus rewards vary."


def describe_availability(
    quest: QuestDefinition,
    progress: Optional[QuestProgress],
    now: datetime,
) -> QuestAvailability:
    return quest.availability(progress, now)


__all__ = [
    "QuestDefinition",
    "QuestReward",
    "QuestMaterialReward",
    "QuestProgress",
    "QuestAvailability",
    "EncounterOutcome",
    "RandomEncounter",
    "all_quests",
    "quests_by_category",
    "find_quest",
    "search_quests",
    "category_display_name",
    "roll_random_encounter",
    "summarize_rewards",
    "describe_availability",
]
