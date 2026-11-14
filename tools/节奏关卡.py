# -*- coding: utf-8 -*-
"""
关卡 L · 台词与节奏硬线校验（MG动画手册 §4.6）

两档输入，自动识别：
  A) --表 分镜表.json     读 "镜头" 键（F0/F12…）或裸数组；时长按相邻帧号差 ÷ fps
  B) --稿 台词稿.json     [{"镜号":"01","台词":"…","时长":4.0}, ...]

硬线（不过 → 退出码 1）：
  H1 单句 ≤ 24 字            （英文 20 words/sentence 换算）
  H2 全片字/秒 ∈ [2.5, 5.5]   （低于＝镜头空转，高于＝念不完；MG 不按「每镜 20 字」卡）
  H3 单镜时长 1.0–12.0 秒     （MG 默认 2–4 秒）
  H4 平均 ≤ 8 秒/镜           （≈ 每 15–30 秒至少换一次画面）
  H5 前 10 秒 ≥ 2 镜          （钩子）
  H6 Tier1 反 AI 腔词命中     （出现即拦）

软线（只报不拦）：
  S1 Tier2 词 ≥2 个
  S2 单镜台词 > 70 字
  S3 屏幕字 > 14 字
  S4 全片时长与 --目标 偏差 > 10%
"""
import argparse
import json
import re
import sys

TIER1 = ["在这个全面的指南中", "让我们深入探讨", "赋能", "无缝集成", "释放全部潜力",
         "举足轻重的是", "在当今数字化浪潮下", "充分利用", "打造闭环"]
TIER2 = ["此外", "前沿的", "顶尖的", "助力你", "提升你的", "旅程", "图景", "全方位"]
TIER3_PAT = [
    # 只在「A、B、C的/性/化」这种形容词串上触发，避免把地名列表误判
    ("三连形容词", re.compile(r"[^\s，。、；：]{2,4}、[^\s，。、；：]{2,4}、[^\s，。、；：]{2,4}[的性化型]")),
    ("空强调词", re.compile(r"真正|确实|非常|极其|绝对")),
    ("套路开头", re.compile(r"^接下来(我们|来看|讲)")),
]

CJK = re.compile(r"[一-鿿0-9A-Za-z]")


def count_chars(s: str) -> int:
    """只数实字（不含标点/空白），与手册口径一致。"""
    return len(CJK.findall(s or ""))


def split_sentences(s: str):
    parts = re.split(r"[。！？；!?;]", s or "")
    return [p.strip() for p in parts if count_chars(p) > 0]


