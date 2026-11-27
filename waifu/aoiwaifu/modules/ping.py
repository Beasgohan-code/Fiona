from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
import time
from pyrogram import filters, enums
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from aoiwaifu import app, application, sudo_users, OWNER_ID
from aoiwaifu.unit.rich_ui import premium_text, rich_card, rich_table, reply_notice


START_TIME_PING = time.time()

def _format_uptime():
    sec = int(time.time() - START_TIME_PING)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m}m {s}s"

@app.on_message(filters.command("ping"))
async def pyro_ping(client, message):
    lang = await get_effective_lang(message)
    start_time = time.time()
    msg = await reply_notice(message, tr("🌸 <i>Pinging Fiona servers...</i>", lang), parse_mode=enums.ParseMode.HTML)
    elapsed_time = round((time.time() - start_time) * 1000, 2)
    response_text = rich_card(
        'Fiona service health',
        rich_table(
            ('CHECK', 'RESULT'),
            [
                ('Telegram response', f'<code>{elapsed_time:.2f} ms</code>'),
                ('Process uptime', f'<code>{_format_uptime()}</code>'),
                ('Bot status', '<b>Online</b>'),
            ],
        ),
        '📶',
    )
    await msg.edit_text(premium_text(tr(response_text, lang)), parse_mode=enums.ParseMode.HTML)

async def ping(update: Update, context: CallbackContext) -> None:
    lang = await get_effective_lang(update)
    start_time = time.time()
    message = await reply_notice(update.message, tr("🌸 <i>Pinging Fiona servers...</i>", lang), parse_mode="HTML")
    elapsed_time = round((time.time() - start_time) * 1000, 2)
    response_text = rich_card(
        'Fiona service health',
        rich_table(
            ('CHECK', 'RESULT'),
            [
                ('Telegram response', f'<code>{elapsed_time:.2f} ms</code>'),
                ('Process uptime', f'<code>{_format_uptime()}</code>'),
                ('Bot status', '<b>Online</b>'),
            ],
        ),
        '📶',
    )
    await message.edit_text(premium_text(tr(response_text, lang)), parse_mode="HTML")

application.add_handler(CommandHandler("ping", ping))
