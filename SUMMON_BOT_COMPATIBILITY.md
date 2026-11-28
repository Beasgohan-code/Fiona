# Summon-bot feature map for Fiona

Source inspected with the user's permission: `Beasgohan-code/Summon-bot` at
`504fe3635df2024e3f7ee901db91ab1e676b054a`. Fiona stays a single Pyrogram /
Mongo-backed combined bot; Summon-bot's standalone PTB handlers and SQL schema
are not copied wholesale.

## Available in Fiona

| Summon-bot command/feature | Fiona command or equivalent |
| --- | --- |
| `/start`, `/ping`, `/help`, `/menu`, `/commands` | `/start`, `/ping`, `/help`, `/menu`, `/commands` |
| `/balance`, `/bal`, `/daily`, `/givemoney`, `/rmmoney` | `/balance`, `/bal`, `/daily` and `/dailygift`; owner-only `/givemoney <user_id> <amount>` and `/rmmoney <user_id> <amount>` adjust collector coins |
| `/spin` | `/spin` — Fiona-sized daily coin rewards; one atomic 24-hour claim per user |
| `/collection`, `/harem`, `/claimlist` | `/harem`, `/collection`, `/claimlist`; accepts an optional case-insensitive anime-title fragment, keeps it while paging, and shows per-anime progress percentages plus duplicate-copy totals |
| Fiona collection pins | `/pincharacter`, `/unpincharacter`, `/pinnedcharacters` (legacy aliases `/hpin`, `/hunpin`, `/pinlist`); the pinned list provides owner-scoped one-tap unpin controls |
| `/check`, `/info` | `/check` |
| `/search`, `/find` | `/search`, `/sips` or the bot's inline search |
| `/summon`, `/guess` | `/summon`, `/guess` and related Fiona catch aliases |
| `/fav`, `/pay`, `/shop`, `/gift`, `/hmode` | Same Fiona commands |
| `/top`, `/rank` | `/top`, `/rank` |
| `/stats`, `/server` | `/server` or `/st` for community totals; `/stats` remains the music statistics command |
| `/profile`, `/hstats`, `/me` | `/profile`, `/hstats`, `/me` |
| `/achievements`, `/ach`, `/badges` | `/achievements` and aliases; milestones are derived from Fiona's Mongo user data |
| Rarity catalog | Fiona's canonical upload/shop/spawn/filter options follow Summon-bot's rarity order and names, with rarity 15 customized to `🔞 Ecchi` at the user's request; `/rarity` and `/rarities` show the configured options plus a grouped legacy count, without deleting catalog characters or user collection entries |
| `/claim`, `/hclaim`, `/redeem`, `/setclaim` | Fiona's `/claim`, `/hclaim`, `/redeem`; owner-only `/setclaim <rarity_id> <weight>` persists daily-claim weights (0–1,000,000), shown with configured odds in `/claimweights` (rarities unavailable for a particular draw are excluded; Fiona keeps `/claimlist` for a user's collected characters) |
| `/transfer`, `/addchar`, `/give` | Fiona's `/transfer`, `/addchar`; owner-only `/give <character_id>` replies to a user and grants the catalog character |
| `/removeall` | Owner-only `/removeall <user_id>` clears only the target's character copies after a one-use confirmation; economy and profile data are preserved |
| `/add`, `/update`, `/deletechar` | Fiona's `/add`, `/update`, `/deletechar`, with existing aliases `/gupload`, `/gupdate`, and `/gdelete` retained |
| Admin character uploads | `/add` accepts direct Catbox, ImgBB, or Endtrz HTTPS image URLs; `/gupload` asks per upload whether to use ImgBB or Catbox, then posts image and metadata to `CHARA_CHANNEL_ID` (falls back to `GLOG`) |
| `/checkspawn`, `/changetime` | `/checkspawn` shows a Richgram blockquote panel with per-group threshold, in-memory progress, and catch-round state; `/changetime <count>` aliases Fiona's admin-authorized `/ctime <count>` |
| `/spawn`, `/chance`, `/chancelist` | Owner-only manual group spawn; persistent relative rarity weights for automatic drops (0–1,000,000), configurable with `/chance <rarity_id> <weight>`; `/chancelist` displays current weights and estimated odds |
| `/ban`, `/unban`, `/warn` | Existing Fiona group moderation commands |
| `/broadcast` | Owner/Sudo-only `/waifubcast` and `/waifubroadcast` |
| `/owner`, `/panel` | Private, `OWNER_ID`-gated interactive Richgram owner overview with character, economy, spawn/claim, and safety sections; callback navigation is owner-only and admin commands retain their own checks |

