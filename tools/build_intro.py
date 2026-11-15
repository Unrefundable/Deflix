#!/usr/bin/env python3
"""Render the Deflix startup intro from tools/intro.json.

Writes, into extras/media/:
  deflix_intro_<name>.mp4   one per entry in "outputs" (silent audio track)
  deflix_splash.png         the still wordmark, for the "image" splash option

Everything about the look lives in tools/intro.json: the text, colour, size,
the bow of the wordmark and the timing of each phase. A look is a "style": a
function that draws one frame for a given time. Add a new one to STYLES and
select it with "style" in the config.

Needs Pillow (pip install pillow) and ffmpeg on PATH.

Usage:
  python3 tools/build_intro.py                  render the videos and splash
  python3 tools/build_intro.py --frame 3.0      write one preview frame (PNG)
  python3 tools/build_intro.py --sheet          write a contact sheet (PNG)
  options: --config PATH, --out PATH (for --frame/--sheet), --height N
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: pip install pillow")


ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "extras" / "media"
DEFAULT_CONFIG = Path(__file__).with_name("intro.json")
SUPERSAMPLE = 4  # glyphs are drawn this much larger, then scaled down


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def progress(t: float, start: float, end: float) -> float:
    """0 before start, 1 after end, linear in between."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp((t - start) / (end - start))


def ease_in_out(p: float) -> float:
    return p * p * (3 - 2 * p)


def ease_in(p: float) -> float:
    return p * p


def ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# --------------------------------------------------------------------------
# lettering
#
# The Bingie wordmark is hand-drawn, so the letters Deflix needs are drawn
# here in the same style: heavy strokes, square stems, rounded bowls. Shapes
# are in units of the cap height. Any character without a shape below is set
# in "fallback_font" (or every character, when "font" is given).
# --------------------------------------------------------------------------

STROKE = 0.225


def _glyph_canvas(width: float, px: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int, int]:
    w, h = max(1, round(width * px)), px
    img = Image.new("L", (w, h), 0)
    return img, ImageDraw.Draw(img), w, h


def _glyph_i(px: int) -> Image.Image:
    img, draw, w, h = _glyph_canvas(STROKE, px)
    draw.rectangle((0, 0, w, h), fill=255)
    return img


def _glyph_l(px: int) -> Image.Image:
    img, draw, w, h = _glyph_canvas(0.56, px)
    s = STROKE * px
    draw.rectangle((0, 0, s, h), fill=255)
    draw.rectangle((0, h - s, w, h), fill=255)
    return img


def _glyph_f(px: int) -> Image.Image:
    img, draw, w, h = _glyph_canvas(0.58, px)
    s = STROKE * px
    draw.rectangle((0, 0, s, h), fill=255)
    draw.rectangle((0, 0, w, s), fill=255)
    draw.rectangle((0, 0.41 * h, 0.86 * w, 0.41 * h + 0.9 * s), fill=255)
    return img


def _glyph_d(px: int) -> Image.Image:
    img, draw, w, h = _glyph_canvas(0.75, px)
    s = STROKE * px
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=0.36 * h, fill=255,
                           corners=(False, True, True, False))
    draw.rounded_rectangle((s, s, w - s, h - s), radius=0.14 * h, fill=0,
                           corners=(False, True, True, False))
    return img


def _glyph_e(px: int) -> Image.Image:
    img, draw, w, h = _glyph_canvas(0.60, px)
    s = STROKE * px
    draw.rectangle((0, 0, s, h), fill=255)
    draw.rectangle((0, 0, w, s), fill=255)
    draw.rectangle((0, 0.5 * h - 0.45 * s, 0.86 * w, 0.5 * h + 0.45 * s), fill=255)
    draw.rectangle((0, h - s, w, h), fill=255)
    return img


def _glyph_x(px: int) -> Image.Image:
    img, draw, w, h = _glyph_canvas(0.80, px)
    arm = STROKE * 1.3 * px
    draw.polygon(((0, 0), (arm, 0), (w, h), (w - arm, h)), fill=255)
    draw.polygon(((w, 0), (w - arm, 0), (0, h), (arm, h)), fill=255)
    return img


BUILTIN_GLYPHS = {"D": _glyph_d, "E": _glyph_e, "F": _glyph_f,
                  "L": _glyph_l, "I": _glyph_i, "X": _glyph_x}


def _font_glyph(char: str, font_path: Path, cap_px: int) -> Image.Image:
    """Render one character from a font file, scaled so capitals are cap_px tall."""
    probe = ImageFont.truetype(str(font_path), 1000)
    top, bottom = probe.getbbox("H")[1], probe.getbbox("H")[3]
    font = ImageFont.truetype(str(font_path), max(8, round(1000 * cap_px / (bottom - top))))
    cap_top = font.getbbox("H")[1]
    left, _, right, _ = font.getbbox(char)
    img = Image.new("L", (max(1, right - left), cap_px), 0)
    ImageDraw.Draw(img).text((-left, -cap_top), char, font=font, fill=255)
    return img


def letter_masks(config: dict, cap_px: int) -> list[Image.Image]:
    """One greyscale mask per character of config["text"], cap_px tall."""
    font = config.get("font")
    fallback = config.get("fallback_font")
    masks = []
    for char in config["text"]:
        if not font and char.upper() in BUILTIN_GLYPHS:
            big = BUILTIN_GLYPHS[char.upper()](cap_px * SUPERSAMPLE)
        else:
            path = font or fallback
            if not path:
                raise SystemExit(f'No shape for "{char}": set "font" or "fallback_font".')
            big = _font_glyph(char, ROOT / path, cap_px * SUPERSAMPLE)
        size = (max(1, round(big.width / SUPERSAMPLE)), cap_px)
        masks.append(big.resize(size, Image.LANCZOS))
    return masks


# --------------------------------------------------------------------------
# scene: the flat wordmark plus the tools styles use to animate it
# --------------------------------------------------------------------------

