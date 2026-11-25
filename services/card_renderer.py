"""Renders the now-playing picture (1280x720 JPEG): blurred artwork background, sharp rounded cover, title,
artist, kind badge, length and a footer. Persian / Arabic text is shaped right-to-left by Pillow + libraqm."""

import os
import re
import glob
import asyncio
import logging
from dataclasses import dataclass

log = logging.getLogger("vpb.card")
W, H = 1280, 720
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
FONT_DIRS = ["/usr/share/fonts/truetype/vazirmatn", os.path.abspath("assets/fonts"), "/usr/share/fonts/truetype/dejavu"]


@dataclass(frozen=True)
class CardInfo:
    title: str
    artist: str | None
    badge: str          # AUDIO / VIDEO / LYRICS / LIVE
    length: str | None  # "04:56"
    footer: str         # group name · bot name


def _font_file(weight: str) -> str | None:
    for folder in FONT_DIRS:
        for pattern in (f"*-{weight}.ttf", f"*{weight}*.ttf", "*.ttf"):
            found = sorted(glob.glob(os.path.join(folder, pattern)))
            if found:
                return found[0]
    return None


class CardRenderer:
    def __init__(self):
        try:
            from PIL import features
            self.available = True
            self.raqm = features.check("raqm")
        except ImportError:
            self.available, self.raqm = False, False
            log.warning("Pillow is not installed: the card uses the plain artwork")
        self.fonts = {w: _font_file(w) for w in ("Bold", "SemiBold", "Regular")}

    async def render(self, info: CardInfo, cover: str | None, dest: str) -> str | None:
        """Path of the rendered JPEG, or None (then the caller shows the plain artwork)."""
        if not self.available:
            return None
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:     # same media + kind in this chat: same picture
            return dest
        try:
            return await asyncio.to_thread(self._render, info, cover, dest)
        except Exception as e:
            log.warning("card rendering failed: %s: %s", type(e).__name__, e)
            return None

    # ------------------------------------------------------------------------------------------------- drawing

    def _font(self, weight: str, size: int):
        from PIL import ImageFont
        path = self.fonts.get(weight) or self.fonts.get("Regular")
        if not path:
            return ImageFont.load_default(size)
        layout = ImageFont.Layout.RAQM if self.raqm else ImageFont.Layout.BASIC
        return ImageFont.truetype(path, size, layout_engine=layout)

    @staticmethod
    def _fit_lines(draw, text: str, font, width: int, max_lines: int) -> list[str]:
        words, lines, line = text.split(), [], ""
        for word in words:
            test = f"{line} {word}".strip()
            if draw.textlength(test, font=font) <= width:
                line = test
                continue
            if line:
                lines.append(line)
            line = word
            if len(lines) == max_lines:
                break
        if line and len(lines) < max_lines:
            lines.append(line)
        if not lines:
            return [""]
        used = " ".join(lines)
        if len(used) < len(" ".join(words)):                    # cut: end the last line with …
            last = lines[-1]
            while last and draw.textlength(last + "…", font=font) > width:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"
        return lines

    def _render(self, info: CardInfo, cover: str | None, dest: str) -> str:
        from PIL import Image, ImageDraw, ImageFilter
        art = None
        if cover and os.path.isfile(cover):
            try:
                art = Image.open(cover).convert("RGB")
            except Exception:
                art = None

        if art:   # background: the artwork, cover-scaled, blurred and darkened
            scale = max(W / art.width, H / art.height)
            bg = art.resize((int(art.width * scale) + 1, int(art.height * scale) + 1))
            left, top = (bg.width - W) // 2, (bg.height - H) // 2
            bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(30))
            bg = Image.blend(bg, Image.new("RGB", (W, H), (8, 10, 20)), 0.55)
        else:     # no artwork: dark gradient
            bg = Image.new("RGB", (W, H))
            px = ImageDraw.Draw(bg)
            for y in range(H):
                t = y / H
                px.line([(0, y), (W, y)], fill=(int(15 + 25 * t), int(23 + 10 * t), int(42 + 40 * t)))
        canvas = bg.convert("RGBA")

        text_left = 80
        if art:   # sharp square cover with rounded corners and a soft shadow
            size, x0, y0, radius = 440, 80, 140, 36
            square = min(art.width, art.height)
            crop = art.crop(((art.width - square) // 2, (art.height - square) // 2,
                             (art.width + square) // 2, (art.height + square) // 2)).resize((size, size))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius, fill=255)
            shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rounded_rectangle((x0 + 10, y0 + 18, x0 + size + 10, y0 + size + 18), radius, fill=(0, 0, 0, 150))
            canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(18)))
            canvas.paste(crop, (x0, y0), mask)
            text_left = x0 + size + 70

        draw = ImageDraw.Draw(canvas)
        right, width = W - 80, W - 80 - text_left

        def put(y, text, font, fill):
            rtl = bool(_ARABIC.search(text))
            x, anchor = (right, "ra") if rtl else (text_left, "la")
            draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

        # badge
        badge_font = self._font("SemiBold", 30)
        bw = draw.textlength(info.badge, font=badge_font) + 44
        colors = {"LIVE": (220, 38, 38, 235), "LYRICS": (147, 51, 234, 235), "VIDEO": (37, 99, 235, 235)}
        draw.rounded_rectangle((text_left, 150, text_left + bw, 200), 25, fill=colors.get(info.badge, (16, 185, 129, 235)))
        draw.text((text_left + 22, 175), info.badge, font=badge_font, fill="white", anchor="lm")

        y = 240
        title_font = self._font("Bold", 64)
        for line in self._fit_lines(draw, info.title, title_font, width, 2):
            put(y, line, title_font, (255, 255, 255))
            y += 82
        if info.artist:
            artist_font = self._font("Regular", 42)
            put(y + 10, self._fit_lines(draw, info.artist, artist_font, width, 1)[0], artist_font, (210, 214, 222))
            y += 70
        if info.length:
            put(y + 30, info.length, self._font("SemiBold", 36), (190, 196, 210))

        footer_font = self._font("Regular", 28)
        draw.line([(80, 630), (W - 80, 630)], fill=(255, 255, 255, 60), width=2)
        draw.text((80, 668), self._fit_lines(draw, info.footer, footer_font, W - 160, 1)[0], font=footer_font,
                  fill=(200, 204, 214), anchor="lm")

        canvas.convert("RGB").save(dest, "JPEG", quality=88, optimize=True)
        return dest