def load_items(args):
    """返回 (items, 总时长秒 or None, 说明)"""
    raw = json.load(open(args.表 or args.稿, encoding="utf-8"))

    # B) 台词稿：裸数组，每项自带 时长
    if isinstance(raw, list):
        items = []
        total = 0.0
        for it in raw:
            d = float(it.get("时长", 0) or 0)
            items.append({"镜号": str(it.get("镜号", len(items) + 1)), "台词": it.get("台词", ""),
                          "时长": d, "屏幕字": it.get("屏幕字", "")})
            total += d
        return items, total, "台词稿（自带时长）"

    # A) 分镜表：{"镜头": {...}}
    shots = raw.get("镜头")
    if isinstance(shots, dict):
        keys = list(shots.keys())
        nums = []
        for k in keys:
            m = re.search(r"(\d+(?:\.\d+)?)", k)
            nums.append((float(m.group(1)) if m else None, k))
        if all(n is not None for n, _ in nums):
            nums.sort()
            fps = float(args.fps)
            items = []
            for i, (n, k) in enumerate(nums):
                d = (nums[i + 1][0] - n) / fps if i + 1 < len(nums) else None
                it = shots[k]
                if d is None:                      # 末镜：看生成块/字段
                    for kk in ("时长", "duration"):
                        if kk in it:
                            d = float(it[kk]); break
                items.append({"镜号": k, "台词": it.get("台词", ""),
                              "时长": d if d is not None else 0.0,
                              "屏幕字": it.get("屏幕字", "")})
            total = sum(i["时长"] for i in items)
            return items, total, f"分镜表（按帧号差 ÷ {args.fps}fps）"
        # 帧号不可解析 → 退化成无时长
        items = [{"镜号": k, "台词": v.get("台词", ""), "时长": 0.0, "屏幕字": v.get("屏幕字", "")}
                 for k, v in shots.items()]
        return items, None, "分镜表（帧号不可解析，跳过时长检查）"

    if isinstance(shots, list):
        items = [{"镜号": str(i + 1), "台词": v.get("台词", ""),
                  "时长": float(v.get("时长", 0) or 0), "屏幕字": v.get("屏幕字", "")}
                 for i, v in enumerate(shots)]
        return items, sum(i["时长"] for i in items), "分镜表（数组）"

    raise SystemExit("✗ 认不出输入格式：需要 '镜头' 键或裸数组")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--表")
    ap.add_argument("--稿")
    ap.add_argument("--fps", default="30")
    ap.add_argument("--目标", type=float, default=None, help="目标总时长（秒），用于 S4")
    a = ap.parse_args()
    if not (a.表 or a.稿):
        raise SystemExit("✗ 要么 --表 要么 --稿")

    items, total, how = load_items(a)
    hard, soft = [], []
    has_dur = total and total > 0 and any(i["时长"] > 0 for i in items)

    # ── 硬线 ──
    for i, it in enumerate(items):
        lines = split_sentences(it["台词"])
        for ln in lines:
            n = count_chars(ln)
            if n > 24:
                hard.append(f"H1 单句超 24 字（{n}）｜镜 {it['镜号']}：{ln[:28]}…")
        if has_dur and it["时长"] > 0:
            if it["时长"] < 1.0:
                hard.append(f"H3 单镜 {it['时长']:.1f}s < 1.0s（太快）｜镜 {it['镜号']}")
            elif it["时长"] > 12.0:
                hard.append(f"H3 单镜 {it['时长']:.1f}s > 12.0s（MG 太长）｜镜 {it['镜号']}")

    if has_dur and items:
        all_chars = sum(count_chars(it["台词"]) for it in items)
        rate = all_chars / total if total else 0
        if not (2.5 <= rate <= 5.5):
            hard.append(f"H2 全片 {rate:.1f} 字/秒，超出 2.5–5.5（{'镜头空转' if rate<2.5 else '念不完'}）")
        avg = total / max(1, len(items))
        if avg > 8.0:
            hard.append(f"H4 平均 {avg:.1f}s/镜 > 8s（换画面太慢）")
        # 钩子：前 10 秒内至少 2 镜
        acc, cnt = 0.0, 0
        for it in items:
            if it["时长"] <= 0:
                break
            acc += it["时长"]; cnt += 1
            if acc >= 10.0:
                break
        if cnt < 2:
            hard.append(f"H5 前 10 秒只有 {cnt} 个镜头（钩子不够）")

    for it in items:
        for w in TIER1:
            if w in (it["台词"] or ""):
                hard.append(f"H6 Tier1 反 AI 腔：「{w}」｜镜 {it['镜号']}")

    # ── 软线 ──
    for it in items:
        hit = [w for w in TIER2 if w in (it["台词"] or "")]
        if hit:
            soft.append(f"S1 Tier2 词 {hit}｜镜 {it['镜号']}")
        if count_chars(it["台词"]) > 70:
            soft.append(f"S2 单镜台词 {count_chars(it['台词'])} 字 > 70｜镜 {it['镜号']}")
        if it["时长"] > 3.0 and count_chars(it["台词"]) < 8:
            soft.append(f"S2b 空镜偏长：{it['时长']:.1f}s 只有 {count_chars(it['台词'])} 字｜镜 {it['镜号']}")
        if count_chars(it.get("屏幕字", "")) > 14:
            soft.append(f"S3 屏幕字超 14 字｜镜 {it['镜号']}")
    for name, pat in TIER3_PAT:
        for it in items:
            m = pat.search(it["台词"] or "")
            if m:
                soft.append(f"S? Tier3 {name}：「{m.group(0)}」｜镜 {it['镜号']}")
                break
    if a.目标 and has_dur:
        dev = abs(total - a.目标) / a.目标
        if dev > 0.10:
            soft.append(f"S4 总时长 {total:.1f}s 与目标 {a.目标:.1f}s 偏差 {dev*100:.0f}% > 10%")

    # ── 报告 ──
    print(f"# 关卡 L · 台词与节奏　输入：{how}")
    print(f"\n| 项 | 值 |")
    print(f"|---|---|")
    print(f"| 镜数 | {len(items)} |")
    if has_dur:
        print(f"| 总时长 | {total:.1f} 秒 |")
        print(f"| 平均 | {total/max(1,len(items)):.1f} 秒/镜 |")
    print()
    if hard:
        print("## ✗ 硬线未过（不许往下走）\n")
        for h in hard:
            print(f"- {h}")
    else:
        print("## ✓ 硬线全过")
    if soft:
        print("\n## 软线（只报不拦）\n")
        for s in soft:
            print(f"- {s}")
    print(f"\n**结论：** {'BLOCKED' if hard else 'PASS'}"
          f"（硬 {len(hard)} / 软 {len(soft)}）")
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
