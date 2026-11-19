#!/usr/bin/env python3
"""Unified, SHA-256-verified Russian texture override generator for BABBDI.

Reads source Texture2D assets directly from the user's BABBDI installation,
verifies every decoded pixel hash against tools/texture_source_manifest.json,
rebuilds all 53 localized textures from scratch using perspective homography,
cylindrical warping, 3D cast-iron embossing, and surface-preserving cleanup,
and writes only PNG overrides plus texture_manifest.json to --output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import UnityPy
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "tools" / "texture_source_manifest.json"
_FONT_CACHE: dict[tuple[str, int, tuple[int, ...] | None], ImageFont.FreeTypeFont] = {}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_font_paths() -> dict[str, Path]:
    fonts_dir = Path(r"C:\Windows\Fonts")
    local_monofonto = ROOT / "local_build" / "font_monofonto_rg.ttf"

    def pick(*names: str) -> Path:
        for name in names:
            p = fonts_dir / name
            if p.is_file():
                return p
        raise FileNotFoundError(f"None of expected system fonts found: {names}")

    return {
        "bahn": pick("bahnschrift.ttf", "arialbd.ttf"),
        "impact": pick("impact.ttf", "arialbd.ttf"),
        "sans": pick("segoeuib.ttf", "arialbd.ttf"),
        "sans_reg": pick("segoeui.ttf", "arial.ttf"),
        "serif_bold": pick("georgiab.ttf", "cambriab.ttf"),
        "serif_reg": pick("georgia.ttf", "times.ttf"),
        "serif_italic": pick("georgiai.ttf", "timesi.ttf"),
        "chalk": pick("segoeprb.ttf", "segoepr.ttf", "comicbd.ttf"),
        "handwriting": pick("segoesc.ttf", "segoepr.ttf", "comic.ttf"),
        "comic": pick("comicbd.ttf", "arialbd.ttf"),
        "mono": local_monofonto if local_monofonto.is_file() else pick("consolab.ttf"),
        "mono_bold": pick("consolab.ttf"),
    }


def get_font(fonts: dict[str, Path], key: str, size: int, axes: tuple[int, ...] | None = None) -> ImageFont.FreeTypeFont:
    cache_key = (key, size, axes)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
    font = ImageFont.truetype(str(fonts[key]), size=max(4, int(size)))
    if axes is not None:
        try:
            font.set_variation_by_axes(list(axes))
        except Exception:
            pass
    _FONT_CACHE[cache_key] = font
    return font


def measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    spacing: int = 0,
    stroke_width: int = 0,
) -> tuple[int, int, int, int]:
    if "\n" in text:
        return draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, stroke_width=stroke_width)
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)


def fit_font(
    draw: ImageDraw.ImageDraw,
    fonts: dict[str, Path],
    font_key: str,
    text: str,
    max_w: float,
    max_h: float,
    max_size: int,
    min_size: int = 6,
    spacing: int = 0,
    stroke_width: int = 0,
    axes: tuple[int, ...] | None = None,
) -> ImageFont.FreeTypeFont:
    for size in range(max_size, min_size - 1, -1):
        font = get_font(fonts, font_key, size, axes=axes)
        b = measure_text(draw, text, font, spacing=spacing, stroke_width=stroke_width)
        if (b[2] - b[0]) <= max_w and (b[3] - b[1]) <= max_h:
            return font
    return get_font(fonts, font_key, min_size, axes=axes)


def draw_text_in_box(
    image: Image.Image,
    box: tuple[int, int, int, int],
    text: str,
    fonts: dict[str, Path],
    font_key: str,
    max_size: int,
    min_size: int,
    fill: tuple[int, int, int] | tuple[int, int, int, int],
    align: str = "center",
    valign: str = "center",
    spacing: int = 0,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] = (0, 0, 0),
    shadow: tuple[int, int, tuple[int, int, int] | tuple[int, int, int, int]] | None = None,
    axes: tuple[int, ...] | None = None,
    pad_x: int = 4,
    pad_y: int = 2,
) -> None:
    draw = ImageDraw.Draw(image)
    l, t, r, b = box
    font = fit_font(
        draw, fonts, font_key, text,
        max(4, (r - l) - pad_x), max(4, (b - t) - pad_y),
        max_size, min_size, spacing=spacing, stroke_width=stroke_width, axes=axes,
    )
    tb = measure_text(draw, text, font, spacing=spacing, stroke_width=stroke_width)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    if align == "left":
        x = l + pad_x // 2 - tb[0]
    elif align == "right":
        x = r - pad_x // 2 - tw - tb[0]
    else:
        x = l + ((r - l) - tw) / 2.0 - tb[0]
    if valign == "top":
        y = t + pad_y // 2 - tb[1]
    elif valign == "bottom":
        y = b - pad_y // 2 - th - tb[1]
    else:
        y = t + ((b - t) - th) / 2.0 - tb[1]
    pos = (round(x), round(y))

    if shadow is not None:
        dx, dy, sfill = shadow
        spos = (pos[0] + dx, pos[1] + dy)
        if "\n" in text:
            draw.multiline_text(spos, text, font=font, fill=sfill, spacing=spacing, align=align if align in ("left", "center", "right") else "center")
        else:
            draw.text(spos, text, font=font, fill=sfill)

    if "\n" in text:
        draw.multiline_text(
            pos, text, font=font, fill=fill, spacing=spacing,
            align=align if align in ("left", "center", "right") else "center",
            stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
    else:
        draw.text(pos, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


# ---------------------------------------------------------------------------
# Ink masking, texture synthesis & geometric warping helpers
# ---------------------------------------------------------------------------

def make_ink_mask(rgb: np.ndarray, box: tuple[int, int, int, int], mode: str, threshold: int = 120, dilate: int = 2) -> np.ndarray:
    l, t, r, b = box
    roi = rgb[t:b, l:r].astype(np.int16)
    gray = cv2.cvtColor(roi.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    red, green, blue = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    spread = roi.max(axis=2) - roi.min(axis=2)

    if mode == "dark":
        sel = gray < threshold
    elif mode == "bright":
        sel = (gray > threshold) & (spread < 135)
    elif mode == "localdark":
        bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=4.5)
        sel = gray < (bg - threshold)
    elif mode == "localbright":
        bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=4.5)
        sel = gray > (bg + threshold)
    elif mode == "blue":
        sel = (blue > red + 22) & (blue > green + 6) & (gray < threshold)
    elif mode == "magenta":
        sel = (red > threshold) & (red > green * 1.2) & (blue > green * 1.08)
    elif mode == "gold":
        sel = (red > threshold * 0.55) & (green > threshold * 0.50) & (green > blue * 1.18) & (gray < 210)
    elif mode == "neon":
        sel = ((gray > threshold) & (spread < 175)) | ((red > 165) & (green > 70) & (red > blue * 1.3))
    elif mode == "ticket_neutral":
        # Exclude bright red watermark ("RT") where R >> G, but catch dark ink printed over red RT!
        sel = ((gray < threshold) & ((red - green) < 40)) | (red < 168)
    elif mode == "olive_brown":
        # Used for dirty weathered brown/olive letters on light background (#529).
        sel = (gray < threshold) & (blue < 165) & ((red - blue) >= 6)
    elif mode == "toilet_blue":
        # Catch dark blue letter cores even where shadow makes blue - red near zero (#339).
        sel = (gray < threshold) & ((blue - red) >= -6)
    else:
        raise ValueError(f"Unknown ink mask mode: {mode}")

    local = sel.astype(np.uint8) * 255
    if dilate > 0:
        local = cv2.dilate(local, np.ones((3, 3), np.uint8), iterations=dilate)
    full = np.zeros(rgb.shape[:2], dtype=np.uint8)
    full[t:b, l:r] = local
    return full


def inpaint_rgb(rgb: np.ndarray, mask: np.ndarray, radius: float = 3.0) -> np.ndarray:
    if not np.any(mask):
        return rgb.copy()
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    out = cv2.inpaint(bgr, mask, radius, cv2.INPAINT_TELEA)
    out = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
    return np.where(mask[:, :, None] > 0, out, rgb).astype(np.uint8)


def tile_patch(patch: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Create seamless mirror-tiled texture patch of size (target_h, target_w)."""
    flipped_h = np.concatenate([patch, patch[:, ::-1]], axis=1)
    mirrored = np.concatenate([flipped_h, flipped_h[::-1, :]], axis=0)
    reps_y = math.ceil(target_h / mirrored.shape[0])
    reps_x = math.ceil(target_w / mirrored.shape[1])
    tiled = np.tile(mirrored, (reps_y, reps_x, 1))
    return tiled[:target_h, :target_w].copy()


