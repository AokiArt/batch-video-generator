# -*- coding: utf-8 -*-
"""
分镜关卡（关卡 K）—— 拦住「一帧没有主角」这件事。

它由**两道**组成，一硬一软，分工必须说清：

  ┌ 关卡 K-1（硬）· 分镜表关卡  · `--表 分镜表.json`
  │   校验每镜八列填满（含「这句的物件」），且「主角」栏只写一个。
  │   全填满、主角唯一 → 过；缺一格 → 拦。**这一道是可靠的**，因为它查的是文本不是像素。
  │
  └ 关卡 K-2（软）· 画面体检   · `--帧 a.png b.png ...`
      出三个数（重点度 / 亮区占比 / 亮斑簇数）+ 最亮区位置，**只报数，不拦人**。
      唯一会记告警的是「亮斑簇数 ≥ 4」—— 那是画面里有 4 处以上亮点在抢注意力。

【🔴 2026-10-09 标定结论：亮度统计不能当判别器（重要，别重蹈）】
最初想把「一帧一主角」做成像素关卡：算最亮区占比、亮度集中度，不达标就拦。
拿两组图实测后**否定**了这个设计（下面数字是裁掉水印边距后重测的最终值）：
  · 参考片 10 张代表帧：重点度 0.17–0.64，亮区占比 0.89%–9.52%，亮斑簇数 1–8
  · 上一版 CatanVibe 8 帧：重点度 0.28–0.43，亮区占比 0.60%–13.10%，亮斑簇数 1–10
**两组完全重叠** —— 连上一版的重点度下限（0.28）都比参考片的下限（0.17）还高。
原因很清楚：上一版的毛病不是「画面不暗、没有亮区」，它的配色和参考片一样是
近黑 + 一小块暖光。亮度分布只能看出「亮的地方在哪」，看不出「亮的是不是**该亮的那一个**」。
  V_250 只有一团亮斑，看着合格；但那团亮斑里塞着整套棋盘 —— 亮度分不出
  「一个棋子当主角」和「整块棋盘均匀亮着」的区别。
→ 所以「谁是主角」这件事**像素算不出来，必须由会看画面的模型（VLM）来判**。
  这一道留在 `--帧` 里当**体检报告**用（它说得出「最亮的地方在九宫格的哪一格」，
  对人对稿子都有用），但不冒充关卡。
  真正要拦「没有主角」，走的是 K-1 那道文本关卡 + 人工/VLM 逐帧看图作答
  （每帧问一句「这一帧的视线第一落点是什么」，2 秒答不出就废）。

【另一条实测教训：图片边距会污染结果】
参考片是抖音截图，四角带着 抖音水印 / 账号名 / LOGO 框。不裁边直接测，
好几帧的「最亮区」落在 (1720,887) —— 那是右下角的抖音水印，不是画面内容。
所以默认 `--忽略边距 0.08`（四边各裁 8%）。**测任何带 UI 覆盖层的图都要先裁边。**

【用法】
  python3 分镜关卡.py --表 分镜表.json                      # 硬关卡
  python3 分镜关卡.py --帧 out/*.png --json 体检.json        # 软体检
  python3 分镜关卡.py --帧 a.png --忽略边距 0.12

【退出码】硬关卡不过 = 1；体检永远 = 0（它不拦人）。
"""

import argparse
import json
import os
import sys
from collections import deque
from statistics import median

try:
    from PIL import Image
except ImportError:
    raise SystemExit("缺 Pillow：pip3 install Pillow（本机已装，换机器才要装）")

# ── 体检用的常量（2026-10-09 标定；只用于描述，不用于拦人）────────
BRIGHT_T = 0.72         # 「亮像素」= 全图峰值 × 这个系数
CLUSTER_T = 0.80        # 「亮格」= 峰值格 × 这个系数
CLUSTER_WARN = 4        # 亮斑簇数到几就记一条告警
GW, GH = 24, 14         # 工作网格（宽 × 高）
REF_W, REF_H = 1920, 1080

# 硬关卡要求的列（缺一格就不许往下走）
NEED_COLS = ["台词", "这句的物件", "景别", "主角", "配角", "镜头", "主角动", "光", "转场"]
HERO_COL = "主角"

ZONES = ["左上", "上中", "右上", "左中", "正中", "右中", "左下", "下中", "右下"]


def zone_of(x, y, w, h):
    col = min(2, int(x * 3 / max(1, w)))
    row = min(2, int(y * 3 / max(1, h)))
    return ZONES[row * 3 + col]


def load_gray(path, margin):
    """读图 → 灰度 → 按边距裁掉四周 → 缩到 GW×GH 网格。返回 (网格亮度表, 有效区尺寸)。"""
    if not os.path.exists(path):
        raise SystemExit(f"缺图：{path}")
    im = Image.open(path).convert("L")
    w, h = im.size
    dx, dy = int(w * margin), int(h * margin)
    if dx * 2 >= w or dy * 2 >= h:
        raise SystemExit(f"--忽略边距 {margin} 太大，把整张图裁没了：{path}")
    im = im.crop((dx, dy, w - dx, h - dy))
    cw, ch = im.size
    grid = im.resize((GW, GH), Image.BOX)
    return list(grid.getdata()), (cw, ch), (dx, dy)


def bright_ratio_from_grid(means):
    peak = max(means)
    if peak <= 0:
        return 0.0
    thr = peak * BRIGHT_T
    return sum(1 for v in means if v >= thr) / len(means)


