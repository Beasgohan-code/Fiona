
#

import asyncio
import html

from py_yt import VideosSearch
from pyrogram import enums
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineQueryResultPhoto,
)

from config import BANNED_USERS
from AoiMusic import app
from AoiMusic.utils.inlinequery import answer
from AoiMusic.utils.premium import link_btn


@app.on_inline_query(~BANNED_USERS)
async def inline_query_handler(client, query):
    text = query.query.strip().lower()
    # Character searches are routed to the collection inline bridge; answering
    # them here as YouTube results would race the collection response.
    if text.startswith(("collection.", "see.", "waifu ", "w ")):
        return
    answers = []
    if text.strip() == "":
        try:
            await client.answer_inline_query(query.id, results=answer, cache_time=10)
        except Exception:
            return
    else:
        # Inline results need the raw py_yt fields (channel link, view counts),
        # but a hung search must not leave the inline button spinning: cap it.
        a = VideosSearch(text, limit=20)
        try:
            result = (await asyncio.wait_for(a.next(), 15)).get("result") or []
        except asyncio.TimeoutError:
            try:
                return await client.answer_inline_query(query.id, results=answer, cache_time=10)
            except Exception:
                return
        for res in result[:15]:
            title = (res["title"]).title()
            duration = res["duration"]
            views = res["viewCount"]["short"]
            thumbnail = res["thumbnails"][0]["url"].split("?")[0]
            channellink = res["channel"]["link"]
            channel = res["channel"]["name"]
            link = res["link"]
            published = res.get("publishedTime") or "Unknown"
            description = f"{views} | {duration} Mins | {channel}  | {published}"
            buttons = InlineKeyboardMarkup(
                [
                    [
                        link_btn(
                            "🎥 ᴡᴀᴛᴄʜ ᴏɴ ʏᴏᴜᴛᴜʙᴇ",
                            url=link,
                            emoji="🎥",
                        )
                    ],
                ]
            )

            def esc(value):
                return html.escape(str(value))

            def esc_attr(value):
                return html.escape(str(value), quote=True)
            link_e = esc_attr(link)
            channellink_e = esc_attr(channellink)
            bot_e = (
                f"<a href='tg://user?id={int(app.id)}'>{esc(app.name)}</a>"
                if getattr(app, "id", None) is not None
                else esc(app.name)
            )
            searched_text = f"""
❇️<b>ᴛɪᴛʟᴇ:</b> <a href='{link_e}'>{esc(title)}</a>

⏳<b>ᴅᴜʀᴀᴛɪᴏɴ:</b> {esc(duration)} Mins
👀<b>ᴠɪᴇᴡs:</b> <code>{esc(views)}</code>
⏰<b>ᴘᴜʙʟɪsʜᴇᴅ ᴛɪᴍᴇ:</b> {esc(published)}
🎥<b>ᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ:</b> {esc(channel)}
📎<b>ᴄʜᴀɴɴᴇʟ ʟɪɴᴋ:</b> <a href='{channellink_e}'>ᴠɪsɪᴛ ғʀᴏᴍ ʜᴇʀᴇ</a>

<i>ʀᴇᴘʟʏ ᴡɪᴛʜ /play ᴏɴ ᴛʜɪs sᴇᴀʀᴄʜᴇᴅ ᴍᴇssᴀɢᴇ ᴛᴏ sᴛʀᴇᴀᴍ ɪᴛ ᴏɴ ᴠᴏɪᴄᴇᴄʜᴀᴛ.</i>

⚡️ <b>ɪɴʟɪɴᴇ sᴇᴀʀᴄʜ ʙʏ {bot_e}</b>"""
            answers.append(
                InlineQueryResultPhoto(
                    photo_url=thumbnail,
                    title=title,
                    thumb_url=thumbnail,
                    description=description,
                    caption=searched_text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=buttons,
                )
            )
        try:
            return await client.answer_inline_query(query.id, results=answers)
        except Exception:
            return
