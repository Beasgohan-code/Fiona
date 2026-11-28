#
#  Fiona Music - Atmospheric, cover-derived now-playing poster generator.
#
#  Pillow renders an original record-sleeve layout with blurred cover art,
#  fitted track metadata, requester details, and a decorative waveform. Live
#  playback progress and controls remain in the Richgram message itself.
#

import asyncio
import base64
import colorsys
import hashlib
import html as _html
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from py_yt import VideosSearch

from AoiMusic.utils.rich_msg import url_ok

LOGGER = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_ASSETS = _ROOT / "assets"
_BASE_IMG = _ASSETS / "now_playing_base.png"
_HTML_TPL = _ASSETS / "now_playing_template.html"
_FONT_BOLD = _ASSETS / "font.ttf"
_FONT_REG = _ASSETS / "font2.ttf"
_CACHE_DIR = _ROOT / "cache"
_BOT_AVATAR_CACHE = _CACHE_DIR / "bot_avatar.jpg"

_CANVAS_W = 1280
_CANVAS_H = 720
_RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
_MAX_CACHE_FILES = 30
_bot_avatar_checked = False

# Persistent Playwright browser singleton for fast, low-memory HTML renders
_PW_LOCK = asyncio.Lock()
_PW_INSTANCE = None
_PW_BROWSER = None


