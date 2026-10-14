> 历史归档：本文记录当时方案或结果，当前以项目 docs/PLAN.md 和用户后续确认为准。

# 天马G到 ES-DE 首版实施计划

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** 实现 scan、plan、export-script、apply-local，以同一份逐 ROM 计划生成 XML 和媒体操作。

**Architecture:** 标准库负责读取、解析、规划、合并和执行。local/adb 来源适配器提供统一文件索引，Android 脚本只执行生成好的命令；Pillow 为缩放模式的可选依赖。

**Tech Stack:** Python 3.9+、unittest、ElementTree、Android sh/Toybox、可选 Pillow。

**Spec:** ../specs/2026-10-10-pegasus-to-esde-python-design.md

## Global Constraints

- 只修改明确选中的平台，源 ROM 和天马G文件只读。
- 不读取 ROM 内容；默认不下载视频，不导出 mini 图片。
- 原样媒体按 ROM 相对路径命名，图片后缀由文件头识别。
- 默认保留媒体，合并和备份配置；覆盖必须显式选择。
- 未确认的启动映射、路径冲突、缺失 ROM 阻止执行导出。
- 脚本 UTF-8 无 BOM、LF，无 eval、Python、Root 或联网依赖。
- 每次 ADB 访问检查授权设备；目录索引和图片头按平台批量读取。
- 当前不是 Git 仓库：原地开发，不初始化仓库、不自动提交；执行账本保留。

## Review Focus

- 路径越界、符号链接、换行及单引号：拒绝越界，正确引用合法路径。
- 配置变化与中断窗口：拒绝外部变化，仅接受本任务有发布意图记录的新摘要。
- 同名、共享媒体及大小写：保留层级，冲突不得靠覆盖消除。
- 部分配置发布与保留文件：备份不能被恢复运行覆盖，不把跳过当作一致证明。
- 镜像时间和设备真实时间：首次记录设备时间，恢复核对；不相信 Windows 镜像时间。

### Task 1: 配置、解析、来源读取和 scan

**Files:** frontend_trans_tool/{__init__,errors,paths,metadata,storage,profile}.py; tests/test_reading.py
**Interfaces:** parse_metadata(raw: bytes, encoding: str = None) -> dict；load_profile(path) -> dict；make_storage(profile) -> Storage；scan(profile) -> list[dict]。

- [ ] 编写真实节选 5/1/2 条游戏、file/files、BOM/GBK、续行、独立子平台和越界测试。
- [ ] 运行 `python -m unittest discover -s tests -v`，Expected: 新接口不存在而失败。
- [ ] 实现严格解码、字段解析、local 与批量 adb 索引，scan 只发现平台和读取 metadata。
- [ ] 同命令，Expected: 全部 PASS；记入账本。

### Task 2: 平台/资产映射、XML合并、统一计划与预览

**Files:** frontend_trans_tool/{systems,xmlio,planner,planio}.py; tests/test_planning.py
**Interfaces:** build_plan(profile, platforms, overwrite=False, strict=False, resize=False) -> dict；save_plan(plan, out) -> Path；load_plan(path) -> dict。
Consumes: Task 1 的模型和 Storage。Produces: 版本化计划，含 records、operations、configs、snapshots、issues、summary、digest。

- [ ] 编写 12/36、15/45、错误引用、保留资料、现有系统复用、嵌套扫描、目标冲突和 vib 阻塞测试。
- [ ] 运行全套测试，Expected: 规划接口不存在而失败。
- [ ] 实现官方 Android 3.4.1 GBA 模板映射；gpsp_rumble 必须显式确认；生成合并 XML 和报告，快照绑定源和目标。
- [ ] 运行全套测试，Expected: 全部 PASS；记入账本。

### Task 3: 本地执行与 Android 任务包

**Files:** frontend_trans_tool/{execution,script}.py; tests/test_execution.py
**Interfaces:** apply_local(plan) -> dict；export_script(plan, directory) -> Path。
Consumes: Task 2 的有效计划和操作，不重新推导 ROM/媒体对应。

- [ ] 编写复制、保留、覆盖备份、配置变化、源变化、恢复、部分配置发布、空间不足、脚本实际执行测试。
- [ ] 运行全套测试，Expected: 执行接口不存在而失败。
- [ ] 实现所有源和配置预检、按实际存储空间检查、同目录临时文件发布、任务摘要绑定恢复、发布意图和状态记录、失败停止。
- [ ] 生成引用安全的 sh，实际执行相同案例；运行全套测试，Expected: 全部 PASS；记入账本。

### Task 4: 可选缩放、CLI、原样节选验收与文档

**Files:** frontend_trans_tool/{images,__main__}.py; examples/profile.local.json; tests/test_cli.py; tests/test_images.py; README.md; pyproject.toml; docs/evaluations/2026-10-12-python-implementation-results.md
Consumes: Tasks 1–3 的接口。Produces: 四命令可用入口、预览/任务包、用户说明和验收证据。

- [ ] 编写 CLI 非零错误、不默认整库、透明缩放/不放大/格式保留及真实节选端到端测试。
- [ ] 运行全套测试，Expected: CLI 和缩放接口不存在而失败。
- [ ] 实现 CLI 与 Pillow 按需加载，任务包携带生成封面；补齐示例和使用说明。
- [ ] 原包核对、12/36 与 15/45 逐路径和摘要核对；可取得原 ZIP 时只节选 GBA 到独立测试目录，检查 503/1509。
- [ ] 运行全套测试和 sh 实际执行，Expected: 全部 PASS；没有设备时明确记录 Android 手动权限、断连和启动仍未验收。

## 完成检查

最终进行一次独立上下文代码审查，修复重要问题并重新测试。不发布、不操作正式设备配置。四阶段软件实现完成不等同于设备全部验收完成。
