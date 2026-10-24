"""What each rune's per-game values (var1-var3 on a selected rune) mean. Riot doesn't document these and they change
with rune reworks, so labels are best guesses unless the rune is in VERIFIED_RUNES (checked against real games in
ticket 08). Runes not listed, and listed runes' unlabelled slots that have values, show their raw values."""

# perk id -> labels for var1, var2, var3 (None = unused)
RUNE_VALUE_LABELS = {
    # Precision
    8005: ("Total damage", None, None),  # Press the Attack
    8008: ("Total attack speed gained", None, None),  # Lethal Tempo
    8021: ("Total healing", None, None),  # Fleet Footwork
    8010: ("Total healing", None, None),  # Conqueror
    9101: ("Total healing", None, None),  # Absorb Life
    9111: ("Total healing", "Bonus gold", None),  # Triumph (verified)
    8009: ("Total mana restored", None, None),  # Presence of Mind
    9104: ("Stacks", None, None),  # Legend: Alacrity
    9105: ("Stacks", None, None),  # Legend: Haste
    9103: ("Stacks", None, None),  # Legend: Bloodline
    8014: ("Total bonus damage", None, None),  # Coup de Grace
    8017: ("Total bonus damage", None, None),  # Cut Down
    8299: ("Total bonus damage", None, None),  # Last Stand
    # Domination
    8112: ("Total damage", None, None),  # Electrocute
    8128: ("Total damage", "Souls collected", None),  # Dark Harvest
    9923: ("Total damage", None, None),  # Hail of Blades
    8126: ("Total damage", None, None),  # Cheap Shot
    8139: ("Total healing", None, None),  # Taste of Blood
    8143: ("Total damage", None, None),  # Sudden Impact
    8137: ("Wards destroyed", None, None),  # Sixth Sense
    8140: ("Total damage", None, None),  # Grisly Mementos
    8141: ("Wards destroyed", None, None),  # Deep Ward
    8135: ("Stacks", "Bonus gold", None),  # Treasure Hunter
    8105: ("Stacks", "Out-of-combat time", None),  # Relentless Hunter
    8106: ("Stacks", None, None),  # Ultimate Hunter
    # Sorcery
    8214: ("Total damage", "Total shielding", None),  # Summon Aery
    8229: ("Total damage", None, None),  # Arcane Comet
    8230: ("Activations", None, None),  # Phase Rush
    8224: ("Total shield", None, None),  # Axiom Arcanist (was Nullifying Orb); real games fill var1 and var2
    8226: ("Max mana gained", "Mana restored", None),  # Manaflow Band
    8275: ("Activations", None, None),  # Nimbus Cloak
    8210: ("Cooldown refunded (s)", None, None),  # Transcendence
    8234: ("Extra distance moved", None, None),  # Celerity
    8233: ("Total bonus damage", None, None),  # Absolute Focus
    8237: ("Total damage", None, None),  # Scorch
    8232: ("Bonus adaptive force", None, None),  # Waterwalking
    8236: ("Bonus adaptive force", None, None),  # Gathering Storm (verified)
    # Resolve
    8437: ("Total damage", "Total healing", None),  # Grasp of the Undying
    8439: ("Damage mitigated", "Total damage", None),  # Aftershock
    8465: ("Total shielding", None, None),  # Guardian
    8446: ("Total tower damage", None, None),  # Demolish
    8463: ("Total ally healing", None, None),  # Font of Life
    8401: ("Total damage", None, None),  # Shield Bash
    8429: ("Total bonus resists", None, None),  # Conditioning
    8444: ("Total healing", None, None),  # Second Wind
    8473: ("Total damage blocked", None, None),  # Bone Plating
    8451: ("Max health gained", None, None),  # Overgrowth
    8453: ("Bonus healing", "Bonus shielding", None),  # Revitalize
    8242: ("Total bonus resists", None, None),  # Unflinching
    # Inspiration
    8351: ("Total damage", None, None),  # Glacial Augment
    8360: ("Spells used", "Gold gained", None),  # Unsealed Spellbook
    8369: ("Total damage", "Gold gained", None),  # First Strike
    8306: ("Times hit", None, None),  # Hextech Flashtraption
    8304: ("Boots arrival time (s)", None, None),  # Magical Footwear
    8321: ("Gold gained", None, None),  # Cash Back (verified)
    8313: ("Elixirs and potions used", None, None),  # Triple Tonic
    8352: ("Total healing", None, None),  # Time Warp Tonic
    8345: ("Biscuits received", None, None),  # Biscuit Delivery
    8347: ("Ability haste gained", None, None),  # Cosmic Insight
    8410: ("Time with bonus speed (s)", None, None),  # Approach Velocity
    8316: ("Adaptive force gained", None, None),  # Jack of All Trades
}

# Runes whose labels were checked against real games (ticket 08, 60 Lillia games on patches 16.16-16.21); the rest
# stay marked unverified in the UI. Evidence:
# - Triumph: var2 == 20 x (kills + assists) in every game; var1 is 53-137 per takedown, the size of its takedown heal.
# - Cash Back: var1 == 7.5% of the gold cost of the completed legendaries, exactly, in every game.
# - Gathering Storm: var1 == 8 x T(n) adaptive force (8, 24, 48, 80), n = whole 10-minute blocks played, in every game.
VERIFIED_RUNES = frozenset({9111, 8321, 8236})

SHARD_NAMES = {
    5008: "Adaptive Force", 5005: "Attack Speed", 5007: "Ability Haste", 5010: "Move Speed",
    5001: "Health Scaling", 5011: "Health", 5013: "Tenacity and Slow Resist", 5002: "Armor", 5003: "Magic Resist",
}
