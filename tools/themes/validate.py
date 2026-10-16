# -*- coding: utf-8 -*-
"""配置预检：在生成图片前验证工程路径、批次规则和母体资源。"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import (BASE, batch as load_batch, ext_of, path, profile_for_batch,
                    profile_path, project, source_candidates, platform_registry)  # noqa: E402


def exact_file(folder, filename):
    """按目录真实文件名匹配，避免 Windows 大小写不敏感造成误判。"""
    if not os.path.isdir(folder):
        return False
    return filename in os.listdir(folder)


def validate(batch_name):
    errors = []
    proj = project()
    b = load_batch(batch_name)
    profile = profile_for_batch(b)

    required_paths = (
        "system_config", "reference_system_config", "themes", "reports", "lab",
    )
    for key in required_paths:
        if key not in proj.get("paths", {}):
            errors.append("project.paths 缺少 %s" % key)

    slots = profile.get("slots", {})
    if not slots:
        errors.append("theme profile 未定义 slots")
    slot_targets = [(directory, ext_of(profile, slot)) for slot, directory in slots.items()]
    if len(set(slot_targets)) != len(slots):
        errors.append("slots 存在重复目录和扩展名映射")

    src_theme = profile_path(profile, "source_theme")
    if not os.path.isdir(src_theme):
        errors.append("源主题目录不存在: %s" % os.path.relpath(src_theme, BASE))

    try:
        ET.parse(path("system_config"))
    except (OSError, ET.ParseError) as exc:
        errors.append("system_config 无法解析: %s" % exc)

    # Shared recognition data comes from the complete, verified system_config XML.
    systems = platform_registry().records if not errors else {}

    valid_slots = set(b.get("slots_all", []))
    allowed_actions = {"new", "alias", "patch"}
    seen = set()
    for item in b.get("platforms", []):
        name = item.get("name")
        if not name or name in seen:
            errors.append("平台 name 缺失或重复: %r" % name)
            continue
        seen.add(name)
        if item.get("action") not in allowed_actions:
            errors.append("平台 %s 的 action 无效: %r" % (name, item.get("action")))
        if name not in systems:
            errors.append("平台 %s 不在 system_config 中" % name)
        else:
            actual_theme = systems[name]["theme"]
            if actual_theme != item.get("theme"):
                errors.append("平台 %s 的 theme 不一致: 配置=%r, system_config=%r" %
                              (name, item.get("theme"), actual_theme))

        wanted = b.get("slots_all", []) if item.get("slots") == "all" else item.get("slots", [])
        for slot in wanted:
            if slot not in valid_slots or slot not in slots:
                errors.append("平台 %s 使用未知槽位: %s" % (name, slot))
                continue
            ext = ext_of(profile, slot)
            folder = os.path.join(src_theme, slots[slot])
            if slot in profile.get("directory_slots", {}):
                for suffix in profile["directory_slots"][slot]:
                    candidates = [os.path.join(candidate, candidate + suffix + ext)
                                  for candidate in source_candidates(item)]
                    found = any(exact_file(folder, candidate) and
                                exact_file(os.path.join(folder, candidate),
                                           candidate + suffix + ext)
                                for candidate in source_candidates(item))
                    if not found and slot in profile.get("required_slots", []):
                        errors.append("平台 %s 缺少源文件: %s/%s" %
                                      (name, slots[slot], " 或 ".join(candidates)))
            else:
                candidates = [candidate + ext for candidate in source_candidates(item)]
                if not any(exact_file(folder, filename) for filename in candidates) and slot in profile.get("required_slots", []):
                    errors.append("平台 %s 缺少源文件: %s/%s" %
                                  (name, slots[slot], " 或 ".join(candidates)))

        if profile.get("metadata_dir"):
            source_xml = os.path.join(src_theme, profile["metadata_dir"], item.get("source", "") + ".xml")
            if not os.path.isfile(source_xml):
                errors.append("平台 %s 缺少母体 XML: %s" % (name, os.path.relpath(source_xml, BASE)))

    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="batch1")
    args = ap.parse_args()
    errors = validate(args.batch)
    if errors:
        print("配置预检失败")
        for error in errors:
            print("- " + error)
        return 1
    print("配置预检通过: %s" % args.batch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
