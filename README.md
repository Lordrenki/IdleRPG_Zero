# IdleRPG Zero

IdleRPG Zero is a cosy idle adventure for Discord. Create a hero, take on light-hearted quests, and collect loot while chatting with friends. Progress is shared globally, so your adventurer travels with you to every community that invites the bot.

## Highlights

- **Slash command native.** Every action is a modern Discord slash command with colourful embeds.
- **Global progression.** Characters, inventories, and leaderboards are synced across every server the bot joins.
- **Relaxed gameplay loop.** Quest, work, rest, and heal on gentle timers that reward checking in between conversations.
- **Collect, craft, and compete.** Unlock classes, earn achievements, gather materials, and show off rare cosmetics.
- **Guild camaraderie.** Found a clan with friends, tackle raids, and coordinate crafting projects together.

## Command overview

- `/start` – roll a new character and choose your class.
- `/profile` – admire your stats, loadout, achievements, and guild affiliation.
- `/quest` – embark on story-driven missions for XP, gold, and loot.
- `/work` – earn a steady wage while saving energy for bigger adventures.
- `/rest` – recharge stamina so you are ready for the next outing.
- `/heal` – pay the town healer to patch up battle scars.
- `/inventory`, `/equip`, `/use` – manage gear, items, and consumables.
- `/guild` commands – create and manage player-run clans, launch raids, and coordinate upgrades.
- `/leaderboard` – celebrate the top heroes across the entire IdleRPG Zero community.
- `/global leaderboard` – switch between XP, gold, or PvP rankings for a broader view of the realm.

## How to play

1. Invite the bot to a Discord server where you and your friends hang out.
2. Use `/start` to create your hero and pick a class that matches your play style.
3. Alternate between `/quest` and `/work` to earn XP and gold while timers tick in the background.
4. Spend downtime on `/rest`, `/heal`, and crafting to keep your character in top form.
5. Form a guild to unlock cooperative raids, group crafting bonuses, and shared achievements.
6. Check `/leaderboard` to see how your progress stacks up against players everywhere.

IdleRPG Zero is designed for drop-in fun—log in when you have a spare moment, collect your rewards, and watch your hero grow.

## Project layout

```
src/idlerpg_zero/
├── bot.py          # Discord bot class and slash command definitions
├── config.py       # Environment-based configuration loader
├── database.py     # Async SQLite wrapper and player model
├── embeds.py       # Embed styling shared across commands
├── progression.py  # Game mechanics (quests, work, healing, etc.)
└── __main__.py     # Entry point (python -m idlerpg_zero)
```

## License

This project is released under the MIT License.