def feather_composite(base_rgb: np.ndarray, overlay_rgb: np.ndarray, mask: np.ndarray, blur_sigma: float = 1.2) -> np.ndarray:
    if blur_sigma > 0:
        alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), sigmaX=blur_sigma)
    else:
        alpha = (mask > 0).astype(np.float32)
    alpha = np.clip(alpha, 0.0, 1.0)[:, :, None]
    out = base_rgb.astype(np.float32) * (1.0 - alpha) + overlay_rgb.astype(np.float32) * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def warp_rgba_quad(
    base_rgb: np.ndarray,
    rgba_layer: np.ndarray,
    quad: list[tuple[float, float]],
    feather_mask: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Warp an RGBA overlay into quad [TL, TR, BR, BL] onto base_rgb."""
    sh, sw = rgba_layer.shape[:2]
    dh, dw = base_rgb.shape[:2]
    src_pts = np.array([[0, 0], [sw - 1, 0], [sw - 1, sh - 1], [0, sh - 1]], dtype=np.float32)
    dst_pts = np.array(quad, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(rgba_layer, M, (dw, dh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    alpha = warped[:, :, 3].astype(np.float32) / 255.0
    if feather_mask:
        poly_mask = np.zeros((dh, dw), dtype=np.uint8)
        cv2.fillConvexPoly(poly_mask, np.round(dst_pts).astype(np.int32), 255)
        poly_mask = cv2.erode(poly_mask, np.ones((3, 3), np.uint8), iterations=1)
        poly_feather = cv2.GaussianBlur(poly_mask.astype(np.float32) / 255.0, (0, 0), sigmaX=1.2)
        alpha *= poly_feather
    a3 = alpha[:, :, None]
    blended = np.clip(base_rgb.astype(np.float32) * (1.0 - a3) + warped[:, :, :3].astype(np.float32) * a3, 0, 255).astype(np.uint8)
    out = np.where(a3 > 0.0, blended, base_rgb).astype(np.uint8)
    changed_mask = (alpha > 0.0).astype(np.uint8) * 255
    return out, changed_mask


def render_quad_text(
    base_rgb: np.ndarray,
    quad: list[tuple[float, float]],
    render_w: int,
    render_h: int,
    draw_fn: Callable[[Image.Image], None],
    oversample: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    hi = Image.new("RGBA", (render_w * oversample, render_h * oversample), (0, 0, 0, 0))
    draw_fn(hi)
    if oversample != 1:
        hi = hi.resize((render_w, render_h), Image.Resampling.LANCZOS)
    return warp_rgba_quad(base_rgb, np.asarray(hi, dtype=np.uint8), quad)


def warp_cylindrical_rgba(rgba_layer: np.ndarray, bow_px: float, x_compress: float = 0.08) -> np.ndarray:
    """Warp a flat RGBA label into a downward-curving cylindrical band."""
    h, w = rgba_layer.shape[:2]
    pad_y = max(4, int(abs(bow_px)) + 4)
    out_h = h + pad_y * 2
    ys, xs = np.mgrid[0:out_h, 0:w].astype(np.float32)
    u = (xs - (w - 1) * 0.5) / max(1.0, (w - 1) * 0.5)  # -1..1
    # Horizontal foreshortening near cylinder sides
    src_x = (w - 1) * 0.5 + (xs - (w - 1) * 0.5) * (1.0 + x_compress * (u ** 2))
    # Vertical arc downward in center
    arc_shift = bow_px * (1.0 - u ** 2)
    src_y = ys - pad_y - arc_shift
    return cv2.remap(
        rgba_layer, src_x, src_y,
        interpolation=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def apply_surface_wear(rgba: np.ndarray, bg_rgb: np.ndarray, strength: float = 0.32) -> np.ndarray:
    """Modulate flat rendered paint with underlying texture luminance variation so it feels printed."""
    out = rgba.copy().astype(np.float32)
    bg_gray = cv2.cvtColor(bg_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    local_mean = cv2.GaussianBlur(bg_gray, (0, 0), sigmaX=18.0)
    delta = (bg_gray - np.maximum(local_mean, 1.0)) / np.maximum(local_mean, 40.0)
    mod = np.clip(1.0 + delta * strength * 1.8, 0.45, 1.25)[:, :, None]
    out[:, :, :3] = np.clip(out[:, :, :3] * mod, 0, 255)
    return out.astype(np.uint8)


def composite_rgba(base_rgb: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    a = (rgba[:, :, 3:4].astype(np.float32) / 255.0)
    out = base_rgb.astype(np.float32) * (1.0 - a) + rgba[:, :, :3].astype(np.float32) * a
    return np.clip(out, 0, 255).astype(np.uint8)


def paste_rgba_box(base_rgb: np.ndarray, box: tuple[int, int, int, int], rgba: np.ndarray) -> np.ndarray:
    l, t, r, b = box
    out = base_rgb.copy()
    sub = out[t:b, l:r]
    if rgba.shape[:2] != sub.shape[:2]:
        rgba = np.asarray(Image.fromarray(rgba, "RGBA").resize((r - l, b - t), Image.Resampling.LANCZOS), dtype=np.uint8)
    out[t:b, l:r] = composite_rgba(sub, rgba)
    return out


# ---------------------------------------------------------------------------
# Category localizers
# ---------------------------------------------------------------------------

def localize_map(image: Image.Image, regions: list[tuple], fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    neutral = spread < 90
    restore_mask = np.zeros((h, w), dtype=np.uint8)
    allow_mask = np.zeros((h, w), dtype=np.uint8)

    for box, erase_box, text, max_sz, min_sz, align, stroke in regions:
        el, et, er, eb = erase_box or box
        bright = ((gray[et:eb, el:er] >= 156) & neutral[et:eb, el:er]).astype(np.uint8) * 255
        cnt, labels, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
        sel = np.zeros_like(bright)
        mw, mh = max(8, int((er - el) * 0.95)), max(8, int((eb - et) * 0.90))
        for idx in range(1, cnt):
            _, _, cw, ch, area = stats[idx]
            if area >= 3 and cw <= mw and ch <= mh:
                sel[labels == idx] = 255
        sel = cv2.dilate(sel, np.ones((3, 3), np.uint8), iterations=2)
        restore_mask[et:eb, el:er] = np.maximum(restore_mask[et:eb, el:er], sel)
        bl, bt, br, bb = box
        allow_mask[bt:bb, bl:br] = 255

    restored = inpaint_rgb(rgb, restore_mask, radius=4.0)
    canvas = Image.fromarray(restored, "RGB")
    for box, _, text, max_sz, min_sz, align, stroke in regions:
        draw_text_in_box(
            canvas, box, text, fonts, "bahn", max_sz, min_sz,
            fill=(242, 246, 250), align=align, stroke_width=stroke,
            stroke_fill=(38, 45, 54), axes=(700, 90),
        )
    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_xbox_diagram(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#29: Pure white cleanup right of pointer line ends (x=631) + crisp Segoe UI labels."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    # All 14 leader lines end at x=624; clean starting at x=631..1045, y=75..605.
    allow_mask[75:605, 631:1045] = 255
    rgb[allow_mask > 0] = (255, 255, 255)
    canvas = Image.fromarray(rgb, "RGB")
    # Exact measured Y centers of the 11 labeled lines in original diagram:
    items = [
        (106, "Бег", 20),
        (212, "Правая кнопка мыши", 17),
        (243, "Левая кнопка мыши", 17),
        (265, "Взаимодействие (взять/бросить, говорить)", 16),
        (286, "Скольжение", 17),
        (339, "Взаимодействие (взять/бросить, говорить)", 16),
        (371, "Прыжок", 18),
        (424, "Меню паузы", 17),
        (445, "Библиотека", 17),
        (530, "Поворот камеры", 17),
        (572, "Движение", 18),
    ]
    for cy, text, sz in items:
        draw_text_in_box(
            canvas, (635, cy - 13, 1042, cy + 13), text, fonts, "sans",
            sz, 12, fill=(24, 28, 36), align="left", valign="center", pad_x=2, pad_y=0,
        )
    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), orig[:, :, :3]).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_chalkboard(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#30 XONCKN 1: Seamless chalkboard patch restoration + chalk-textured Russian labels."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape

    # Assemble clean seamless chalkboard texture from verified empty areas.
    clean_a = rgb[20:180, 860:1020]
    clean_b = rgb[260:420, 980:1140]
    clean_big = np.concatenate([clean_a, clean_b], axis=1)
    bg_synth = tile_patch(clean_big, h, w)

    # Boxes strictly preserving original chalk colons (left colons at x=420..465, right colons at x=1499..1527).
    erase_boxes = [
        (485, 85, 920, 260),      # Move
        (485, 310, 910, 465),     # Jump
        (485, 465, 910, 610),     # Sprint
        (485, 620, 1200, 765),    # Crouch / slide
        (485, 775, 1140, 865),    # - Interact
        (462, 862, 1140, 968),    # - Grab objects
        (1532, 65, 1980, 174),    # Open
        (1430, 174, 2000, 285),   # library
        (1532, 340, 1985, 495),   # Use item
        (1532, 590, 1985, 735),   # Zoom in
        (1532, 800, 2015, 965),   # Screenshot + subtitle
    ]
    allow_mask = np.zeros((h, w), dtype=np.uint8)
    for l, t, r, b in erase_boxes:
        allow_mask[t:b, l:r] = 255
    # Also ensure draw boxes for new labels are included in allow_mask.
    draw_specs = [
        ((490, 75, 1180, 275), "Движение", "chalk", 74, 54, "left", 0),
        ((490, 305, 1180, 495), "Прыжок", "chalk", 80, 56, "left", 0),
        ((490, 475, 1180, 620), "Бег", "chalk", 80, 56, "left", 0),
        ((490, 622, 1220, 775), "Присесть / скользить", "chalk", 60, 42, "left", 0),
        ((490, 780, 1220, 975), "Взаимодействие:\nвзять предмет", "chalk", 58, 42, "left", 2),
        ((1535, 55, 2015, 285), "Открыть\nбиблиотеку", "chalk", 68, 48, "left", 2),
        ((1535, 315, 2015, 505), "Использовать\nпредмет", "chalk", 58, 42, "left", 2),
        ((1535, 555, 2015, 755), "Приблизить", "chalk", 68, 48, "left", 0),
        ((1535, 785, 2025, 915), "Снимок экрана", "chalk", 62, 44, "left", 0),
        ((1535, 915, 2025, 962), "Сохраняется в папку «Изображения»", "sans_reg", 19, 12, "left", 0),
    ]
    for box, *_ in draw_specs:
        l, t, r, b = box
        allow_mask[t:b, l:r] = 255

    # Feather-blend clean chalkboard texture into allow_mask.
    clean_board = feather_composite(rgb, bg_synth, allow_mask, blur_sigma=4.0)

    # Render chalk text onto transparent layer, add subtle chalk grain, and composite.
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for box, text, fkey, max_sz, min_sz, align, sp in draw_specs:
        draw_text_in_box(
            overlay, box, text, fonts, fkey, max_sz, min_sz,
            fill=(238, 240, 232, 245), align=align, spacing=sp, pad_x=4, pad_y=2,
        )
    ov_arr = np.asarray(overlay, dtype=np.uint8).astype(np.float32)
    rng = np.random.default_rng(30)
    chalk_grain = rng.normal(1.0, 0.08, size=(h, w, 1)).astype(np.float32)
    ov_arr[:, :, 3] = np.clip(ov_arr[:, :, 3:4] * chalk_grain, 0, 255)[:, :, 0]
    composed = composite_rgba(clean_board, ov_arr.astype(np.uint8))
    out_rgb = np.where(allow_mask[:, :, None] > 0, composed, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_tuto_pogo(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#560 tutoPogo: Clean pink patch over HOLD without touching mouse outline + tilted marker ЗАЖМИ."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    bg_pink = tuple(int(v) for v in np.median(rgb[105:135, 200:235], axis=(0, 1)))
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    allow_mask[102:154, 224:344] = 255
    # Only fill dark ink pixels + small margin inside HOLD area so black mouse line below stays sharp.
    ink = make_ink_mask(rgb, (238, 114, 344, 154), "dark", threshold=135, dilate=3)
    restored = rgb.copy()
    restored[ink > 0] = bg_pink

    # Render slightly tilted hand-drawn comic label matching original slant.
    patch = Image.new("RGBA", (120, 52), (0, 0, 0, 0))
    draw_text_in_box(patch, (0, 0, 120, 52), "ЗАЖМИ", fonts, "comic", 24, 16, fill=(18, 12, 16, 255))
    rotated = patch.rotate(8, resample=Image.Resampling.BICUBIC, expand=False)
    composed = paste_rgba_box(restored, (224, 102, 344, 154), np.asarray(rotated, dtype=np.uint8))
    out_rgb = np.where(allow_mask[:, :, None] > 0, composed, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_tuto_scale(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#641 TutoScale.png: Clean flat pink patch clear of mouse contour (x<=248) + crisp bold label."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    bg_pink = tuple(int(v) for v in np.median(rgb[400:420, 40:200], axis=(0, 1)))
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    allow_mask[412:582, 14:248] = 255
    restored = rgb.copy()
    restored[allow_mask > 0] = bg_pink
    canvas = Image.fromarray(restored, "RGB")
    draw_text_in_box(
        canvas, (16, 414, 246, 580), "КРУТИ КОЛЁСИКО\nМЫШИ, ЧТОБЫ\nМЕНЯТЬ ГАММУ",
        fonts, "bahn", 32, 18, fill=(18, 12, 16), align="left", spacing=2, axes=(700, 88),
    )
    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_ticket(image: Image.Image, is_hud: bool, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """Localize either #663 (512x256 RGB) or #553 (537x280 RGBA) preserving red RT watermark & alpha."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    allow_mask = np.zeros((h, w), dtype=np.uint8)
    ink_mask = np.zeros((h, w), dtype=np.uint8)

    if not is_hud:
        # #663 (512x256)
        white_boxes = [
            ((104, 34, 206, 54), "БИЛЕТ НА ПОЕЗД", 11, 7, "center"),
            ((372, 34, 478, 54), "БИЛЕТ НА ПОЕЗД", 10, 6, "center"),
            ((36, 201, 134, 212), "ЭКОНОМ-КЛАСС", 8, 5, "left"),
            ((382, 201, 480, 212), "ЭКОНОМ-КЛАСС", 8, 5, "center"),
        ]
        # Clean middle pink guilloche labels using chromaticity-safe neutral ink mask.
        pink_erase = [
            (37, 62, 130, 96),    # NAME OF PASSENGER / Griselda
            (366, 62, 466, 108),  # right stub NAME / Griselda / FM:
            (172, 62, 256, 98),   # PRICE / 26 Tokens
            (37, 98, 122, 130),   # FROM / BABBDI
            (366, 98, 456, 130),  # right FROM / BABBDI
            (37, 130, 125, 164),  # TO / MERZER
            (366, 130, 458, 165), # right TO / MERZER
            (256, 98, 326, 132),  # PLATFORM / 1
        ]
        pink_draw = [
            ((38, 63, 128, 76), "ПАССАЖИР", "sans_reg", 8, 5, (28, 22, 24)),
            ((38, 75, 128, 94), "Гризельда", "serif_reg", 12, 7, (16, 12, 12)),
            ((368, 63, 464, 76), "ПАССАЖИР", "sans_reg", 8, 5, (28, 22, 24)),
            ((368, 75, 464, 94), "Гризельда", "serif_reg", 11, 7, (16, 12, 12)),
            ((176, 63, 250, 76), "ЦЕНА", "sans", 8, 5, (20, 18, 20)),
            ((174, 77, 254, 94), "26 жетонов", "serif_reg", 10, 6, (16, 12, 12)),
            ((38, 99, 118, 111), "ОТКУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((38, 110, 118, 128), "БАББДИ", "serif_reg", 11, 6, (16, 12, 12)),
            ((368, 99, 452, 111), "ОТКУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((368, 110, 452, 128), "БАББДИ", "serif_reg", 11, 6, (16, 12, 12)),
            ((38, 132, 118, 144), "КУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((38, 143, 118, 162), "МЕРЦЕР", "serif_reg", 11, 6, (16, 12, 12)),
            ((368, 132, 452, 144), "КУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((368, 143, 452, 162), "МЕРЦЕР", "serif_reg", 11, 6, (16, 12, 12)),
            ((258, 99, 326, 111), "ПЛАТФОРМА", "sans_reg", 7, 5, (22, 18, 20)),
            ((260, 112, 294, 129), "1", "serif_reg", 11, 6, (16, 12, 12)),
        ]
        brand_box = (32, 172, 290, 200)
    else:
        # #553 (537x280)
        white_boxes = [
            ((112, 37, 214, 57), "БИЛЕТ НА ПОЕЗД", 11, 7, "center"),
            ((392, 37, 498, 57), "БИЛЕТ НА ПОЕЗД", 10, 6, "center"),
            ((42, 219, 142, 231), "ЭКОНОМ-КЛАСС", 8, 5, "left"),
            ((404, 219, 506, 231), "ЭКОНОМ-КЛАСС", 8, 5, "center"),
        ]
        pink_erase = [
            (40, 68, 140, 104),
            (384, 68, 488, 114),
            (184, 68, 266, 105),
            (40, 106, 132, 140),
            (384, 106, 476, 140),
            (40, 142, 132, 176),
            (384, 142, 476, 180),
            (268, 106, 342, 142),
        ]
        pink_draw = [
            ((42, 70, 138, 84), "ПАССАЖИР", "sans_reg", 8, 5, (28, 22, 24)),
            ((42, 82, 138, 102), "Гризельда", "serif_reg", 13, 7, (16, 12, 12)),
            ((386, 70, 486, 84), "ПАССАЖИР", "sans_reg", 8, 5, (28, 22, 24)),
            ((386, 82, 486, 102), "Гризельда", "serif_reg", 12, 7, (16, 12, 12)),
            ((186, 70, 262, 84), "ЦЕНА", "sans", 8, 5, (20, 18, 20)),
            ((184, 83, 264, 102), "26 жетонов", "serif_reg", 10, 6, (16, 12, 12)),
            ((42, 108, 128, 121), "ОТКУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((42, 119, 128, 138), "БАББДИ", "serif_reg", 12, 6, (16, 12, 12)),
            ((386, 108, 472, 121), "ОТКУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((386, 119, 472, 138), "БАББДИ", "serif_reg", 12, 6, (16, 12, 12)),
            ((42, 144, 128, 157), "КУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((42, 155, 128, 174), "МЕРЦЕР", "serif_reg", 12, 6, (16, 12, 12)),
            ((386, 144, 472, 157), "КУДА:", "sans_reg", 8, 5, (22, 18, 20)),
            ((386, 155, 472, 174), "МЕРЦЕР", "serif_reg", 12, 6, (16, 12, 12)),
            ((270, 108, 340, 121), "ПЛАТФОРМА", "sans_reg", 7, 5, (22, 18, 20)),
            ((272, 121, 306, 139), "1", "serif_reg", 12, 6, (16, 12, 12)),
        ]
        brand_box = (36, 183, 308, 220)

    for box in pink_erase:
        l, t, r, b = box
        allow_mask[t:b, l:r] = 255
        ink_mask = np.maximum(ink_mask, make_ink_mask(rgb, box, "ticket_neutral", threshold=175, dilate=2))

    # Also erase red brand letters via inpainting so diagonal pink guilloché stays intact!
    bl, bt, br, bb = brand_box
    allow_mask[bt:bb, bl:br] = 255
    red_brand_ink = ((rgb[bt:bb, bl:br, 0].astype(int) - rgb[bt:bb, bl:br, 1].astype(int)) > 40).astype(np.uint8) * 255
    red_brand_ink = cv2.dilate(red_brand_ink, np.ones((3, 3), np.uint8), iterations=2)
    ink_mask[bt:bb, bl:br] = np.maximum(ink_mask[bt:bb, bl:br], red_brand_ink)

    restored = inpaint_rgb(rgb, ink_mask, radius=3.0)

    # White header & footer strips: match local paper white (not harsh pure 255 if shadowed).
    for box, text, max_sz, min_sz, align in white_boxes:
        l, t, r, b = box
        allow_mask[t:b, l:r] = 255
        paper_white = tuple(int(v) for v in np.percentile(restored[t:b, l:r], 95, axis=(0, 1)))
        restored[t:b, l:r] = paper_white

    canvas = Image.fromarray(restored, "RGB")
    for box, text, max_sz, min_sz, align in white_boxes:
        draw_text_in_box(canvas, box, text, fonts, "bahn", max_sz, min_sz, fill=(18, 18, 20), align=align, axes=(600, 90), pad_x=2, pad_y=1)
    for box, text, fkey, max_sz, min_sz, fill in pink_draw:
        draw_text_in_box(canvas, box, text, fonts, fkey, max_sz, min_sz, fill=fill, align="left", pad_x=2, pad_y=0)
    draw_text_in_box(canvas, brand_box, "Ралтиайл Траннил", fonts, "sans", 24, 14, fill=(224, 78, 92), align="left", pad_x=2, pad_y=0)

    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_portrait(image: Image.Image, text: str, path_id: int, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """13 Polaroid character photos: preserve parchment paper texture + organic handwriting."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    # WifePhoto (#567) has a pink heart on the right (starts ~x=645) -> protect it!
    max_x = 632 if path_id == 567 else 860
    box = (180, 862, max_x, 974)
    l, t, r, b = box
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    allow_mask[t:b, l:r] = 255

    # Erase only dark ink inside parchment strip so natural aged Polaroid paper grain survives!
    ink = make_ink_mask(rgb, box, "dark", threshold=145, dilate=3)
    restored = inpaint_rgb(rgb, ink, radius=3.5)

    # Render smooth handwritten signature slightly softened & blended into paper grain.
    ov = Image.new("RGBA", (r - l, b - t), (0, 0, 0, 0))
    draw_text_in_box(ov, (0, 0, r - l, b - t), text, fonts, "handwriting", 58, 38, fill=(26, 22, 20, 240))
    ov = ov.filter(ImageFilter.GaussianBlur(0.35))
    composed = paste_rgba_box(restored, box, np.asarray(ov, dtype=np.uint8))
    out_rgb = np.where(allow_mask[:, :, None] > 0, composed, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_manhole(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#651 M_ManholeCover00: Synthesize cast-iron plate + 3D beveled embossed КАНАЛИЗАЦИЯ."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape

    # Inner octagonal recessed plate polygon (safely inside the raised border).
    poly = np.array([[250, 426], [774, 426], [794, 448], [794, 566], [774, 588], [250, 588], [230, 566], [230, 448]], dtype=np.int32)
    allow_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(allow_mask, poly, 255)

    # Build stud-free cast-iron plate background inside recess using smooth recess lighting
    # + procedural multi-scale sand-cast iron grain (no diamond studs!).
    rec_sample = rgb[426:588, 230:794].astype(np.float32)
    rec_smooth = cv2.GaussianBlur(rec_sample, (0, 0), sigmaX=28.0)
    rng = np.random.default_rng(651)
    fine_grain = rng.normal(0.0, 7.5, size=rec_sample.shape[:2]).astype(np.float32)
    med_grain = cv2.GaussianBlur(rng.normal(0.0, 12.0, size=rec_sample.shape[:2]).astype(np.float32), (0, 0), sigmaX=1.4)
    iron_grain = (fine_grain + med_grain)[:, :, None]
    plate_bg = np.clip(rec_smooth + iron_grain, 0, 255).astype(np.uint8)

    restored = rgb.copy()
    restored[426:588, 230:794] = plate_bg
    inner_mask = cv2.erode(allow_mask, np.ones((9, 9), np.uint8))
    clean_iron = feather_composite(rgb, restored, inner_mask, blur_sigma=2.2)

    # Render bold letter mask inside center plate -> build 3D cast-iron relief with cast shadow.
    text_img = Image.new("L", (w, h), 0)
    draw_text_in_box(text_img, (242, 434, 782, 580), "КАНАЛИЗАЦИЯ", fonts, "bahn", 92, 52, fill=255, stroke_width=2, stroke_fill=255, axes=(700, 82))
    tmask = np.asarray(text_img, dtype=np.uint8)
    dist = cv2.distanceTransform((tmask > 127).astype(np.uint8), cv2.DIST_L2, 5)
    height_map = np.clip(dist / 4.2, 0.0, 1.0)
    height_map = cv2.GaussianBlur(height_map, (0, 0), sigmaX=1.1)

    gx = cv2.Sobel(height_map, cv2.CV_32F, 1, 0, ksize=3) * 2.5
    gy = cv2.Sobel(height_map, cv2.CV_32F, 0, 1, ksize=3) * 2.5
    gz = np.ones_like(gx)
    norm = np.sqrt(gx * gx + gy * gy + gz * gz) + 1e-6
    nx, ny, nz = -gx / norm, -gy / norm, gz / norm

    lx, ly, lz = -0.48, -0.66, 0.57
    ndotl = nx * lx + ny * ly + nz * lz

    # Cast shadow down-right (dx=3, dy=4) + ambient occlusion ring around letter base.
    dil = cv2.GaussianBlur((tmask > 80).astype(np.float32), (0, 0), sigmaX=2.6)
    ao = 1.0 - 0.42 * np.clip(dil - height_map, 0.0, 1.0)
    shadow_shift = np.zeros((h, w), dtype=np.float32)
    shadow_shift[4:, 3:] = (tmask[:-4, :-3] > 127).astype(np.float32)
    shadow_blur = cv2.GaussianBlur(shadow_shift, (0, 0), sigmaX=2.2)
    cast_shadow = 1.0 - 0.48 * np.clip(shadow_blur - height_map, 0.0, 1.0)

    grain_full = np.zeros((h, w), dtype=np.float32)
    grain_full[426:588, 230:794] = iron_grain[:, :, 0] * 0.45
    base_f = clean_iron.astype(np.float32) * (ao * cast_shadow)[:, :, None]
    raised_metal = np.stack([
        128 + ndotl * 60 + grain_full,
        134 + ndotl * 62 + grain_full,
        142 + ndotl * 64 + grain_full,
    ], axis=2)
    raise_alpha = np.clip(height_map * 1.6, 0.0, 1.0)[:, :, None]
    embossed = np.clip(base_f * (1.0 - raise_alpha) + raised_metal * raise_alpha, 0, 255).astype(np.uint8)

    out_rgb = np.where(allow_mask[:, :, None] > 0, embossed, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_elevator_panel(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#329 concorde-hotel-kl: Clean button rings/circles + brushed-steel engraved bottom plate."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    ink_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)

    # Clean exact circular/box areas for buttons:
    # 1) Top-left red ring (CALL/CANCEL) & top-center red ring (HOLD/OFF/ON/FIRE)
    ink_boxes = [
        ((244, 6, 294, 38), "bright", 188, 2),     # HOLD
        ((220, 38, 252, 92), "bright", 188, 2),    # OFF
        ((286, 38, 320, 92), "bright", 188, 2),    # ON
        ((240, 88, 296, 126), "bright", 188, 2),   # FIRE
        ((384, 804, 416, 856), "bright", 155, 2),  # STOP
        ((406, 788, 442, 826), "bright", 155, 2),  # RUN
    ]
    for box, mode, thr, dil in ink_boxes:
        l, t, r, b = box
        allow_mask[t:b, l:r] = 255
        ink_mask = np.maximum(ink_mask, make_ink_mask(rgb, box, mode, thr, dil))

    # Top-left red alarm button white arcs: erase curved CALL / CANCEL ink while keeping inner phone emblem.
    yy, xx = np.ogrid[:rgb.shape[0], :rgb.shape[1]]
    rr = np.sqrt((xx - 74.5) ** 2 + (yy - 64.5) ** 2)
    alarm_arcs = (
        (rr >= 13.5)
        & (rr <= 30.2)
        & (((yy >= 35) & (yy <= 53) & (xx >= 48) & (xx <= 102))
           | ((yy >= 76) & (yy <= 95) & (xx >= 48) & (xx <= 102)))
    )
    alarm_red = alarm_arcs & (rgb[:, :, 1] < 218) & ((rgb[:, :, 0].astype(int) - rgb[:, :, 1].astype(int)) > 8)
    alarm_mask = cv2.dilate(alarm_red.astype(np.uint8) * 255, np.ones((3, 3), np.uint8), iterations=2)
    alarm_mask = np.where(alarm_arcs, alarm_mask, 0).astype(np.uint8)
    allow_mask = np.maximum(allow_mask, alarm_arcs.astype(np.uint8) * 255)
    ink_mask = np.maximum(ink_mask, alarm_mask)

    restored = inpaint_rgb(rgb, ink_mask, radius=2.5)

    # White circular buttons: clean inside exact white circle disks (leaving bevel edge intact!).
    white_buttons = [
        ((199, 717), 20, "ОТКР.\nДВЕРИ", "sans", 8, 5),    # DOOR OPEN (measured x=175..223, y=681..753)
        ((427, 718), 20, "ЗАКР.\nДВЕРИ", "sans", 8, 5),    # DOOR CLOSE (measured x=403..451, y=683..753)
        ((199, 830), 20, "ТРЕВОГА", "sans", 9, 5),          # ALARM (measured x=175..222, y=795..865)
    ]
    for (cx, cy), rad, _, _, _, _ in white_buttons:
        yy, xx = np.ogrid[:rgb.shape[0], :rgb.shape[1]]
        disk = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (rad ** 2)
        allow_mask[disk] = 255
        # Smooth ivory white matching button surface brightness
        clean_iv = tuple(int(v) for v in np.percentile(rgb[cy - rad:cy + rad, cx - rad:cx + rad], 85, axis=(0, 1)))
        restored[disk] = clean_iv

    # Bottom brushed-metal plaque (138..374, 910..982): horizontal directional blur preserves brushed specular!
    pl, pt, pr, pb = (138, 910, 374, 982)
    allow_mask[pt:pb, pl:pr] = 255
    plate_roi = rgb[pt:pb, pl:pr]
    plate_clean = cv2.medianBlur(plate_roi, 11)
    plate_brushed = cv2.GaussianBlur(plate_clean, (39, 3), 0)
    restored[pt:pb, pl:pr] = plate_brushed

    canvas = Image.fromarray(restored, "RGB")
    ivory = (244, 238, 224)
    red_ink = (155, 58, 56)
    dark_ink = (36, 36, 34)

    # Red-ring labels
    draw_text_in_box(canvas, (56, 38, 93, 49), "ВЫЗОВ", fonts, "sans", 7, 4, fill=red_ink, pad_x=1, pad_y=0)
    draw_text_in_box(canvas, (54, 80, 95, 91), "ОТМЕНА", fonts, "sans", 7, 4, fill=red_ink, pad_x=1, pad_y=0)
    draw_text_in_box(canvas, (244, 8, 294, 34), "УДЕРЖ.", fonts, "sans", 7, 4, fill=ivory, pad_x=1, pad_y=0)
    draw_text_in_box(canvas, (240, 92, 294, 120), "ПОЖАР", fonts, "sans", 7, 4, fill=ivory, pad_x=1, pad_y=0)
    draw_text_in_box(canvas, (406, 792, 440, 822), "ПУСК", fonts, "sans", 6, 4, fill=ivory, pad_x=1, pad_y=0)

    # Rotated labels on ring & keyhole
    for box, txt, ang in [((222, 42, 248, 88), "ВЫКЛ", 90), ((288, 42, 316, 88), "ВКЛ", -90), ((386, 808, 412, 852), "СТОП", 90)]:
        l, t, r, b = box
        p = Image.new("RGBA", (r - l, b - t), (0, 0, 0, 0))
        draw_text_in_box(p, (0, 0, r - l, b - t), txt, fonts, "sans", 7, 4, fill=ivory + (255,), pad_x=0, pad_y=0)
        rot = p.rotate(ang, resample=Image.Resampling.BICUBIC, expand=False)
        canvas = Image.fromarray(paste_rgba_box(np.asarray(canvas, dtype=np.uint8), box, np.asarray(rot, dtype=np.uint8)), "RGB")

    # White circular buttons centered on disk
    for (cx, cy), rad, txt, fkey, msz, mnsz in white_buttons:
        draw_text_in_box(canvas, (cx - rad + 2, cy - rad + 4, cx + rad - 2, cy + rad - 4), txt, fonts, fkey, msz, mnsz, fill=dark_ink, spacing=0, pad_x=1, pad_y=1)

    # Engraved bottom metal plate with subtle top specular highlight
    draw_text_in_box(canvas, (146, 913, 366, 949), "ЛИФТ D1", fonts, "bahn", 20, 11, fill=dark_ink, axes=(700, 95), shadow=(0, 1, (220, 215, 200)), pad_x=2, pad_y=0)
    draw_text_in_box(canvas, (144, 949, 368, 978), "ГРУЗОПОДЪЁМНОСТЬ 1588 КГ", fonts, "bahn", 13, 7, fill=dark_ink, axes=(700, 85), shadow=(0, 1, (220, 215, 200)), pad_x=2, pad_y=0)

    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_detector(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#588 T_Detector00: Perspective-unwarp both olive strips, clean ink locally, warp monospace Russian back."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    allow_mask = np.zeros((h, w), dtype=np.uint8)

    strips = [
        # Upper olive tape (SEARCH MODE): keep orange rust spot at SW while erasing 100% of "SE"
        ([(146, 428), (246, 332), (276, 353), (178, 454)], 176, 42, (24, 4, 170, 38), "РЕЖИМ ПОИСКА", 17, 102),
        # Lower olive tape (DECAYING CORPSE): covers 100% of "D" and "E"
        ([(158, 502), (304, 348), (356, 384), (204, 548)], 256, 58, (6, 4, 250, 54), "РАЗЛОЖИВШИЙСЯ ТРУП", 18, 105),
    ]
    out_rgb = rgb.copy()
    for quad, rw, rh, tbox, txt, msz, dark_thr in strips:
        # Unwarp source strip cleanly to flat rw x rh
        dst_rect = np.array([[0, 0], [rw - 1, 0], [rw - 1, rh - 1], [0, rh - 1]], dtype=np.float32)
        src_quad = np.array(quad, dtype=np.float32)
        M_fwd = cv2.getPerspectiveTransform(src_quad, dst_rect)
        flat_src = cv2.warpPerspective(out_rgb, M_fwd, (rw, rh), flags=cv2.INTER_CUBIC)

        # Remove dark letters via local contrast + neutral dark threshold, protecting orange rust mark!
        ink_local = make_ink_mask(flat_src, (2, 2, rw - 2, rh - 2), "localdark", threshold=8, dilate=3)
        f_gray = cv2.cvtColor(flat_src, cv2.COLOR_RGB2GRAY)
        f_r = flat_src[:, :, 0].astype(int)
        f_g = flat_src[:, :, 1].astype(int)
        if dark_thr == 102:
            ink_abs = ((f_gray < dark_thr) & ((f_r - f_g) < 22)).astype(np.uint8) * 255
        else:
            ink_abs = (f_gray < dark_thr).astype(np.uint8) * 255
        ink_abs = cv2.dilate(ink_abs, np.ones((3, 3), np.uint8), iterations=3)
        ink = np.maximum(ink_local, ink_abs)
        flat_clean = inpaint_rgb(flat_src, ink, radius=3.0)

        # Render dark monospace text on transparent layer, blend slightly worn onto flat_clean.
        ov = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        draw_text_in_box(ov, tbox, txt, fonts, "mono", msz, 9, fill=(28, 32, 20, 235), pad_x=2, pad_y=1)
        flat_done = composite_rgba(flat_clean, np.asarray(ov, dtype=np.uint8))

        # Warp back with feathered quad alpha
        flat_rgba = np.dstack([flat_done, np.full((rh, rw), 255, dtype=np.uint8)])
        out_rgb, cmask = warp_rgba_quad(out_rgb, flat_rgba, quad, feather_mask=True)
        allow_mask = np.maximum(allow_mask, cmask)

    return _finish_image(image, orig, out_rgb), allow_mask


def localize_hotel_facade(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#380 T_HotelSign_00_BC: Pure cyan tiled wall (no windows!) + 3D extruded ОТЕЛЬ / ПОТТЕЛЬ."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    allow_mask = np.zeros((h, w), dtype=np.uint8)

    # 1) Upper dark fascia band behind HOLZATEI: y=476..644, x=18..960
    # Use clean shadowed glass tone (no right-side window reflection!) with subtle vertical shading + grain.
    allow_mask[476:644, 18:960] = 255
    fh, fw = 644 - 476, 960 - 18
    yy = np.linspace(0.0, 1.0, fh, dtype=np.float32)[:, None]
    # Dark edge top/bottom (11,17,20), subtle deep teal glass reflection in center (22,34,38).
    center_wave = np.maximum(0.0, np.sin(yy * np.pi)) ** 1.4
    fascia_rgb = np.zeros((fh, fw, 3), dtype=np.float32)
    fascia_rgb[:, :, 0] = 11.0 + 10.0 * center_wave
    fascia_rgb[:, :, 1] = 17.0 + 16.0 * center_wave
    fascia_rgb[:, :, 2] = 20.0 + 17.0 * center_wave
    rng = np.random.default_rng(380)
    fascia_rgb += rng.normal(0.0, 2.2, size=(fh, fw, 3)).astype(np.float32)
    fascia_patch = np.clip(fascia_rgb, 0, 255).astype(np.uint8)
    inner_feather = cv2.erode(allow_mask, np.ones((7, 7), np.uint8), iterations=1)
    rgb[476:644, 18:960] = fascia_patch
    rgb = feather_composite(orig[:, :, :3].copy(), rgb, inner_feather, blur_sigma=1.5)

    # 2) Lower cyan tiled wall behind POTTEL + its drop shadows: y=645..864, x=22..990
    allow_mask[645:864, 22:990] = 255
    # Pure cyan tiles verified at y=346..466 (zero windows!). Tile cleanly across y=645..864.
    clean_tiles = rgb[346:466, 22:990]
    rgb[645:864, 22:990] = tile_patch(clean_tiles, 864 - 645, 990 - 22)

    # Render 3D-extruded pink hotel letters (dark 3D side extrusion + front magenta neon face)
    canvas = Image.fromarray(rgb, "RGB")
    for box, txt, sz in [((20, 482, 956, 638), "ОТЕЛЬ", 132), ((30, 650, 970, 845), "ПОТТЕЛЬ", 130)]:
        l, t, r, b = box
        ov = Image.new("RGBA", (r - l, b - t), (0, 0, 0, 0))
        # Stacked 3D extrusion layers (dark teal/black side wall shifted down-right)
        for step in range(10, 0, -1):
            sh_col = (14, 20, 22, 235)
            draw_text_in_box(ov, (step, step, (r - l) + step, (b - t) + step), txt, fonts, "bahn", sz, 80, fill=sh_col, axes=(700, 92))
        draw_text_in_box(ov, (0, 0, r - l, b - t), txt, fonts, "bahn", sz, 80, fill=(224, 62, 108, 255), axes=(700, 92))
        ov_arr = apply_surface_wear(np.asarray(ov, dtype=np.uint8), np.asarray(canvas)[t:b, l:r], strength=0.22)
        canvas = Image.fromarray(paste_rgba_box(np.asarray(canvas, dtype=np.uint8), box, ov_arr), "RGB")

    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), orig[:, :, :3]).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_hool_sign(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#474 HoolSign: Perspective-unwarp vertical white blade panel + extruded magenta О/Т/Е/Л/Ь."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    quad = [(95, 20), (221, 30), (192, 888), (73, 870)]
    rw, rh = 136, 870

    # Smooth clean backlit white plastic panel with cool edge vignette (zero old letter shadow smudges).
    ux = np.linspace(-1.0, 1.0, rw, dtype=np.float32)[None, :]
    uy = np.linspace(-1.0, 1.0, rh, dtype=np.float32)[:, None]
    edge = np.clip(1.0 - 0.06 * (ux ** 4 + uy ** 8), 0.90, 1.0)
    flat_clean = np.zeros((rh, rw, 3), dtype=np.uint8)
    flat_clean[:, :, 0] = np.clip(248.0 * edge, 0, 255).astype(np.uint8)
    flat_clean[:, :, 1] = np.clip(249.0 * edge, 0, 255).astype(np.uint8)
    flat_clean[:, :, 2] = np.clip(252.0 * edge, 0, 255).astype(np.uint8)

    # Render vertical 3D-extruded magenta О / Т / Е / Л / Ь
    ov = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    draw_text_in_box(ov, (12, 24, rw - 6, rh - 14), "О\nТ\nЕ\nЛ\nЬ", fonts, "bahn", 132, 80, fill=(38, 22, 28, 225), spacing=6, axes=(700, 95))
    ov = ov.filter(ImageFilter.GaussianBlur(1.0))
    ov_front = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    draw_text_in_box(ov_front, (6, 18, rw - 12, rh - 20), "О\nТ\nЕ\nЛ\nЬ", fonts, "bahn", 132, 80, fill=(244, 14, 108, 255), spacing=6, axes=(700, 95))
    flat_done = composite_rgba(flat_clean, np.asarray(ov, dtype=np.uint8))
    flat_done = composite_rgba(flat_done, np.asarray(ov_front, dtype=np.uint8))

    flat_rgba = np.dstack([flat_done, np.full((rh, rw), 255, dtype=np.uint8)])
    out_rgb, allow_mask = warp_rgba_quad(rgb, flat_rgba, quad, feather_mask=True)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_destaurant02(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#585 T_Destaurant02: Perspective-unwarp tilted red lightbox + warm backlit white РЕСТОРАН."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    quad = [(158, 392), (820, 308), (820, 488), (154, 534)]
    rw, rh = 680, 168

    dst_rect = np.array([[0, 0], [rw - 1, 0], [rw - 1, rh - 1], [0, rh - 1]], dtype=np.float32)
    flat = cv2.warpPerspective(rgb, cv2.getPerspectiveTransform(np.array(quad, dtype=np.float32), dst_rect), (rw, rh), flags=cv2.INTER_CUBIC)
    bright = make_ink_mask(flat, (6, 6, rw - 6, rh - 6), "bright", threshold=145, dilate=3)
    flat_clean = inpaint_rgb(flat, bright, radius=4.5)

    ov = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    draw_text_in_box(ov, (18, 18, rw - 18, rh - 18), "РЕСТОРАН", fonts, "bahn", 132, 70, fill=(255, 240, 224, 248), axes=(700, 92))
    flat_done = composite_rgba(flat_clean, np.asarray(ov, dtype=np.uint8))
    flat_rgba = np.dstack([flat_done, np.full((rh, rw), 255, dtype=np.uint8)])
    out_rgb, allow_mask = warp_rgba_quad(rgb, flat_rgba, quad, feather_mask=True)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_paint_bucket(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#288 T_PaintBucket00: Curved cylindrical label on white bucket wall (protecting blue swoosh)."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    # Target box around APEX ULTIMA + subline (measured x=270..412, y=218..318)
    box = (266, 214, 416, 324)
    l, t, r, b = box
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    allow_mask[t:b, l:r] = 255

    # Erase neutral dark pixels only, preserving blue swoosh & orange/red paint drips!
    ink = make_ink_mask(rgb, box, "ticket_neutral", threshold=170, dilate=2)
    restored = inpaint_rgb(rgb, ink, radius=3.0)

    rw, rh = 136, 76
    ov = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    draw_text_in_box(ov, (0, 0, rw, 46), "АПЕКС\nУЛЬТИМА", fonts, "bahn", 21, 12, fill=(24, 30, 42, 245), spacing=0, axes=(700, 88))
    draw_text_in_box(ov, (0, 46, rw, 74), "ФАСАДНАЯ ЭМАЛЬ", fonts, "sans", 9, 5, fill=(40, 44, 52, 235), pad_x=2, pad_y=0)
    # Tilt upward slightly (-14 deg) + subtle cylinder curve matching bucket curvature!
    curved = warp_cylindrical_rgba(np.asarray(ov, dtype=np.uint8), bow_px=6.0, x_compress=0.06)
    tilted = Image.fromarray(curved, "RGBA").rotate(13, resample=Image.Resampling.BICUBIC, expand=True)
    # Center inside box
    tw, th = tilted.size
    px = l + ((r - l) - tw) // 2
    py = t + ((b - t) - th) // 2
    full_ov = Image.new("RGBA", rgb.shape[:2][::-1], (0, 0, 0, 0))
    full_ov.paste(tilted, (px, py), tilted)
    composed = composite_rgba(restored, np.asarray(full_ov, dtype=np.uint8))
    out_rgb = np.where(allow_mask[:, :, None] > 0, composed, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_can(image: Image.Image, path_id: int, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#532 T_Can00 & #627 T_Can01: Full-width ink cleanup + cylindrical downward arc + surface wear."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    allow_mask = np.zeros((h, w), dtype=np.uint8)

    if path_id == 532:
        boxes = [(274, 462, 766, 666), (274, 676, 736, 814)]
        ink = np.maximum(
            make_ink_mask(rgb, boxes[0], "dark", threshold=135, dilate=3),
            make_ink_mask(rgb, boxes[1], "dark", threshold=142, dilate=3),
        )
        restored = inpaint_rgb(rgb, ink, radius=3.5)
        for b in boxes:
            allow_mask[b[1]:b[3], b[0]:b[2]] = 255

        # Top main title: КАНТ (cylindrical arc bow_px=18)
        rw, rh = 420, 150
        ov1 = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        draw_text_in_box(ov1, (0, 0, rw, rh), "КАНТ", fonts, "impact", 132, 70, fill=(20, 52, 42, 238))
        c1 = warp_cylindrical_rgba(np.asarray(ov1, dtype=np.uint8), bow_px=18.0, x_compress=0.14)
        dest1 = (305, 480, 305 + c1.shape[1], 480 + c1.shape[0])
        allow_mask[dest1[1]:dest1[3], dest1[0]:dest1[2]] = 255
        c1 = apply_surface_wear(c1, restored[dest1[1]:dest1[3], dest1[0]:dest1[2]], strength=0.35)
        restored = paste_rgba_box(restored, dest1, c1)

        # Subtitle: КОТ В БАНКЕ (bow_px=15)
        rw2, rh2 = 400, 90
        ov2 = Image.new("RGBA", (rw2, rh2), (0, 0, 0, 0))
        draw_text_in_box(ov2, (0, 0, rw2, rh2), "КОТ В БАНКЕ", fonts, "bahn", 56, 30, fill=(22, 54, 45, 228), axes=(600, 88))
        c2 = warp_cylindrical_rgba(np.asarray(ov2, dtype=np.uint8), bow_px=15.0, x_compress=0.14)
        dest2 = (312, 686, 312 + c2.shape[1], 686 + c2.shape[0])
        allow_mask[dest2[1]:dest2[3], dest2[0]:dest2[2]] = 255
        c2 = apply_surface_wear(c2, restored[dest2[1]:dest2[3], dest2[0]:dest2[2]], strength=0.38)
        restored = paste_rgba_box(restored, dest2, c2)
    else:
        # #627 T_Can01 (CAINU inside white oval pill x=386..752, y=448..596)
        box = (386, 448, 752, 596)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        roi = rgb[448:596, 386:752]
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        rb = roi[:, :, 0].astype(int) - roi[:, :, 2].astype(int)
        sel = ((gray < 110) | ((gray < 172) & (rb < 28))).astype(np.uint8) * 255
        sel = cv2.dilate(sel, np.ones((3, 3), np.uint8), iterations=3)
        ink = np.zeros(rgb.shape[:2], dtype=np.uint8)
        ink[448:596, 386:752] = sel
        restored = inpaint_rgb(rgb, ink, radius=4.0)

        rw, rh = 340, 100
        ov = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        draw_text_in_box(ov, (0, 0, rw, rh), "КАЙНУ", fonts, "impact", 92, 52, fill=(18, 34, 30, 240))
        c = warp_cylindrical_rgba(np.asarray(ov, dtype=np.uint8), bow_px=10.0, x_compress=0.10)
        dest = (396, 474, 396 + c.shape[1], 474 + c.shape[0])
        allow_mask[dest[1]:dest[3], dest[0]:dest[2]] = 255
        c = apply_surface_wear(c, restored[dest[1]:dest[3], dest[0]:dest[2]], strength=0.30)
        restored = paste_rgba_box(restored, dest, c)

    out_rgb = np.where(allow_mask[:, :, None] > 0, restored, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_weathered_sign(image: Image.Image, path_id: int, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """Weathered signs (#339, #491, #522, #529) preserving 100% of rust, stains & speckles."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    allow_mask = np.zeros((h, w), dtype=np.uint8)

    if path_id == 339:
        # FOLLT blue/dark-blue letters over heavily rusted white metal
        box = (92, 220, 930, 578)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "toilet_blue", threshold=178, dilate=4)
        restored = inpaint_rgb(rgb, ink, radius=5.0)
        ov = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov, (0, 0, ov.width, ov.height), "ТУАЛЕТ", fonts, "impact", 260, 120, fill=(22, 56, 98, 242))
        ov_arr = apply_surface_wear(np.asarray(ov, dtype=np.uint8), restored[box[1]:box[3], box[0]:box[2]], strength=0.55)
        restored = paste_rgba_box(restored, box, ov_arr)

    elif path_id == 491:
        # Top dark chipped bar (POSTIL LIELST) & bottom white metal (TOTE)
        top_box = (112, 42, 986, 192)
        bot_box = (274, 842, 756, 982)
        allow_mask[top_box[1]:top_box[3], top_box[0]:top_box[2]] = 255
        allow_mask[bot_box[1]:bot_box[3], bot_box[0]:bot_box[2]] = 255
        ink = np.maximum(
            make_ink_mask(rgb, top_box, "bright", threshold=165, dilate=3),
            make_ink_mask(rgb, bot_box, "dark", threshold=140, dilate=3),
        )
        restored = inpaint_rgb(rgb, ink, radius=4.0)

        ov_top = Image.new("RGBA", (top_box[2] - top_box[0], top_box[3] - top_box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov_top, (0, 0, ov_top.width, ov_top.height), "ЖЕНСКИЙ", fonts, "bahn", 104, 56, fill=(236, 234, 224, 242), axes=(700, 88))
        ov_top_arr = apply_surface_wear(np.asarray(ov_top, dtype=np.uint8), restored[top_box[1]:top_box[3], top_box[0]:top_box[2]], strength=0.35)
        restored = paste_rgba_box(restored, top_box, ov_top_arr)

        ov_bot = Image.new("RGBA", (bot_box[2] - bot_box[0], bot_box[3] - bot_box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov_bot, (0, 0, ov_bot.width, ov_bot.height), "ТУАЛЕТ", fonts, "bahn", 112, 60, fill=(14, 14, 14, 245), axes=(700, 92))
        ov_bot_arr = apply_surface_wear(np.asarray(ov_bot, dtype=np.uint8), restored[bot_box[1]:bot_box[3], bot_box[0]:bot_box[2]], strength=0.30)
        restored = paste_rgba_box(restored, bot_box, ov_bot_arr)

    elif path_id == 529:
        # Top blue TOLLET over backlit vertical panel + bottom olive FLILF over dirty glass
        top_box = (58, 154, 968, 392)
        bot_box = (80, 392, 960, 886)
        allow_mask[top_box[1]:top_box[3], top_box[0]:top_box[2]] = 255
        allow_mask[bot_box[1]:bot_box[3], bot_box[0]:bot_box[2]] = 255
        ink = np.maximum(
            make_ink_mask(rgb, top_box, "blue", threshold=160, dilate=3),
            make_ink_mask(rgb, bot_box, "dark", threshold=168, dilate=3),
        )
        restored = inpaint_rgb(rgb, ink, radius=4.0)

        ov_top = Image.new("RGBA", (top_box[2] - top_box[0], top_box[3] - top_box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov_top, (0, 0, ov_top.width, ov_top.height), "ТУАЛЕТ", fonts, "impact", 230, 120, fill=(0, 36, 198, 242))
        ov_top_arr = apply_surface_wear(np.asarray(ov_top, dtype=np.uint8), restored[top_box[1]:top_box[3], top_box[0]:top_box[2]], strength=0.45)
        restored = paste_rgba_box(restored, top_box, ov_top_arr)

        ov_bot = Image.new("RGBA", (bot_box[2] - bot_box[0], bot_box[3] - bot_box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov_bot, (0, 0, ov_bot.width, ov_bot.height), "ТЯНИ", fonts, "impact", 360, 160, fill=(134, 124, 68, 232))
        ov_bot_arr = apply_surface_wear(np.asarray(ov_bot, dtype=np.uint8), restored[bot_box[1]:bot_box[3], bot_box[0]:bot_box[2]], strength=0.58)
        restored = paste_rgba_box(restored, bot_box, ov_bot_arr)

    else:  # 522 T_Bleach00 (preserve orange stripes while erasing dark strokes to cream boundary!)
        box = (304, 448, 656, 750)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        roi = rgb[448:750, 304:656]
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        orange = (roi[:, :, 0].astype(int) - roi[:, :, 2].astype(int)) > 40
        sel = ((gray < 168) & (~orange)).astype(np.uint8) * 255
        sel = cv2.dilate(sel, np.ones((3, 3), np.uint8), iterations=3)
        sel = np.where(~orange, sel, 0).astype(np.uint8)
        ink = np.zeros((h, w), dtype=np.uint8)
        ink[448:750, 304:656] = sel
        restored = inpaint_rgb(rgb, ink, radius=4.0)
        ov = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov, (8, 6, ov.width - 8, ov.height - 6), "БЛИЧ\nБАЧ", fonts, "impact", 132, 68, fill=(16, 20, 30, 236), spacing=2)
        ov_arr = apply_surface_wear(np.asarray(ov, dtype=np.uint8), restored[box[1]:box[3], box[0]:box[2]], strength=0.42)
        restored = paste_rgba_box(restored, box, ov_arr)

    out_rgb = np.where(allow_mask[:, :, None] > 0, restored, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_ciggies(image: Image.Image, path_id: int, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """All 9 cigarette packs (#306, #405, #414, #512, #514, #598, #612, #632, #655) with full erasure & perspective."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    h, w, _ = rgb.shape
    allow_mask = np.zeros((h, w), dtype=np.uint8)
    out = rgb.copy()

    if path_id == 306:
        # Top black lid (КЛУМЕНСИКА), red band (ЛЕЕНОГРРА), middle black (Легси)
        top_quad = [(350, 102), (710, 96), (710, 152), (350, 156)]
        mid_quad = [(302, 174), (748, 172), (748, 258), (302, 260)]
        bot_quad = [(325, 294), (725, 290), (725, 424), (325, 426)]
        # Clean backgrounds smoothly
        allow_mask[96:158, 345:715] = 255
        out[96:158, 345:715] = (24, 23, 21)
        ink_mid = make_ink_mask(out, (300, 170, 750, 262), "bright", threshold=170, dilate=3)
        allow_mask[170:262, 300:750] = 255
        out = inpaint_rgb(out, ink_mid, radius=4.5)
        ink_bot = make_ink_mask(out, (320, 290, 730, 428), "bright", threshold=155, dilate=4)
        allow_mask[290:428, 320:730] = 255
        out = inpaint_rgb(out, ink_bot, radius=5.0)

        out, cm = render_quad_text(out, top_quad, 360, 56, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "КЛУМЕНСИКА", fonts, "handwriting", 48, 24, (206, 26, 22, 255)))
        allow_mask = np.maximum(allow_mask, cm)
        out, cm = render_quad_text(out, mid_quad, 446, 86, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ЛЕЕНОГРРА", fonts, "serif_bold", 112, 60, (245, 232, 206, 255)))
        allow_mask = np.maximum(allow_mask, cm)
        out, cm = render_quad_text(out, bot_quad, 400, 132, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "Легси", fonts, "handwriting", 132, 70, (246, 236, 220, 255)))
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 405:
        # Gittefes on clean cream band
        box = (368, 320, 715, 406)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(out, box, "dark", threshold=140, dilate=3)
        out = inpaint_rgb(out, ink, radius=4.0)
        quad = [(372, 324), (710, 322), (710, 402), (372, 404)]
        out, cm = render_quad_text(out, quad, 340, 80, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ГИТТЕФЕС", fonts, "serif_bold", 118, 60, (20, 17, 17, 255)))
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 414:
        # LONECRDIA on upper charcoal face
        box = (176, 128, 650, 256)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(out, box, "bright", threshold=150, dilate=3)
        out = inpaint_rgb(out, ink, radius=4.0)
        quad = [(186, 136), (642, 130), (642, 248), (186, 252)]
        out, cm = render_quad_text(out, quad, 460, 120, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ЛОНЕКРДИА", fonts, "serif_bold", 128, 64, (234, 230, 218, 255)))
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 512:
        # Legrardaz: full front width x=322..748 (zero trailing z!), keeping gold emblem & stripes intact!
        box = (322, 480, 748, 616)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(out, box, "bright", threshold=105, dilate=3)
        out = inpaint_rgb(out, ink, radius=4.0)
        quad = [(334, 486), (738, 482), (738, 612), (334, 614)]
        out, cm = render_quad_text(out, quad, 410, 128, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ЛЕГРАРДАЗ", fonts, "bahn", 128, 60, (244, 237, 220, 255), axes=(600, 82)))
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 514:
        # LONGARD: full front width x=306..818, y=2..154 (zero trailing D!)
        box = (306, 2, 818, 154)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(out, box, "bright", threshold=110, dilate=3)
        out = inpaint_rgb(out, ink, radius=4.5)
        quad = [(316, 8), (806, 4), (806, 146), (316, 150)]
        out, cm = render_quad_text(out, quad, 490, 140, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ЛОНГАРД", fonts, "bahn", 160, 70, (236, 232, 216, 255), axes=(700, 85)))
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 598:
        # LERRAR (upper black x=330..708) & LLENEBOR (middle cream x=376..682) -> zero leftover R!
        b1 = (330, 224, 708, 338)
        b2 = (376, 408, 682, 484)
        allow_mask[b1[1]:b1[3], b1[0]:b1[2]] = 255
        allow_mask[b2[1]:b2[3], b2[0]:b2[2]] = 255
        ink = np.maximum(
            make_ink_mask(out, b1, "bright", threshold=135, dilate=3),
            make_ink_mask(out, b2, "dark", threshold=140, dilate=3),
        )
        out = inpaint_rgb(out, ink, radius=4.0)
        out, cm = render_quad_text(out, [(340, 232), (702, 236), (702, 332), (340, 328)], 370, 96, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ЛЕРРАР", fonts, "bahn", 150, 65, (237, 231, 214, 255), axes=(700, 88)))
        allow_mask = np.maximum(allow_mask, cm)
        out, cm = render_quad_text(out, [(384, 416), (674, 419), (674, 476), (384, 473)], 290, 58, lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "ЛЛЕНЕБОР", fonts, "bahn", 86, 40, (22, 22, 22, 255), axes=(700, 85)))
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 612:
        # CIGARETTES: restore clean vertical stripes above/below white ribbon & fill full ribbon (x=322..755)
        allow_mask[410:605, 320:758] = 255
        # Sample clean vertical stripes from y=390..410 (above) and y=605..625 (below)
        top_stripe = np.median(out[386:408, 320:758], axis=0).astype(np.uint8)
        bot_stripe = np.median(out[606:626, 320:758], axis=0).astype(np.uint8)
        out[410:490, 320:758] = np.repeat(top_stripe[None, :, :], 80, axis=0)
        out[540:605, 320:758] = np.repeat(bot_stripe[None, :, :], 65, axis=0)
        # Clean slanted white ribbon across front (x=322..715) & shaded side (x=715..755)
        front_poly = np.array([[322, 444], [715, 464], [715, 578], [322, 558]], dtype=np.int32)
        side_poly = np.array([[715, 464], [755, 475], [755, 588], [715, 578]], dtype=np.int32)
        cv2.fillConvexPoly(out, front_poly, (246, 246, 246))
        cv2.fillConvexPoly(out, side_poly, (218, 218, 218))
        out, cm = render_quad_text(
            out, [(328, 448), (708, 468), (708, 574), (328, 554)], 380, 106,
            lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "СИГАРЕТЫ", fonts, "impact", 180, 75, (18, 18, 18, 255)),
        )
        allow_mask = np.maximum(allow_mask, cm)

    elif path_id == 632:
        # Cinteres tilted dark blue lid: clean all white flourishes/text & perspective-warp serif СИНТАРЕС
        lid_poly = np.array([[254, 94], [748, 172], [712, 366], [238, 276]], dtype=np.int32)
        lid_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillConvexPoly(lid_mask, lid_poly, 255)
        allow_mask = np.maximum(allow_mask, lid_mask)
        bright = (((cv2.cvtColor(out, cv2.COLOR_RGB2GRAY) > 85) | (out[:, :, 0] > 75)) & (lid_mask > 0)).astype(np.uint8) * 255
        bright = cv2.dilate(bright, np.ones((3, 3), np.uint8), iterations=4)
        out = inpaint_rgb(out, bright, radius=6.0)
        out, cm = render_quad_text(
            out, [(268, 146), (712, 214), (692, 330), (252, 256)], 450, 118,
            lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "СИНТАРЕС", fonts, "serif_bold", 156, 70, (246, 239, 222, 255)),
        )
        allow_mask = np.maximum(allow_mask, cm)

    else:  # 655 T_Ciggies05 (NiC / Caghels)
        b1 = (242, 86, 392, 250)
        b2 = (426, 72, 758, 206)
        allow_mask[b1[1]:b1[3], b1[0]:b1[2]] = 255
        allow_mask[b2[1]:b2[3], b2[0]:b2[2]] = 255
        ink1 = make_ink_mask(out, b1, "localbright", threshold=16, dilate=3)
        ink2 = make_ink_mask(out, b2, "localdark", threshold=16, dilate=4)
        out = inpaint_rgb(out, np.maximum(ink1, ink2), radius=3.5)
        out, cm = render_quad_text(
            out, [(248, 96), (386, 98), (386, 208), (248, 206)], 140, 110,
            lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "Ник", fonts, "serif_reg", 104, 50, (234, 229, 198, 255)),
        )
        allow_mask = np.maximum(allow_mask, cm)
        out, cm = render_quad_text(
            out, [(434, 78), (750, 84), (750, 176), (434, 170)], 320, 96,
            lambda im: draw_text_in_box(im, (0, 0, im.width, im.height), "Кагнетс", fonts, "serif_bold", 148, 60, (26, 22, 24, 255)),
        )
        allow_mask = np.maximum(allow_mask, cm)

    out_rgb = np.where(allow_mask[:, :, None] > 0, out, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_books_collage(image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """#493 T_Bouquinsrefs00: Full Russian localization across all visible book covers & spines."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    out = rgb.copy()

    # Book 1 (Strugatsky): header + spine (cover full KY while keeping yellow S&F badge!)
    b_strug_top = (220, 58, 386, 78)
    b_strug_main = (220, 78, 412, 134)
    for bx in (b_strug_top, b_strug_main, (195, 52, 216, 392)):
        allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255
    ink = np.maximum(
        make_ink_mask(out, b_strug_top, "bright", 140, 2),
        make_ink_mask(out, b_strug_main, "bright", 130, 3),
    )
    ink = np.maximum(ink, make_ink_mask(out, (195, 52, 216, 392), "bright", 140, 2))

    # Book 2 (Harrison): leaf-preserving dark ink cleanup on title/subtitle; clean full cloth spine x=654..697
    b_har_title = (712, 86, 912, 304)
    b_har_sub = (712, 304, 912, 360)
    b_har_spine = (654, 28, 697, 396)
    for bx in (b_har_title, b_har_sub, b_har_spine):
        allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255
    ink = np.maximum(ink, make_ink_mask(out, b_har_title, "dark", 125, 3))
    ink = np.maximum(ink, make_ink_mask(out, b_har_sub, "localdark", 14, 3))
    har_red = ((out[304:360, 712:912, 0].astype(int) - out[304:360, 712:912, 2].astype(int)) > 45).astype(np.uint8) * 255
    har_red = cv2.dilate(har_red, np.ones((3, 3), np.uint8), iterations=3)
    ink[304:360, 712:912] = np.maximum(ink[304:360, 712:912], har_red)

    # Book 4 (Orwell 1984): GEORGE ORWELL header & full red spine x=464..494 below gold border
    b_orwell = (500, 500, 576, 518)
    b_orwell_sp = (464, 492, 494, 624)
    for bx in (b_orwell, b_orwell_sp):
        allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255

    # Book 5 (Jancovici white cover): pure white clean boxes protecting green globe (x=368..424, y=775..837)
    b_janc1 = (388, 645, 575, 702)
    b_janc2 = (355, 704, 575, 766)
    b_janc3 = (425, 766, 578, 838)
    b_janc4 = (396, 838, 578, 864)
    for bx in (b_janc1, b_janc2, b_janc3, b_janc4):
        allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255

    # Book 6 (Dostoevsky blue spine) & Book 7 (Voltaire olive spines)
    b_dost = (636, 548, 691, 596)
    b_volt1 = (718, 504, 776, 534)
    b_volt2 = (790, 504, 850, 534)
    for bx in (b_dost, b_volt1, b_volt2):
        allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255
    ink = np.maximum(ink, make_ink_mask(out, b_dost, "bright", 118, 3))

    # Book 3 (Jared Diamond 3 spines)
    b_d1_t = (34, 492, 100, 660)
    b_d1_a = (36, 682, 100, 745)
    b_d2_t = (128, 476, 198, 706)
    b_d2_a = (124, 770, 200, 845)
    b_d3_t = (218, 474, 290, 654)
    b_d3_m = (226, 667, 286, 702)
    b_d3_a = (226, 712, 284, 842)
    for bx in (b_d1_t, b_d1_a, b_d2_t, b_d2_a, b_d3_t, b_d3_m, b_d3_a):
        allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255
    for bx, mode, thr in [
        (b_d1_t, "dark", 130), (b_d1_a, "dark", 130),
        (b_d2_t, "localbright", 16), (b_d2_a, "bright", 135),
        (b_d3_t, "bright", 105),
    ]:
        ink = np.maximum(ink, make_ink_mask(out, bx, mode, thr, 3))
    ink = np.maximum(ink, make_ink_mask(out, b_d3_m, "localdark", 14, 2))
    d3_roi = out[b_d3_a[1]:b_d3_a[3], b_d3_a[0]:b_d3_a[2]]
    d3_gray = cv2.cvtColor(d3_roi, cv2.COLOR_RGB2GRAY)
    d3_bg = cv2.GaussianBlur(d3_gray.astype(np.float32), (0, 0), sigmaX=5.0)
    d3_red = d3_roi[:, :, 0].astype(int) - d3_roi[:, :, 1].astype(int)
    d3_mask = ((d3_gray < (d3_bg - 12)) | (d3_red > 18)).astype(np.uint8) * 255
    ink[b_d3_a[1]:b_d3_a[3], b_d3_a[0]:b_d3_a[2]] = np.maximum(
        ink[b_d3_a[1]:b_d3_a[3], b_d3_a[0]:b_d3_a[2]],
        cv2.dilate(d3_mask, np.ones((3, 3), np.uint8), iterations=2),
    )

    out = inpaint_rgb(out, ink, radius=3.5)

    # Clean direct fills for dark/solid book panels where inpaint smears tiny text.
    out[28:394, 654:697] = (36, 38, 42)          # Harrison spine cloth
    out[500:518, 500:576] = (28, 22, 20)          # Orwell cover dark band under arch
    out[492:624, 464:494] = (204, 18, 26)         # Orwell red spine
    out[548:596, 636:691] = cv2.GaussianBlur(out[548:596, 636:691], (9, 3), 0)  # Dostoevsky smooth cloth
    for jl, jt, jr, jb in (b_janc1, b_janc2, b_janc3, b_janc4):
        out[jt:jb, jl:jr] = (255, 255, 255)
    for vl, vt, vr, vb in (b_volt1, b_volt2):
        out[vt:vb, vl:vr] = (34, 36, 32)

    canvas = Image.fromarray(out, "RGB")

    # Draw localized Russian book covers & spines
    draw_text_in_box(canvas, (222, 60, 384, 78), "АРКАДИЙ И БОРИС", fonts, "bahn", 10, 6, (238, 232, 210), axes=(600, 90), pad_x=1, pad_y=0)
    draw_text_in_box(canvas, (222, 78, 410, 108), "СТРУГАЦКИЕ", fonts, "bahn", 22, 10, (242, 238, 224), axes=(700, 88), pad_x=1, pad_y=0)
    draw_text_in_box(canvas, (222, 106, 410, 128), "ПИКНИК НА ОБОЧИНЕ", fonts, "bahn", 12, 6, (228, 224, 210), axes=(600, 85), pad_x=1, pad_y=0)

    draw_text_in_box(canvas, b_har_title, "ПОДВИНЬТЕСЬ!\nПОДВИНЬТЕСЬ!", fonts, "impact", 42, 14, (22, 21, 20), align="left", spacing=2, pad_x=2, pad_y=2)
    draw_text_in_box(canvas, (714, 304, 910, 326), "Роман о жизни в 1999 году", fonts, "sans_reg", 11, 6, (44, 36, 30), align="left", pad_x=2, pad_y=0)
    draw_text_in_box(canvas, (714, 328, 910, 356), "ГАРРИ ГАРРИСОН", fonts, "bahn", 18, 8, (198, 56, 44), align="left", axes=(700, 85), pad_x=2, pad_y=0)

    draw_text_in_box(canvas, b_orwell, "ДЖОРДЖ ОРУЭЛЛ", fonts, "serif_bold", 10, 5, (236, 224, 198), pad_x=1, pad_y=0)
    draw_text_in_box(canvas, b_janc1, "Жан-Марк\nЖанковиси", fonts, "sans", 16, 8, (18, 18, 18), align="right", spacing=0, pad_x=2, pad_y=2)
    draw_text_in_box(canvas, b_janc2, "Спите спокойно\nдо 2100 года", fonts, "serif_reg", 17, 8, (200, 40, 36), align="right", spacing=0, pad_x=2, pad_y=2)
    draw_text_in_box(canvas, (426, 768, 576, 836), "и другие\nзаблуждения\nо климате", fonts, "sans", 13, 6, (16, 82, 118), align="center", spacing=0, pad_x=2, pad_y=1)
    draw_text_in_box(canvas, (400, 838, 576, 862), "и энергии", fonts, "sans", 13, 6, (16, 82, 118), align="center", spacing=0, pad_x=2, pad_y=1)

    draw_text_in_box(canvas, (636, 549, 690, 567), "ДОСТОЕВСКИЙ", fonts, "bahn", 10, 5, (226, 220, 206), axes=(600, 75), pad_x=0, pad_y=0)
    draw_text_in_box(canvas, (638, 572, 690, 594), "ИДИОТ", fonts, "serif_bold", 12, 6, (232, 228, 214), pad_x=1, pad_y=0)
    draw_text_in_box(canvas, b_volt1, "Вольтер", fonts, "serif_reg", 14, 6, (218, 200, 148), pad_x=2, pad_y=1)
    draw_text_in_box(canvas, b_volt2, "Вольтер", fonts, "serif_reg", 14, 6, (218, 200, 148), pad_x=2, pad_y=1)

    draw_text_in_box(canvas, b_d1_t, "РУЖЬЯ,\nМИКРОБЫ\nИ СТАЛЬ", fonts, "serif_bold", 16, 7, (36, 26, 18), spacing=2, pad_x=2, pad_y=2)
    draw_text_in_box(canvas, b_d1_a, "Джаред\nДаймонд", fonts, "serif_reg", 13, 6, (36, 26, 18), spacing=1, pad_x=2, pad_y=2)
    draw_text_in_box(canvas, b_d2_a, "ДЖАРЕД\nДАЙМОНД", fonts, "serif_reg", 13, 6, (210, 205, 195), spacing=1, pad_x=2, pad_y=2)
    draw_text_in_box(canvas, (227, 668, 285, 700), "ЧЕМУ УЧАТ\nДРЕВНИЕ\nОБЩЕСТВА?", fonts, "sans", 9, 4, (44, 38, 32), spacing=0, pad_x=1, pad_y=1)

    # Vertical spines (rotated -90 deg)
    out = np.asarray(canvas, dtype=np.uint8)
    for box, txt, fkey, msz, col in [
        ((195, 58, 216, 388), "СТРУГАЦКИЕ · ПИКНИК НА ОБОЧИНЕ", "bahn", 11, (240, 236, 220, 255)),
        ((657, 34, 694, 388), "ПОДВИНЬТЕСЬ! · ГАРРИ ГАРРИСОН", "bahn", 15, (238, 234, 222, 255)),
        ((466, 494, 493, 622), "ДЖ. ОРУЭЛЛ · 1984", "serif_bold", 11, (238, 226, 200, 255)),
        ((134, 480, 192, 700), "КОЛЛАПС", "bahn", 36, (216, 198, 152, 240)),
        ((226, 480, 282, 646), "МИР ДО\nВЧЕРАШНЕГО", "bahn", 20, (235, 226, 198, 245)),
        ((228, 714, 282, 838), "Джаред\nДаймонд", "serif_reg", 24, (118, 36, 34, 245)),
    ]:
        l, t, r, b = box
        # Render horizontally in (b-t) x (r-l) then rotate -90 deg
        horiz = Image.new("RGBA", (b - t, r - l), (0, 0, 0, 0))
        draw_text_in_box(horiz, (2, 1, horiz.width - 2, horiz.height - 1), txt, fonts, fkey, msz, 6, fill=col, spacing=0, pad_x=2, pad_y=1)
        rot = horiz.rotate(-90, resample=Image.Resampling.BICUBIC, expand=True)
        out = paste_rgba_box(out, box, np.asarray(rot, dtype=np.uint8))

    out_rgb = np.where(allow_mask[:, :, None] > 0, out, rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def localize_simple_sign(image: Image.Image, path_id: int, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    """Remaining flat/clean signs, LCDs, wine bottle & train signs (#307, #422, #545, #555, #557, #576, #613, #622, #661)."""
    orig = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = orig[:, :, :3].copy()
    allow_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)

    if path_id == 307:
        # trainstation yellow sign -> СТАНЦИЯ
        box = (10, 275, 1014, 505)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "dark", 115, 4)
        restored = inpaint_rgb(rgb, ink, 5.0)
        canvas = Image.fromarray(restored, "RGB")
        draw_text_in_box(canvas, (18, 282, 1006, 498), "СТАНЦИЯ", fonts, "bahn", 200, 100, fill=(8, 22, 50), axes=(700, 92))
    elif path_id == 422:
        box = (12, 446, 1012, 656)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "dark", 110, 4)
        restored = inpaint_rgb(rgb, ink, 5.0)
        canvas = Image.fromarray(restored, "RGB")
        draw_text_in_box(canvas, (20, 452, 1004, 650), "СТАНЦИЯ", fonts, "bahn", 196, 100, fill=(14, 13, 13), axes=(700, 92))
    elif path_id == 555:
        box = (20, 366, 1004, 560)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "dark", 125, 4)
        restored = inpaint_rgb(rgb, ink, 5.0)
        canvas = Image.fromarray(restored, "RGB")
        draw_text_in_box(canvas, (28, 372, 996, 554), "СТАНЦИЯ", fonts, "bahn", 170, 90, fill=(14, 14, 14), axes=(600, 95))
    elif path_id == 557:
        box = (590, 312, 1425, 632)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "dark", 120, 4)
        restored = inpaint_rgb(rgb, ink, 5.0)
        ov = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        draw_text_in_box(ov, (0, 0, ov.width, ov.height), "СТАНЦИЯ", fonts, "bahn", 172, 90, fill=(8, 20, 46, 242), axes=(700, 92))
        ov_arr = apply_surface_wear(np.asarray(ov, dtype=np.uint8), restored[box[1]:box[3], box[0]:box[2]], strength=0.28)
        canvas = Image.fromarray(paste_rgba_box(restored, box, ov_arr), "RGB")
    elif path_id == 613:
        box = (220, 738, 1930, 926)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "bright", 165, 3)
        restored = inpaint_rgb(rgb, ink, 5.0)
        canvas = Image.fromarray(restored, "RGB")
        draw_text_in_box(canvas, (236, 744, 1916, 920), "Ралтиайл Траннил", fonts, "sans", 156, 80, fill=(246, 241, 243))
    elif path_id == 545:
        box = (398, 174, 668, 274)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "bright", 162, 2)
        restored = inpaint_rgb(rgb, ink, 3.0)
        canvas = Image.fromarray(restored, "RGB")
        pale = (228, 236, 218)
        draw_text_in_box(canvas, (414, 180, 652, 216), "РЕЖИМ ПОИСКА", fonts, "mono", 24, 14, fill=pale)
        draw_text_in_box(canvas, (402, 218, 664, 266), "СЕКРЕТНЫЕ ПРЕДМЕТЫ", fonts, "mono", 26, 14, fill=pale)
    elif path_id == 576:
        # Neon DESTAURANT -> РЕСТОРАН with glowing orange-red bloom + bright core
        box = (118, 366, 896, 560)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "neon", 140, 5)
        restored = inpaint_rgb(rgb, ink, 5.5)
        glow_l = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        draw_text_in_box(glow_l, (0, 0, glow_l.width, glow_l.height), "РЕСТОРАН", fonts, "bahn", 148, 80, fill=(255, 86, 20, 220), stroke_width=6, stroke_fill=(255, 70, 10), axes=(700, 88))
        glow_l = glow_l.filter(ImageFilter.GaussianBlur(7.0))
        core_l = Image.new("RGBA", glow_l.size, (0, 0, 0, 0))
        draw_text_in_box(core_l, (0, 0, core_l.width, core_l.height), "РЕСТОРАН", fonts, "bahn", 148, 80, fill=(255, 240, 220, 255), stroke_width=2, stroke_fill=(255, 130, 45), axes=(700, 88))
        out = paste_rgba_box(restored, box, np.asarray(glow_l, dtype=np.uint8))
        out = paste_rgba_box(out, box, np.asarray(core_l, dtype=np.uint8))
        canvas = Image.fromarray(out, "RGB")
    elif path_id == 661:
        boxes = [
            ((30, 296, 464, 416), "МУРИАН", 84),
            ((482, 296, 996, 416), "МУТИОЛСТЕ", 80),
            ((20, 508, 616, 656), "МААРУРХОТ", 94),
        ]
        ink = np.zeros(rgb.shape[:2], dtype=np.uint8)
        for bx, _, _ in boxes:
            allow_mask[bx[1]:bx[3], bx[0]:bx[2]] = 255
            ink = np.maximum(ink, make_ink_mask(rgb, bx, "gold", 150, 9))
        restored = inpaint_rgb(rgb, ink, 6.0)
        out = restored.copy()
        for bx, txt, sz in boxes:
            glow = Image.new("RGBA", (bx[2] - bx[0], bx[3] - bx[1]), (0, 0, 0, 0))
            draw_text_in_box(glow, (0, 0, glow.width, glow.height), txt, fonts, "bahn", sz, 48, fill=(246, 200, 36, 175), axes=(700, 90))
            glow = glow.filter(ImageFilter.GaussianBlur(4.0))
            core = Image.new("RGBA", glow.size, (0, 0, 0, 0))
            draw_text_in_box(core, (0, 0, core.width, core.height), txt, fonts, "bahn", sz, 48, fill=(250, 232, 74, 255), axes=(700, 90))
            out = paste_rgba_box(out, bx, np.asarray(glow, dtype=np.uint8))
            out = paste_rgba_box(out, bx, np.asarray(core, dtype=np.uint8))
        canvas = Image.fromarray(out, "RGB")
    else:  # 622 Wine3 (HUBOO -> ХУБУ)
        box = (378, 620, 650, 748)
        allow_mask[box[1]:box[3], box[0]:box[2]] = 255
        ink = make_ink_mask(rgb, box, "dark", 140, 3)
        restored = inpaint_rgb(rgb, ink, 3.5)
        canvas = Image.fromarray(restored, "RGB")
        draw_text_in_box(canvas, (388, 630, 640, 738), "ХУБУ", fonts, "serif_reg", 86, 48, fill=(32, 30, 28))

    out_rgb = np.where(allow_mask[:, :, None] > 0, np.asarray(canvas, dtype=np.uint8), rgb).astype(np.uint8)
    return _finish_image(image, orig, out_rgb), allow_mask


def _finish_image(source_image: Image.Image, orig_rgba: np.ndarray, out_rgb: np.ndarray) -> Image.Image:
    if "A" in source_image.getbands():
        result = Image.fromarray(np.dstack((out_rgb, orig_rgba[:, :, 3])), "RGBA")
    else:
        result = Image.fromarray(out_rgb, "RGB")
    if result.size != source_image.size or result.mode != source_image.mode:
        raise RuntimeError(f"Output format changed: {result.mode} {result.size} != {source_image.mode} {source_image.size}")
    return result


# ---------------------------------------------------------------------------
# Verification & dispatch
# ---------------------------------------------------------------------------

MAP_SMALL = [
    ((372, 82, 656, 130), None, "РАЙОН КАНАЛА", 30, 20, "center", 2),
    ((554, 252, 652, 284), None, "ЦЕНТР", 17, 11, "center", 1),
    ((674, 229, 764, 262), (680, 236, 760, 260), "ПАРКОВКА", 15, 10, "center", 1),
    ((870, 253, 987, 288), (876, 258, 985, 284), "ПЛОЩАДКА", 15, 10, "center", 1),
    ((77, 345, 147, 378), None, "ДОМ", 16, 11, "left", 1),
    ((77, 394, 186, 427), (77, 394, 166, 427), "ИНФОЦЕНТР", 16, 10, "left", 1),
    ((78, 441, 177, 474), None, "СТАНЦИЯ", 16, 10, "left", 1),
    ((585, 454, 688, 491), (585, 464, 654, 484), "ЦЕРКОВЬ", 15, 10, "center", 1),
]

MAP_LARGE = [
    ((407, 111, 704, 166), None, "РАЙОН КАНАЛА", 35, 24, "center", 2),
    ((602, 338, 712, 381), (612, 346, 712, 369), "ЦЕНТР", 20, 13, "center", 1),
    ((732, 307, 842, 349), (738, 315, 836, 345), "ПАРКОВКА", 18, 11, "center", 1),
    ((944, 337, 1081, 383), (950, 346, 1076, 379), "ПЛОЩАДКА", 18, 11, "center", 1),
    ((83, 463, 171, 505), None, "ДОМ", 19, 13, "left", 1),
    ((82, 525, 206, 569), (82, 525, 190, 569), "ИНФОЦЕНТР", 19, 12, "left", 1),
    ((82, 584, 196, 636), None, "СТАНЦИЯ", 19, 12, "left", 1),
    ((619, 610, 737, 655), None, "ЦЕРКОВЬ", 18, 11, "center", 1),
]

PHOTO_NAMES = {
    335: "Тео",
    340: "Ашраф",
    371: "Альбин",
    387: "Ли Чонг",
    398: "Мина",
    477: "Тренер Тиммус",
    485: "Ивано",
    489: "Золушка",
    531: "Артур",
    567: "Жена",
    590: "Холфред",
    637: "Абуби",
    645: "Жанин",
}


def output_filename_for(spec: dict) -> str:
    pid = spec["path_id"]
    fixed = {
        430: "T_Map00.png",
        483: "T_Map00_1.png",
        560: "tutoPogo.png",
        641: "TutoScale.png",
    }
    if pid in fixed:
        return fixed[pid]
    return f"Texture_{pid}_{spec['name'].replace(' ', '_')}.png"


def localize_by_spec(spec: dict, image: Image.Image, fonts: dict[str, Path]) -> tuple[Image.Image, np.ndarray]:
    pid = spec["path_id"]
    if pid == 430:
        return localize_map(image, MAP_SMALL, fonts)
    if pid == 483:
        return localize_map(image, MAP_LARGE, fonts)
    if pid == 29:
        return localize_xbox_diagram(image, fonts)
    if pid == 30:
        return localize_chalkboard(image, fonts)
    if pid == 560:
        return localize_tuto_pogo(image, fonts)
    if pid == 641:
        return localize_tuto_scale(image, fonts)
    if pid == 663:
        return localize_ticket(image, False, fonts)
    if pid == 553:
        return localize_ticket(image, True, fonts)
    if pid in PHOTO_NAMES:
        return localize_portrait(image, PHOTO_NAMES[pid], pid, fonts)
    if pid == 651:
        return localize_manhole(image, fonts)
    if pid == 329:
        return localize_elevator_panel(image, fonts)
    if pid == 588:
        return localize_detector(image, fonts)
    if pid == 380:
        return localize_hotel_facade(image, fonts)
    if pid == 474:
        return localize_hool_sign(image, fonts)
    if pid == 585:
        return localize_destaurant02(image, fonts)
    if pid == 288:
        return localize_paint_bucket(image, fonts)
    if pid in (532, 627):
        return localize_can(image, pid, fonts)
    if pid in (339, 491, 522, 529):
        return localize_weathered_sign(image, pid, fonts)
    if pid in (306, 405, 414, 512, 514, 598, 612, 632, 655):
        return localize_ciggies(image, pid, fonts)
    if pid == 493:
        return localize_books_collage(image, fonts)
    if pid in (307, 422, 545, 555, 557, 576, 613, 622, 661):
        return localize_simple_sign(image, pid, fonts)
    raise KeyError(f"Unhandled texture path_id={pid}")


def load_verified_sources(data_dir: Path, specs: list[dict]) -> dict[tuple[str, int], Image.Image]:
    envs: dict[str, dict[int, object]] = {}
    for asset_name in sorted({s["asset"] for s in specs}):
        asset_path = data_dir / asset_name
        if not asset_path.is_file():
            raise FileNotFoundError(f"Missing game asset file: {asset_path}")
        env = UnityPy.load(str(asset_path))
        envs[asset_name] = {obj.path_id: obj for obj in env.objects if obj.type.name == "Texture2D"}

    loaded: dict[tuple[str, int], Image.Image] = {}
    for spec in specs:
        asset_name, pid = spec["asset"], spec["path_id"]
        obj = envs[asset_name].get(pid)
        if obj is None:
            raise RuntimeError(f"Texture2D {asset_name}#{pid} ({spec['name']!r}) was not found.")
        data = obj.read()
        actual_name = str(getattr(data, "m_Name", getattr(data, "name", "")))
        image = getattr(data, "image", None)
        if image is None:
            raise RuntimeError(f"Could not decode Texture2D {asset_name}#{pid} ({actual_name!r}).")
        image = image.copy()
        if actual_name != spec["name"] or image.size != (spec["width"], spec["height"]):
            raise RuntimeError(
                f"Texture mismatch at {asset_name}#{pid}: got {actual_name!r} {image.size}, "
                f"expected {spec['name']!r} {(spec['width'], spec['height'])}."
            )
        actual_hash = sha256_bytes(image.convert("RGBA").tobytes())
        if actual_hash != spec["rgba_sha256"]:
            raise RuntimeError(
                f"Pixel SHA-256 mismatch at {asset_name}#{pid} ({actual_name!r}): "
                f"{actual_hash} != {spec['rgba_sha256']}"
            )
        loaded[(asset_name, pid)] = image
    return loaded


def build(args: argparse.Namespace) -> int:
    game_dir = args.game_dir.resolve()
    data_dir = game_dir / "Babbdi_Data"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Babbdi_Data directory not found: {data_dir}")

    specs = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))["textures"]
    fonts = resolve_font_paths()
    sources = load_verified_sources(data_dir, specs)

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work_dir = args.work_dir.resolve() if args.work_dir else None
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict] = []
    expected_files: set[str] = set()

    for spec in specs:
        src_img = sources[(spec["asset"], spec["path_id"])]
        result, allow_mask = localize_by_spec(spec, src_img, fonts)

        # Strict invariance verification: alpha & outside-mask RGB must be bit-identical.
        src_rgba = np.asarray(src_img.convert("RGBA"), dtype=np.uint8)
        res_rgba = np.asarray(result.convert("RGBA"), dtype=np.uint8)
        if not np.array_equal(src_rgba[:, :, 3], res_rgba[:, :, 3]):
            raise RuntimeError(f"Alpha channel changed in {spec['asset']}#{spec['path_id']} ({spec['name']!r})")
        outside = allow_mask == 0
        if not np.array_equal(src_rgba[:, :, :3][outside], res_rgba[:, :, :3][outside]):
            raise RuntimeError(f"Pixels outside allow_mask changed in {spec['asset']}#{spec['path_id']} ({spec['name']!r})")

        out_name = output_filename_for(spec)
        expected_files.add(out_name)
        out_path = output / out_name
        result.save(out_path, format="PNG", optimize=False)

        if work_dir:
            stem = out_path.stem
            src_img.save(work_dir / f"{stem}_source.png", format="PNG")
            result.save(work_dir / f"{stem}_result.png", format="PNG")
            Image.fromarray(allow_mask, "L").save(work_dir / f"{stem}_allow_mask.png", format="PNG")

        manifest_entries.append({
            "file": out_name,
            "name": spec["name"],
            "contains": False,
            "width": result.width,
            "height": result.height,
        })
        print(f"{out_name}: {result.width}x{result.height}, sha256={sha256_bytes(out_path.read_bytes())[:16]}")

    # Remove stale PNG files in output directory that are no longer in the manifest.
    for existing in output.glob("*.png"):
        if existing.name not in expected_files:
            existing.unlink()

    manifest_entries.sort(key=lambda e: e["file"].casefold())
    manifest_path = output / "texture_manifest.json"
    manifest_path.write_text(json.dumps({"textures": manifest_entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(manifest_entries)} verified texture overrides to {output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", required=True, type=Path, help="BABBDI installation directory")
    parser.add_argument("--output", required=True, type=Path, help="Output directory for localized PNGs and texture_manifest.json")
    parser.add_argument("--work-dir", type=Path, help="Optional directory for source/result/mask audit images")
    args = parser.parse_args()
    try:
        return build(args)
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
