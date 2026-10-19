"""ES-DE official theme catalogue and staged Git downloads.

Follows GuiThemeDownloader.cpp: themes-list/themes.json, themes + themesAndroid,
repository inventory, clone/fetch and fast-forward updates. Qt is not required.
See docs/THEME_CONVERSION.md for upstream attribution and deliberate differences.
"""
from datetime import datetime
import codecs
import os
from pathlib import Path, PurePosixPath
import re
import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit

from frontend_common.files import write_json
from frontend_common.jobs import checkpoint, new_job
from frontend_platforms import platform_component
from retrolibx.errors import ValidationError


CATALOG_URL = "https://gitlab.com/es-de/themes/themes-list.git"
MARKER = ".frontendtrans-original.json"


def git_progress(line):
    """Keep Git's real percentages/transfer sizes, with readable stage names."""
    line = line.strip()
    if line.startswith("Cloning into "):
        return "连接主题仓库…", -1
    for original, translated in (("Receiving objects", "接收数据"), ("Resolving deltas", "整理数据"),
                                  ("Updating files", "写入主题文件"), ("Checking out files", "写入主题文件"),
                                  ("Enumerating objects", "服务器整理文件"), ("Counting objects", "服务器统计文件"),
                                  ("Compressing objects", "服务器压缩文件")):
        line = line.replace(original, translated)
    line = line.removeprefix("remote: ")
    percent = re.search(r"\b(\d{1,3})%", line)
    return line[-350:], min(100, int(percent[1])) if percent else -1


def live_git_output(process, cancelled, deadline, progress):
    """Drain merged output live, including CR-only Git updates on Windows.

    Windows communicate() reads a pipe to EOF in its reader thread, so polling
    TimeoutExpired.stderr cannot provide reliable intermediate progress.
    """
    events = queue.Queue()
    chunks = []
    def read_pipe():
        try:
            while chunk := process.stdout.read1(8192):
                events.put(chunk)
        finally:
            process.stdout.close()
            events.put(None)
    reader = threading.Thread(target=read_pipe, name="theme-git-progress", daemon=True)
    reader.start()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    last_message, last_percent = "等待服务器响应…", -1
    last_data = last_report = time.monotonic()
    progress(last_message, last_percent)
    try:
        while True:
            checkpoint(cancelled)
            now = time.monotonic()
            if now >= deadline:
                raise ValidationError("Git 操作超时，旧原版保持不变。")
            try:
                chunk = events.get(timeout=0.1)
            except queue.Empty:
                if now - last_report >= 1:
                    waiting = max(1, int(now - last_data))
                    progress(f"{last_message} · 等待响应 {waiting} 秒", last_percent)
                    last_report = now
                continue
            if chunk is None:
                pending += decoder.decode(b"", final=True)
                if pending.strip():
                    progress(*git_progress(pending))
                break
            chunks.append(chunk)
            last_data = time.monotonic()
            parts = re.split(r"[\r\n]", pending + decoder.decode(chunk))
            pending = parts.pop()
            lines = [line for line in parts if line.strip()]
            if lines:
                last_message, last_percent = git_progress(lines[-1])
                progress(last_message, last_percent)
                last_report = last_data
        while process.poll() is None:
            checkpoint(cancelled)
            if time.monotonic() >= deadline:
                raise ValidationError("Git 操作超时，旧原版保持不变。")
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
    finally:
        # On cancellation the outer runner terminates the process tree, allowing
        # this reader to exit; don't wait here for a still-open network pipe.
        if process.poll() is not None:
            reader.join(timeout=1)
    return b"".join(chunks)


