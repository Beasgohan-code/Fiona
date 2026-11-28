"""Interactive help menu definitions for Fiona."""

HELP_DATA = {
    "guess": {
        "HELP_NAME": "Catch",
        "HELP": (
            "Catch anime characters that spawn in groups:\n\n"
            "• `/guess <name>` (or `/summon`, `/protecc`, `/collect`, `/grab`, `/hunt`) — Catch the spawned character and earn coins.\n"
            "• `/checkspawn` — View this group's message threshold and catch-round state; tap the Richgram button to refresh live progress.\n"
            "• `/spawn` — Manually start a character round (bot owner only)."
        ),
    },
    "harem": {
        "HELP_NAME": "Collection",
        "HELP": (
            "Manage and browse your character collection:\n\n"
            "• `/harem [anime]` / `/collection [anime]` / `/claimlist [anime]` — View all characters or filter by anime title\n"
            "• `/hmode` — Filter your harem by rarity\n"
            "• `/fav <id>` — Set your featured profile character\n"
            "• `/wishlist [id]` (alias `/wish`) — View your wishlist or add a catalog character; `/unwish <id>` removes one\n"
            "• `/pincharacter <id>` / `/unpincharacter <id>` / `/pinnedcharacters` — Manage pinned collection characters; `/pinnedcharacters` includes one-tap unpin buttons (aliases: `/hpin`, `/hunpin`, `/pinlist`)\n"
            "• `/collectionvalue` — Estimate the market value of your collection\n"
            "• Group-message pinning uses the separate admin commands `/pin` and `/unpin`."
        ),
    },
    "profile": {
        "HELP_NAME": "Profile",
        "HELP": (
            "View collector stats and rankings:\n\n"
            "• `/profile`, `/me`, or `/hstats` — View your visual profile, featured favourite, collection progress, daily streak, and rarity breakdown\n"
            "• `/rank` or `/top` — View global top collectors\n"
            "• `/achievements` — Track collection, rarity, coin, and referral milestones\n"
            "• `/ctop` — Top collectors in the current group\n"
            "• `/TopGroups` — Top 10 groups globally\n"
            "• `/server` — View Fiona community totals"
        ),
    },
    "balance": {
        "HELP_NAME": "Economy",
        "HELP": (
            "Manage your coins and rewards:\n\n"
            "• `/balance` or `/bal` — Check your Coins & Tokens\n"
            "• `/dailygift` or `/daily` — Claim your daily coin reward and build a streak\n"
            "• `/streak` — View your current and longest daily reward streak\n"
            "• `/spin` — Claim one 24-hour coin spin\n"
            "• `/weekly` — Claim your weekly coin reward\n"
            "• `/pay <amount>` — Send coins to another user (reply or pass ID/@username)\n"
            "• `/shop` — Buy characters with coins\n"
            "• `/sell <character_id>` — Sell one extra copy while keeping your last copy safe\n"
            "• `/sellall` — Preview duplicate-sale value; `/sellall confirm` sells duplicates only\n"
            "• `/hclaim` or `/claim` — Claim your daily character"
        ),
    },
    "trade": {
        "HELP_NAME": "Trade & Gift",
        "HELP": (
            "Exchange characters with other collectors:\n\n"
            "• `/trade <your_char_id> <their_char_id>` — Reply to a user to propose a trade\n"
            "• `/gift <char_id>` — Reply to a user to gift a character\n"
            "• `/redeem <code>` — Redeem a character code\n"
            "• `/refer` — Invite friends and earn coin rewards"
        ),
    },
    "auction": {
        "HELP_NAME": "Auctions",
        "HELP": (
            "Live character auctions — escrow a copy, collectors bid with coins:\n\n"
            "• `/auction <id> <start_price> [minutes]` — Escrow one copy of a character and list it for live auction\n"
            "• `/bid <auction_id> <amount>` — Place a bid; tap the quick-bid buttons on the auction card for instant bids\n"
            "• `/auctionlist` (alias `/auctions`) — Browse live auctions\n"
            "• `/mybids` — Track the auctions you have bid on\n"
            "• `/cancelauction <auction_id>` — Cancel your auction before any bid is placed; the character is returned\n"
            "• `/auctionhistory` (alias `/auctionlog`) — Browse recently closed auctions\n"
            "• `/auctionstats` (alias `/auctionsummary`) — Your closed-auction profit and escrowed-coin summary\n"
        ),
    },
    "search": {
        "HELP_NAME": "Search",
        "HELP": (
            "Explore the character database:\n\n"
            "• `/check <id>` — View details of a character by ID\n"
            "• `/sips` or `/search <name>` — Search characters by name with inline preview\n"
            "• `/rarity` or `/rarities` — View every rarity currently in the catalog\n"
            "• `/total` — Total characters in the database\n"
            "• `/addchar <name> <anime>` — Reply to an image, choose ImgBB/Catbox, then request review\n"
            "• Inline mode: type `@BotUsername <query>` in any chat"
        ),
    },
    "lang": {
        "HELP_NAME": "Language",
        "HELP": (
            "Customize bot language:\n\n"
            "• `/lang` or `/settings` — Choose from 10 supported languages for DM or Group"
        ),
    },
    "admin": {
        "HELP_NAME": "Admin",
        "HELP": (
            "Available owner and admin controls:\n\n"
            "• `/add <name> <anime> <rarity-id> <image-url>` — Add from a Catbox/ImgBB/Endtrz HTTPS image URL\n"
            "• `/gupload <name> <anime> <rarity>` — Choose ImgBB/Catbox; uploads and posts to the character channel\n"
            "• `/update` or `/gupdate <id> <field> <value>` — Update character data/image\n"
            "• `/deletechar <id>` or `/gdelete <id>` — Delete a character and remove it from collections\n"
            "• `/maxupdate`, `/rdelete` — Bulk update or rarity administration\n"
            "• `/find`, `/findani` — Find next available ID or search anime\n"
            "• `/ctime <count>` or `/changetime <count>` — Set group character spawn message threshold\n"
            "• `/spawn` — Manually start a character round (bot owner only)\n"
            "• `/chance <rarity_id> <weight>` / `/chancelist` — Set relative automatic spawn weights (0–1,000,000) and view estimated odds (owner only; weight 0 disables that rarity)\n"
            "• `/setclaim <rarity_id> <weight>` / `/claimweights` — Set daily claim weights (0–1,000,000) and view configured odds (owner only; weight 0 disables a rarity)\n"
            "• `/givemoney <user_id> <amount>` / `/rmmoney <user_id> <amount>` — Adjust collector coins (owner only).\n"
            "• `/give <character_id>` — Reply to a user to grant a character (owner only).\n"
            "• `/removeall <user_id>` — Clear a user's character collection after owner confirmation; their economy/profile are preserved.\n"
            "• `/cgen <char_id> <limit>` — Generate a character redeem code\n"
            "• `/add`, `/kill`, `/transfer`, `/backtransfer` — Manage user data & currency\n"
            "• `/blocklist`, `/removeblocklist`, `/addblocklistgc`, `/removeblocklistgc` — Blocklists\n"
            "• `/saddsudo` — grant sudo (reply; starts with add_character power)\n"
            "• `/sremovesudo` — remove sudo (reply or user id)\n"
            "• `/seditsudo` — toggle a sudo's powers via keyboard (reply)\n"
            "• `/waifusudolist` — list sudo users + powers (owner only; music sudo list is `/sudolist`)\n"
            "• `/bcast`, `/list`, `/groups`, `/backup`"
        ),
    },
}