class Scene:
    """Geometry and drawing helpers for one output height.

    Styles draw letters onto a flat greyscale "band" (a full-width strip
    around the vertical centre), then call finish() to bow, zoom, colour and
    place it on a frame.
    """

    LIGHT = 8  # glow canvas is 1/8 of the frame size

    def __init__(self, config: dict, width: int, height: int):
        self.config = config
        self.width, self.height = width, height
        self.fps = config["fps"]
        self.duration = duration(config)
        self.frame_count = round(self.duration * self.fps) + 1
        self.cy = round(config.get("center_y", 0.5) * height)
        # glows are painted on a small canvas and scaled up, which blurs them for free
        self.light_size = (width // self.LIGHT, height // self.LIGHT)
        # a round spot of light: full in the centre, smoothly down to nothing at the rim
        n = 128
        self._spot = Image.new("L", (n, n))
        self._spot.putdata([
            round(255 * clamp(1 - math.hypot(i + 0.5 - n / 2, j + 0.5 - n / 2) / (n / 2)) ** 2)
            for j in range(n) for i in range(n)])
        self._cache: dict = {}
        self.color = hex_rgb(config["color"])
        self.background = hex_rgb(config["background"])

        self.cap = round(config["cap_height"] * height)
        self.letters = letter_masks(config, self.cap)
        gap = config["letter_gap"] * self.cap
        total = sum(m.width for m in self.letters) + gap * (len(self.letters) - 1)
        self.half_width = total / 2
        self.cx = width / 2
        # left edge of each letter when the wordmark is centred
        self.letter_x = []
        x = self.cx - total / 2
        for mask in self.letters:
            self.letter_x.append(x)
            x += mask.width + gap

        # the band is tall enough for the bow and the largest zoom
        self.band_h = 2 * round(self.cap * 1.6)
        self.band_top = round(config.get("center_y", 0.5) * height) - self.band_h // 2
        self.letter_top = (self.band_h - self.cap) // 2
        self._fields: dict[tuple[int, float], Image.Image] = {}

    # -- drawing letters ---------------------------------------------------

    def new_band(self) -> Image.Image:
        return Image.new("L", (self.width, self.band_h), 0)

    def letter_center(self, index: int) -> float:
        return self.letter_x[index] + self.letters[index].width / 2

    def _wipe_field(self, index: int, angle: float) -> Image.Image:
        """Greyscale ramp across a letter: 0 where the wipe ends, 255 where it starts."""
        key = (index, angle)
        if key not in self._fields:
            n = 48
            dx, dy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
            w, h = self.letters[index].size
            # project each sample point onto the wipe direction, in letter pixels
            proj = [((i + 0.5) / n * w) * dx + ((j + 0.5) / n * h) * dy
                    for j in range(n) for i in range(n)]
            low, high = min(proj), max(proj)
            small = Image.new("L", (n, n))
            small.putdata([round(255 * (p - low) / (high - low)) for p in proj])
            self._fields[key] = small.resize((w, h), Image.BICUBIC)
        return self._fields[key]

    def wiped(self, index: int, angle: float, amount: float, softness: float) -> Image.Image:
        """Letter mask with `amount` (0..1) of it wiped away.

        The wipe starts at the side the angle points to (0 = right, 90 = up)
        and travels the opposite way, with a soft edge `softness` wide.
        """
        mask = self.letters[index]
        if amount <= 0:
            return mask
        field = self._wipe_field(index, angle)
        edge = (1 + softness) * (1 - amount)  # ramp position of the soft edge
        soft = max(softness, 1e-3)
        lut = [round(255 * clamp((edge - v / 255) / soft)) for v in range(256)]
        return ImageChops.multiply(mask, field.point(lut))

    def draw_letter(self, band: Image.Image, mask: Image.Image, index: int, shift: float = 0.0) -> None:
        box = (round(self.letter_x[index] + shift), self.letter_top)
        band.paste(mask, box, mask)

    # -- finishing ---------------------------------------------------------

    def _bow(self, x: float) -> float:
        """Vertical stretch at screen position x: 1 in the centre, more at the edges."""
        bow = self.config["bow"]
        distance = abs(x - self.cx) / self.half_width
        return 1 + bow["amount"] * distance ** bow["power"]

    def warp(self, band: Image.Image, zoom: float = 1.0) -> Image.Image:
        """Apply the bow (taller towards the edges) and a zoom about the centre."""
        step = max(4, self.width // 480)
        cy = self.band_h / 2
        mesh = []
        for x0 in range(0, self.width, step):
            x1 = min(self.width, x0 + step)
            s0 = self.cx + (x0 - self.cx) / zoom
            s1 = self.cx + (x1 - self.cx) / zoom
            h0 = cy / (zoom * self._bow(s0))
            h1 = cy / (zoom * self._bow(s1))
            # source quad for this strip: NW, SW, SE, NE
            mesh.append(((x0, 0, x1, self.band_h),
                         (s0, cy - h0, s0, cy + h0, s1, cy + h1, s1, cy - h1)))
        return band.transform(band.size, Image.MESH, mesh, Image.BICUBIC)

    def colorize(self, band: Image.Image, color: tuple[int, int, int] | None = None,
                 opacity: float = 1.0) -> Image.Image:
        """Turn a greyscale band into colour over the background."""
        color = color or self.color
        channels = []
        for fg, bg in zip(color, self.background):
            lut = [round(bg + (fg - bg) * opacity * v / 255) for v in range(256)]
            channels.append(band.point(lut))
        return Image.merge("RGB", channels)

    def frame(self, band_rgb: Image.Image | None = None) -> Image.Image:
        """A full frame of background, with an RGB band placed on it."""
        frame = Image.new("RGB", (self.width, self.height), self.background)
        if band_rgb is not None:
            frame.paste(band_rgb, (0, self.band_top))
        return frame

    def finish(self, band: Image.Image, zoom: float = 1.0, opacity: float = 1.0) -> Image.Image:
        if opacity <= 0 or band.getbbox() is None:
            return self.frame()
        return self.frame(self.colorize(self.warp(band, zoom), opacity=opacity))

    # -- light: soft coloured glows behind everything ------------------------

    def new_light(self) -> Image.Image:
        return Image.new("RGB", self.light_size, self.background)

    def add_glow(self, light: Image.Image, x: float, y: float, rx: float, ry: float,
                 color: tuple[int, int, int], strength: float = 1.0) -> Image.Image:
        """Add a soft elliptical glow centred on frame position (x, y)."""
        if strength <= 0:
            return light
        k = self.LIGHT
        w, h = max(2, round(2 * rx / k)), max(2, round(2 * ry / k))
        spot = self._spot.resize((w, h), Image.BILINEAR)
        tint = Image.merge("RGB", [
            spot.point([min(255, round(v * c * strength / 255)) for v in range(256)])
            for c in color])
        layer = Image.new("RGB", light.size, 0)
        layer.paste(tint, (round(x / k - w / 2), round(y / k - h / 2)))
        return ImageChops.add(light, layer)

    def add_bars(self, light: Image.Image, bars: list[tuple[float, float, tuple[int, int, int]]]
                 ) -> Image.Image:
        """Add full-height vertical bars of light: (centre x, width, colour) in frame pixels."""
        k = self.LIGHT
        layer = Image.new("RGB", light.size, 0)
        draw = ImageDraw.Draw(layer)
        for x, width, color in bars:
            draw.rectangle(((x - width / 2) / k, 0, (x + width / 2) / k, light.height), fill=color)
        return ImageChops.add(light, layer)

    def dim(self, light: Image.Image, x: float, y: float, rx: float, ry: float,
            amount: float) -> Image.Image:
        """Darken an elliptical pocket of the light, so things drawn there stay readable."""
        if amount <= 0:
            return light
        k = self.LIGHT
        w, h = max(2, round(2 * rx / k)), max(2, round(2 * ry / k))
        pocket = self._spot.resize((w, h), Image.BILINEAR).point(
            [round(255 - amount * v) for v in range(256)])
        mask = Image.new("L", light.size, 255)
        mask.paste(pocket, (round(x / k - w / 2), round(y / k - h / 2)))
        return ImageChops.multiply(light, Image.merge("RGB", [mask] * 3))

    def lit_frame(self, light: Image.Image) -> Image.Image:
        return light.resize((self.width, self.height), Image.BICUBIC)

    # -- sprites: text, images, strokes and the wordmark on a frame ---------

    def text_mask(self, text: str, font_path: str, size: int) -> Image.Image:
        key = ("text", text, font_path, size)
        if key not in self._cache:
            font = ImageFont.truetype(str(ROOT / font_path), size)
            left, top, right, bottom = font.getbbox(text)
            img = Image.new("L", (right - left, bottom - top), 0)
            ImageDraw.Draw(img).text((-left, -top), text, font=font, fill=255)
            self._cache[key] = img
        return self._cache[key]

    def image(self, path: str, height: int) -> Image.Image:
        key = ("image", path, height)
        if key not in self._cache:
            img = Image.open(ROOT / path).convert("RGBA")
            self._cache[key] = img.resize((round(img.width * height / img.height), height),
                                          Image.LANCZOS)
        return self._cache[key]

    def star(self, size: int, points: int = 5, depth: float = 0.42) -> Image.Image:
        """A star-shaped mask `size` pixels across."""
        key = ("star", size, points, depth)
        if key not in self._cache:
            big = 4 * size
            corners = []
            for i in range(2 * points):
                r = big / 2 * (1 if i % 2 == 0 else depth)
                angle = math.pi * i / points - math.pi / 2
                corners.append((big / 2 + r * math.cos(angle), big / 2 + r * math.sin(angle)))
            img = Image.new("L", (big, big), 0)
            ImageDraw.Draw(img).polygon(corners, fill=255)
            self._cache[key] = img.resize((size, size), Image.LANCZOS)
        return self._cache[key]

    def stamp(self, frame: Image.Image, sprite: Image.Image, x: float, y: float,
              color: tuple[int, int, int] | None = None, opacity: float = 1.0,
              scale: float = 1.0) -> None:
        """Draw a sprite centred on (x, y): a greyscale mask in `color`, or an RGBA image."""
        if opacity <= 0:
            return
        if scale != 1:
            sprite = sprite.resize((max(1, round(sprite.width * scale)),
                                    max(1, round(sprite.height * scale))), Image.BICUBIC)
        mask = sprite if sprite.mode == "L" else sprite.getchannel("A")
        if opacity < 1:
            mask = mask.point([round(v * opacity) for v in range(256)])
        box = (round(x - sprite.width / 2), round(y - sprite.height / 2))
        frame.paste(color if sprite.mode == "L" else sprite.convert("RGB"), box, mask)

    def stroke_arc(self, frame: Image.Image, box: tuple[float, float, float, float],
                   start: float, end: float, width: float,
                   color: tuple[int, int, int], opacity: float = 1.0) -> None:
        """Draw part of an ellipse outline. Angles are in degrees, clockwise from 3 o'clock."""
        if end <= start or opacity <= 0:
            return
        x0, y0, x1, y1 = (round(v) for v in box)
        pad = math.ceil(width)
        w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        big = Image.new("L", (2 * w, 2 * h), 0)  # drawn at 2x, scaled down for smooth edges
        ImageDraw.Draw(big).arc((2 * pad, 2 * pad, 2 * (w - pad), 2 * (h - pad)),
                                start, end, fill=255, width=max(1, round(2 * width)))
        self.stamp(frame, big.resize((w, h), Image.LANCZOS), (x0 + x1) / 2, (y0 + y1) / 2,
                   color, opacity)

    def stamp_wordmark(self, frame: Image.Image, color: tuple[int, int, int] | None = None,
                       opacity: float = 1.0, zoom: float = 1.0) -> None:
        """Draw the complete, bowed wordmark on a frame."""
        if opacity <= 0:
            return
        key = ("wordmark", round(zoom, 4))
        if key not in self._cache:
            band = self.new_band()
            for index, mask in enumerate(self.letters):
                self.draw_letter(band, mask, index)
            warped = self.warp(band, zoom)
            if zoom != 1:  # zooming frames are used once; don't keep them
                mask = warped
            else:
                mask = self._cache[key] = warped
        else:
            mask = self._cache[key]
        if opacity < 1:
            mask = mask.point([round(v * opacity) for v in range(256)])
        frame.paste(color or self.color, (0, self.band_top), mask)


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------

def style_classic(scene: Scene, t: float) -> Image.Image:
    """The Bingie intro: fade in, hold, wipe letters away right to left while
    the first letter slides to the centre, then that letter zooms and wipes out."""
    c = scene.config["classic"]
    count = len(scene.letters)
    anchor = c["anchor"]

    fade = progress(t, *c["fade_in"])
    zoom_start, zoom_end, zoom_to = c["anchor_zoom"]
    zoom = 1 + (zoom_to - 1) * ease_in(progress(t, zoom_start, zoom_end))
    out_start, out_end, out_to = c["fade_out"]
    opacity = fade * (1 - (1 - out_to) * progress(t, out_start, out_end))

    slide = ease_in_out(progress(t, *c["slide"])) * (scene.cx - scene.letter_center(anchor))

    band = scene.new_band()
    # letters leave in order, the one furthest right of the anchor first
    leaving = [i for i in range(count - 1, -1, -1) if i != anchor]
    angles = c["wipe_angles"]
    for order, index in enumerate(leaving):
        start = c["wipe_start"] + order * c["wipe_stagger"]
        amount = progress(t, start, start + c["wipe_time"])
        if amount >= 1:
            continue
        mask = scene.wiped(index, angles[order % len(angles)], amount, c["wipe_softness"])
        scene.draw_letter(band, mask, index, slide)

    # the anchor letter: a partial wipe that leaves its stem, then a final wipe
    part, last = c["anchor_wipe"], c["final_wipe"]
    mask = scene.wiped(anchor, part["angle"],
                       (1 - part["keep"]) * ease_in_out(progress(t, *part["time"])),
                       part["softness"])
    final = progress(t, *last["time"])
    if final > 0:
        mask = ImageChops.multiply(mask, scene.wiped(anchor, last["angle"], final, last["softness"]))
    scene.draw_letter(band, mask, anchor, slide)

    return scene.finish(band, zoom=zoom, opacity=opacity)


# -- showcase: each provider gets a moment, then the Deflix wordmark ---------
#
# A provider effect paints glows on `light` (returned) and appends functions
# to `draws`; those run afterwards on the full-size frame, on top of the light.
# `p` runs 0..1 across the provider's time on screen, `a` is the opacity of its
# background and `ta` the opacity of what is drawn on top (logos fade out
# sooner, so two providers' logos never overlap).

def mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = clamp(t)
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))  # type: ignore[return-value]