def normalize_fancy_telegram_name(text: str, max_len: int = 24) -> str:
    """Normalize stylized Unicode Telegram names/titles so fonts never show tofu boxes."""
    if not text:
        return "Unknown"
    raw = re.sub(r"<[^>]+>", "", str(text))
    norm = unicodedata.normalize("NFKD", raw)
    # Keep printable ASCII + common Latin/Indic characters, drop broken combining/private marks
    cleaned = "".join(
        ch for ch in norm
        if (32 <= ord(ch) <= 126) or (0x0900 <= ord(ch) <= 0x097F) or (0x00A0 <= ord(ch) <= 0x024F)
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "Unknown"
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


async def _pick(videoid):
    """maxresdefault when it exists, else the search thumbnail, else hqdefault."""
    direct = f"https://img.youtube.com/vi/{videoid}/maxresdefault.jpg"
    if await url_ok(direct):
        return direct
    fallback = f"https://img.youtube.com/vi/{videoid}/hqdefault.jpg"
    try:
        query = f"https://www.youtube.com/watch?v={videoid}"
        thumbnail = fallback
        results = VideosSearch(query, limit=1)
        for result in (await results.next())["result"]:
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return thumbnail
    except Exception:
        return fallback


async def gen_thumb(videoid, thumb=None):
    if thumb:
        return thumb
    return await _pick(videoid)


async def gen_qthumb(vidid, thumb=None):
    if thumb:
        return thumb
    return await _pick(vidid)


async def _ensure_bot_avatar() -> Optional[Path]:
    """Download and cache the bot's own Telegram profile photo once."""
    global _bot_avatar_checked
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _BOT_AVATAR_CACHE.exists() and _BOT_AVATAR_CACHE.stat().st_size > 512:
        return _BOT_AVATAR_CACHE
    if _bot_avatar_checked:
        return None
    _bot_avatar_checked = True
    try:
        from AoiMusic import app

        me = await app.get_me()
        photo = getattr(me, "photo", None)
        file_id = getattr(photo, "big_file_id", None) or getattr(photo, "small_file_id", None)
        if file_id:
            dl = await app.download_media(file_id, file_name=str(_BOT_AVATAR_CACHE))
            if dl and os.path.exists(dl):
                return Path(dl)
    except Exception as exc:
        LOGGER.debug("Could not fetch bot profile photo for thumbnail: %s", exc)
    return None


async def _download_song_thumb(url: Optional[str], videoid: str) -> Optional[Path]:
    """Download the YouTube/song thumbnail into cache/."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    candidates = []
    if url and str(url).startswith(("http://", "https://")):
        candidates.append(str(url))
    if videoid and str(videoid) not in ("telegram", "soundcloud", "None") and "index_" not in str(videoid):
        candidates.append(f"https://i.ytimg.com/vi/{videoid}/hqdefault.jpg")

    dest = _CACHE_DIR / f"st_{hashlib.md5((str(videoid) + str(url)).encode()).hexdigest()[:10]}.jpg"
    if dest.exists() and dest.stat().st_size > 1024:
        return dest

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for u in candidates:
            try:
                resp = await client.get(u)
                if resp.status_code == 200 and len(resp.content) > 1024:
                    dest.write_bytes(resp.content)
                    return dest
            except Exception:
                continue
    return None


def _file_to_data_uri(path: Optional[Path], mime: str = "image/png") -> str:
    if not path or not path.exists():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def render_now_playing_html(
    title: str,
    artist: str,
    duration: str,
    requester: str,
    song_thumb_path: Optional[Path],
    bot_avatar_path: Optional[Path],
    elapsed: str = "00:00",
) -> str:
    """Populate assets/now_playing_template.html with dynamic song & bot data."""
    tpl = _HTML_TPL.read_text(encoding="utf-8")
    song_uri = _file_to_data_uri(song_thumb_path, "image/jpeg") or _file_to_data_uri(_BASE_IMG, "image/png")
    bot_uri = _file_to_data_uri(bot_avatar_path, "image/jpeg") or song_uri

    repls = {
        "{{BASE_IMG_URI}}": _file_to_data_uri(_BASE_IMG, "image/png"),
        "{{FONT_BOLD_URI}}": _file_to_data_uri(_FONT_BOLD, "font/ttf"),
        "{{FONT_REG_URI}}": _file_to_data_uri(_FONT_REG, "font/ttf"),
        "{{SONG_THUMB_URI}}": song_uri,
        "{{BOT_AVATAR_URI}}": bot_uri,
        "{{TITLE}}": _html.escape(title),
        "{{ARTIST}}": _html.escape(artist),
        "{{DURATION}}": _html.escape(duration),
        "{{REQUESTER}}": _html.escape(requester),
        "{{ELAPSED}}": _html.escape(elapsed),
    }
    for k, v in repls.items():
        tpl = tpl.replace(k, v)
    return tpl


# ---------------------------------------------------------------------------
#  HTML-to-PNG Render Chain: Playwright -> Chromium CLI -> Selenium
# ---------------------------------------------------------------------------

async def _render_with_playwright(html_content: str, output_path: str) -> bool:
    """Tier 1: Render HTML to PNG using a persistent Playwright Chromium instance."""
    global _PW_INSTANCE, _PW_BROWSER
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    page = None
    try:
        async with _PW_LOCK:
            if _PW_BROWSER is None or not _PW_BROWSER.is_connected():
                if _PW_INSTANCE is None:
                    _PW_INSTANCE = await async_playwright().start()
                _PW_BROWSER = await _PW_INSTANCE.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
            browser = _PW_BROWSER

        page = await browser.new_page(viewport={"width": _CANVAS_W, "height": _CANVAS_H})
        await page.set_content(html_content, wait_until="load", timeout=15000)
        await page.screenshot(path=output_path, type="png")
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 65536
    except Exception as exc:
        LOGGER.warning("Playwright thumbnail render failed: %s", exc)
        return False
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass


def _find_chromium_binary() -> Optional[str]:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        path = shutil.which(name)
        if path:
            return path
    return None


async def _render_with_chromium_cli(html_content: str, output_path: str) -> bool:
    """Tier 2: Render HTML to PNG directly via async headless Chromium CLI."""
    binary = _find_chromium_binary()
    if not binary:
        return False

    tmp_html = None
    tmp_profile = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
            tf.write(html_content)
            tmp_html = tf.name
        tmp_profile = tempfile.mkdtemp(prefix="thumb_chrome_")

        abs_out = os.path.abspath(output_path)
        cmd = [
            binary,
            "--headless=new",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={tmp_profile}",
            f"--window-size={_CANVAS_W},{_CANVAS_H}",
            f"--screenshot={abs_out}",
            f"file://{os.path.abspath(tmp_html)}",
        ]
        env = {**os.environ, "HOME": "/tmp", "TMPDIR": "/tmp"}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            LOGGER.warning("Headless Chromium CLI timed out.")
            return False

        if os.path.isfile(abs_out) and os.path.getsize(abs_out) > 65536:
            with Image.open(abs_out) as im:
                if im.size != (_CANVAS_W, _CANVAS_H):
                    im.crop((0, 0, min(im.width, _CANVAS_W), min(im.height, _CANVAS_H))).save(abs_out, "PNG")
            return True
        if stderr:
            LOGGER.debug("Headless Chromium CLI error: %s", stderr.decode(errors="ignore")[:300])
        return False
    except Exception as exc:
        LOGGER.debug("Chromium CLI render failed: %s", exc)
        return False
    finally:
        if tmp_html and os.path.exists(tmp_html):
            try:
                os.remove(tmp_html)
            except OSError:
                pass
        if tmp_profile and os.path.exists(tmp_profile):
            shutil.rmtree(tmp_profile, ignore_errors=True)


def _render_with_selenium_sync(html_content: str, output_path: str) -> bool:
    """Tier 3: Synchronous Selenium fallback executed in a worker thread."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        return False

    tmp_html = None
    driver = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
            tf.write(html_content)
            tmp_html = tf.name

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--hide-scrollbars")
        opts.add_argument(f"--window-size={_CANVAS_W},{_CANVAS_H}")

        driver = webdriver.Chrome(options=opts)
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": _CANVAS_W, "height": _CANVAS_H, "deviceScaleFactor": 1, "mobile": False},
        )
        driver.get(f"file://{os.path.abspath(tmp_html)}")
        abs_out = os.path.abspath(output_path)
        driver.save_screenshot(abs_out)
        return os.path.isfile(abs_out) and os.path.getsize(abs_out) > 65536
    except Exception as exc:
        LOGGER.debug("Selenium thumbnail render failed: %s", exc)
        return False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        if tmp_html and os.path.exists(tmp_html):
            try:
                os.remove(tmp_html)
            except OSError:
                pass


