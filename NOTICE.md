# 许可与第三方声明

HandheldToolbox — Copyright (c) 2026 quning19 and contributors.

除保留原许可的上游代码、第三方资源及另有声明的文件外，本项目应用代码和文档采用 GNU General Public License version 3 only（SPDX: GPL-3.0-only），许可全文见根目录 LICENSE。

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3 only.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

## 软件来源

| 组件 | 来源与许可 |
|---|---|
| RetroLibX 引擎及原始示例 | [tiancheng91/retrolibx](https://github.com/tiancheng91/retrolibx)，Copyright (c) 2026 tiancheng91；原 MIT 许可完整保留于 [RetroLibX-MIT.txt](docs/licenses/RetroLibX-MIT.txt)，上游提交历史保留 |
| ES-DE 主题下载器参考逻辑 | [ES-DE](https://gitlab.com/es-de/emulationstation-de)，GuiThemeDownloader.cpp；保留 [ES-DE.txt](docs/licenses/ES-DE.txt) 中的版权及 MIT 声明 |
| QFluentWidgets / PySide6-Fluent-Widgets | [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6)，本项目使用 GPLv3 开源版本 |
| PySide6 / Qt for Python | [Qt for Python](https://www.qt.io/qt-for-python)，适用其 LGPLv3 / GPLv3 / 商业许可；本项目通过包管理器安装，依赖包保留自身许可 |

其他 Python 依赖见 pyproject.toml 与 uv.lock，各自版权和许可保持不变。本文件不替代随依赖包提供的声明；后续二进制打包须同时保留所需依赖许可。

## 第三方图像与主题

平台卡片位于 `src/frontend_gui/assets/cards/`，从相应主题提取用于平台展示；不包含完整主题。来源 README、作者署名及许可原文保留在各目录的 SOURCE-NOTICE.txt / SOURCE-LICENSE.txt。

| 卡片目录 | 来源与许可记录 |
|---|---|
| alekfull-nx | [Alekfull NX](https://github.com/anthonycaccese/alekfull-nx-es-de)，原画与布局 fagnerpc，移植 anthonycaccese，部分素材 ClassicxCola；来源声明 CC BY-NC-SA 2.0 |
| aura | [Aura](https://github.com/Siddy212/aura-es-de)，作者 Siddy212；来源 README 声明 CC BY-NC-SA 2.0，同时附带 CC0 文本，二者范围存在差异，未将整套卡片视为 CC0 |
| canvas | [Canvas](https://github.com/Siddy212/canvas-es-de)，作者 Siddy212；来源 README 声明 CC BY-NC-SA 2.0，同时附带 CC0 文本，二者范围存在差异，未将整套卡片视为 CC0 |
| iisu | [iiSU Interpreted](https://github.com/VictorUnlocked/iisu-interpreted-es-de)；官方目录署名 MrVictorFull、UsagiShade，来源 README 致谢 anthonycaccese、solojazz，保留的资料未提供明确素材许可，不能视为已获得 GPL 或商业使用授权 |

CC BY-NC-SA 2.0 条款见 https://creativecommons.org/licenses/by-nc-sa/2.0/ 。游戏、主机、商标及其他原始图像的权利仍归各权利人；上述记录不额外授予相关权利。涉及许可范围不明确的素材，再分发或商用前应向权利人确认。

官方目录和预览取自 [ES-DE themes-list](https://gitlab.com/es-de/themes/themes-list)，运行时下载的主题及预览遵循各自来源许可。主题转换不会改变素材许可。

应用图标及设计原稿的生成来源记录见 [图标说明](docs/design/assets/app-icons/README.md)。
