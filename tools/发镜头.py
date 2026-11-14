#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发镜头.py —— 生视频/生图片的唯一入口（关卡）。

规则（2026-10-20 用户定）：
  花积分之前，必须先有「任务表」：积分、参考图清单（每张写清为什么用）、完整题词。
  用户确认之后才能提交；未确认不许传。

用法：
  # 1. 建表（填完给我看，等我点头）
  python3 发镜头.py --新表 任务表_镜头05.json
  # 2. 我确认后，把表里的 user_confirmed 改成 true，再跑
  python3 发镜头.py --表 任务表_镜头05.json

关卡（任一不过直接 exit 1，不花积分）：
  A 参考图必须逐条写 why（为什么用这张）
  B 题词文件必须存在且不少于 50 字
  C 必须填积分预估
  D user_confirmed 必须为 true —— 未确认不许提交
  E 服务端报价不得超过预估的 1.2 倍

调用 dreamina-canvas（国际版），只用 res:/vid: 资源引用。
"""
import argparse, json, pathlib, subprocess, sys, textwrap

CANVAS = "dreamina-canvas"
TEMPLATE = {
    "title": "",
    "mode": "video",              # video | image
    "model": "seedance_2.5",      # 视频：seedance_2.5；图片：dreamina_gpt_image_2_5_sunburst
    "duration": 20,               # 视频秒数；图片忽略
    "ratio": "21:9",
    "resolution": "720p",         # 视频 720p；图片 2K
    "refs": [],                   # [{"res": "<resourceId>", "file": "<本地路径>", "why": "<为什么用>"}]
    "prompt_file": "",            # 题词 txt 路径
    "credits_estimate": 0,
    "user_confirmed": False,      # 用户点头后才改成 true
}


def die(msg):
    print("✗ 关卡未通过：" + msg)
    print("  未提交，未花积分。")
    sys.exit(1)


def load(path):
    p = pathlib.Path(path)
    if not p.exists():
        die(f"任务表不存在：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"任务表不是合法 JSON：{e}")
    return data


def make_montage(data, refs, out_path):
    """按顺序把将要上传的参考图拼成一张（带序号/文件名/sha），供用户肉眼核对。"""
    from PIL import Image, ImageDraw, ImageFont
    root_ref = pathlib.Path(data.get("project_root") or ".")
    cols, cw, ch, bar = 2, 760, 326, 34
    rows = (len(refs) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, (ch + bar) * rows), (248, 248, 248))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 20)
    except Exception:
        font = ImageFont.load_default()
    for i, r in enumerate(refs):
        p = root_ref / r["file"]
        im = Image.open(p).convert("RGB"); im.thumbnail((cw, ch))
        x, y = (i % cols) * cw, (i // cols) * (ch + bar)
        sheet.paste(im, (x, y))
        d.text((x + 10, y + ch + 6), f"{i+1}. {p.name}   sha:{r['sha256'][:8]}",
               fill=(20, 20, 20), font=font)
    sheet.save(out_path, quality=90)
    return pathlib.Path(out_path)


def check_montage(data, refs, sheet_path):
    """提交前必须有拼图、并且"已经打开给用户看过"，且拼图比所有参考图/题词都新。"""
    root_ref = pathlib.Path(data.get("project_root") or ".")
    m = sheet_path.with_name(sheet_path.stem + "_预览.jpg")
    marker = sheet_path.with_name(sheet_path.stem + "_预览.opened")
    if not m.exists():
        die("没有预览拼图 —— 必须先跑 --看 生成拼图并打开给用户看（三样东西缺一不可）")
    if not marker.exists():
        die("预览拼图没有打开给用户看（缺 .opened 标记）—— 不许提交")
    if marker.stat().st_mtime < m.stat().st_mtime:
        die("拼图重新生成后没有重新打开 —— 不许提交")
    newest = max([(root_ref / r["file"]).stat().st_mtime for r in refs] +
                 [(sheet_path.parent / data["prompt_file"]).resolve().stat().st_mtime])
    if m.stat().st_mtime < newest:
        die("预览拼图比参考图/题词旧 —— 文件改过了，必须重新 --看 生成拼图")


def check(data, root, require_confirm=True):
    import hashlib
    refs = data.get("refs") or []
    root_ref = pathlib.Path(data.get("project_root") or root)
    if not refs and not (data.get("no_refs_reason") or "").strip():
        die("参考图清单为空（A）；纯文生图必须写 no_refs_reason")
    for i, r in enumerate(refs, 1):
        if not r.get("res"):
            die(f"第 {i} 张参考缺少 res 资源号（A）")
        if not (r.get("why") or "").strip():
            die(f"第 {i} 张参考没写「为什么用这张」（A）")
        fp = root_ref / (r.get("file") or "")
        if not fp.exists():
            die(f"第 {i} 张参考的本地文件不存在：{fp}（A）")
        if not r.get("sha256"):
            die(f"第 {i} 张参考缺少 sha256 —— 任务表必须用 建任务表.py 生成，不许手打（A）")
        actual = hashlib.sha256(fp.read_bytes()).hexdigest()
        if actual != r["sha256"]:
            die(f"第 {i} 张参考的本地文件已改动（sha 不符）——上传的是旧快照，必须重新上传（A）")

    pf = data.get("prompt_file") or ""
    p = (root / pf).resolve() if pf else None
    if not p or not p.exists():
        die(f"题词文件不存在：{pf}（B）")
    prompt = p.read_text(encoding="utf-8").strip()
    if len(prompt) < 50:
        die(f"题词太短（{len(prompt)} 字），疑似占位（B）")

    if not data.get("credits_estimate"):
        die("没填积分预估（C）")
    if require_confirm and data.get("user_confirmed") is not True and data.get("skip_confirm") is not True:
        die("user_confirmed 不是 true，也没有 skip_confirm —— 用户还没确认，不许提交（D）")
    return refs, prompt


def render(data, refs, prompt, credits):
    mode = data.get("mode", "video")
    head = f"任务：{data.get('title','')}  ｜ {mode} ｜ {data.get('model')} ｜ {data.get('ratio')} ｜ {data.get('resolution')}"
    if mode == "video":
        head += f" ｜ {data.get('duration')}s"
    print("=" * 66)
    print(head)
    print(f"积分预估：{data.get('credits_estimate')}（服务端报价 {credits}）")
    print("-" * 66)
    print("参考图：")
    for i, r in enumerate(refs, 1):
        print(f"  {i}. {pathlib.Path(r.get('file','')).name:28s} {r.get('why')}")
    print("-" * 66)
    print("题词：")
    print(textwrap.indent(prompt, "  "))
    print("=" * 66)


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    out = r.stdout or r.stderr
    try:
        return json.loads(out)
    except Exception:
        print(out[:800])
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--表", dest="sheet")
    ap.add_argument("--新表", dest="new")
    ap.add_argument("--看", dest="look", action="store_true", help="只校验并打印任务表，不建节点、不花积分")
    ap.add_argument("--project", default="")
    a = ap.parse_args()

    if a.new:
        t = dict(TEMPLATE)
        t["refs"] = [{"res": "", "file": "", "why": ""}]
        pathlib.Path(a.new).write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已建模板：" + a.new)
        print("填好 refs / prompt_file / credits_estimate，给我看，等我确认后把 user_confirmed 改成 true。")
        return

    if not a.sheet:
        ap.print_help()
        sys.exit(0)

    sheet = pathlib.Path(a.sheet)
    root = sheet.parent
    data = load(sheet)

    if a.look:
        refs, prompt = check(data, root, require_confirm=False)
        render(data, refs, prompt, data.get("credits_estimate", 0))
        m = make_montage(data, refs, sheet.with_name(sheet.stem + "_预览.jpg"))
        print("参考图拼图（按上传顺序）：" + str(m))
        import subprocess as sp, time as _t
        r = sp.run(["open", str(m)])
        if r.returncode == 0:
            sheet.with_name(sheet.stem + "_预览.opened").write_text(str(_t.time()))
            print("已打开拼图给用户看（写入 .opened 标记）")
        else:
            print("⚠ 拼图没能打开 —— 没有 .opened 标记，提交会被拦")
        print("三样必须给用户看到：① 积分  ② 完整题词（以上）  ③ 参考图拼图（已打开）")
        print("↑ 未提交、未花积分。用户点头后把 user_confirmed 改 true；"
              "即便用户说跳过确认，也必须先把这三样摆给他看。")
        return

    refs, prompt = check(data, root)
    check_montage(data, refs, sheet)

    mode = data.get("mode", "video")
    cmds = [CANVAS, "node", "create", mode]
    if a.project:
        cmds += ["--project-id", a.project]
    cmds += ["--mode", "m2v" if mode == "video" else "i2i",
             "--model", data["model"],
             "--ratio", data["ratio"],
             "--resolution", data["resolution"]]
    if mode == "video":
        cmds += ["--duration", str(data["duration"])]
    for r in refs:
        cmds += ["--ref", "res:" + r["res"]]
    cmds += ["--title", data.get("title", "shot"), "--prompt", prompt, "--format", "json"]

    node = run(cmds).get("data", {}).get("node", {}).get("nodeId")
    if not node:
        die("建节点失败（服务端拒绝）")

    q = run([CANVAS, "node", "quote", "--node-id", node] + (["--project-id", a.project] if a.project else []) + ["--format", "json"])
    credits = q.get("data", {}).get("totalMaxCredits", 0)
    render(data, refs, prompt, credits)

    if credits > data["credits_estimate"] * 1.2:
        die(f"服务端报价 {credits} 超过预估 {data['credits_estimate']} 的 1.2 倍（E）")

    conf = [CANVAS, "node", "confirm", "--node-id", node, "--credit-ceiling", str(credits)]
    if a.project:
        conf += ["--project-id", a.project]
    token = run(conf + ["--format", "json"]).get("data", {}).get("creditConfirmationToken")
    if not token:
        die("拿不到积分确认令牌")

    ran = run([CANVAS, "node", "run", "--node-id", node, "--credit-token", token] +
              (["--project-id", a.project] if a.project else []) + ["--format", "json"])
    print("✓ 已提交：", json.dumps(ran.get("data", {}), ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