def faded(mask: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 1:
        return mask
    return mask.point([round(v * clamp(opacity)) for v in range(256)])


def ramp(scene: Scene, size: tuple[int, int], key: str, fn) -> Image.Image:
    """A greyscale map the size of a logo: fn(u, v) gives 0..1 for each point
    (u, v run 0..1 across and down). Used to reveal a logo in a chosen order."""
    cache_key = ("ramp", key, size)
    if cache_key not in scene._cache:
        nx = 96
        ny = max(8, round(nx * size[1] / size[0]))
        small = Image.new("L", (nx, ny))
        small.putdata([round(255 * clamp(fn((i + 0.5) / nx, (j + 0.5) / ny)))
                       for j in range(ny) for i in range(nx)])
        scene._cache[cache_key] = small.resize(size, Image.BILINEAR)
    return scene._cache[cache_key]


def reveal(mask: Image.Image, order: Image.Image, amount: float, soft: float = 0.12) -> Image.Image:
    """Show the part of `mask` whose `order` value is below `amount` (0..1), soft-edged."""
    if amount >= 1:
        return mask
    edge = amount * (1 + soft)
    return ImageChops.multiply(mask, order.point(
        [round(255 * clamp((edge - v / 255) / soft)) for v in range(256)]))


class Logo:
    """A logo image scaled and placed on the frame, with ways to pick out its parts."""

    def __init__(self, scene: Scene, path: str, height: float, cx: float, cy: float):
        self.scene = scene
        self.image = scene.image(path, round(height * scene.height))
        self.rgb = self.image.convert("RGB")
        self.alpha = self.image.getchannel("A")
        self.w, self.h = self.image.size
        self.x0, self.y0 = round(cx - self.w / 2), round(cy - self.h / 2)
        self._parts: dict = {}

    def point(self, u: float, v: float) -> tuple[float, float]:
        """Frame position of a point given as fractions across and down the logo."""
        return self.x0 + u * self.w, self.y0 + v * self.h

    def region(self, box: tuple[float, float, float, float]) -> Image.Image:
        """The logo's alpha inside a box given in fractions (left, top, right, bottom)."""
        if box not in self._parts:
            px = (round(box[0] * self.w), round(box[1] * self.h),
                  round(box[2] * self.w), round(box[3] * self.h))
            mask = Image.new("L", self.alpha.size, 0)
            mask.paste(self.alpha.crop(px), px[:2])
            self._parts[box] = mask
        return self._parts[box]

    def piece(self, side: str) -> Image.Image:
        """The separate shape of the logo that reaches furthest to the "top" or "right"."""
        if side not in self._parts:
            sw = 360
            sh = max(8, round(sw * self.h / self.w))
            small = self.alpha.resize((sw, sh), Image.BILINEAR).point(
                [255 if v > 40 else 0 for v in range(256)])
            left, top, right, bottom = small.getbbox()
            if side == "top":
                row = small.crop((0, top, sw, top + 1)).getbbox()
                seed = ((row[0] + row[2]) // 2, top)
            else:
                col = small.crop((right - 1, 0, right, sh)).getbbox()
                seed = (right - 1, (col[1] + col[3]) // 2)
            ImageDraw.floodfill(small, seed, 128)
            shape = small.point([255 if v == 128 else 0 for v in range(256)])
            shape = shape.filter(ImageFilter.MaxFilter(5)).resize(self.alpha.size, Image.BILINEAR)
            self._parts[side] = ImageChops.multiply(self.alpha, shape.point(
                [255 if v > 60 else 0 for v in range(256)]))
        return self._parts[side]

    def put(self, frame: Image.Image, mask: Image.Image | None = None,
            color: tuple[int, int, int] | None = None, opacity: float = 1.0,
            dy: float = 0.0) -> None:
        """Draw the logo (or just `mask` of it), in its own colours or in `color`."""
        if opacity <= 0:
            return
        mask = faded(self.alpha if mask is None else mask, opacity)
        frame.paste(color if color else self.rgb, (self.x0, round(self.y0 + dy)), mask)

    def put_zoomed(self, frame: Image.Image, zoom: float, color: tuple[int, int, int],
                   opacity: float = 1.0, blur: float = 0.0) -> None:
        """Draw the logo's shape enlarged about the screen centre, optionally out of focus."""
        if opacity <= 0:
            return
        scene = self.scene
        k = 4 if blur > 1 else 1
        size = (scene.width // k, scene.height // k)
        layer = self.alpha.transform(size, Image.AFFINE, (
            k / zoom, 0, self.w / 2 - scene.cx / zoom,
            0, k / zoom, self.h / 2 - scene.cy / zoom), Image.BILINEAR)
        if k > 1:
            layer = layer.filter(ImageFilter.GaussianBlur(blur / k)).resize(
                (scene.width, scene.height), Image.BILINEAR)
        frame.paste(color, (0, 0), faded(layer, opacity))


def get_logo(scene: Scene, prov: dict, key: str = "logo", height: float | None = None,
             dy: float = 0.0) -> Logo:
    height = height or prov.get(key + "_height", 0.2)
    cache_key = ("logo", prov[key], height, dy)
    if cache_key not in scene._cache:
        scene._cache[cache_key] = Logo(scene, prov[key], height, scene.cx,
                                       scene.cy + dy * scene.height)
    return scene._cache[cache_key]


def add_fill(light: Image.Image, color: tuple[int, int, int], strength: float) -> Image.Image:
    """Add an even wash of colour over the whole background."""
    if strength <= 0:
        return light
    return ImageChops.add(light, Image.new("RGB", light.size,
                                           tuple(round(c * strength) for c in color)))


def rays(scene: Scene, light: Image.Image, colors: list[tuple[int, int, int]], turn: float,
         level: float, repeats: int = 1, softness: float = 0.05,
         reach: tuple[float, float] = (0.8, 1.0), grow: float = 1.0) -> Image.Image:
    """Soft beams of colour fanning out from the centre of the screen, like a
    slowly turning pinwheel seen through frosted glass. `turn` is in degrees."""
    w, h = light.size
    k = scene.LIGHT
    radius = math.hypot(w, h) * 0.6 * grow
    if radius < 1 or level <= 0:
        return light
    cx, cy = scene.cx / k, scene.cy / k
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    count = len(colors) * repeats
    wedge = 360 / count
    wheel = Image.new("RGB", (w, h), 0)
    draw = ImageDraw.Draw(wheel)
    for i in range(count):
        draw.pieslice(box, turn + i * wedge, turn + (i + 1) * wedge + 0.5,
                      fill=tuple(round(c * level) for c in colors[i % len(colors)]))
    wheel = wheel.filter(ImageFilter.GaussianBlur(max(0.5, w * softness)))
    # brightest in the middle, fading towards the edges of the screen
    rx, ry = round(w * reach[0]), round(h * reach[1])
    falloff = Image.new("L", (w, h), 0)
    falloff.paste(scene._spot.resize((2 * rx, 2 * ry), Image.BILINEAR),
                  (round(cx - rx), round(cy - ry)))
    wheel = ImageChops.multiply(wheel, Image.merge("RGB", [falloff] * 3))
    return ImageChops.add(light, wheel)


# Netflix: the N is drawn stroke by stroke, then the camera dives into it and
# it comes apart into strands of coloured light.

STRAND_COLORS = [(229, 9, 20), (229, 9, 20), (180, 6, 15), (255, 60, 30), (255, 140, 40),
                 (255, 215, 170), (255, 120, 170), (120, 190, 255), (20, 80, 255),
                 (0, 170, 255), (229, 9, 20), (255, 255, 255)]


def _strand_strips(scene: Scene) -> tuple[Image.Image, Image.Image]:
    """One-pixel-high strips: a colour per strand, and dark gaps between strands."""
    if "strands" not in scene._cache:
        n = 220
        colors, gaps = [], []
        for i in range(n):
            u = math.sin(i * 12.9898 + 4.1) * 43758.5453
            v = math.sin(i * 78.233 + 1.7) * 12345.678
            u, v = u - math.floor(u), v - math.floor(v)
            colors.append(STRAND_COLORS[int(u * len(STRAND_COLORS))])
            gaps.append(round(255 * (0.08 if v < 0.3 else 0.35 + 0.65 * v)))
        color_strip = Image.new("RGB", (n, 1))
        color_strip.putdata(colors)
        gap_strip = Image.new("L", (n, 1))
        gap_strip.putdata(gaps)
        scene._cache["strands"] = (color_strip, gap_strip)
    return scene._cache["strands"]


def _ribbon_burst(scene: Scene, frame: Image.Image, logo: Logo, burst: float, opacity: float) -> None:
    w, h = frame.size
    zoom = 1 + 13 * burst
    # the camera heads for the N's left stem, which drifts to the centre of the screen
    fx, fy = logo.point(0.3, 0.5)
    sx, sy = fx + (scene.cx - fx) * burst, fy + (scene.cy - fy) * burst
    big = logo.image.transform((w, h), Image.AFFINE, (
        1 / zoom, 0, (fx - logo.x0) - sx / zoom,
        0, 1 / zoom, (fy - logo.y0) - sy / zoom), Image.BILINEAR)
    layer = Image.new("RGB", (w, h), 0)
    layer.paste(big.convert("RGB"), (0, 0), big.getchannel("A"))

    # smear every column of the picture to the full height of the screen
    cover = clamp(zoom * logo.h / h, 0.05, 1)
    cols = w // 2
    level = layer.getchannel("R").resize((cols, 1), Image.BOX).point(
        [min(255, round(v / cover)) for v in range(256)])
    color_strip, gap_strip = _strand_strips(scene)
    n = color_strip.width
    span = n / (1 + 2.5 * burst)  # strands spread apart as the camera moves in
    window = (round(n / 2 - span / 2), 0, round(n / 2 + span / 2), 1)
    tint = Image.blend(Image.new("RGB", (cols, 1), (229, 9, 20)),
                       color_strip.crop(window).resize((cols, 1), Image.NEAREST),
                       progress(burst, 0.12, 0.55))
    level = ImageChops.multiply(level, gap_strip.crop(window).resize((cols, 1), Image.NEAREST))
    strands = ImageChops.multiply(tint, Image.merge("RGB", [level] * 3)).resize((w, h), Image.BILINEAR)

    out = Image.blend(layer, strands, progress(burst, 0.0, 0.3))
    if opacity < 1:
        out = out.point([round(v * clamp(opacity)) for v in range(256)] * 3)
    frame.paste(ImageChops.add(frame, out))


def effect_ribbon(scene: Scene, light: Image.Image, draws: list, prov: dict,
                  p: float, a: float, ta: float) -> Image.Image:
    logo = get_logo(scene, prov)
    burst = ease_in(progress(p, 0.5, 1.0))
    light = scene.add_glow(light, scene.cx, scene.cy, scene.width * 0.2, scene.height * 0.4,
                           hex_rgb(prov["glow"]), 0.16 * a * (1 - burst))
    if burst > 0:
        draws.append(lambda frame: _ribbon_burst(scene, frame, logo, burst, a))
        return light

    def stroke_order(u: float, v: float) -> float:
        if 0.64 * v <= u <= 0.64 * v + 0.36:  # the diagonal, drawn downwards
            return (1 + v) / 3
        return (1 - v) / 3 if u < 0.5 else (3 - v) / 3  # the stems, drawn upwards

    order = ramp(scene, logo.alpha.size, "ribbon", stroke_order)
    mask = reveal(logo.alpha, order, progress(p, 0.0, 0.32), 0.06)
    draws.append(lambda frame: logo.put(frame, mask, opacity=a))
    return light


# Disney+: a rim of light runs along the arc over a dark logo, flares at the
# plus, and the whole logo lights up on a teal glow.

def effect_comet(scene: Scene, light: Image.Image, draws: list, prov: dict,
                 p: float, a: float, ta: float) -> Image.Image:
    logo = get_logo(scene, prov)
    glow = hex_rgb(prov["glow"])
    pale = hex_rgb(prov.get("color", "#DDF6FF"))
    arc = logo.piece("top")
    plus = ImageChops.subtract(logo.region((0.84, 0.5, 1.0, 0.95)), arc)
    word = ImageChops.subtract(ImageChops.subtract(logo.alpha, arc), plus)

    sweep = ease_in_out(progress(p, 0.04, 0.46))
    flash = math.sin(math.pi * progress(p, 0.42, 0.8))
    lit = ease_out(progress(p, 0.5, 0.78))

    light = scene.add_glow(light, scene.cx + scene.width * 0.15, scene.height * 1.05,
                           scene.width * 0.8, scene.height * 0.9, glow, 0.6 * a * lit)
    light = scene.add_glow(light, scene.cx, scene.cy, scene.width * 0.6, scene.height * 0.8,
                           (8, 40, 70), 0.9 * a * lit)
    px, py = logo.point(0.925, 0.7)
    light = scene.add_glow(light, px, py, scene.width * 0.17, scene.width * 0.17,
                           (40, 225, 245), 0.9 * a * flash)

    across = ramp(scene, logo.alpha.size, "across", lambda u, v: u)
    arc_now = reveal(arc, across, sweep, 0.2)
    draws.append(lambda frame: logo.put(frame, word, mix((7, 14, 34), pale, lit),
                                        ta * (0.5 + 0.5 * lit)))
    draws.append(lambda frame: logo.put(frame, arc_now, mix((255, 150, 70), pale, lit), ta))
    draws.append(lambda frame: logo.put(frame, plus, mix((150, 245, 255), pale, lit),
                                        ta * progress(p, 0.42, 0.52)))
    return light


# Prime Video: blue rings of light sweep past, the name rises and the smile
# draws itself from left to right, ending in its arrow.

def effect_smile(scene: Scene, light: Image.Image, draws: list, prov: dict,
                 p: float, a: float, ta: float) -> Image.Image:
    logo = get_logo(scene, prov)
    glow = hex_rgb(prov["glow"])
    smile = logo.region((0.2, 0.62, 0.8, 1.0))
    text = ImageChops.subtract(logo.alpha, smile)

    light = scene.add_glow(light, scene.cx + scene.width * 0.3, scene.cy - scene.height * 0.1,
                           scene.width * 0.6, scene.height * 0.9, glow, 0.3 * a * (1 - 0.6 * p))
    ring_x, ring_y = scene.cx + scene.width * 0.75, scene.cy + scene.height * 0.9
    for i in range(6):
        r = scene.height * (0.75 + 0.13 * i + 0.25 * ease_out(p))
        box = (ring_x - r * 1.5, ring_y - r, ring_x + r * 1.5, ring_y + r)
        draws.append(lambda frame, box=box, i=i: scene.stroke_arc(
            frame, box, 180, 290, scene.height * 0.022, mix(glow, (0, 20, 90), 0.6),
            ta * 0.55 * (1 - progress(p, 0.25, 0.75)) * (1 - 0.1 * i)))

    rise = (1 - ease_out(progress(p, 0.05, 0.45))) * scene.height * 0.03
    draws.append(lambda frame: logo.put(frame, text, opacity=ta * progress(p, 0.05, 0.35), dy=rise))
    across = ramp(scene, logo.alpha.size, "smile", lambda u, v: (u - 0.22) / 0.58)
    drawn = reveal(smile, across, ease_in_out(progress(p, 0.25, 0.7)), 0.1)
    draws.append(lambda frame: logo.put(frame, drawn, opacity=ta))
    return light


# Apple TV+: the logo comes up out of black with a flare of light on the plus.

def effect_flare(scene: Scene, light: Image.Image, draws: list, prov: dict,
                 p: float, a: float, ta: float) -> Image.Image:
    logo = get_logo(scene, prov)
    peak = math.sin(math.pi * progress(p, 0.03, 0.6)) ** 0.7 if 0.03 < p < 0.6 else 0.0
    px, py = logo.point(0.87, 0.52)
    size = scene.width * (0.045 + 0.1 * peak)
    light = scene.add_glow(light, px, py, size, size, (235, 240, 255), a * (0.3 + 0.7 * peak))
    light = scene.add_glow(light, px, py, size * 2.4, size * 2.4, hex_rgb(prov["glow"]),
                           0.3 * a * peak)
    across = ramp(scene, logo.alpha.size, "from_right", lambda u, v: 1 - u)
    mask = reveal(logo.alpha, across, progress(p, 0.03, 0.38), 0.5)
    draws.append(lambda frame: logo.put(frame, mask, opacity=ta))
    return light


# HBO Max: the logo starts huge, purple and out of focus among beams of light,
# then pulls back into focus in white on a purple wash.

def effect_focus(scene: Scene, light: Image.Image, draws: list, prov: dict,
                 p: float, a: float, ta: float) -> Image.Image:
    logo = get_logo(scene, prov)
    glow, glow2 = hex_rgb(prov["glow"]), hex_rgb(prov.get("glow2", prov["glow"]))
    settle = ease_out(progress(p, 0.0, 0.62))
    light = add_fill(light, glow, a * (0.12 + 0.5 * settle))
    light = scene.add_glow(light, scene.cx, scene.cy, scene.width * 0.9, scene.height * 1.2,
                           glow, 0.4 * a)
    light = scene.add_glow(light, scene.width, scene.height, scene.width * 0.7, scene.height * 0.9,
                           glow2, 0.7 * a * settle)
    light = rays(scene, light, [(190, 90, 255), (30, 0, 80), (120, 40, 255), (20, 0, 60)],
                 40 + 50 * p, 0.7 * a * (1 - settle), repeats=2, softness=0.025,
                 reach=(0.9, 1.3))
    color = mix((200, 110, 255), (255, 255, 255), progress(p, 0.3, 0.65))
    zoom = 5.0 - 4.0 * settle
    blur = (1 - settle) * scene.height * 0.035
    draws.append(lambda frame: logo.put_zoomed(frame, zoom, color, ta, blur))
    return light


# Paramount+: stars fly in and ring the mountain on a field of blue, then the
# name appears beneath.

def effect_starring(scene: Scene, light: Image.Image, draws: list, prov: dict,
                    p: float, a: float, ta: float) -> Image.Image:
    blue = hex_rgb(prov["glow"])
    light = add_fill(light, blue, a)
    emblem = get_logo(scene, prov, "logo", prov.get("logo_height", 0.34), dy=-0.07)
    word = get_logo(scene, prov, "wordmark", prov.get("wordmark_height", 0.1), dy=0.175)

    # the emblem is a round dome (with the mountain cut out of it) ringed by stars
    aspect = emblem.h / emblem.w
    centre_u, centre_v, dome = 0.501, 0.499 / aspect, 0.428

    def radius(u: float, v: float) -> float:
        return math.hypot(u - centre_u, (v - centre_v) * aspect)

    def ring_order(u: float, v: float) -> float:  # bottom left, over the top, to bottom right
        angle = math.degrees(math.atan2((v - centre_v) * aspect, u - centre_u))
        return ((angle - 140) % 360) / 265

    size = emblem.alpha.size
    in_dome = ramp(scene, size, "dome", lambda u, v: 1.0 if radius(u, v) < dome else 0.0)
    dome_mask = ImageChops.multiply(emblem.alpha, in_dome)
    stars_mask = ImageChops.subtract(emblem.alpha, dome_mask)
    ring = reveal(stars_mask, ramp(scene, size, "ring", ring_order),
                  progress(p, 0.12, 0.55), 0.04)

    white = (255, 255, 255)
    draws.append(lambda frame: emblem.put(frame, ring, white, ta))
    draws.append(lambda frame: emblem.put(frame, dome_mask, white, ta * progress(p, 0.42, 0.6)))
    rise = (1 - ease_out(progress(p, 0.5, 0.8))) * scene.height * 0.02
    draws.append(lambda frame: word.put(frame, None, white, ta * progress(p, 0.5, 0.72), dy=rise))

    # a few large stars sweep in and shrink into the ring
    ex, ey = emblem.point(centre_u, centre_v * 1.0)
    for j in range(3):
        q = progress(p, 0.02 + 0.07 * j, 0.42 + 0.07 * j)
        if not 0 < q < 1:
            continue
        e = ease_out(q)
        angle = math.radians(200 - 150 * e + 25 * j)
        reach = emblem.w * (1.5 - 1.02 * e)
        x, y = ex + reach * math.cos(angle), ey + reach * math.sin(angle) * 0.8
        star = scene.star(max(6, round(scene.height * (0.13 - 0.105 * e))))
        draws.append(lambda frame, star=star, x=x, y=y, q=q: scene.stamp(
            frame, star, x, y, (225, 235, 255), ta * math.sin(math.pi * q) ** 0.5))
    flash = math.sin(math.pi * progress(p, 0.4, 0.7))
    light = scene.add_glow(light, ex, ey, scene.width * 0.2, scene.width * 0.2,
                           (200, 225, 255), 0.5 * a * flash)
    return light


# Any other provider: its logo (or name, if it has no logo) with a soft glow.

def effect_bloom(scene: Scene, light: Image.Image, draws: list, prov: dict,
                 p: float, a: float, ta: float) -> Image.Image:
    glow = hex_rgb(prov["glow"])
    grow = 0.18 + 0.3 * ease_out(p)
    light = scene.add_glow(light, scene.cx, scene.cy, scene.width * grow, scene.width * grow * 0.6,
                           glow, 0.45 * a * (1 - 0.4 * p))
    if prov.get("logo"):
        logo = get_logo(scene, prov)
        draws.append(lambda frame: logo.put(frame, opacity=ta))
    else:
        s = scene.config["showcase"]
        size = round(prov.get("size", s["provider_size"]) * scene.height)
        mask = scene.text_mask(prov["name"], prov.get("font", s["provider_font"]), size)
        color = hex_rgb(prov.get("text_color", "#FFFFFF"))
        draws.append(lambda frame: scene.stamp(frame, mask, scene.cx, scene.cy, color, ta,
                                               0.94 + 0.06 * p))
    return light


EFFECTS = {
    "ribbon": effect_ribbon,
    "comet": effect_comet,
    "smile": effect_smile,
    "flare": effect_flare,
    "focus": effect_focus,
    "starring": effect_starring,
    "bloom": effect_bloom,
}


def showcase_duration(config: dict) -> float:
    s = config["showcase"]
    step = s["provider_time"] - s["crossfade"]
    return s["lead_in"] + len(s["providers"]) * step + s["finale"]["time"]


def style_showcase(scene: Scene, t: float) -> Image.Image:
    """Each provider appears briefly, then their colours turn slowly as one
    soft aura behind the Deflix wordmark."""
    s = scene.config["showcase"]
    providers = s["providers"]
    slot, cross = s["provider_time"], s["crossfade"]
    step = slot - cross
    light, draws = scene.new_light(), []

    for i, prov in enumerate(providers):
        u = t - (s["lead_in"] + i * step)
        if not 0 <= u <= slot:
            continue
        a = min(progress(u, 0, cross), 1 - progress(u, slot - cross, slot))
        name = prov.get("effect", "bloom")
        if name not in EFFECTS:
            raise SystemExit(f'Unknown effect "{name}". Available: {", ".join(sorted(EFFECTS))}')
        light = EFFECTS[name](scene, light, draws, prov, u / slot, a, clamp(2 * a - 1))

    f = t - (s["lead_in"] + len(providers) * step)  # seconds into the finale
    if f >= 0:
        colors = [hex_rgb(prov["glow"]) for prov in providers]
        light = finale(scene, light, draws, f, s["finale"], colors)

    frame = scene.lit_frame(light)
    for draw in draws:
        draw(frame)
    return frame


def finale(scene: Scene, light: Image.Image, draws: list, f: float, fin: dict,
           colors: list[tuple[int, int, int]], boost: float = 1.0,
           turn_extra: float = 0.0) -> Image.Image:
    """The colours turn as one soft aura behind the wordmark, then all fades out.
    `f` is seconds into the finale; `boost` brightens the aura and `turn_extra`
    (degrees) is added to its rotation."""
    out = 1 - progress(f, fin["time"] - fin["fade_out"], fin["time"])
    gather = ease_out(progress(f, 0, fin["gather"]))
    breathe = 1 + 0.08 * math.sin(1.8 * f)
    light = rays(scene, light, colors, math.degrees(fin["spin"] * f) + turn_extra,
                 fin["aura_strength"] * progress(f, 0, fin.get("aura_in", 0.6)) * out
                 * breathe * boost,
                 repeats=fin.get("repeats", 1), softness=fin["softness"],
                 reach=tuple(fin["reach"]), grow=0.35 + 0.65 * gather)
    scale = fin.get("wordmark_scale", 1.0)
    light = scene.dim(light, scene.cx, scene.cy,
                      scene.half_width * 2.2 * scale, scene.cap * 3.4 * scale,
                      fin["pocket"] * gather)
    reveal = progress(f, *fin["reveal"])
    zoom = scale * (0.92 + 0.08 * ease_out(reveal))
    color = hex_rgb(fin["wordmark_color"]) if fin.get("wordmark_color") else None
    draws.append(lambda frame: scene.stamp_wordmark(frame, color, reveal * out, zoom))
    return light


# -- orbit: logo tiles circle the centre faster and faster, then burst ---------
#
# Each logo is drawn as a rounded tile, like the provider icons in the skin's
# sidebar. The tiles leave the centre one at a time and settle on a ring that
# turns slowly, then ever faster until they smear into streaks of their own
# colours. The ring falls into the centre, bursts into those colours, and the
# colours keep turning behind the Deflix wordmark.

def make_tile(scene: Scene, logo: dict, size: int) -> Image.Image:
    """A rounded square tile with the logo centred on it (RGBA)."""
    key = ("tile", logo["logo"], size)
    if key in scene._cache:
        return scene._cache[key]
    big = 2 * size  # drawn at 2x for smooth corners
    background = logo.get("background", "#000000")
    if isinstance(background, str):
        tile = Image.new("RGB", (big, big), hex_rgb(background))
    else:  # [top, bottom]: a vertical gradient
        top, bottom = (hex_rgb(c) for c in background)
        strip = Image.new("RGB", (1, 256))
        strip.putdata([mix(top, bottom, i / 255) for i in range(256)])
        tile = strip.resize((big, big), Image.BILINEAR)

    art = Image.open(ROOT / logo["logo"]).convert("RGBA")
    fit = logo.get("logo_scale", 0.66) * big
    ratio = min(fit / art.width, fit / art.height)
    art = art.resize((max(1, round(art.width * ratio)), max(1, round(art.height * ratio))),
                     Image.LANCZOS)
    paint = hex_rgb(logo["logo_color"]) if logo.get("logo_color") else art.convert("RGB")
    tile.paste(paint, ((big - art.width) // 2, (big - art.height) // 2), art.getchannel("A"))

    # a faint rim, so black tiles still read against the black background
    rim = Image.new("L", (big, big), 0)
    ImageDraw.Draw(rim).rounded_rectangle((0, 0, big - 1, big - 1), radius=0.225 * big,
                                          outline=46, width=max(2, round(0.014 * big)))
    tile.paste((255, 255, 255), (0, 0), rim)
    shape = Image.new("L", (big, big), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, big - 1, big - 1), radius=0.225 * big, fill=255)
    tile.putalpha(shape)
    scene._cache[key] = tile.resize((size, size), Image.LANCZOS)
    return scene._cache[key]


def orbit_spin(o: dict, t: float) -> tuple[float, float]:
    """How far the ring has turned by time t, and how fast it is turning
    (radians, radians per second). The speed grows exponentially while it
    accelerates, so it starts gently and ends very fast."""
    slow, fast = o["spin"]
    start, end = o["accelerate"]
    if t <= start:
        return slow * t, slow
    k = math.log(fast / slow) / (end - start)
    u = min(t, end) - start
    speed = slow * math.exp(k * u)
    angle = slow * start + (speed - slow) / k + fast * max(0.0, t - end)
    return angle, speed


def _sparks(scene: Scene, colors: list[tuple[int, int, int]], count: int) -> list:
    if "sparks" not in scene._cache:
        import random
        rng = random.Random(7)
        scene._cache["sparks"] = [
            (rng.uniform(0, 2 * math.pi), rng.uniform(0.35, 1.5), rng.uniform(0.6, 1.0),
             rng.uniform(0.5, 1.4), rng.choice(colors + [(255, 255, 255)]))
            for _ in range(count)]
    return scene._cache["sparks"]


def _draw_sparks(scene: Scene, frame: Image.Image, sparks: list, b: float) -> None:
    """Streaks of colour thrown outwards from the centre, `b` seconds after the burst."""
    k = 2
    layer = Image.new("RGB", (scene.width // k, scene.height // k), 0)
    draw = ImageDraw.Draw(layer)

    def travelled(seconds: float, speed: float) -> float:  # fast at first, then slowing
        return speed * scene.height * 0.75 * (1 - math.exp(-2.4 * max(0.0, seconds)))

    for angle, speed, life, width, color in sparks:
        fade = 1 - progress(b, 0.15 * life, 1.5 * life)
        if fade <= 0:
            continue
        dx, dy = math.cos(angle), math.sin(angle)
        head, tail = travelled(b, speed), travelled(b - 0.09, speed)
        draw.line(((scene.cx + dx * tail) / k, (scene.cy + dy * tail) / k,
                   (scene.cx + dx * head) / k, (scene.cy + dy * head) / k),
                  fill=tuple(round(c * fade) for c in color),
                  width=max(1, round(scene.height * 0.005 * width / k)))
    layer = layer.filter(ImageFilter.GaussianBlur(max(0.6, scene.height / 1400)))
    frame.paste(ImageChops.add(frame, layer.resize(frame.size, Image.BILINEAR)))


def orbit_duration(config: dict) -> float:
    o = config["orbit"]
    return o["burst"] + o["finale"]["time"]


def style_orbit(scene: Scene, t: float) -> Image.Image:
    o = scene.config["orbit"]
    logos = o["logos"]
    count = len(logos)
    colors = [hex_rgb(logo["glow"]) for logo in logos]
    light, draws = scene.new_light(), []
    k = scene.LIGHT
    cx, cy = scene.cx, scene.cy
    burst = o["burst"]

    if t < burst:
        angle, speed = orbit_spin(o, t)
        collapse = ease_in(progress(t, burst - o["collapse"], burst))
        streak = progress(speed, *o["streak_speed"])  # 0 = crisp tiles, 1 = streaks of colour
        ring = o["radius"] * scene.height * (1 - collapse)
        size = round(o["tile"] * scene.height)
        trails = Image.new("RGB", light.size, 0)

        for i, logo in enumerate(logos):
            born = o["lead_in"] + i * o["stagger"]
            e = progress(t, born, born + o["emerge"])
            if e <= 0:
                continue
            out = ease_out(e)
            r = ring * out
            theta = -math.pi / 2 + 2 * math.pi * i / count + angle
            shown = progress(e, 0, 0.3)
            x, y = cx + r * math.cos(theta), cy + r * math.sin(theta)
            scale = (0.2 + 0.8 * out) * (1 - 0.7 * collapse)
            light = scene.add_glow(light, x, y, size * 1.3 * scale, size * 1.3 * scale,
                                   colors[i], 0.3 * shown * (1 - streak))

            # a tail of the logo's colour, longer and brighter the faster it goes
            sweep = math.degrees(speed * o["trail"]) * out
            if streak > 0 and r > 4 and sweep > 0.5:
                layer = Image.new("RGB", light.size, 0)
                draw = ImageDraw.Draw(layer)
                box = ((cx - r) / k, (cy - r) / k, (cx + r) / k, (cy + r) / k)
                head = math.degrees(theta)
                steps = 12
                for s in range(steps - 1, -1, -1):
                    level = streak * shown * (1 - s / steps) ** 1.4
                    draw.arc(box, head - sweep * (s + 1) / steps, head - sweep * s / steps + 0.5,
                             fill=tuple(round(c * level) for c in colors[i]),
                             width=max(2, round(size * scale * 0.62 / k)))
                trails = ImageChops.add(trails, layer)

            # the tile itself, with fainter copies behind it when it is moving fast
            tile = make_tile(scene, logo, size)
            ghosts = 1 + round(3 * streak)
            for g in range(ghosts - 1, -1, -1):
                th = theta - g * speed / scene.fps / ghosts
                gx, gy = cx + r * math.cos(th), cy + r * math.sin(th)
                opacity = shown * (1 - 0.8 * streak) / (g + 1)
                draws.append(lambda frame, tile=tile, gx=gx, gy=gy, opacity=opacity, scale=scale:
                             scene.stamp(frame, tile, gx, gy, opacity=opacity, scale=scale))

        light = ImageChops.add(light, trails.filter(ImageFilter.GaussianBlur(0.8)))
        # the ring falls inwards and the centre heats up
        heat = scene.width * (0.05 + 0.1 * collapse)
        light = scene.add_glow(light, cx, cy, heat, heat, (255, 255, 255), collapse)
    else:
        b = t - burst
        fin = o["finale"]
        angle, speed = orbit_spin(o, burst)
        # the aura carries on from the ring's spin and slows to its own pace
        carry = math.degrees(angle + speed * (1 - math.exp(-3 * b)) / 3)
        light = finale(scene, light, draws, b, fin, colors,
                       boost=1 + o["burst_boost"] * (1 - progress(b, 0, 1.0)) ** 2,
                       turn_extra=carry)
        flash = (1 - progress(b, 0, o["flash"])) ** 2
        light = add_fill(light, (255, 255, 255), flash)
        # a ring of light races out to the edges of the screen
        wave = progress(b, 0, 0.9)
        if 0 < wave < 1:
            r = ease_out(wave) * scene.width * 0.7
            layer = Image.new("RGB", light.size, 0)
            level = round(200 * (1 - wave) ** 1.5)
            ImageDraw.Draw(layer).ellipse(((cx - r) / k, (cy - r) / k, (cx + r) / k, (cy + r) / k),
                                          outline=(level, level, level),
                                          width=max(2, round(scene.height * 0.03 / k)))
            light = ImageChops.add(light, layer.filter(ImageFilter.GaussianBlur(1.2)))
        sparks = _sparks(scene, colors, o["sparks"])
        draws.insert(0, lambda frame: _draw_sparks(scene, frame, sparks, b))

    frame = scene.lit_frame(light)
    for draw in draws:
        draw(frame)
    return frame


STYLES = {
    "classic": style_classic,
    "showcase": style_showcase,
    "orbit": style_orbit,
}

# Styles whose length depends on their settings; the rest use "duration".
STYLE_DURATIONS = {
    "showcase": showcase_duration,
    "orbit": orbit_duration,
}


def duration(config: dict) -> float:
    style = config["style"]
    return STYLE_DURATIONS[style](config) if style in STYLE_DURATIONS else config["duration"]


def render(scene: Scene, t: float) -> Image.Image:
    name = scene.config["style"]
    if name not in STYLES:
        raise SystemExit(f'Unknown style "{name}". Available: {", ".join(sorted(STYLES))}')
    return STYLES[name](scene, t)


def still(scene: Scene) -> Image.Image:
    """The complete, unanimated wordmark."""
    band = scene.new_band()
    for index, mask in enumerate(scene.letters):
        scene.draw_letter(band, mask, index)
    return scene.finish(band)


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def encode(config: dict) -> list[Path]:
    """Render at the largest output size and let ffmpeg scale the rest."""
    outputs = sorted(config["outputs"], key=lambda o: -o["height"])
    master = outputs[0]
    scene = Scene(config, master["width"], master["height"])
    fps = str(config["fps"])

    labels = [f"v{i}" for i in range(len(outputs))]
    graph = [f"[0:v]split={len(outputs)}" + "".join(f"[s{i}]" for i in range(len(outputs)))]
    for i, out in enumerate(outputs):
        graph.append(f"[s{i}]scale={out['width']}:{out['height']}:flags=lanczos:"
                     f"out_color_matrix=bt709:out_range=tv,format=yuv420p[{labels[i]}]")

    command = ["ffmpeg", "-v", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{scene.width}x{scene.height}", "-r", fps, "-i", "-",
               "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
               "-filter_complex", ";".join(graph)]
    paths = []
    for i, out in enumerate(outputs):
        path = MEDIA_DIR / f"deflix_intro_{out['name']}.mp4"
        paths.append(path)
        command += ["-map", f"[{labels[i]}]", "-map", "1:a",
                    "-c:v", "libx264", "-profile:v", "high", "-preset", "slow",
                    "-crf", str(config.get("quality", 20)),
                    "-r", fps, "-colorspace", "bt709", "-color_primaries", "bt709",
                    "-color_trc", "bt709", "-color_range", "tv",
                    "-c:a", "aac", "-b:a", "64k", "-shortest",
                    "-movflags", "+faststart", str(path)]

    try:
        ffmpeg = subprocess.Popen(command, stdin=subprocess.PIPE)
    except FileNotFoundError:
        raise SystemExit("ffmpeg is required and was not found on PATH.")
    assert ffmpeg.stdin is not None
    for n in range(scene.frame_count):
        ffmpeg.stdin.write(render(scene, n / scene.fps).tobytes())
        if n % 30 == 0:
            print(f"\rrendering {n + 1}/{scene.frame_count}", end="", flush=True)
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("\nffmpeg failed.")
    print(f"\rrendered {scene.frame_count} frames      ")

    splash = MEDIA_DIR / "deflix_splash.png"
    still(scene).save(splash, optimize=True)
    return paths + [splash]


def contact_sheet(scene: Scene, columns: int = 5, rows: int = 6) -> Image.Image:
    cell_w, cell_h = scene.width // 3, scene.height // 3
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows))
    for n in range(columns * rows):
        t = scene.duration * n / (columns * rows - 1)
        frame = render(scene, t).resize((cell_w, cell_h), Image.BILINEAR)
        sheet.paste(frame, ((n % columns) * cell_w, (n // columns) * cell_h))
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--frame", type=float, metavar="SECONDS",
                        help="write a single preview frame instead of the videos")
    parser.add_argument("--sheet", action="store_true",
                        help="write a contact sheet of the whole animation instead of the videos")
    parser.add_argument("--out", type=Path, help="where to write the --frame/--sheet image")
    parser.add_argument("--height", type=int, default=1080, help="preview height (default 1080)")
    args = parser.parse_args()

    config = json.loads(args.config.read_text())

    if args.frame is not None or args.sheet:
        scene = Scene(config, args.height * 16 // 9, args.height)
        image = contact_sheet(scene) if args.sheet else render(scene, args.frame)
        out = args.out or Path("intro_sheet.png" if args.sheet else "intro_frame.png")
        image.save(out)
        print(f"wrote {out}")
        return 0

    for path in encode(config):
        print(f"wrote {path.relative_to(ROOT)}  ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