def count_clusters(means):
    """在网格上数「亮格」的连通簇（4 邻域，手写 BFS，不引 scipy）。"""
    peak = max(means)
    if peak <= 0:
        return 0
    thr = peak * CLUSTER_T
    hotset = {i for i, v in enumerate(means) if v >= thr}
    seen = set()
    n = 0
    for start in hotset:
        if start in seen:
            continue
        n += 1
        q = deque([start])
        seen.add(start)
        while q:
            cur = q.popleft()
            r, c = divmod(cur, GW)
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < GH and 0 <= nc < GW:
                    nxt = nr * GW + nc
                    if nxt in hotset and nxt not in seen:
                        seen.add(nxt)
                        q.append(nxt)
    return n


def check_frame(path, margin):
    means, (cw, ch), (dx, dy) = load_gray(path, margin)
    peak_cell = max(means)
    med_cell = median(means)
    focus = (peak_cell - med_cell) / 255.0
    idx = means.index(peak_cell)
    row, col = divmod(idx, GW)
    # 网格坐标 → 裁切后像素 → 原图像素
    cx = dx + int((col + 0.5) * (cw / GW))
    cy = dy + int((row + 0.5) * (ch / GH))
    ratio = bright_ratio_from_grid(means)
    clusters = count_clusters(means)

    warns = []
    if clusters >= CLUSTER_WARN:
        warns.append(f"亮斑簇数 {clusters} ≥ {CLUSTER_WARN}：画面里有 {clusters} 处亮点在抢注意力，"
                     f"看看是不是该压暗几处")
    if ratio < 0.01:
        warns.append(f"亮区占比 {ratio*100:.2f}% 极低：确认这是故意的「留白景」")

    return {
        "帧": os.path.basename(path),
        "最亮区像素": [cx, cy],
        "最亮区九宫格": zone_of(cx, cy, REF_W, REF_H),
        "重点度": round(focus, 3),
        "亮区占比": round(ratio, 4),
        "亮斑簇数": clusters,
        "告警": warns,
    }


def report_one(r):
    print(f"\n【画面体检】{r['帧']}")
    print(f"  最亮区     ({r['最亮区像素'][0]}, {r['最亮区像素'][1]})　九宫格：{r['最亮区九宫格']}")
    print(f"  重点度     {r['重点度']:.2f}　（越大越集中；本片型实测 0.26–0.55 都正常）")
    print(f"  亮区占比   {r['亮区占比']*100:.2f}%")
    print(f"  亮斑簇数   {r['亮斑簇数']}　（≥ {CLUSTER_WARN} 会记告警）")
    for w in r["告警"]:
        print(f"  ⚠ {w}")
    if not r["告警"]:
        print("  ✓ 无告警")


def check_table(path):
    """硬关卡：八列填满 + 主角唯一。返回 (镜数, 问题列表)。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        shots = data
    elif isinstance(data, dict):
        shots = data.get("镜头", [])
    else:
        raise SystemExit(f"分镜表格式不对：{path}（要 JSON 数组，或带「镜头」键的对象）")

    problems = []
    if not shots:
        problems.append("分镜表是空的")
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict):
            problems.append(f"镜 {i:02d}：这一条不是对象")
            continue
        for k in NEED_COLS:
            if not str(s.get(k, "")).strip():
                problems.append(f"镜 {i:02d}：『{k}』栏是空的")
        hero = str(s.get(HERO_COL, "")).strip()
        if hero and any(ch in hero for ch in "、，,"):
            problems.append(f"镜 {i:02d}：主角写了不止一个（「{hero}」）—— 一帧只能有一个主角")
    return len(shots), problems


def main():
    ap = argparse.ArgumentParser(description="分镜关卡：硬关卡查分镜表，软体检看画面")
    ap.add_argument("--帧", nargs="+", help="要体检的帧图（一张或多张）")
    ap.add_argument("--表", help="分镜表 JSON（硬关卡）")
    ap.add_argument("--忽略边距", type=float, default=0.08, dest="margin",
                    help="四边各裁掉的比例，默认 0.08（避开抖音水印/LOGO 框）")
    ap.add_argument("--json", help="把体检结果另存成 JSON")
    args = ap.parse_args()

    if not args.帧 and not args.表:
        ap.print_help()
        raise SystemExit(2)

    results = []
    hard_failed = False

    if args.表:
        n, problems = check_table(args.表)
        print(f"【分镜表关卡 · 硬】{args.表}　共 {n} 镜")
        if problems:
            print(f"  判定：不通过，{len(problems)} 处：")
            for p in problems:
                print(f"    ✗ {p}")
            hard_failed = True
        else:
            print("  判定：通过 —— 八列填满，每镜只有一个主角")

    if args.帧:
        for p in args.帧:
            r = check_frame(p, args.margin)
            report_one(r)
            results.append(r)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"边距": args.margin, "提示": "本体检只报数不拦人；拦人的是 --表",
                       "结果": results}, f, ensure_ascii=False, indent=2)
        print(f"\n体检结果已存：{args.json}")

    if args.帧:
        print(f"\n{'='*52}")
        print(f"共体检 {len(results)} 帧；有告警 {sum(1 for r in results if r['告警'])} 帧")

    sys.exit(1 if hard_failed else 0)


if __name__ == "__main__":
    main()
