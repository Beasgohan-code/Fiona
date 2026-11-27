"""Generate a compact, brand-styled image card for collector profiles."""

from __future__ import annotations

from html import unescape
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1200, 630


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    # Pillow's bundled default font is always available and keeps this portable
    # across containers where system font packages differ.
    return ImageFont.load_default(size=size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = str(text or "Collector").replace("\n", " ").strip() or "Collector"
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-2].rstrip() + "…"
    return text


def build_profile_card(stats: dict) -> BytesIO:
    """Render profile stats to an in-memory PNG suitable for Pyrogram reply_photo."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "#100d1d")
    draw = ImageDraw.Draw(image)

    # Richgram-inspired violet/rose backdrop and soft accent rails.
    for y in range(HEIGHT):
        blend = y / max(1, HEIGHT - 1)
        color = (
            int(20 + 22 * blend),
            int(13 + 5 * blend),
            int(42 + 27 * blend),
        )
        draw.line((0, y, WIDTH, y), fill=color)
    draw.text((88, 70), "FIONA  /  COLLECTOR PROFILE", font=_font(29, True), fill="#e8d7ff")

    first_name = _fit_text(draw, unescape(str(stats.get("first_name", "Collector"))), _font(65, True), 1020)
    draw.text((86, 130), first_name, font=_font(65, True), fill="#ffffff")
    draw.text(
        (90, 220),
        f"USER  {stats.get('user_id', '—')}     •     GLOBAL RANK  "
        f"{('#' + str(stats['rank'])) if stats.get('rank') else 'UNRANKED'}",
        font=_font(23),
        fill="#c8b7df",
    )

    cards = (
        ("WAIFUS", f"{int(stats.get('character_count', 0)):,}"),
        ("UNIQUE", f"{int(stats.get('unique_character_count', 0)):,} / {int(stats.get('total_characters', 0)):,}"),
        ("COINS", f"{int(stats.get('balance', 0)):,}"),
        ("TOKENS", f"{int(stats.get('tokens', 0)):,}"),
    )
    metric_left, metric_top, gap, metric_width = 90, 310, 28, 245
    label_font, value_font = _font(19, True), _font(31, True)
    for index, (label, value) in enumerate(cards):
        left = metric_left + index * (metric_width + gap)
        draw.text((left, metric_top), label, font=label_font, fill="#d3afea")
        shown = _fit_text(draw, value, value_font, metric_width)
        draw.text((left, metric_top + 42), shown, font=value_font, fill="#ffffff")

    progress = max(0.0, min(100.0, float(stats.get("progress_percentage", 0.0))))
    draw.text((90, 470), f"COLLECTION PROGRESS     {progress:.1f}%", font=_font(20, True), fill="#e8d7ff")
    bar_left, bar_top, bar_width, bar_height = 90, 510, 1020, 16
    draw.rounded_rectangle((bar_left, bar_top, bar_left + bar_width, bar_top + bar_height), radius=9, fill="#40334f")
    if progress:
        fill_width = max(bar_height, round(bar_width * progress / 100))
        draw.rounded_rectangle((bar_left, bar_top, bar_left + fill_width, bar_top + bar_height), radius=9, fill="#d780ef")

    output = BytesIO()
    output.name = "fiona-profile.png"
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
