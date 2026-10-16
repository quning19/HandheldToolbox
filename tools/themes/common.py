# -*- coding: utf-8 -*-
"""工程公共模块：路径解析与配置加载。

所有脚本必须通过这里取路径，不得自行拼 BASE 或硬编码目录名。
"""
import json
import os
import sys
from pathlib import Path

BASE = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(BASE) / "src"))


def load_json(rel):
    with open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return json.load(f)


def project():
    return load_json("tools/themes/config/project.json")


def resolve(rel):
    return rel if os.path.isabs(rel) else os.path.join(BASE, rel)


def path(key):
    """取 project.json -> paths.<key> 的绝对路径。"""
    return resolve(project()["paths"][key])


def theme_profile(name):
    rel = project()["theme_profiles"][name]
    return load_json(rel)


def profile_path(profile, key):
    return resolve(profile[key])


def ext_of(profile, slot):
    return profile.get("slot_ext", {}).get(slot, ".webp")


def platform_registry():
    """Load the one platform configuration used by game and theme conversion."""
    config_path = Path(path("platform_config"))
    sys.path.insert(0, str(config_path.parent.parent))
    from frontend_platforms import PlatformRegistry
    return PlatformRegistry.load(config_path, config_dir=Path(path("system_config")).parent)


def batch(name):
    cfg = load_json("tools/themes/config/batches/%s.json" % name)
    registry = platform_registry()
    for item in cfg["platforms"]:
        record = registry.resolve(item["name"])
        if record is None:
            raise ValueError("Unknown configured platform: " + item["name"])
        rule = registry.theme_rule(record)
        for key, value in rule.items():
            if key in item and item[key] != value:
                raise ValueError("Platform rule conflicts with shared configuration: " + item["name"])
        item.update(rule)
    return cfg


def profile_for_batch(batch_cfg):
    return theme_profile(batch_cfg["theme_profile"])


def source_candidates(platform):
    """按目标平台优先、再母体、再显式 fallback 的顺序返回资源名。"""
    result = []
    for name in (platform.get("theme"), platform.get("source"), platform.get("fallback_source")):
        if name and name not in result:
            result.append(name)
    return result


def report_path(name):
    d = path("reports")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)
