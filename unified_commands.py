"""Curated Telegram command menus for the combined Fiona bot.

Keeping these lists centralized prevents commands from being advertised twice
when music and collection features share one bot token.
"""

PRIVATE_COMMANDS = (
    ("start", "Open Fiona home"),
    ("help", "Browse music, moderation, and collection help"),
    ("ping", "Check bot and voice-service status"),
    ("play", "Play audio in a voice chat"),
    ("queue", "Show the current queue"),
    ("song", "Find or download a song"),
    ("lyrics", "Look up lyrics"),
    ("waifu", "Open the character collection panel"),
    ("harem", "View your collected characters"),
    ("profile", "View a collector profile"),
    ("hpin", "Pin a character in your collection"),
    ("hunpin", "Unpin a collection character"),
    ("pinlist", "List pinned characters"),
    ("guess", "Catch the current character"),
    ("hunt", "Hunt for a character"),
    ("balance", "Check your collection balance"),
    ("dailygift", "Claim your daily reward"),
    ("weekly", "Claim your weekly reward"),
    ("shop", "Browse collection shop"),
    ("refer", "Invite friends and view referral rewards"),
    ("wlang", "Set collection language"),
    ("lang", "Set music language"),
    ("privacy", "Read the privacy information"),
)

GROUP_COMMANDS = (
    ("start", "Show group start panel"),
    ("help", "Browse all bot features"),
    ("ping", "Check bot and voice-service status"),
    ("play", "Play audio in a voice chat"),
    ("vplay", "Play video in a voice chat"),
    ("queue", "Show the current queue"),
    ("skip", "Skip the current track"),
    ("pause", "Pause voice-chat playback"),
    ("resume", "Resume voice-chat playback"),
    ("end", "Stop playback"),
    ("waifu", "Open the character collection panel"),
    ("guess", "Catch the current character"),
    ("hunt", "Hunt for a character"),
    ("harem", "View your collected characters"),
    ("lang", "Set music language"),
    ("wlang", "Set collection language"),
    ("settings", "Open group playback settings"),
    ("rules", "Show group rules"),
    ("notes", "List saved notes"),
    ("report", "Report a message to admins"),
    ("admins", "List group admins"),
    ("id", "Show a user or chat ID"),
    ("info", "Show user or chat info"),
)

ADMIN_COMMANDS = (
    ("promote", "Promote a group admin"),
    ("demote", "Demote a group admin"),
    ("ban", "Ban a user"),
    ("tban", "Temporarily ban a user"),
    ("unban", "Unban a user"),
    ("kick", "Remove a user from the group"),
    ("mute", "Mute a user or voice chat"),
    ("tmute", "Temporarily mute a user"),
    ("unmute", "Unmute a user or voice chat"),
    ("warn", "Warn a user"),
    ("warns", "Check user warnings"),
    ("resetwarns", "Reset user warnings"),
    ("pin", "Pin a group message"),
    ("unpin", "Unpin a group message"),
    ("purge", "Delete a range of messages"),
    ("lock", "Lock a group content type"),
    ("unlock", "Unlock a group content type"),
    ("setrules", "Set group rules"),
    ("welcome", "Configure welcome messages"),
    ("setwelcome", "Set the welcome template"),
    ("setlog", "Set the moderation log chat"),
)


def validate_command_list(commands: tuple[tuple[str, str], ...]) -> None:
    names = [name for name, _ in commands]
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"duplicate BotFather command names: {', '.join(duplicates)}")
    for name, description in commands:
        if not name.isascii() or not name.replace("_", "").isalnum() or len(name) > 32:
            raise ValueError(f"invalid Telegram command name: {name}")
        if not description or len(description) > 256:
            raise ValueError(f"invalid command description for /{name}")


for _commands in (PRIVATE_COMMANDS, GROUP_COMMANDS, ADMIN_COMMANDS):
    validate_command_list(_commands)
