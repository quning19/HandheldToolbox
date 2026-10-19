"""Independent theme CLI; no GUI or library converter imports."""
import argparse
from pathlib import Path
import json
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="ES-DE 原版主题导入、通用适配和上传")
    parser.add_argument("operation", choices=("list", "import", "catalog", "check-updates", "download",
                                             "download-convert", "refresh", "convert", "upload",
                                             "delete-original", "delete-output"))
    parser.add_argument("targets", nargs="*", help="主题 ID；import 时为一个本地原版目录")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    from frontend_common.state import UiStore
    from frontend_common.locking import workspace_lock
    from frontend_platforms.user_catalog import load_catalog
    from frontend_devices.discovery import discover_device
    from .service import run_themes, import_original
    from .catalog import managed_themes
    from retrolibx.errors import RetroLibXError
    workspace = args.workspace.resolve() if args.workspace else UiStore().workspace
    progress = lambda text, *_: print(text, file=sys.stderr)
    try:
        with workspace_lock(workspace):
            definitions, notices = load_catalog(workspace)
            for notice in notices:
                print(notice, file=sys.stderr)
            if args.operation == "list":
                result = managed_themes(workspace, definitions)
            elif args.operation == "import":
                if len(args.targets) != 1:
                    parser.error("import 需要一个本地原版目录")
                identity = import_original(workspace, Path(args.targets[0]), progress=progress)
                print("已导入 " + identity, file=sys.stderr)
                result = managed_themes(workspace, definitions)
            else:
                if args.operation not in {"refresh", "catalog", "check-updates"} and not args.targets:
                    parser.error("请明确选择主题 ID；先 catalog 再 list")
                device = discover_device() if args.operation in {"refresh", "upload"} else None
                result = run_themes(args.operation, workspace, definitions, args.targets, device, lambda: False, progress)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=lambda obj: str(obj) if isinstance(obj, Path) else vars(obj)))
    except (OSError, ValueError, RetroLibXError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
