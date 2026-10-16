# -*- coding: utf-8 -*-
"""打包器：源主题全量 + 当前 profile 的 staged 增量 = 完整主题。

用法:
    python tools/package.py --batch batch1
    python tools/package.py --batch iisu-batch1
输出:
    dist/themes/<源主题 themeName>_天马G/     完整主题
    dist/_reports/package_<批次>.txt        打包明细

每次运行先清空对应完整主题目录，再从源主题复制并覆盖增量文件。
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import (batch as load_batch, path, profile_for_batch, profile_path,
                    project, report_path)  # noqa: E402

TARGET_SUFFIX = "_天马G"


def match_androidgames_cover_ratio(theme_root):
    """Keep Android games' vertical cover and cart ratios aligned with Switch."""
    changed = []
    for directory, _, files in os.walk(theme_root):
        if "androidgames.xml" not in files or "switch.xml" not in files:
            continue
        android = os.path.join(directory, "androidgames.xml")
        switch = os.path.join(directory, "switch.xml")
        with open(android, encoding="utf-8-sig") as stream:
            content = stream.read()
        with open(switch, encoding="utf-8-sig") as stream:
            reference = stream.read()
        updated = content
        for tag in ("systemCoverSize", "systemCartSize"):
            source = re.search(r"<%s>(.*?)</%s>" % (tag, tag), reference, flags=re.S)
            if source:
                updated = re.sub(r"<%s>.*?</%s>" % (tag, tag),
                                 "<%s>%s</%s>" % (tag, source.group(1), tag),
                                 updated, count=1, flags=re.S)
        if updated != content:
            with open(android, "w", encoding="utf-8") as stream:
                stream.write(updated)
            changed.append(os.path.relpath(android, theme_root))
    return changed


def count_files(root):
    n = 0
    for _, _, fs in os.walk(root):
        n += len(fs)
    return n


def dir_size(root):
    t = 0
    for r, _, fs in os.walk(root):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return t


def theme_name(proj, src):
    """推导输出名：源主题 <themeName> + 天马 G 固定后缀。"""
    naming = proj.get("theme_naming", {})
    base = naming.get("fallback_base", "Theme")
    cap = os.path.join(src, "capabilities.xml")
    if os.path.isfile(cap):
        with open(cap, encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"<themeName>(.*?)</themeName>", txt, flags=re.S)
        if m and m.group(1).strip():
            base = m.group(1).strip()
    return base, base + TARGET_SUFFIX


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="batch1")
    args = ap.parse_args()

    proj = project()
    batch_cfg = load_batch(args.batch)
    profile = profile_for_batch(batch_cfg)
    clean = proj["clean_patterns"]
    skip_files = set(clean.get("files", []))
    skip_dirs = set(clean.get("dirs", []))

    src = profile_path(profile, "source_theme")
    staged = profile_path(profile, "staged")
    base, name = theme_name(proj, src)
    dst = os.path.join(path("themes"), name)

    lines = ["打包目标 %s" % name,
             "命名规则 源主题 <%s> = %s  +  固定后缀 %s" % ("themeName", base, TARGET_SUFFIX),
             "源主题 %s" % os.path.relpath(src, os.path.dirname(dst)), ""]

    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*skip_dirs, *skip_files))
    n_base = count_files(dst)
    lines.append("1) 复制源主题全量      %5d 个文件  %.1f MB" % (n_base, dir_size(dst) / 1048576))

    n_over = 0
    if os.path.isdir(staged):
        for root, _, files in os.walk(staged):
            rel = os.path.relpath(root, staged)
            target = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(target, exist_ok=True)
            for f in files:
                if f in skip_files:
                    continue
                shutil.copyfile(os.path.join(root, f), os.path.join(target, f))
                n_over += 1
    lines.append("2) 覆盖增量产物        %5d 个文件" % n_over)

    cap = os.path.join(dst, "capabilities.xml")
    if os.path.isfile(cap):
        with open(cap, encoding="utf-8") as f:
            txt = f.read()
        new = re.sub(r"<themeName>.*?</themeName>",
                     "<themeName>%s</themeName>" % name, txt, count=1, flags=re.S)
        if new != txt:
            with open(cap, "w", encoding="utf-8") as f:
                f.write(new)
            lines.append("3) 主题名改写          %s" % name)
        else:
            lines.append("3) 主题名未变化")

    adjusted = match_androidgames_cover_ratio(dst)
    lines.append("4) androidgames 竖版比例   %d 个 XML" % len(adjusted))

    lines.append("")
    lines.append("输出 %s" % dst)
    lines.append("合计 %d 个文件  %.1f MB" % (count_files(dst), dir_size(dst) / 1048576))
    txt = "\n".join(lines)
    print(txt)
    with open(report_path("package_%s.txt" % args.batch), "w", encoding="utf-8") as f:
        f.write(txt)


if __name__ == "__main__":
    main()
