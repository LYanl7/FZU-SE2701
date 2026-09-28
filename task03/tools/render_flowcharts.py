"""Render task03 workflow figures from the Penpot prototype's flow descriptions."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "images"
FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

INK = "#1B1D20"
MUTED = "#68717A"
LINE = "#7D8790"
WHITE = "#FFFFFF"
YELLOW = "#FFE134"
TEAL = "#E5F5EF"
CORAL = "#FFF0E8"
PALE = "#F4F6F7"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def centered(draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], size: int = 27, color: str = INK, bold: bool = False) -> None:
    x0, y0, x1, y1 = box
    lines = text.split("\n")
    f = font(size, bold)
    line_height = size + 13
    y = (y0 + y1 - len(lines) * line_height) / 2
    for line in lines:
        width = draw.textbbox((0, 0), line, font=f)[2]
        draw.text(((x0 + x1 - width) / 2, y), line, font=f, fill=color)
        y += line_height


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fill: str = WHITE, *, size: int = 27, bold: bool = False) -> None:
    draw.rounded_rectangle(box, radius=22, fill=fill, outline="#DDE2E5", width=2)
    centered(draw, text, box, size=size, bold=bold)


def decision(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> None:
    x0, y0, x1, y1 = box
    mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
    draw.polygon([(mid_x, y0), (x1, mid_y), (mid_x, y1), (x0, mid_y)], fill="#FFF9DD", outline="#E4C84C", width=3)
    centered(draw, text, box, size=26, bold=True)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], label: str | None = None, label_at: tuple[int, int] | None = None) -> None:
    draw.line((start, end), fill=LINE, width=4)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - 17 * math.cos(angle - 0.5), end[1] - 17 * math.sin(angle - 0.5))
    right = (end[0] - 17 * math.cos(angle + 0.5), end[1] - 17 * math.sin(angle + 0.5))
    draw.polygon([end, left, right], fill=LINE)
    if label and label_at:
        draw.text(label_at, label, font=font(22, True), fill=MUTED)


def base(title: str, subtitle: str, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1480, height), "#FAFBFC")
    draw = ImageDraw.Draw(image)
    draw.text((80, 38), title, font=font(45, True), fill=INK)
    draw.text((80, 101), subtitle, font=font(22), fill=MUTED)
    draw.line((80, 154, 1400, 154), fill="#E4E8EA", width=2)
    return image, draw


def search_flow() -> None:
    image, d = base("流程 A  查找与认领", "从浏览或搜索信息，到核对线索并安全交接", 1530)
    card(d, (580, 205, 900, 275), "打开首页", YELLOW, bold=True)
    decision(d, (565, 345, 915, 465), "是否使用搜索？")
    card(d, (160, 555, 550, 665), "浏览首页寻物 / 招领\n或查看附近地图", TEAL)
    card(d, (930, 555, 1320, 665), "输入关键词\n选择分类、时间等条件", CORAL)
    card(d, (580, 755, 900, 840), "浏览匹配的信息列表", WHITE, bold=True)
    card(d, (580, 920, 900, 1005), "查看物品详情与特征", WHITE)
    card(d, (580, 1085, 900, 1170), "发起站内联系并核对", WHITE)
    decision(d, (565, 1250, 915, 1370), "信息是否匹配？")
    card(d, (160, 1415, 550, 1495), "返回列表，继续查找", PALE)
    card(d, (930, 1415, 1320, 1495), "约定交接，确认找回 / 领回", TEAL, size=25)
    arrow(d, (740, 275), (740, 345))
    arrow(d, (565, 405), (355, 555), "否", (430, 455))
    arrow(d, (915, 405), (1125, 555), "是", (1030, 455))
    arrow(d, (355, 665), (580, 795))
    arrow(d, (1125, 665), (900, 795))
    arrow(d, (740, 840), (740, 920))
    arrow(d, (740, 1005), (740, 1085))
    arrow(d, (740, 1170), (740, 1250))
    arrow(d, (565, 1310), (355, 1415), "否", (420, 1358))
    arrow(d, (915, 1310), (1125, 1415), "是", (1030, 1358))
    d.line([(160, 1455), (85, 1455), (85, 795), (555, 795)], fill=LINE, width=4)
    arrow(d, (555, 795), (580, 795))
    image.save(OUT / "flow-search.png", optimize=True)


def publish_flow() -> None:
    image, d = base("流程 B  发布与信息管理", "从发布寻物 / 招领信息，到持续跟进并标记完成", 1770)
    card(d, (580, 205, 900, 275), "点击底栏“发布”", YELLOW, bold=True)
    decision(d, (565, 350, 915, 470), "选择发布类型")
    card(d, (160, 550, 550, 640), "寻物：我丢了东西", CORAL)
    card(d, (930, 550, 1320, 640), "招领：我捡到东西", TEAL)
    card(d, (530, 730, 950, 830), "填写照片、名称、时间、地点\n物品描述与联系方式", WHITE, size=25)
    decision(d, (565, 920, 915, 1040), "必填信息完整？")
    card(d, (160, 1115, 550, 1205), "补全缺失信息", PALE)
    card(d, (930, 1115, 1320, 1205), "提交发布", YELLOW, bold=True)
    card(d, (580, 1300, 900, 1390), "在“我的 → 我的发布”\n查看与编辑记录", WHITE, size=25)
    decision(d, (565, 1475, 915, 1595), "物品已找回 / 领回？")
    card(d, (160, 1660, 550, 1740), "继续等待线索和联系", PALE)
    card(d, (930, 1660, 1320, 1740), "标记完成，归入已完成", TEAL, size=25)
    arrow(d, (740, 275), (740, 350))
    arrow(d, (565, 410), (355, 550), "寻物", (414, 470))
    arrow(d, (915, 410), (1125, 550), "招领", (1012, 470))
    arrow(d, (355, 640), (530, 780))
    arrow(d, (1125, 640), (950, 780))
    arrow(d, (740, 830), (740, 920))
    arrow(d, (565, 980), (355, 1115), "否", (420, 1045))
    arrow(d, (915, 980), (1125, 1115), "是", (1030, 1045))
    arrow(d, (1125, 1205), (900, 1345))
    arrow(d, (740, 1390), (740, 1475))
    arrow(d, (565, 1535), (355, 1660), "否", (420, 1595))
    arrow(d, (915, 1535), (1125, 1660), "是", (1030, 1595))
    d.line([(160, 1160), (85, 1160), (85, 780), (505, 780)], fill=LINE, width=4)
    arrow(d, (505, 780), (530, 780))
    image.save(OUT / "flow-publish.png", optimize=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    search_flow()
    publish_flow()
