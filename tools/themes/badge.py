# -*- coding: utf-8 -*-
"""角标实验台：在源主题图上叠加角标，按 config/badge_params.json 生成候选图。

每轮实验输出到独立目录，并自动存一份参数快照，便于事后回溯"这张图是哪套参数画的"。

用法:
    python tools/badge.py                      # 输出到 lab/_current
    python tools/badge.py --round r02-x        # 输出到 lab/r02-x
    python tools/badge.py --cand C_badge_dark  # 只渲染指定候选
输出:
    lab/<round>/base_<system>.png       底图
    lab/<round>/ref_pg_<system>.png     canvas-PG 参考图
    lab/<round>/cand_<候选>_<tag>.png   各候选 × 各样本
    lab/<round>/_params_snapshot.json   本轮参数快照
    lab/<round>/_last.txt               本轮明细
"""
import argparse
import json
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, path, profile_path, theme_profile  # noqa: E402

CFG_REL = "tools/themes/config/badge_params.json"


def load_cfg():
    return load_json(CFG_REL)


def pick_font(cfg, key):
    p = cfg["fonts"].get(key) or cfg["fonts"]["arialbd"]
    if os.path.exists(p):
        return p
    for c in cfg["fonts"].values():
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default="_current", help="实验轮次目录名，位于 lab/ 下")
    ap.add_argument("--cand", default=None, help="只渲染指定候选")
    ap.add_argument("--theme", default="canvas", help="主题 profile，默认 canvas")
    args = ap.parse_args()

    cfg = load_cfg()
    default = cfg["default"]
    profile = theme_profile(args.theme)
    src_theme = profile_path(profile, "source_theme")
    ref_theme = profile_path(profile, "reference_theme") if profile.get("reference_theme") else None
    out_dir = os.path.join(path("lab"), args.round)
    os.makedirs(out_dir, exist_ok=True)

    samples = cfg["samples"]
    lines = ["实验轮次 %s  源主题=%s" % (args.round, os.path.basename(src_theme)), ""]

    first = samples[0]
    src = os.path.join(src_theme, first["slot"], first["system"] + ".webp")
    if os.path.exists(src):
        Image.open(src).convert("RGBA").save(os.path.join(out_dir, "base_%s.png" % first["system"]))

    ref = cfg.get("reference")
    if ref and ref_theme:
        rp = os.path.join(ref_theme, ref["slot"], ref["system"] + ".webp")
        if os.path.exists(rp):
            Image.open(rp).convert("RGBA").save(
                os.path.join(out_dir, "ref_pg_%s.png" % ref["system"].replace(" ", "_")))

    for cand in cfg["candidates"]:
        if not cand.get("enabled", True):
            continue
        if args.cand and cand["name"] != args.cand:
            continue
        p = dict(default)
        p.update({k: v for k, v in cand.items() if k not in ("name", "note", "enabled")})
        lines.append("候选 %s  %s" % (cand["name"], cand.get("note", "")))
        for smp in samples:
            sp = dict(p)
            sp["text"] = smp.get("text", p["text"])
            ip = os.path.join(src_theme, smp["slot"], smp["system"] + ".webp")
            if not os.path.exists(ip):
                lines.append("  跳过 %s（缺图）" % smp["tag"])
                continue
            img = Image.open(ip)
            out = draw_badge(img, sp, cfg)
            out.save(os.path.join(out_dir, "cand_%s_%s.png" % (cand["name"], smp["tag"])))
            lines.append("  %-14s %-32s %s" % (smp["tag"], smp["slot"].split("/")[-1], img.size))
        lines.append("")

    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 os.pardir, "config", "badge_params.json"),
                    os.path.join(out_dir, "_params_snapshot.json"))
    open(os.path.join(out_dir, "_last.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
    print("\n输出目录: %s" % out_dir)


if __name__ == "__main__":
    main()
