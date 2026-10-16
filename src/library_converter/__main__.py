"""Independent game-library workflow; imports no GUI or theme tool."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="天马 G → ES-DE 游戏库转换")
    parser.add_argument("operation", choices=("scan", "convert"))
    parser.add_argument("source", help="电脑目录；使用 --device 时为设备完整 ROM 目录")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--device", action="store_true", help="明确读取/写入当前已授权的唯一设备")
    parser.add_argument("--platform", action="append", default=[], help="scan 输出的相对目录；可重复")
    parser.add_argument("--shared-media", action="store_true")
    parser.add_argument("--full", action="store_true", help="重新处理所选平台已有游戏与素材")
    args = parser.parse_args(argv)
    if args.operation == "convert" and not args.platform:
        parser.error("convert 必须用 --platform 明确选择平台；请先 scan")
    from frontend_common.state import UiStore
    from frontend_common.locking import workspace_lock
    from frontend_platforms.user_catalog import load_catalog
    from frontend_devices.discovery import discover_device
    from .desktop import scan_library, convert_library
    from retrolibx.errors import RetroLibXError
    workspace = args.workspace.resolve() if args.workspace else UiStore().workspace
    progress = lambda text, *_: print(text, file=sys.stderr)
    try:
        with workspace_lock(workspace):
            definitions, notices = load_catalog(workspace)
            for notice in notices:
                print(notice, file=sys.stderr)
            device = discover_device() if args.device else None
            session = scan_library(workspace, definitions, args.source, device, lambda: False, progress, lambda _item: None)
            if args.operation == "scan":
                print(json.dumps([asdict(item) for item in session.platforms.values()], ensure_ascii=False, indent=2))
            else:
                unknown = set(args.platform) - set(session.platforms)
                if unknown:
                    parser.error("未发现平台：" + "、".join(sorted(unknown)))
                result = convert_library(session, args.platform, args.shared_media, args.full, workspace, lambda: False, progress)
                print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RetroLibXError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
