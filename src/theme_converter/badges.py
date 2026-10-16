"""Badge rendering retained from the local FrontendThemeConverter tools/badge.py."""

import os
from PIL import Image, ImageDraw, ImageFont


def pick_font(cfg, key):
    fonts = {name: os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", os.path.basename(value))
             for name, value in cfg["fonts"].items()}
    p = fonts.get(key) or fonts["arialbd"]
    if os.path.exists(p):
        return p
    for c in fonts.values():
        if os.path.exists(c):
            return c
    return None


def hex_rgba(h, opacity):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), opacity)


def rounded_frame_bounds(img):
    """Return the rounded background bounds, or None for a cutout image.

    The largest vertically continuous alpha region is considered first so an
    art panel can be separated from its logo below. A solid interior and
    similarly tapered top and bottom edges distinguish a rounded background
    from an irregular controller or logo silhouette.
    """
    alpha = img.convert("RGBA").getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= 128 else 0)
    width, height = mask.size
    _, occupied_rows = mask.getprojection()
    bands = []
    start = None
    for y, occupied in enumerate(occupied_rows):
        if occupied and start is None:
            start = y
        elif not occupied and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, height))

    candidates = []
    for top, bottom in bands:
        local = mask.crop((0, top, width, bottom)).getbbox()
        if local is None:
            continue
        x0, y0, x1, y1 = local
        y0 += top
        y1 += top
        region = mask.crop((x0, y0, x1, y1))
        region_width, region_height = region.size
        occupied = region.histogram()[255]
        row_width = lambda row: region.crop((0, row, region_width, row + 1)).histogram()[255]
        top_width = row_width(0)
        middle_width = row_width(region_height // 2)
        bottom_width = row_width(region_height - 1)
        fill_ratio = occupied / (region_width * region_height)
        rounded = (fill_ratio >= 0.97 and
                   middle_width / region_width >= 0.98 and
                   0.75 <= top_width / region_width <= 0.96 and
                   abs(top_width - bottom_width) / region_width <= 0.05)
        candidates.append((occupied, rounded, (x0, y0, x1, y1)))

    if not candidates:
        return None
    _, rounded, bounds = max(candidates, key=lambda item: item[0])
    return bounds if rounded else None


def draw_pill(img, p, cfg):
    """Draw a proportional top-right label inside a frame or canvas margin."""
    out = img.convert("RGBA").copy()
    width, height = out.size
    size_basis = max(width, height) + min(width, height) / 2
    frame = rounded_frame_bounds(out)
    if frame:
        left, top, right, bottom = frame
        anchor_basis = min(right - left, bottom - top)
        inset = round(anchor_basis * p.get("frame_margin_ratio", 0.035))
        x_right, y_top = right - inset, top + inset
    else:
        anchor_basis = min(width, height)
        inset = round(anchor_basis * p.get("margin", 0.045))
        x_right, y_top = width - inset, inset

    pill_height = max(1, round(size_basis * p["scale_h"] + p.get("size_add_px", 0)))
    if p.get("max_height_px") is not None:
        pill_height = min(pill_height, max(1, round(p["max_height_px"])))
    if "font_to_pill_ratio" in p:
        font_size = max(1, round(pill_height * p["font_to_pill_ratio"]))
    else:
        font_size = max(1, round(size_basis * p["font_ratio"]))
    font_path = pick_font(cfg, p.get("font", "arialbd"))
    font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    text = p.get("text", "HACK")
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    padding = round(pill_height * p.get("pill_padding_ratio", 0.38))
    pill_width = text_width + 2 * padding
    x_left = x_right - pill_width
    draw.rounded_rectangle((x_left, y_top, x_right - 1, y_top + pill_height - 1),
                           radius=pill_height // 2,
                           fill=hex_rgba(p["bg"], p["opacity"]))
    draw.text((x_left + (pill_width - text_width) / 2 - bbox[0],
               y_top + (pill_height - text_height) / 2 - bbox[1]),
              text, font=font, fill=hex_rgba(p["fg"], 255))
    out.alpha_composite(layer)
    return out


def draw_badge(img, p, cfg):
    """在原图副本上叠加角标；药丸按画布长边加半个短边缩放。"""
    if p.get("style") == "pill":
        return draw_pill(img, p, cfg)
    out = img.convert("RGBA").copy()
    w, h = out.size
    s = min(w, h)

    text = p.get("text", "HACK")
    style = p.get("style", "ribbon")
    pos = p.get("position", "top-left")
    align = p.get("align", "center")
    bw = p["scale_w"] * s
    bh = p["scale_h"] * s
    margin = p["margin"] * s
    fs = p["font_ratio"] * s
    bg = hex_rgba(p["bg"], p["opacity"])
    fg = hex_rgba(p["fg"], 255)
    radius = p.get("radius_ratio", 0.0) * s

    font_path = pick_font(cfg, p.get("font", "arialbd"))
    font = ImageFont.truetype(font_path, int(fs)) if font_path else ImageFont.load_default()

    if style == "bar":
        x0, y0, bw = 0.0, float(h - bh), w
    elif pos == "top-right":
        x0, y0 = w - margin - bw, margin
    elif pos == "bottom-left":
        x0, y0 = margin, h - margin - bh
    else:
        x0, y0 = margin, margin
    x0, y0 = float(x0), float(y0)

    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    if style == "ribbon":
        tail = bh * 0.55
        d.rectangle([x0, y0, x0 + bw, y0 + bh], fill=bg)
        d.polygon([(x0, y0), (x0 - tail, y0 + bh / 2), (x0, y0 + bh)], fill=bg)
    elif style == "badge":
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=radius, fill=bg)
    elif style == "bar":
        d.rectangle([x0, y0, x0 + bw, y0 + bh], fill=bg)

    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if style == "bar" and align == "center":
        tx = (w - tw) / 2 - bbox[0]
    elif style == "bar":
        tx = margin - bbox[0]
    else:
        tx = x0 + (bw - tw) / 2 - bbox[0]
    ty = y0 + (bh - th) / 2 - bbox[1]

    stroke_w = int(p.get("stroke_ratio", 0) * s)
    if stroke_w > 0 and p.get("stroke"):
        d.text((tx, ty), text, font=font, fill=fg,
               stroke_width=stroke_w, stroke_fill=hex_rgba(p["stroke"], 255))
    else:
        d.text((tx, ty), text, font=font, fill=fg)

    out.alpha_composite(layer)
    return out

