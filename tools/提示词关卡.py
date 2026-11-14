# -*- coding: utf-8 -*-
"""关卡 P · 生视频提示词上传前的硬闸。

用法：
    python3 提示词关卡.py --稿 提示词.txt --时长 15
    python3 提示词关卡.py --稿 提示词.txt --时长 15 --镜字数 100 --密度 8

不过关 → 退出码 1，禁止上传。
"""
import argparse
import re
import sys

# 继承块：这些段落缺一条就说明没继承总纲
REQUIRED_BLOCKS = [
    ("视觉基准", ("视觉基准", "朱漆红墙")),
    ("镜头参数", ("35mm", "胶片颗粒")),
    ("光", ("侧逆光", "暖金")),
    ("空间方位", ("背对红墙", "面朝红墙")),
    ("画面左右", ("永远在画面", "右边")),
    ("人物道具", ("长衫", "相机")),
    ("声音", ("音色", "没有背景音乐|禁止任何背景音乐|不铺任何背景音乐")),
    ("画面总则", ("不要字幕", "水印")),
]

SHOT_RE = re.compile(r"【?((?:第[一二三四五六七八九十]+镜)|(?:镜\s*\d+))\s*[｜|]\s*([0-9.]+)\s*[–-]\s*([0-9.]+)\s*秒")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--稿", required=True)
    ap.add_argument("--时长", type=float, required=True, help="本条视频总时长（秒）")
    ap.add_argument("--镜字数", type=int, default=100, help="每镜「画面」字段最少字数")
    ap.add_argument("--动作字数", type=int, default=50, help="每镜「动作」字段最少字数")
    ap.add_argument("--密度", type=float, default=8.0, help="每秒最少字数（8 字/秒 = 每 10 秒 80 字）")
    ap.add_argument("--无人物", action="store_true", help="空镜/无人物段：跳过空间方位与画面左右两项继承检查")
    a = ap.parse_args()

    txt = open(a.稿, encoding="utf-8").read()
    body = re.sub(r"\s", "", txt)
    errs = []

    # 1. 继承块
    skip = {"空间方位", "画面左右"} if a.无人物 else set()
    for name, keys in REQUIRED_BLOCKS:
        if name in skip:
            continue
        if not any(re.search(k, txt) for k in keys):
            errs.append(f"[继承] 缺少「{name}」：应含 {' / '.join(keys)}")

    # 2. 镜头切分
    marks = list(SHOT_RE.finditer(txt))
    if not marks:
        errs.append("[结构] 找不到「镜N｜起–止秒」形式的镜头块")
    blocks = []
    for i, m in enumerate(marks):
        s = m.start()
        e = marks[i + 1].start() if i + 1 < len(marks) else len(txt)
        blocks.append((m.group(1), float(m.group(2)), float(m.group(3)), txt[s:e]))

    # 3. 每镜字段与字数
    for name, t0, t1, blk in blocks:
        flat = re.sub(r"\s", "", blk)
        for field, alias in (("画面", r"画面(?:细节(?:与位置关系)?)?"), ("动作", r"(?:动作|主角动)")):
            mm = re.search(alias + r"[：:]([^\n]*)", blk)
            if not mm:
                errs.append(f"[字段] {name} 缺「{field}」")
                continue
            n = len(re.sub(r"\s", "", mm.group(1)))
            bar = a.镜字数 if field == "画面" else a.动作字数
            if n < bar:
                errs.append(f"[字数] {name} 的「{field}」只有 {n} 字，要求 ≥{bar}")
        if "台词" not in blk and "line" not in blk:
            errs.append(f"[字段] {name} 缺「台词」（没台词也要写“无台词”）")

    # 4. 整条密度
    density = len(body) / a.时长 if a.时长 else 0
    if density < a.密度:
        errs.append(f"[密度] 全文 {len(body)} 字 / {a.时长:g} 秒 = {density:.1f} 字/秒，要求 ≥{a.密度:g}（每 10 秒 ≥{a.密度*10:g} 字）")

    # 5. 时长覆盖
    if blocks:
        span = max(b[2] for b in blocks) - min(b[1] for b in blocks)
        if abs(span - a.时长) > 1.0:
            errs.append(f"[时长] 镜头块覆盖 {span:.1f} 秒，与声明时长 {a.时长:g} 秒不符")

    print(f"镜头块 {len(blocks)} 个 · 全文 {len(body)} 字 · 密度 {density:.1f} 字/秒")
    if errs:
        print("❌ 不过关，禁止上传：")
        for e in errs:
            print("   -", e)
        sys.exit(1)
    print("✅ 过关，可以上传")


if __name__ == "__main__":
    main()
