"""Render modern collector profile cards with a blurred user/favourite image."""

from __future__ import annotations

from html import unescape
from io import BytesIO

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


WIDTH, HEIGHT = 1200, 630
MAX_SOURCE_PIXELS = 20_000_000


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    # Pillow's bundled font keeps rendering portable in minimal containers.
    return ImageFont.load_default(size=size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = str(text or "Collector").replace("\n", " ").strip() or "Collector"
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-2].rstrip() + "…"
    return text


def _source_image(image_bytes: bytes | None) -> Image.Image | None:
    if not image_bytes:
        return None
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.width * source.height > MAX_SOURCE_PIXELS:
                return None
            source.seek(0)
            return source.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _blurred_backdrop(image_bytes: bytes | None) -> Image.Image:
    source = _source_image(image_bytes)
    if source is not None:
        backdrop = ImageOps.fit(source, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        backdrop = ImageEnhance.Color(backdrop).enhance(0.72)
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=26))
        backdrop = ImageEnhance.Brightness(backdrop).enhance(0.43)
        return backdrop.convert("RGBA")

    # No favorite image or Telegram avatar: use a restrained Fiona-purple gradient.
    backdrop = Image.new("RGB", (WIDTH, HEIGHT), "#171025")
    draw = ImageDraw.Draw(backdrop)
    for y in range(HEIGHT):
        blend = y / max(HEIGHT - 1, 1)
        draw.line((0, y, WIDTH, y), fill=(
            int(17 + 17 * blend), int(10 + 5 * blend), int(36 + 24 * blend)
        ))
    return backdrop.convert("RGBA")


