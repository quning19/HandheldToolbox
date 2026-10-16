# Frontend Theme Converter

将 ES-DE 官方主题转换为适配天马 G 平台配置的主题。现有第一批处理任天堂和 Sony 平台，覆盖七个主题；后续范围见 [TODO.md](TODO.md)。

## 项目目录

| 路径 | 用途 |
| --- | --- |
| `source/configs/` | 最终完整天马 G 平台 XML 基线及 ES-DE 对照配置 |
| `source/themes/` | 七个原版主题，构建输入 |
| `source/sample/` | 参考主题，仅用于对照和实验 |
| `config/project.json` | 共用平台配置路径、主题 profile 注册和命名规则 |
| `config/themes/` | 各主题的源路径、增量路径和资源槽位 |
| `config/batches/` | 平台与槽位处理清单 |
| `config/badge_params.json` | 栅格图片标记参数 |
| `tools/` | 预检、构建、校验、打包及角标实验脚本 |
| `lab/` | 按轮次保存的角标实验文件 |
| `dist/staged/` | 各主题第一批的增量文件 |
| `dist/themes/` | 已打包的完整主题 |
| `dist/_reports/` | 构建清单、manifest 和校验报告 |
| `tests/` | 配置与规则测试 |

`source/` 是输入，`dist/` 是可重建输出。现有素材、实验文件和产物均保留在原位置。

## 七个主题

| 批次参数 | 源主题 | 增量目录 | 完整主题目录 |
| --- | --- | --- | --- |
| `alekfull-nx-batch1` | `alekfull-nx-es-de` | `dist/staged/alekfull-nx` | `dist/themes/Alekfull NX (Revisited)_天马G` |
| `aura-batch1` | `aura-es-de` | `dist/staged/aura` | `dist/themes/Aura_天马G` |
| `batch1` | `canvas-es-de` | `dist/staged/canvas` | `dist/themes/Canvas_天马G` |
| `elementerial-batch1` | `elementerial-es-de` | `dist/staged/elementerial` | `dist/themes/Elementerial_天马G` |
| `iconic-batch1` | `iconic-es-de` | `dist/staged/iconic` | `dist/themes/Iconic_天马G` |
| `iisu-batch1` | `iisu-interpreted-es-de` | `dist/staged/iisu` | `dist/themes/iiSU Interpreted_天马G` |
| `playstation-x-batch1` | `playstation-x-es-de` | `dist/staged/playstation-x` | `dist/themes/PlayStation-X_天马G` |

每个批次有独立的增量目录。完整主题由原版主题全量复制，再覆盖对应增量文件。打包时从源主题 `capabilities.xml` 读取 `<themeName>` 并追加固定后缀 `_天马G`；目录名和主题自述名相同。

## 运行流程

在项目根目录使用 Python 3.9 或更新版本，先安装 [requirements.txt](requirements.txt) 中的依赖。以下以 iiSU Interpreted 为例；处理其他主题时，把 `$batch` 和 `$theme` 替换为上表中的对应值。

```powershell
& '<python>' -m pip install -r requirements.txt
$batch = 'iisu-batch1'
$theme = 'iiSU Interpreted_天马G'

& '<python>' tools/validate.py --batch $batch
& '<python>' tools/build.py --batch $batch
& '<python>' tools/verify.py --batch $batch
& '<python>' tools/package.py --batch $batch
& '<python>' tools/verify.py --batch $batch --root "dist/themes/$theme"
& '<python>' -m unittest discover -s tests -v
```

不带 `--platform` 的构建会先清空当前 profile 的 `dist/staged/<profile>` 目录；指定 `--platform` 时只增量处理一个平台。打包会先清空对应的完整主题目录再重建。要保留现有产物时，只运行 `validate.py`、`verify.py` 和测试，不运行 `build.py` 或 `package.py`。

## 第一批规则

批次只处理清单列出的平台和槽位。资源按目标平台名、母体平台名、显式回退名依次查找；目标资源存在时原样复制。缺失时使用回退资源：列入主题 `badge_slots` 的栅格图使用右上半透明黑色药丸与白字；高度按 `0.065 ×（长边＋半个短边）＋15 像素` 计算，上限 140 像素，压黑值为 170。各 profile 指定的 carousel 与 overlay 槽位不加标记，SVG 和视频直接复制并改名。XML 按相同优先级选取源文件，只修改已有的 `<systemName>`，或按原脚本规则插入；图片、SVG、视频资源名按大小写精确匹配。`nesh` 等平台已有的专用资源因而能够保留，只补缺失槽位。

打包时，若主题有 `androidgames.xml` 与 `switch.xml`，会将 Android games 的封面和卡带比例改成与 Switch 相同，以适配竖版图。七个主题的批次配置和槽位细节见 [配置规范](docs/CONFIGURATION.md)。现有文件已通过配置、槽位及单元测试校验；真机运行情况仍需单独验证。

2026-09-24 的 HACK 药丸标记参数、定位规则、各主题排除槽位和预览结果见 [显示调整记录](docs/2026-09-24-hack-badge.md)。

## 共用平台配置

平台定义与识别已抽到[platforms.json](../FrontendTransTool/retrolibx/src/frontend_platforms/platforms.json)（路径按工程根目录说明）。通过project.paths.platform_config指定位置，Python 3.9可直接加载旁边的frontend_platforms模块。76个系统定义来自本项目已验证的custom_systems-PG/es_systems.xml；Wii标识wii与目录WII、GBA HACK与目录/主题GBA hack均保留。九个平台的母体、角标和显示名也已抽出，七个批次仅保留平台选择、槽位与主题特有处理。system_config所在的custom_systems-PG目录是最终完整配置基线，四个XML不得按主题批次或游戏选择裁剪。2026-10-12只读比较确认与RP6逐字节一致。此次没有重建或改动主题素材和dist产物。
