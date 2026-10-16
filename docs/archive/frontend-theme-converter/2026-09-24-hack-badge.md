# 2026-09-24 HACK 标记显示调整记录

本记录整理第一批七个主题的栅格图片回退标记方案。当前正式构建使用 [`P_pill_top_right`](../config/badge_params.json)；旧版底部灰色通栏保留为实验基线，不参与正式构建。标记文字来自批次配置，因此同一套显示规则也用于 HD、MSU1、VIB、WARE 等回退标记。

## 最终显示效果

- 右上角黑色药丸底板，透明度 170/255，白色粗体文字；圆角半径为药丸高度的一半。
- 尺寸依据为 **画布长边 + 画布短边的一半**。药丸高度为 `min(round(0.065 × 尺寸依据 + 15), 140)` 像素，至少 1 像素。字体大小约为药丸高度的 62%，左右内边距各约为高度的 38%。
- 对于 1920×1080 的图，原公式约得 175 像素，最终由 140 像素上限控制；较小图片继续按公式增长。
- 若脚本识别到原图的圆角矩形画面板，则相对画面板右上角定位，内缩量为画面板短边的 3.5%；否则相对整张图片右上角定位，内缩量为画布短边的 4.5%。

圆角矩形识别是 [`tools/badge.py`](../tools/badge.py) 中基于透明度与行宽变化的脚本判断。今天针对镂空图误识别增加了填充率、中心行宽度及上下边缘一致性检查；未通过判断的图按整张画布定位。预览图中用于显示图片边界的青色描边仅出现在实验拼图里，不进入导出素材。

## 哪些资源会加标记

目标平台已有的资源一律原样复制。只有目标资源缺失、使用母体或显式回退资源，且该栅格槽位列在主题 `badge_slots` 时，才渲染药丸标记。各主题具体槽位以 [`config/themes/`](../config/themes/) 为准：

| 主题 | 回退时加标记的主要栅格资源 | 明确直接复制的资源 |
| --- | --- | --- |
| Alekfull NX | JPG backgrounds | carousel；SVG logos |
| Aura | controllers；default-art 的四种附加图片 | default-art 的基础图片；system-logo WebP/SVG |
| Canvas | art、capsule、controller、logo、screenshot 等栅格槽位 | SVG system-logo |
| Elementerial | classic/modern artwork | logos |
| Iconic | system 图片；default/classic/modern background | carousel；default/classic/modern overlay |
| iiSU Interpreted | artwork、controllers | — |
| PlayStation-X | background、consoles、icons | overlays；SVG logos；视频 |

这里的“carousel 跳过”指 Alekfull NX、Iconic 等主题中**明确配置为复制**的 carousel 槽位。Canvas 的 `carousel-icons-*` 是已配置的标记槽位，回退时仍会加标记。SVG 与视频只复制、改名，不渲染标记。

## 今天的调整过程

1. 从固定像素大小改为按图片尺寸缩放，采用“长边 + 半个短边”作为基础。
2. 改为右上角黑底白字药丸，并将底板透明度定为 170/255。
3. 针对有圆角画面板的图改为对齐画面板；对镂空图加强判断，避免误把镂空轮廓当作圆角矩形。
4. 将各 profile 指定的 carousel、overlay 等展示层资源排除；不能仅凭目录名中的 `carousel` 判定。
5. 试过 `0.05 × 尺寸依据 + 30`，小图标记偏大，改回 `0.065 × 尺寸依据 + 15`。
6. 为 1080×1920 等大图加入 140 像素高度上限，保留小图的原有比例。

## 预览与验证

GBA HACK 最终样张：[Canvas](../lab/pill-canvas-gba-hack-v6-cap140/overview.png)、[Iconic](../lab/pill-iconic-gba-hack-v6-cap140/overview.png)、[iiSU Interpreted](../lab/pill-iisu-gba-hack-v6-cap140/overview.png)、[PlayStation-X](../lab/pill-playstation-x-gba-hack-v6-cap140/overview.png)；另有 [Alekfull NX、Aura、Elementerial 的预览拼图](../lab/new-themes-gba-preview.png)。七个主题已按当前规则生成在 [`dist/themes/`](../dist/themes/) 中。

本轮文件验证记录：243 张栅格图带标记、121 个直拷资源与源文件字节一致、62 个生成的 XML 可解析；12 项单元测试及七个主题的配置预检和产物校验通过。这些是文件与规则层面的检查，尚未进行掌机实机显示验证。