Fiona reserves `/claimlist` for a user's character collection, so Summon's claim-weight listing is available as `/claimweights`. `/addchar` also asks the submitter to choose ImgBB or Catbox before posting a pending approval request to `CHARA_CHANNEL_ID`. Fiona's old `/reupload` command is removed as requested. Endtrz direct HTTPS image URLs are accepted by `/add` and `/update image`; Endtrz is not offered as an upload destination in `/gupload` or `/addchar` because this link alone does not establish its upload API.

The command menu and `/help` describe the supported commands. Fiona's music
`/stats` already exists, so the collector profile intentionally uses
`/profile`, `/hstats`, and `/me` rather than registering a conflicting `/stats`.

## Not copied as separate commands

These features need Summon-bot's SQL tables, market state, callback workflows,
or semantics that Fiona does not currently have. They are not safe to attach as
thin aliases to unrelated Fiona commands:

- `/market`, `/inv`, `/inventory`, `/sell`, `/sellchar`, auctions, `/bomb`,
  `/steal`, and `/pinfo` (no equivalent marketplace/inventory model).
- Streak-dependent reward bonuses/achievements are not copied. Fiona now tracks
  a daily-reward streak and longest streak with `/streak`, while retaining its
  existing fixed daily payout and achievement model.
- Claim-code administration beyond Fiona's existing `/cgen` and `/redeem` flows.
- `/font`/`/style`, `/premium`/`/unpremium`, `/nguess`, `/restart`, and
  database-specific `/savegroup` tooling.

## ShizuMusic YouTube downloader/playback adaptation

Reference reviewed: `Badmunda05/ShizuMusic` at commit
`83def61f73de7efd8c19cf451cf2937886c74652`. Fiona adapts its documented
`GET /download` contract rather than copying ShizuMusic's whole Telegram bot:

- Configure `SHIZUMUSIC_API_URL` and `SHIZUMUSIC_API_KEY` privately. Legacy
  `API_URL`/`API_BASE`/`YT_API_URL` and `API_KEY`/`YT_API_KEY` aliases map to
  this provider, not Aoi Hosting's different API.
- Standard audio/video downloads and voice-chat playback try ShizuMusic first,
  cache validated media under `downloads/shizumusic/`, then fall back to the
  separate Aoi Hosting API (if configured) and Fiona's existing yt-dlp client
  fallback ladder.
- Playback uses the downloaded local file for stable voice-chat reads. Fiona
  retains direct yt-dlp URL resolution when no API file is available.
- ShizuMusic's endpoint only accepts `type=audio|video`, so Fiona keeps
  format-specific downloads on its existing yt-dlp path rather than silently
  ignoring the user's selected format.
- Credentials are not committed or logged. The downloader rejects text/JSON
  error responses and incomplete files before caching them.

## Videl1 / Videl0 keep-alive adaptation

Videl1's liveness/readiness separation and stale-heartbeat watchdog were
adapted to Fiona's standard-library health server. Videl0's low-rate public
self-ping pattern was also adapted safely: on Render, Fiona uses the platform's
`RENDER_EXTERNAL_URL` to request `/live` every five minutes by default. The
`/health` and `/ready` endpoints report startup, heartbeat freshness, Telegram
client states, and ping health; `/live` and `/ping` stay liveness probes during
startup or stale event-loop periods. The watchdog logs heartbeat and client
state transitions without force-restarting the bot. Self-pinging is best-effort
and does not replace an always-on service plan or override provider sleep limits.
