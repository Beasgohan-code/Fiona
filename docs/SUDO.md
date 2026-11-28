# Sudo & staff powers in Fiona

Fiona has **two separate sudo systems** (one in the waifu collector package,
one in the music package). They do not share state. This page explains both.

---

## 1. Waifu (character collection) — MongoDB-backed powers

### Who is allowed?

| Check | What it grants |
| --- | --- |
| `OWNER_ID` env var | Full bypass: every `require_power()` gate and every owner check. |
| `EXTRA_ADMIN_ID` env var (optional) | Same bypass a second account. `0`/unset disables it. |
| `SUDO` env var (static, comma-separated IDs) | **Not** a power bypass. Only gates `/list`, `/groups` and `/findani`. |
| `sudo_users` Mongo collection | The real sudo system. `require_power('<power>')` checks this collection's per-user `powers` map after the owner bypass. |

### Managing sudo users

All four commands require the `VIP` power (or `OWNER_ID`):

- **`/saddsudo`** — *reply* to a user's message. Adds them as a sudo with only
  the `add_character` power. Nothing else is granted.
- **`/sremovesudo`** — *reply* to a message or pass a user ID
  (`/sremovesudo 123456789`). Deletes their sudo record entirely.
- **`/seditsudo`** — *reply* to a user's message. Opens a keyboard with one
  Enabled/Disabled toggle per power (add_character, delete_character,
  update_character, approve_request, approve_inventory_request, VIP).
- **`/waifusudolist`** — lists all sudo users with t.me links. **Owner only**,
  not even VIP.

### What each power unlocks

| Power | Grants |
| --- | --- |
| `add_character` | `/add`, `/gupload`, `/find`, approval/cancellation of `/addchar` user submissions (the Approve/Cancel buttons) |
| `delete_character` | `/deletechar`, `/gdelete` (remove a character and purge it from collections) |
| `update_character` | `/update`, `/gupdate <id> <field> <value>`, `/maxupdate` (edit character data/image) |
| `approve_request` | Declared in the schema; **no handler currently enforces it** (reserved for future use) |
| `approve_inventory_request` | Declared in the schema; **no handler currently enforces it** (reserved for future use) |
| `VIP` | `/saddsudo`, `/sremovesudo`, `/seditsudo`, `/backup`, `/backupstatus`, `/listbackups`, `/blocklist`, `/removeblocklist`, `/addblocklistgc`, `/removeblocklistgc`, `/blocklistgc`, `/cgen`, `/kill`, `/add <user-id> <amount>` (economy), `/transfer`, `/backtransfer`, `/rdelete` |

Powers are **independent** — VIP does *not* imply `add_character`, and
`add_character` does not imply VIP. Toggle each one with `/seditsudo`.

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
   replying to an image; a sudo with `add_character` taps **Approve** on the
   review card and the character is inserted with a fresh ID.

Prerequisites for uploads: `CHARA_CHANNEL_ID` (or `GLOG`) must be set and the
bot must be able to post there, and `IMGBB_API_KEYS` must be configured for
ImgBB uploads (Catbox needs no key).

---

## 2. Music (voice chat) — MongoDB `sudoers` collection

The music package does **not** use the `sudo_users` collection and has **no
`/addsudo` command**. Its sudo set is:

1. `OWNER_ID` from the music config (env) — always included.
2. The `sudoers` Mongo document `{"sudo": "sudo"}` → `{"sudoers": [id, ...]}`.
   At boot the bot merges `OWNER_ID` into this document, and every id in it
   becomes a music sudoer.

There is **no in-bot command** to add or remove music sudoers — to grant one,
edit that document in MongoDB directly (or add the person via the waifu side
and they still won't get music powers — the two systems are separate).

Music sudoers can run the music admin commands (e.g. `/globalban`,
`/blacklistchat`, `/auth`, `/autoend`, `/sudoers` …), i.e. the handlers
decorated with the `SUDOERS` filter.

---

## Quick answer

> “Sudo can add characters?”

**Yes.** In the waifu collector: `/saddsudo` the user (or `/seditsudo` → toggle
`add_character`), then they can `/add`, `/gupload` and approve `/addchar`
submissions. Plain `VIP` alone is *not* enough — the `add_character` power is
required. In the music package, sudo status doesn't grant character commands at
all — that's a Fiona-collector concept.
