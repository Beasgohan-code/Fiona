"""Canonical rarity options aligned with Summon-bot's display names."""

rarity_map = {
    1: "⚪ Common",
    2: "🔵 Rare",
    3: "💮 Special Edition",
    4: "⭐ Legendary",
    5: "🛸 Mythic Edition",
    6: "💝 Valentine Edition",
    7: "🏖️ Summer Edition",
    8: "🌧️ Rainy Edition",
    9: "🎃 Halloween Edition",
    10: "🎄 Christmas Edition",
    11: "❄️ Winter Edition",
    12: "🎇 New Year Edition",
    13: "🎍 Festival Edition",
    14: "🎥 AMV Edition",
    15: "🔞 Ecchi",
    16: "🌌 Celestial Edition",
    17: "💎 Luxury Edition",
    18: "🔮 Limited Edition",
}

# Names and emoji lookup are derived from the single canonical map.
RARITY_NAMES = list(rarity_map.values())
rarity_map2 = {name: name.split(maxsplit=1)[0] for name in RARITY_NAMES}
