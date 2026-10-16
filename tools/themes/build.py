# -*- coding: utf-8 -*-
"""批次生成器：按 config/batches/<批次>.json 复制资源、处理回退图片、生成系统定义。

用法:
    python tools/build.py --batch batch1
    python tools/build.py --batch iisu-batch1
    python tools/build.py --batch batch1 --platform FC-HD
输出:
    dist/staged/<profile>/...                       当前主题的增量资源和 XML
    dist/_reports/build_<批次>.txt                  生成明细
    dist/_reports/manifest_<批次>.json              可追溯清单

不指定 --platform 时先清空当前 profile 的 staged 目录；指定时增量构建。
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from badge import load_cfg as load_badge_cfg, draw_badge  # noqa: E402
from common import (BASE, batch as load_batch, ext_of, path, profile_for_batch,
                    profile_path, project, report_path, source_candidates)  # noqa: E402


def badge_params_for(badge_cfg, slot, text):
    p = dict(badge_cfg["default"])
    active = badge_cfg.get("active_candidate")
    if active:
        candidate = next((item for item in badge_cfg["candidates"]
                          if item["name"] == active and item.get("enabled", True)), None)
        if candidate is None:
            raise ValueError("active badge candidate is missing or disabled: " + active)
        p.update({key: value for key, value in candidate.items()
                  if key not in ("name", "note", "enabled")})
    p.update(badge_cfg.get("slot_overrides", {}).get(slot, {}))
    p["text"] = text
    return p


def find_source(profile, src_theme, platform, slot):
    rel = profile["slots"][slot]
    ext = ext_of(profile, slot)
    folder = os.path.join(src_theme, rel)
    if not os.path.isdir(folder):
        return None
    for name in source_candidates(platform):
        filename = name + ext
        if filename in os.listdir(folder):
            return os.path.join(folder, filename), name
    return None


def find_directory_source(profile, src_theme, platform, slot, suffix):
    """Find one file from a per-system directory, preserving target priority."""
    folder = os.path.join(src_theme, profile["slots"][slot])
    ext = ext_of(profile, slot)
    if not os.path.isdir(folder):
        return None
    available = set(os.listdir(folder))
    for name in source_candidates(platform):
        if name not in available:
            continue
        child = os.path.join(folder, name)
        filename = name + suffix + ext
        if os.path.isdir(child) and filename in os.listdir(child):
            return os.path.join(child, filename), name
    return None


def save_raster(img, dst, ext):
    if ext in (".jpg", ".jpeg"):
        img.convert("RGB").save(dst, "JPEG", quality=92)
    elif ext == ".png":
        img.convert("RGBA").save(dst, "PNG")
    else:
        img.convert("RGBA").save(dst, "WEBP", quality=92)


def build_xml(plat, profile, src_theme_dir, out_root, lines,
              metadata_dir=None, use_default=True):
    theme = plat["theme"]
    sys_name = plat.get("system_name")
    mdir = metadata_dir if metadata_dir is not None else profile.get("metadata_dir")
    if not sys_name or not mdir:
        return None
    out_dir = os.path.join(out_root, mdir)
    os.makedirs(out_dir, exist_ok=True)

    src = None
    for cand in source_candidates(plat):
        if not cand:
            continue
        p = os.path.join(src_theme_dir, mdir, cand + ".xml")
        if os.path.isfile(p):
            src = p
            break
    if src is None:
        if not use_default:
            return None
        src = os.path.join(src_theme_dir, mdir, "_default.xml")

    txt = open(src, encoding="utf-8").read()
    new = re.sub(r"<systemName>.*?</systemName>",
                 "<systemName>%s</systemName>" % sys_name, txt, count=1, flags=re.S)
    if "<systemName>" not in txt:
        new = txt.replace("</system>", "    <systemName>%s</systemName>\n</system>" % sys_name)
    dst = os.path.join(out_dir, theme + ".xml")
    open(dst, "w", encoding="utf-8").write(new)
    lines.append("  xml  <- %s  systemName=%s" % (os.path.basename(src), sys_name))
    return os.path.relpath(dst, out_root)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="batch1")
    ap.add_argument("--platform", default=None)
    args = ap.parse_args()

    b = load_batch(args.batch)
    profile = profile_for_batch(b)
    badge_cfg = load_badge_cfg()
    slots_map = profile["slots"]

    src_theme = profile_path(profile, "source_theme")
    out_root = profile_path(profile, "staged")

    # Full batch builds are authoritative; remove stale files before rebuilding.
    # A platform-scoped build remains incremental so it can be used for focused work.
    if not args.platform and os.path.isdir(out_root):
        shutil.rmtree(out_root)

    lines = ["批次 %s  源主题=%s  输出=%s" % (b["batch"], src_theme, out_root), ""]
    total_img, built, failed = 0, [], False

    for plat in b["platforms"]:
        if args.platform and plat["name"] != args.platform:
            continue
        theme, source = plat["theme"], plat["source"]
        want = plat["slots"]
        slot_list = b["slots_all"] if want == "all" else want
        lines.append("%s  [%s]  母体=%s  槽位=%d" % (plat["name"], plat["action"], source, len(slot_list)))
        made = []

        for slot in slot_list:
            rel = slots_map[slot]
            ext = ext_of(profile, slot)
            if slot in profile.get("directory_slots", {}):
                for suffix in profile["directory_slots"][slot]:
                    found = find_directory_source(profile, src_theme, plat, slot, suffix)
                    if not found:
                        lines.append("  无源图 %s/%s/%s%s%s" %
                                     (rel, theme, theme, suffix, ext))
                        if slot in profile.get("required_slots", []):
                            failed = True
                        continue
                    src, source_used = found
                    out_dir = os.path.join(out_root, rel, theme)
                    os.makedirs(out_dir, exist_ok=True)
                    dst = os.path.join(out_dir, theme + suffix + ext)
                    copy_only = (source_used == theme or
                                 suffix in profile.get("copy_only_suffixes", {}).get(slot, []) or
                                 slot not in profile.get("badge_slots", []))
                    if copy_only or not plat.get("badge_text"):
                        shutil.copyfile(src, dst)
                        tag = "复制"
                    else:
                        img = draw_badge(Image.open(src),
                                         badge_params_for(badge_cfg, slot, plat["badge_text"]), badge_cfg)
                        save_raster(img, dst, ext)
                        tag = "复制+%s" % plat["badge_text"]
                    lines.append("  %-12s %s <- %s  %s" %
                                 (slot + suffix, tag, source_used, os.path.basename(dst)))
                    total_img += 1
                made.append(slot)
                continue
            found = find_source(profile, src_theme, plat, slot)
            if not found:
                if slot in profile.get("required_slots", []):
                    lines.append("  缺必需源图 %s/%s%s  -- 失败" % (rel, theme, ext))
                    failed = True
                else:
                    lines.append("  无可选源图 %s/%s%s  -- 保持缺省" % (rel, theme, ext))
                continue
            src, source_used = found
            out_dir = os.path.join(out_root, rel)
            os.makedirs(out_dir, exist_ok=True)
            dst = os.path.join(out_dir, theme + ext)

            # Existing target-platform resources are authoritative and stay unchanged.
            # Badge processing is only for resources copied from a fallback mother.
            if (source_used == theme or ext == ".svg" or
                    slot not in profile.get("badge_slots", [])):
                shutil.copyfile(src, dst)
                lines.append("  %-18s 复制 <- %s" % (slot, source_used))
                total_img += 1
                made.append(slot)
                continue

            img = Image.open(src)
            if plat.get("badge_text"):
                img = draw_badge(img, badge_params_for(badge_cfg, slot, plat["badge_text"]), badge_cfg)
                tag = "复制+%s" % plat["badge_text"]
            else:
                tag = "复制"
            save_raster(img, dst, ext)
            lines.append("  %-12s %s <- %s  %s" % (slot, tag, source_used, img.size))
            total_img += 1
            made.append(slot)

        xml_rel = build_xml(plat, profile, src_theme, out_root, lines)
        extra_xml = [build_xml(plat, profile, src_theme, out_root, lines,
                               metadata_dir=mdir, use_default=False)
                     for mdir in profile.get("metadata_copy_dirs", [])]
        built.append({"name": plat["name"], "theme": theme, "action": plat["action"],
                      "source": source, "slots": made, "badge": plat.get("badge_text"),
                      "xml": xml_rel, "extra_xml": [item for item in extra_xml if item]})
        lines.append("")

    lines.append("合计生成文件 %d" % total_img)
    txt = "\n".join(lines)
    print(txt)
    open(report_path("build_%s.txt" % args.batch), "w", encoding="utf-8").write(txt)

    manifest = {
        "batch": b["batch"],
        "theme_profile": profile["id"],
        "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_theme": os.path.relpath(src_theme, BASE),
        "output": os.path.relpath(out_root, BASE),
        "active_candidate": badge_cfg.get("active_candidate"),
        "badge_params": badge_params_for(badge_cfg, "", badge_cfg["default"].get("text", "HACK")),
        "platforms": built,
        "file_count": total_img,
    }
    open(report_path("manifest_%s.json" % args.batch), "w", encoding="utf-8").write(
        json.dumps(manifest, ensure_ascii=False, indent=2))
    print("\nmanifest: %s" % report_path("manifest_%s.json" % args.batch))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