async def render_html_thumbnail(html_content: str, output_path: str) -> bool:
    """Render HTML string to PNG using Playwright -> Chromium CLI -> Selenium."""
    if await _render_with_playwright(html_content, output_path):
        return True
    if await _render_with_chromium_cli(html_content, output_path):
        return True
    if await asyncio.to_thread(_render_with_selenium_sync, html_content, output_path):
        return True
    return False


async def close_thumbnail_browser() -> None:
    """Graceful shutdown hook for closing persistent Playwright Chromium browser."""
    global _PW_INSTANCE, _PW_BROWSER
    async with _PW_LOCK:
        if _PW_BROWSER is not None:
            try:
                await _PW_BROWSER.close()
            except Exception:
                pass
            _PW_BROWSER = None
        if _PW_INSTANCE is not None:
            try:
                await _PW_INSTANCE.stop()
            except Exception:
                pass
            _PW_INSTANCE = None


# ---------------------------------------------------------------------------
#  Pillow poster renderer (browser-independent for consistent deployment output)
# ---------------------------------------------------------------------------

def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    except Exception:
        pass
    return ImageFont.load_default()


def _render_pillow_card(
    title: str,
    artist: str,
    duration: str,
    requester: str,
    song_thumb_path: Optional[Path],
    bot_avatar_path: Optional[Path],
    out_png: Path,
    elapsed: str = "00:00",
) -> Path:
    """Render Fiona's atmospheric sleeve-and-vinyl now-playing poster."""
    seed = f"{title}|{artist}|{requester}"
    source = None
    if song_thumb_path and song_thumb_path.exists():
        try:
            with Image.open(song_thumb_path) as image:
                if image.width >= 32 and image.height >= 32 and image.width * image.height <= 24_000_000:
                    source = ImageOps.exif_transpose(image).convert("RGB")
        except Exception:
            pass

    if source is None:
        digest = hashlib.sha256(seed.encode("utf-8", "replace")).digest()
        hue = int.from_bytes(digest[:2], "big") / 65535
        accent = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.7, 0.92))
        source = Image.new("RGB", (520, 520), tuple(int(c * 0.24) for c in accent))
        art_draw = ImageDraw.Draw(source, "RGBA")
        for i in range(9):
            x, y = digest[i] * 2, digest[9 + i] * 2
            radius = 35 + digest[18 + i] % 115
            art_draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*accent, 32))
    else:
        sample = source.convert("RGB").resize((1, 1))
        r, g, b = sample.getpixel((0, 0))
        hue, _, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        accent = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.74, 0.94))

    canvas = ImageOps.fit(source, (_CANVAS_W, _CANVAS_H), method=_RESAMPLE)
    canvas = canvas.filter(ImageFilter.GaussianBlur(32))
    canvas = ImageEnhance.Brightness(canvas).enhance(0.36).convert("RGBA")
    shade = Image.new("RGBA", (_CANVAS_W, _CANVAS_H), (8, 8, 17, 158))
    canvas = Image.alpha_composite(canvas, shade)
    glow = Image.new("RGBA", (_CANVAS_W, _CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((650, -300, 1450, 520), fill=(*accent, 45))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(85)))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Vinyl record peeking from behind framed album artwork.
    cover_size, cover_x, cover_y = 390, 92, 177
    disc_x, disc_y, disc_size = 248, cover_y - 8, 356
    draw.ellipse((disc_x, disc_y, disc_x + disc_size, disc_y + disc_size), fill=(5, 6, 12, 245))
    for inset, alpha in ((18, 32), (38, 25), (62, 20), (88, 15), (116, 12)):
        draw.ellipse((disc_x + inset, disc_y + inset, disc_x + disc_size - inset, disc_y + disc_size - inset),
                     outline=(*accent, alpha), width=2)
    center = disc_size // 2
    draw.ellipse((disc_x + center - 37, disc_y + center - 37, disc_x + center + 37, disc_y + center + 37), fill=(*accent, 225))
    draw.ellipse((disc_x + center - 8, disc_y + center - 8, disc_x + center + 8, disc_y + center + 8), fill=(12, 14, 22, 255))

    cover = ImageOps.fit(source, (cover_size, cover_size), method=_RESAMPLE)
    cover_mask = Image.new("L", (cover_size, cover_size), 0)
    ImageDraw.Draw(cover_mask).rounded_rectangle((0, 0, cover_size - 1, cover_size - 1), radius=24, fill=255)
    shadow = Image.new("RGBA", (cover_size + 30, cover_size + 30), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((14, 14, cover_size + 14, cover_size + 14), radius=28, fill=(0, 0, 0, 155))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)), (cover_x - 15, cover_y - 10))
    canvas.paste(cover.convert("RGBA"), (cover_x, cover_y), cover_mask)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((cover_x - 2, cover_y - 2, cover_x + cover_size + 2, cover_y + cover_size + 2),
                           radius=25, outline=(255, 255, 255, 75), width=2)

    def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        return _load_font(_FONT_BOLD if bold else _FONT_REG, size)

    # Brand header and legible, cleanly fitted track metadata.
    draw.rounded_rectangle((78, 66, 95, 83), radius=5, fill=(*accent, 255))
    draw.rounded_rectangle((101, 66, 108, 83), radius=3, fill=(255, 255, 255, 200))
    draw.text((124, 60), "FIONA  /  NOW PLAYING", font=font(20, True), fill=(246, 246, 251, 240))
    draw.text((650, 163), "NOW IN THE ROOM", font=font(16, True), fill=(*accent, 255))

    title_font = font(46, True)
    raw_title = str(title or "Untitled track")
    words = raw_title.split()
    title_lines = []
    current = ""
    clipped = False
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=title_font)[2] <= 560:
            current = candidate
        elif not current:
            current = word
            clipped = True
            break
        elif len(title_lines) < 1:
            title_lines.append(current)
            current = word
        else:
            clipped = True
            break
    if current:
        title_lines.append(current)
    if len(title_lines) > 2:
        title_lines = title_lines[:2]
        clipped = True
    if title_lines:
        last = title_lines[-1]
        while last and draw.textbbox((0, 0), last + ("…" if clipped else ""), font=title_font)[2] > 560:
            last = last[:-1]
            clipped = True
        title_lines[-1] = last.rstrip() + ("…" if clipped else "")
    title_y = 205
    for line in title_lines[:2]:
        draw.text((650, title_y), line, font=title_font, fill=(250, 250, 252, 255))
        title_y += 55
    artist_font = font(25)
    artist_text = str(artist or "Fiona Music")
    while artist_text and draw.textbbox((0, 0), artist_text + "…", font=artist_font)[2] > 550:
        artist_text = artist_text[:-1]
    if artist_text != str(artist or "Fiona Music"):
        artist_text = artist_text.rstrip() + "…"
    draw.text((652, 278 if len(title_lines) < 2 else 315), artist_text, font=artist_font, fill=(208, 211, 222, 240))

    def chip(x: int, top: int, label: str, width: int, color=None):
        draw.rounded_rectangle((x, top, x + width, top + 48), radius=17, fill=(12, 15, 25, 225), outline=(255, 255, 255, 65), width=1)
        if color:
            draw.ellipse((x + 15, top + 18, x + 25, top + 28), fill=(*color, 255))
            tx = x + 35
        else:
            tx = x + 17
        label_font = font(16, True)
        original_label = label
        while label and draw.textbbox((0, 0), label + "…", font=label_font)[2] > width - (tx - x) - 12:
            label = label[:-1]
        if label != original_label:
            label = label.rstrip() + "…"
        draw.text((tx, top + 10), label, font=label_font, fill=(239, 241, 247, 245))

    chip(650, 365, "AUDIO", 112, accent)
    chip(776, 365, str(duration or "LIVE").upper()[:20], 176, (239, 187, 92))
    draw.text((652, 440), "REQUESTED BY", font=font(13, True), fill=(160, 164, 180, 255))
    req_font = font(20, True)
    req = str(requester or "Music lover")
    while req and draw.textbbox((0, 0), req + "…", font=req_font)[2] > 550:
        req = req[:-1]
    if req != str(requester or "Music lover"):
        req = req.rstrip() + "…"
    draw.text((652, 465), req, font=req_font, fill=(242, 243, 248, 255))

    # Decorative, track-stable waveform; live elapsed time remains in Richgram controls.
    digest = hashlib.sha256(seed.encode("utf-8", "replace")).digest()
    wave_x, wave_y, bars = 652, 555, 46
    for index in range(bars):
        level = 12 + digest[index % len(digest)] % 45
        x = wave_x + index * 12
        draw.rounded_rectangle((x, wave_y - level // 2, x + 7, wave_y + level // 2), radius=3,
                               fill=(*accent, 190 if index < bars * 0.42 else 74))
    draw.text((652, 616), f"FIONA MUSIC  ·  {str(elapsed or '00:00')[:10]} / {str(duration or 'LIVE')[:10]}",
              font=font(12, True), fill=(172, 178, 194, 235))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_png, "PNG", optimize=True)
    return out_png


