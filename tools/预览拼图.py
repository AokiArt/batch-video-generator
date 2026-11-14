#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预览拼图.py —— 把"将要上传的图"拼成一张带标签的总览，供确认前肉眼核对。

每格标：序号 / 文件名 / sha256 前 8 位。
名字可能写错，像素不会——拼图上的图就是脚本实际会发出去的那份文件。

用法：
  python3 预览拼图.py --out 预览.jpg 图1.png 图2.png ...
"""
import argparse, hashlib, pathlib
from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    cols = a.cols
    cw, ch = 760, 326
    bar = 34
    rows = (len(a.files) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, (ch + bar) * rows), (248, 248, 248))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 20)
    except Exception:
        font = ImageFont.load_default()

    for i, f in enumerate(a.files):
        p = pathlib.Path(f)
        im = Image.open(p).convert("RGB")
        im.thumbnail((cw, ch))
        x = (i % cols) * cw
        y = (i // cols) * (ch + bar)
        sheet.paste(im, (x, y))
        sha = hashlib.sha256(p.read_bytes()).hexdigest()[:8]
        d.text((x + 10, y + ch + 6), f"{i+1}. {p.name}   sha:{sha}", fill=(20, 20, 20), font=font)

    sheet.save(a.out, quality=90)
    print("拼图已出：" + a.out)


if __name__ == "__main__":
    main()