def _featured_portrait(image_bytes: bytes | None, size: int = 292) -> Image.Image | None:
    source = _source_image(image_bytes)
    if source is None:
        return None
    portrait = ImageOps.fit(source, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((2, 2, size - 3, size - 3), fill=255)
    portrait.putalpha(mask)
    return portrait


def build_profile_card(stats: dict, featured_image: bytes | None = None) -> BytesIO:
    """Render stats and a crisp portrait over its blurred image as a PNG."""
    background = _blurred_backdrop(featured_image)
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (7, 5, 20, 62))
    image = Image.alpha_composite(background, veil)

    # Composite glass panels before drawing opaque text so values remain legible.
    glass = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glass_draw = ImageDraw.Draw(glass)
    glass_draw.rounded_rectangle(
        (48, 42, 810, 588), radius=34,
        fill=(12, 10, 28, 218), outline=(222, 181, 255, 145), width=2,
    )
    metric_left, metric_top, metric_width, gap = 82, 256, 207, 18
    for index in range(3):
        left = metric_left + index * (metric_width + gap)
        glass_draw.rounded_rectangle(
            (left, metric_top, left + metric_width, metric_top + 108), radius=18,
            fill=(255, 255, 255, 22), outline=(231, 206, 255, 75), width=1,
        )
    glass_draw.rounded_rectangle(
        (824, 438, 1163, 566), radius=22,
        fill=(14, 10, 29, 230), outline=(236, 190, 255, 155), width=2,
    )
    image = Image.alpha_composite(image, glass)
    draw = ImageDraw.Draw(image)

    draw.text((82, 70), "FIONA  /  COLLECTOR PROFILE", font=_font(23, True), fill="#e8d7ff")
    name = _fit_text(draw, unescape(str(stats.get("first_name", "Collector"))), _font(52, True), 665)
    draw.text((80, 116), name, font=_font(52, True), fill="#ffffff")

    username = str(stats.get("username") or "").strip().lstrip("@")
    identity = f"@{username}" if username else f"UID {stats.get('user_id', '—')}"
    rank = f"RANK  #{stats['rank']}" if stats.get("rank") else "RANK  UNRANKED"
    draw.text(
        (84, 190), _fit_text(draw, f"{identity}   ·   {rank}", _font(20), 670),
        font=_font(20), fill="#d8c8ea",
    )

    cards = (
        ("COLLECTION", f"{int(stats.get('unique_character_count', 0)):,} / {int(stats.get('total_characters', 0)):,}"),
        ("COINS", f"{int(stats.get('balance', 0)):,}"),
        ("TOKENS", f"{int(stats.get('tokens', 0)):,}"),
    )
    label_font, value_font = _font(16, True), _font(27, True)
    for index, (label, value) in enumerate(cards):
        left = metric_left + index * (metric_width + gap)
        draw.text((left + 16, metric_top + 15), label, font=label_font, fill="#d6b8f2")
        shown = _fit_text(draw, value, value_font, metric_width - 30)
        draw.text((left + 16, metric_top + 52), shown, font=value_font, fill="#ffffff")

    progress = max(0.0, min(100.0, float(stats.get("progress_percentage", 0.0))))
    draw.text((84, 408), "CATALOG PROGRESS", font=_font(17, True), fill="#e8d7ff")
    draw.text((694, 408), f"{progress:.1f}%", font=_font(17, True), fill="#ffffff", anchor="ra")
    bar_left, bar_top, bar_width, bar_height = 84, 444, 682, 15
    draw.rounded_rectangle(
        (bar_left, bar_top, bar_left + bar_width, bar_top + bar_height),
        radius=8, fill="#40334f",
    )
    if progress > 0:
        fill_width = max(bar_height, round(bar_width * progress / 100))
        draw.rounded_rectangle(
            (bar_left, bar_top, bar_left + fill_width, bar_top + bar_height),
            radius=8, fill="#d780ef",
        )

    draw.text(
        (84, 493), f"{int(stats.get('character_count', 0)):,} characters collected",
        font=_font(18), fill="#cbb9de",
    )
    draw.text(
        (430, 493),
        f"STREAK {int(stats.get('daily_streak', 0))}  ·  BEST {int(stats.get('best_daily_streak', 0))}",
        font=_font(15, True), fill="#e4b8ff",
    )

    portrait_size = 292
    portrait_left, portrait_top = 848, 112
    portrait = _featured_portrait(featured_image, portrait_size)
    draw.ellipse(
        (portrait_left - 9, portrait_top - 9,
         portrait_left + portrait_size + 9, portrait_top + portrait_size + 9),
        fill="#100c21", outline="#ecbeff", width=5,
    )
    if portrait is not None:
        image.alpha_composite(portrait, (portrait_left, portrait_top))
        draw = ImageDraw.Draw(image)
    else:
        draw.ellipse(
            (portrait_left, portrait_top, portrait_left + portrait_size, portrait_top + portrait_size),
            fill="#3d285b",
        )
        draw.text(
            (portrait_left + portrait_size // 2, portrait_top + portrait_size // 2),
            "✦", font=_font(94, True), fill="#f5d9ff", anchor="mm",
        )

    featured = stats.get("featured_character") or {}
    portrait_kind = stats.get("portrait_kind")
    if portrait_kind == "profile":
        heading = "PROFILE PHOTO"
    elif featured:
        heading = "FAVOURITE CHARACTER"
    else:
        heading = "FEATURE YOUR FAVOURITE"
    draw.text((848, 456), heading, font=_font(15, True), fill="#e4b8ff")
    if featured:
        featured_name = _fit_text(
            draw, unescape(str(featured.get("name") or "Unknown")), _font(22, True), 290
        )
        anime = _fit_text(
            draw, unescape(str(featured.get("anime") or "Your collection")), _font(16), 290
        )
        draw.text((848, 482), featured_name, font=_font(22, True), fill="#ffffff")
        draw.text((848, 517), anime, font=_font(16), fill="#d2c0e5")
    else:
        draw.text((848, 493), "Set with /fav <character ID>", font=_font(16), fill="#d2c0e5")

    output = BytesIO()
    output.name = "fiona-profile.png"
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
