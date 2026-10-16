# -*- coding: utf-8 -*-
"""校验器：检查批次平台的资源槽位和 XML 是否齐备。

用法:
    python tools/verify.py --batch batch1
    python tools/verify.py --batch iisu-batch1
    python tools/verify.py --batch iisu-batch1 --root "dist/themes/iiSU Interpreted_天马G"

默认校验当前批次 profile 的 dist/staged/<profile>；--root 指定完整主题。
资源槽位按文件名精确匹配；XML 目前使用文件系统存在性判断。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import (BASE, batch as load_batch, ext_of, profile_for_batch,
                    profile_path, report_path, source_candidates)  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="batch1")
    ap.add_argument("--root", default=None, help="待校验主题根目录，默认 dist/staged")
    args = ap.parse_args()

    b = load_batch(args.batch)
    profile = profile_for_batch(b)
    root = os.path.join(BASE, args.root) if args.root and not os.path.isabs(args.root) else (
        args.root if args.root else profile_path(profile, "staged"))
    src_theme = profile_path(profile, "source_theme")
    slots_map = profile["slots"]
    mdir = profile.get("metadata_dir")

    idx = {}
    for slot, rel in slots_map.items():
        d = os.path.join(root, rel)
        idx[slot] = set(os.listdir(d)) if os.path.isdir(d) else set()

    lines = ["校验目标 %s" % os.path.relpath(root, BASE), "批次 %s" % b["batch"], ""]
    all_ok = True
    for plat in b["platforms"]:
        want = plat["slots"]
        slot_list = list(slots_map) if want == "all" else want
        expected_slots = []
        miss = []
        for slot in slot_list:
            ext = ext_of(profile, slot)
            source_dir = os.path.join(src_theme, slots_map[slot])
            if slot in profile.get("directory_slots", {}):
                for suffix in profile["directory_slots"][slot]:
                    source_exists = any(
                        os.path.isfile(os.path.join(source_dir, candidate,
                                                    candidate + suffix + ext))
                        for candidate in source_candidates(plat))
                    expected = source_exists or slot in profile.get("required_slots", [])
                    if expected:
                        expected_slots.append(slot + suffix)
                        dst = os.path.join(root, slots_map[slot], plat["theme"],
                                           plat["theme"] + suffix + ext)
                        if not os.path.isfile(dst):
                            miss.append(slot + suffix)
                continue
            source_exists = os.path.isdir(source_dir) and any(
                name + ext in os.listdir(source_dir) for name in source_candidates(plat)
            )
            expected = source_exists or slot in profile.get("required_slots", [])
            if expected:
                expected_slots.append(slot)
                if plat["theme"] + ext not in idx[slot]:
                    miss.append(slot)
        xok = bool(mdir) and os.path.isfile(os.path.join(root, mdir, plat["theme"] + ".xml"))
        need_xml = bool(mdir and plat.get("system_name"))
        for extra_dir in profile.get("metadata_copy_dirs", []):
            source_extra = os.path.join(src_theme, extra_dir)
            if any(os.path.isfile(os.path.join(source_extra, candidate + ".xml"))
                   for candidate in source_candidates(plat)):
                if not os.path.isfile(os.path.join(root, extra_dir, plat["theme"] + ".xml")):
                    miss.append(extra_dir)
        ok = not miss and (xok or not need_xml)
        all_ok = all_ok and ok
        lines.append("%-10s %-9s %-13s xml=%-4s %s" % (
            plat["theme"], plat["action"], "%d/%d" % (len(expected_slots) - len(miss), len(expected_slots)),
            "有" if xok else ("需要但缺" if need_xml else "无需"),
            ("缺: " + ",".join(miss)) if miss else "OK"))

    lines.append("")
    lines.append("总检: %s" % ("全部通过" if all_ok else "存在缺失，见上"))
    txt = "\n".join(lines)
    print(txt)
    open(report_path("verify_%s.txt" % args.batch), "w", encoding="utf-8").write(txt)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
