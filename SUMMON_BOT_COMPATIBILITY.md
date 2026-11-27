# Summon-bot feature map for Fiona

Source inspected with the user's permission: `Beasgohan-code/Summon-bot` at
`504fe3635df2024e3f7ee901db91ab1e676b054a`. Fiona stays a single Pyrogram /
Mongo-backed combined bot; Summon-bot's standalone PTB handlers and SQL schema
are not copied wholesale.

## Available in Fiona

| Summon-bot command/feature | Fiona command or equivalent |
| --- | --- |
| `/start`, `/ping`, `/help`, `/menu`, `/commands` | `/start`, `/ping`, `/help`, `/menu`, `/commands` |
| `/balance`, `/bal`, `/daily` | `/balance`, `/bal`, `/daily` and `/dailygift` |
| `/spin` | `/spin` — Fiona-sized daily coin rewards; one atomic 24-hour claim per user |
| `/collection`, `/harem`, `/claimlist` | `/harem`, `/collection`, `/claimlist` |
| `/check`, `/info` | `/check` |
| `/search`, `/find` | `/search`, `/sips` or the bot's inline search |
| `/summon`, `/guess` | `/summon`, `/guess` and related Fiona catch aliases |
| `/fav`, `/pay`, `/shop`, `/gift`, `/hmode` | Same Fiona commands |
| `/top`, `/rank` | `/top`, `/rank` |
| `/stats`, `/server` | `/server` or `/st` for community totals; `/stats` remains the music statistics command |
| `/profile`, `/hstats`, `/me` | `/profile`, `/hstats`, `/me` |
| `/achievements`, `/ach`, `/badges` | `/achievements` and aliases; milestones are derived from Fiona's Mongo user data |
| Rarity catalog | `/rarity` and `/rarities`; reads every rarity currently present in Fiona's character catalog, rather than hard-coding a separate 18-rarity list |
| `/claim`, `/hclaim`, `/redeem` | Fiona's `/claim`, `/hclaim`, `/redeem` |
| `/transfer`, `/addchar`, `/update`, `/reupload` | Fiona's `/transfer`, `/addchar`, `/gupdate`, `/reupload` |
| `/ban`, `/unban`, `/warn` | Existing Fiona group moderation commands |
| `/broadcast` | Owner/Sudo-only `/waifubcast` and `/waifubroadcast` |
| `/owner`, `/panel` | Private, `OWNER_ID`-gated `/owner` overview and `/panel` alias; existing restricted admin commands remain separately protected |

The command menu and `/help` describe the supported commands. Fiona's music
`/stats` already exists, so the collector profile intentionally uses
`/profile`, `/hstats`, and `/me` rather than registering a conflicting `/stats`.

## Not copied as separate commands

These features need Summon-bot's SQL tables, market state, callback workflows,
or semantics that Fiona does not currently have. They are not safe to attach as
thin aliases to unrelated Fiona commands:

- `/market`, `/inv`, `/inventory`, `/sell`, `/sellchar`, auctions, `/bomb`,
  `/steal`, and `/pinfo` (no equivalent marketplace/inventory model).
- `/streak` and streak-dependent achievements (Fiona's daily reward does not
  yet maintain a durable consecutive-day streak).
- `/setclaim`, `/chance`, `/chancelist`, `/checkspawn`, `/changetime`, and
  `/spawn` admin controls (Fiona uses its existing spawn and cooldown settings).
- `/give`, `/givemoney`, `/rmmoney`, `/removeall`, `/claimlist`, and claim-code
  administration beyond Fiona's existing `/add`, `/kill`, `/transfer`, `/cgen`,
  and `/redeem` flows.
- `/font`/`/style`, `/premium`/`/unpremium`, `/nguess`, `/restart`, and
  database-specific `/savegroup` tooling.

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
