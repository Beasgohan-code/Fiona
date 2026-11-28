# Sudo & staff powers in Fiona

Fiona has **two separate sudo systems** (one in the waifu collector package,
one in the music package). They do not share state. This page explains both.

---

## 1. Waifu (character collection) — MongoDB-backed powers

### Who is allowed?

| Check | What it grants |
| --- | --- |
| `OWNER_ID` env var | Full bypass: every `require_power()` gate and every owner check. |
| `EXTRA_ADMIN_ID` env var (optional) | Same bypass for a second account. `0`/unset disables it. |
| `SUDO` env var (static, comma-separated IDs) | **Not** a power bypass. Only gates `/list`, `/groups` and `/findani`. |
| `sudo_users` Mongo collection | The real sudo system. `require_power('<power>')` checks each user's `powers` map after the owner bypass. |

### Managing sudo users

All four commands require the `VIP` power (or `OWNER_ID`):

- **`/saddsudo`** — *reply* to a user's message. Adds them as a sudo with only
  the `add_character` power. Nothing else is granted.
- **`/sremovesudo`** — *reply* to a message or pass a user ID
  (`/sremovesudo 123456789`). Deletes their sudo record entirely.
- **`/seditsudo`** — *reply* to a user's message. Opens a keyboard with one
  Enabled/Disabled toggle per power (add_character, delete_character,
  update_character, approve_request, approve_inventory_request, VIP).
- **`/waifusudolist`** — owner-only; lists every sudo user with their enabled
  powers. (The music package owns the name `/sudolist` — it lists music
  sudoers, so Fiona keeps this one prefixed to avoid a command collision in
  the merged bot.)

### What each power unlocks

| Power | Grants |
| --- | --- |
| `add_character` | `/add`, `/gupload`, `/find`, and the Approve/Cancel buttons on `/addchar` user submissions |
| `approve_request` | The Approve/Cancel buttons on `/addchar` user submissions (works as an **alternative** to `add_character`, so you can hand out approval rights without full upload rights) |
| `delete_character` | `/deletechar`, `/gdelete` (remove a character and purge it from collections) |
| `update_character` | `/update`, `/gupdate <id> <field> <value>`, `/maxupdate` (edit character data/image) |
| `approve_inventory_request` | Declared in the schema; **no handler enforces it yet** (reserved — there is no inventory-request flow in the codebase) |
| `VIP` | `/saddsudo`, `/sremovesudo`, `/seditsudo`, `/backup`, `/backupstatus`, `/listbackups`, `/blocklist`, `/removeblocklist`, `/addblocklistgc`, `/removeblocklistgc`, `/blocklistgc`, `/cgen`, `/kill`, `/add <user-id> <amount>` (economy), `/transfer`, `/backtransfer`, `/rdelete` |

Powers are **independent** — VIP does *not* imply `add_character`, and
`add_character` does not imply VIP. Toggle each one with `/seditsudo`.
`require_power` also accepts a list of powers and grants access when the
user holds **any** of them — that is how the submission-review buttons accept
either `add_character` or `approve_request`.

### Can a sudo add characters? Yes — with `add_character`

1. **One-shot from a URL:**
   `/add <name> <anime> <rarity-id> <image-url>`
   (e.g. `/add Muzan-Kibutsuji Demon-Slayer 16 https://i.ibb.co/xyz/muzan.jpg`).
   The image must be a Catbox/ImgBB-style HTTPS URL.
2. **Interactive upload from a photo:**
   Reply to a photo (or image document) with
   `/gupload <name> <anime> <rarity-id>` — you get an ImgBB/Catbox picker;
   the image is re-hosted and the character is posted to the character
   channel. `/gupload`, `/u` and `/upload` are the same command.
3. **Check the next free ID:** `/find` (and `/findani <query>` for the static
   `SUDO` list, owner tooling).
4. **Approving community submissions:** Any user can `/addchar <name> <anime>`
   replying to an image; a staff member with `add_character` **or**
   `approve_request` taps **Approve** on the review card and the character is
   inserted with a fresh ID.

Prerequisites for uploads: `CHARA_CHANNEL_ID` (or `GLOG`) must be set and the
bot must be able to post there, and `IMGBB_API_KEYS` must be configured for
ImgBB uploads (Catbox needs no key).

---

## 2. Music (voice chat) — MongoDB `sudoers` collection

The music package manages sudoers via bot commands, separate from the waifu
power system:

- **`/addsudo`** (owner only) — *reply* to a message or pass a username/ID;
  adds the user to the `sudoers` Mongo document and to the in-memory `SUDOERS`
  set immediately.
- **`/delsudo`** (owner only) — same form; removes the user from the document
  and the set.

Requires `MONGO_DB_URI` to be set; without it the commands refuse (the Aoi
production database won't accept sudo edits). At boot, `OWNER_ID` is merged
into the same `sudoers` document, so music sudoers persist across restarts.

Music sudoers can run the music admin commands (e.g. `/globalban`,
`/blacklistchat`, `/auth`, `/lock`/`/unlock`-style moderation, `/autoend`,
`/videolimit`, … — the handlers decorated with the `SUDOERS` filter).
There is also `/dev` (development tools), which is disabled in the merged
bot launcher.

> Music sudo grants **no** waifu/collector powers, and vice versa. If you want
> someone to moderate voice chats but not add characters, use `/addsudo`; if
> they should only approve character submissions, use `/saddsudo` +
> `/seditsudo` with `approve_request` only.

---

## Quick answer

> “Sudo can add characters?”

**Yes.** In the waifu collector: `/saddsudo` the user (or `/seditsudo` → toggle
`add_character`), then they can `/add`, `/gupload` and approve `/addchar`
submissions. If you want them to *only* approve submissions without upload
rights, grant `approve_request` instead. Plain `VIP` alone is *not* enough —
an actual add/upload power is required. The music package's separate sudo
system has nothing to do with character commands.
