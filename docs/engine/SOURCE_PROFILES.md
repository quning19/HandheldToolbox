# Pegasus 与天马G来源规则

来源规则用于描述资源包的约定，不替代平台定义，也不改变排序策略。文件格式由 Pegasus adapter 解析，来源配置在导入通用模型时决定是否补找媒体、规范版本说明；ES-DE adapter 不再根据 Pegasus 字段猜测开发者含义。

## 配置位置与选择

- [generic.json](../../src/retrolibx/profiles/generic.json)：普通 Pegasus，保留开发者原义，不按天马目录补找未声明的媒体。
- [pegasus-g.json](../../src/retrolibx/profiles/pegasus-g.json)：当前天马G资源包，启用原有媒体约定、版本说明处理及 VIB 确认。
- [加载与规范化代码](../../src/retrolibx/core/source_profiles.py)。

原引擎 `retrolibx.cli` 的 Android `scan --config` 和 `build --config` 默认使用天马G配置，普通 `scan/inspect/validate/convert` 默认使用 generic。其普通命令处理天马包时应明确指定 `--source-profile src/retrolibx/profiles/pegasus-g.json`。该选项为文件路径，相对命令工作目录解析。独立 `library_converter` 的 Windows 业务使用天马G规则，不需在页面手工选择 profile。

HandheldConfig 可指定 `source_profile` 文件，相对配置文件所在目录解析。示例见 [profile.local.json](../../examples/retrolibx/profile.local.json)，复制时需按新位置调整相对路径。使用 `scan --config` 时从配置文件指定规则，不再同时传 `--source-profile`。可将配置复制到自己的目录进行定制；显式文件缺失、字段拼写错误或路径越界会报错，不自动寻找替代文件。

## 当前天马配置

```json
{
  "version": 1,
  "name": "pegasus-g",
  "media_directory": "media",
  "media_fallbacks": {
    "box_front": [
      "boxfront",
      "box_front",
      "boxart2d"
    ],
    "logo": [
      "logo",
      "wheel"
    ],
    "video": "video"
  },
  "developer_as_version_note": true,
  "version_note_label": "版本说明",
  "confirmation_systems": [
    "GBA vib"
  ]
}
```

| 字段 | 含义 |
|---|---|
| `media_directory` | 平台 metadata 目录内的媒体相对目录；`null` 时关闭目录补找 |
| `media_fallbacks` | 通用媒体角色 → 单个文件名 stem 或 stem 列表；不指定扩展名 |
| `developer_as_version_note` | 是否把等于游戏名或以“游戏名加空格”开头的 developer 视为包内版本标记 |
| `version_note_label` | 添加到简介中的说明标签 |
| `confirmation_systems` | Android build 需要用户确认启动方案的内部平台 ID，使用 XML 的精确 `name` |

### 媒体

显式 `assets.*` 引用能解析且格式有效时优先使用。缺失或失效时，内置天马配置只补找封面、Logo、视频三类；所有别名中只有唯一有效候选才采用，歧义不猜测。不补找额外五类素材，也不会因它们不存在而产生默认补找警告。完整规则见 [SHARED_MEDIA.md](SHARED_MEDIA.md)。可把目录改为 `art`、把封面名改为 `front` 等，格式适配器无需改动。补找不能越出来源平台目录。

设置 `media_fallbacks={}` 即关闭这部分补找。ES-DE 只导出 covers、marquees、videos，继续由 ES-DE adapter 管理；自定义补找规则不会扩大 ES-DE 导出范围。原始额外素材字段仍按通用模型或扩展字段保留。

### 版本说明

例如 `game: 黄金太阳1 开启的封印` 的 `developer: 黄金太阳1 开启的封印 2024汉化`，天马规则会把该文字加入简介的“版本说明”，清空标准 developer。`developer: Camelot` 保持为开发者。相同的版本说明行不会再次添加。

普通 generic 不做上述转换。原始记录始终留在 `Game.source_metadata.pegasus_fields`，规范化出的说明还保存在 `source_metadata.version_note`；不会改写源 metadata 文件。规范化后的 Game 可供不同目标前端使用。

### VIB 启动确认

默认天马规则要求 `GBA vib` 出现在 HandheldConfig 的 `confirmed_systems`（或其明确的输出系统名）后，才生成可执行 Android 任务。未确认时仍生成列表及完整配置预览。

确认后沿用现有/基线 XML 的全部启动选项和顺序，不再要求源或目标命令含 `gpsp_rumble`，也不强迫提供覆盖命令。`launch_overrides` 仍是主动替换命令的独立可选设置，非确认的必填条件。若使用者需要取消该来源的额外确认，可在自己的规则文件将 `confirmation_systems` 设为 `[]`。

这项检查只约束 Android 可执行任务，不决定核心是否真的支持震动，也不操作设备界面或游戏。实际启动和震动效果由用户验收。普通 convert 只导出列表/媒体，不生成 Android 启动配置，因而不执行此任务确认检查。

## 本次检查范围

2026-10-12，经用户批准的三个来源规则用例通过，涉及媒体配置、显式引用优先、路径保护、版本说明与原字段保留、VIB确认及完整命令。全部检查范围和交付状态集中在[STATUS.md](STATUS.md)。旧dist已清理，待批准后重新打包。