def _prune_thumb_cache() -> None:
    try:
        files = sorted(
            [p for p in _CACHE_DIR.glob("np_*.png")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in files[_MAX_CACHE_FILES:]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        pass


async def build_now_playing_card(
    videoid: str,
    title: str,
    duration: str,
    requester: str,
    artist: str = "AoiMusic",
    song_thumb: Optional[str] = None,
    elapsed: str = "00:00",
    bot_avatar_override: Optional[Path] = None,
) -> Optional[str]:
    """Generate Fiona's cover-art now-playing poster, with a thumbnail fallback."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    clean_title = normalize_fancy_telegram_name(title, max_len=180)
    clean_artist = normalize_fancy_telegram_name(artist or "Fiona Music", max_len=100)
    clean_req = normalize_fancy_telegram_name(requester or "Music lover", max_len=64)
    clean_dur = str(duration or "00:00").strip()[:10]
    clean_el = str(elapsed or "00:00").strip()[:10]

    # The sleeve uses the song art itself; avoid an unrelated bot-avatar API call.
    song_path = await _download_song_thumb(song_thumb, str(videoid or ""))
    bot_path = bot_avatar_override  # retained for callers of the legacy signature

    sig = hashlib.md5(
        f"{videoid}|{clean_title}|{clean_artist}|{clean_dur}|{clean_req}|{clean_el}".encode()
    ).hexdigest()[:12]
    out_png = _CACHE_DIR / f"np_{sig}.png"

    if out_png.is_file() and out_png.stat().st_size > 65536:
        return str(out_png)

    try:
        # Render one deterministic design across deployments; browsers are optional.
        await asyncio.to_thread(
            _render_pillow_card,
            clean_title,
            clean_artist,
            clean_dur,
            clean_req,
            song_path,
            bot_path,
            out_png,
            clean_el,
        )
        _prune_thumb_cache()
        return str(out_png)
    except Exception as exc:
        LOGGER.warning("build_now_playing_card failed: %s", exc)
        return song_thumb