def git(arguments, *, cwd=None, cancelled=lambda: False, progress=None):
    """Use argument lists and noninteractive Git; only staged mutations can cancel."""
    checkpoint(cancelled)
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", LC_ALL="C")
    try:
        process = subprocess.Popen(
            ["git", "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", *arguments],
            cwd=cwd, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if progress is not None else subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise ValidationError("下载官方主题需要 Git，请安装 Git for Windows 并将其加入 PATH。") from exc
    deadline = time.monotonic() + 3600
    try:
        if progress is not None:
            stdout = stderr = live_git_output(process, cancelled, deadline, progress)
        else:
            while True:
                checkpoint(cancelled)
                if time.monotonic() >= deadline:
                    raise ValidationError("Git 操作超时，旧原版保持不变。")
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
    except BaseException:
        # git.exe can have remote-https children holding its pipe handles open.
        # End the launched process tree before waiting, so cancellation can finish.
        if os.name == "nt":
            try:
                ended = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if ended.returncode and process.poll() is None:
                    process.kill()
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        else:
            process.kill()
        try:
            if progress is not None:
                process.wait(timeout=5)
            else:
                process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        raise
    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()[-2000:]
        raise ValidationError("Git 操作失败：" + detail)
    return stdout.decode("utf-8", errors="replace").strip()


def https_url(value):
    if not isinstance(value, str):
        raise ValidationError("主题仓库地址格式错误")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValidationError("主题仓库必须使用不含凭据的 HTTPS 地址")
    return value


def read_catalog(directory):
    from .service import json_file
    data = json_file(directory / "themes.json", {})
    if not isinstance(data, dict) or not isinstance(data.get("themes"), list):
        raise ValidationError("官方 themes.json 缺少主题列表")
    entries = {}
    for key in ("themes", "themesAndroid"):
        items = data.get(key, [])
        if not isinstance(items, list):
            raise ValidationError("官方主题列表格式错误：" + key)
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("官方主题条目格式错误")
            repo, name = item.get("reponame", ""), item.get("name", "")
            if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", repo):
                raise ValidationError("官方主题目录名无效")
            platform_component(repo)
            if not isinstance(name, str) or not name.strip():
                raise ValidationError("官方主题缺少名称：" + repo)
            url = https_url(item.get("url"))
            if repo in entries and entries[repo]["url"] != url:
                raise ValidationError("官方主题出现同名仓库冲突：" + repo)
            entry = dict(item, name=name.strip(), url=url)
            for field in ("screenshots", "variants", "colorSchemes", "aspectRatios"):
                if not isinstance(item.get(field, []), list):
                    raise ValidationError("官方主题字段格式错误：" + field)
            if any(existing.casefold() == repo.casefold() and existing != repo for existing in entries):
                raise ValidationError("官方主题目录存在大小写冲突：" + repo)
            # Screenshot paths are relative to themes-list, never theme repositories.
            screenshots = []
            for shot in item.get("screenshots", []):
                if not isinstance(shot, dict) or not isinstance(shot.get("image"), str):
                    continue
                relative = PurePosixPath(shot["image"])
                if relative.is_absolute() or ".." in relative.parts or "\\" in shot["image"] or ":" in shot["image"]:
                    raise ValidationError("主题预览路径越界：" + repo)
                path = directory.joinpath(*relative.parts)
                if not path.resolve().is_relative_to(directory.resolve()):
                    raise ValidationError("主题预览路径越界：" + repo)
                screenshots.append((path, str(shot.get("caption", ""))))
            entry["previews"] = screenshots
            entries[repo] = entry
    return sorted(entries.values(), key=lambda entry: entry["name"].casefold())


def managed_themes(workspace, definitions):
    from .service import ThemeInfo, json_file, local_themes
    local = {info.id: info for info in local_themes(workspace, definitions)}
    checks = json_file(workspace / "config/theme-updates.json", {})
    directory = workspace / "themes/catalog"
    entries = read_catalog(directory) if (directory / "themes.json").is_file() else []
    result = []
    for entry in entries:
        identity = "official-" + entry["reponame"]
        info = local.pop(identity, ThemeInfo(identity, entry["name"]))
        # Use capabilities themeName for output matching; catalogue name is a label.
        if not info.original:
            info.name = entry["name"]
        info.repository = entry["url"]
        info.author = str(entry.get("author", ""))
        info.screenshots = entry["previews"]
        for attr, key in (("variants", "variants"), ("color_schemes", "colorSchemes"), ("aspect_ratios", "aspectRatios")):
            setattr(info, attr, [value for value in entry.get(key, []) if isinstance(value, str)])
        info.deprecated = bool(entry.get("deprecated", False))
        record = checks.get(identity, {})
        marker = json_file(info.source / MARKER, {}) if info.source else {}
        if marker.get("repository") == info.repository and record.get("repository") == info.repository:
            info.checked = record.get("checked", "")
            info.update_error = record.get("error", "")
            if record.get("revision") and marker.get("revision") and not info.update_error:
                info.update_available = record["revision"] != marker["revision"]
        result.append(info)
    # A delisted downloaded repository stays manageable; never auto-delete it.
    for info in local.values():
        marker = json_file(info.source / MARKER, {}) if info.source else {}
        info.repository = marker.get("repository", "")
        if info.repository:
            info.deprecated = True
            record = checks.get(info.id, {})
            if record.get("repository") == info.repository:
                info.checked = record.get("checked", "")
                info.update_error = record.get("error", "")
                if record.get("revision") and marker.get("revision") and not info.update_error:
                    info.update_available = record["revision"] != marker["revision"]
        result.append(info)
    return sorted(result, key=lambda info: info.name.casefold())


def remote_head(url, cancelled):
    output = git(["ls-remote", "--symref", "--", https_url(url), "HEAD"], cancelled=cancelled)
    branch = revision = ""
    for line in output.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            branch = line[len("ref: refs/heads/"):].split("\t")[0]
        elif re.fullmatch(r"[0-9a-f]{40,64}\tHEAD", line):
            revision = line.split("\t")[0]
    if not branch or not revision:
        raise ValidationError("无法确定主题仓库的默认分支")
    git(["check-ref-format", "refs/heads/" + branch], cancelled=cancelled)
    return branch, revision


def stage_repository(workspace, source, url, cancelled, *, expected_revision="", progress=None):
    from .state import source_index
    https_url(url)
    job = new_job(workspace, "theme-download")
    target = job / "repository"
    report = progress or (lambda *_: None)
    report("准备原版仓库…", -1)
    if source is not None:
        if source.is_symlink() or source.is_junction():
            raise ValidationError("原版目录不能是链接")
        if not (source / ".git").is_dir() or (source / ".git").is_symlink() or (source / ".git").is_junction():
            raise ValidationError("原版不是受管理的 Git 仓库，请保留本地导入并重新下载官方原版。")
        source_index(source)  # Reject linked paths before copying the repository.
        actual = Path(git(["rev-parse", "--show-toplevel"], cwd=source, cancelled=cancelled)).resolve()
        if actual != source.resolve() or git(["remote", "get-url", "origin"], cwd=source, cancelled=cancelled) != url:
            raise ValidationError("原版仓库来源已改变，停止更新。")
        if git(["status", "--porcelain", "--untracked-files=no"], cwd=source, cancelled=cancelled):
            raise ValidationError("原版存在本地修改，请先保存修改；不会自动覆盖。")
        old_revision = git(["rev-parse", "HEAD"], cwd=source, cancelled=cancelled)
        if expected_revision and old_revision != expected_revision:
            raise ValidationError("本地原版版本已被手动改变，停止更新。")
        report("读取远端版本…", -1)
        branch, latest_revision = remote_head(url, cancelled)
        if latest_revision == old_revision:
            return source, old_revision, old_revision
        report("准备更新副本…", -1)
        shutil.copytree(source, target, copy_function=shutil.copy2)
    else:
        git(["clone", "--progress", "--", https_url(url), str(target)], cancelled=cancelled, progress=progress)
        old_revision = ""
        report("读取远端版本…", -1)
        branch, _revision = remote_head(url, cancelled)
    checkpoint(cancelled)
    reference = "refs/remotes/origin/" + branch
    report("获取更新…", -1)
    git(["fetch", "--progress", "--prune", "origin", "+refs/heads/" + branch + ":" + reference],
        cwd=target, cancelled=cancelled, progress=progress)
    revision = git(["rev-parse", reference], cwd=target, cancelled=cancelled)
    if source is not None:
        # Like upstream, accept fast-forward only; never reset user changes.
        try:
            git(["merge-base", "--is-ancestor", "HEAD", reference], cwd=target, cancelled=cancelled)
        except ValidationError as exc:
            raise ValidationError("主题仓库已分叉或无法确认版本关系；旧原版保留，请先保存自定义内容再重新下载。") from exc
        report("应用主题更新…", -1)
        git(["merge", "--ff-only", "--progress", reference], cwd=target, cancelled=cancelled, progress=progress)
    else:
        report("保存主题文件…", -1)
        git(["checkout", "--progress", "--detach", revision], cwd=target, cancelled=cancelled, progress=progress)
    report("读取下载完成的文件…", -1)
    source_index(target)
    return target, revision, old_revision


def refresh_catalog(workspace, cancelled, progress):
    from .service import promote
    progress("更新 ES-DE 官方主题目录与预览图…", -1, True)
    destination = workspace / "themes/catalog"
    target, revision, old = stage_repository(
        workspace, destination if destination.exists() else None, CATALOG_URL, cancelled,
        progress=lambda stage, percent: progress("官方主题目录 · " + stage, percent, True))
    read_catalog(target)
    checkpoint(cancelled)
    if revision != old:
        promote(target, destination, workspace)


def check_updates(workspace, definitions, identities, cancelled, progress):
    from .service import json_file
    path = workspace / "config/theme-updates.json"
    records = json_file(path, {})
    infos = [info for info in managed_themes(workspace, definitions)
             if info.original and info.repository and (not identities or info.id in identities)]
    failures = []
    for index, info in enumerate(infos):
        checkpoint(cancelled)
        progress("检查更新：" + info.name, int(index * 100 / len(infos)), True)
        record = {"repository": info.repository, "checked": datetime.now().isoformat(timespec="seconds")}
        try:
            _branch, record["revision"] = remote_head(info.repository, cancelled)
        except (OSError, ValidationError) as exc:
            record["error"] = str(exc)
            failures.append(info.name)
        records[info.id] = record
        write_json(path, records)
    return f"已检查 {len(infos)} 个主题。" + ("检查失败：" + "、".join(failures) if failures else "")


def download_themes(workspace, definitions, identities, cancelled, progress):
    from .service import capabilities_name, json_file, promote
    available = {info.id: info for info in managed_themes(workspace, definitions)}
    if not identities or any(identity not in available or not available[identity].repository for identity in identities):
        raise ValidationError("请选择官方列表中的主题。")
    for index, identity in enumerate(identities):
        info = available[identity]
        checkpoint(cancelled)
        label = f"[{index + 1}/{len(identities)}] {info.name} · "
        progress(label + "准备下载／更新…", -1, True)
        marker = json_file(info.source / MARKER, {}) if info.source else {}
        target, revision, old = stage_repository(workspace, info.source, info.repository, cancelled,
                                                  expected_revision=marker.get("revision", ""),
                                                  progress=lambda stage, percent: progress(label + stage, percent, True))
        name = capabilities_name(target)
        if name.endswith("_天马G"):
            raise ValidationError("官方原版不能是适配结果：" + info.name)
        write_json(target / MARKER, {"repository": info.repository, "revision": revision,
                                    "downloaded": datetime.now().isoformat(timespec="seconds")})
        checkpoint(cancelled)
        if revision != old:
            progress(label + "保存原版…", -1, False)
            promote(target, workspace / "themes/original" / identity, workspace)
        path = workspace / "config/theme-updates.json"
        records = json_file(path, {})
        records[identity] = {"repository": info.repository, "revision": revision,
                             "checked": datetime.now().isoformat(timespec="seconds")}
        write_json(path, records)
        progress(label + "下载／更新完成", 100, True)


def remove_local(workspace, definitions, identities, operation):
    """Remove from the active library by retaining existing recovery semantics."""
    from .service import json_file
    infos = {info.id: info for info in managed_themes(workspace, definitions)}
    paths = []
    root = (workspace / "themes").resolve()
    if not root.is_relative_to(workspace.resolve()):
        raise ValidationError("主题目录超出工作目录")
    for identity in identities:
        info = infos.get(identity)
        source = (info.source if operation == "delete-original" else info.output) if info else None
        if source is None or not source.is_dir():
            raise ValidationError("所选主题没有对应本地内容：" + identity)
        if not source.resolve().is_relative_to(root) or source.is_symlink() or source.is_junction():
            raise ValidationError("主题删除路径超出管理目录或是链接")
        paths.append(source)
    for source in paths:
        batch = workspace / "backups/themes" / (datetime.now().strftime("%Y%m%d-%H%M%S-") + os.urandom(4).hex())
        batch.mkdir(parents=True)
        write_json(batch / "recovery.json", {"original_path": str(source), "kind": "theme"})
        source.replace(batch / source.name)
    if operation == "delete-output":
        path = workspace / "config/theme-results.json"
        records = json_file(path, {})
        for identity in identities:
            records.pop(identity, None)
        write_json(path, records)
