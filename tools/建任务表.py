#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建任务表.py —— 只做一件事：把"当前磁盘上的文件"上传，并把 res / sha256 / mtime 写进任务表。

为什么要有它：资源号是上传那一刻的快照，文件后来改了它不会变。
手打资源号 = 任务表写的是一回事、传上去是另一回事（2026-10-20 真实翻车）。

用法：
  python3 建任务表.py --out 任务表/镜头05.json --project <pid> \
      --title "..." --prompt ../题词.txt --credits 400 --duration 20 \
      --ref 02_资产图/关键帧_定稿V3/4_就.png "第⑤段坡屋顶咖啡厅" \
      --ref 02_资产图/关键帧_定稿V3/5_够.png "第⑥段文创市集"

  --ref 可以重复；每次都会重新上传当前文件，并记录 sha256 与 mtime。
"""
import argparse, hashlib, json, pathlib, subprocess, sys, time

CANVAS = "dreamina-canvas"


def upload(path: pathlib.Path, project: str):
    """上传当前文件，返回 (resourceId, 实际上传的那份本地副本路径)。"""
    src = path
    if src.stat().st_size > 4 * 1024 * 1024:
        tmp = pathlib.Path("/tmp/_gate_") / (src.stem + ".jpg")
        tmp.parent.mkdir(exist_ok=True)
        subprocess.run(["sips", "-Z", "1800", "-s", "format", "jpeg",
                        "-s", "formatOptions", "88", str(src), "--out", str(tmp)],
                       capture_output=True)
        src = tmp
    last = ""
    tmpdir = pathlib.Path("/tmp/_gate_")
    tmpdir.mkdir(exist_ok=True)
    for i in range(4):
        cp = tmpdir / f"{src.stem}_g{i}{src.suffix}"   # 临时文件一律放 /tmp，不许写在源目录旁边
        if i == 0:
            cp.write_bytes(src.read_bytes())
        else:
            # 同一份字节重复上传会报 upload_state_unknown；换一档质量重编码，内容等价、字节不同
            subprocess.run(["sips", "-Z", str(1800 - i * 20), "-s", "format", "jpeg",
                            "-s", "formatOptions", str(88 - i * 3), str(src), "--out", str(cp)],
                           capture_output=True)
        r = subprocess.run([CANVAS, "resource", "upload", "--file", str(cp),
                            "--project-id", project, "--format", "json"],
                           capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            rid = d.get("data", {}).get("resourceId")
            if rid:
                return rid, cp
        except Exception:
            last = (r.stdout or r.stderr)[:200]
        time.sleep(1)
    print(f"✗ 上传失败：{path}  {last}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--credits", type=int, required=True)
    ap.add_argument("--mode", default="video", choices=["video", "image"])
    ap.add_argument("--model", default="seedance_2.5")
    ap.add_argument("--duration", type=int, default=20)
    ap.add_argument("--ratio", default="21:9")
    ap.add_argument("--resolution", default="720p")
    ap.add_argument("--ref", nargs=2, action="append", metavar=("文件", "为什么用"), default=[])
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    root = out.parent
    while root.name and not (root / "02_资产图").exists():
        root = root.parent
    refs = []
    # 上传副本统一存档：<项目>/03_生成视频/上传副本_<时间戳>/ ，绝不放进关键帧目录
    attach = root / "03_生成视频" / ("上传副本_" + time.strftime("%Y%m%d_%H%M%S"))
    attach.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H%M")
    for f, why in a.ref:
        p = (root / f)
        if not p.exists():
            print("✗ 文件不存在：" + str(p)); sys.exit(1)
        rid, uploaded = upload(p, a.project)
        # 把"实际上传的那份字节"另存一份，任务表可自证传的是哪一版
        copy_name = f"{p.stem}_上传于{stamp}{uploaded.suffix}"
        copy_path = attach / copy_name
        copy_path.write_bytes(uploaded.read_bytes())
        refs.append({
            "res": rid,
            "file": f,
            "why": why,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "mtime": int(p.stat().st_mtime),
            "uploaded_at": int(time.time()),
            "uploaded_copy": str(copy_path.relative_to(root)),
        })
        print(f"  ✓ {pathlib.Path(f).name}  {rid}  sha {refs[-1]['sha256'][:12]} → {copy_name}")

    sheet = {
        "title": a.title, "mode": a.mode, "model": a.model,
        "duration": a.duration, "ratio": a.ratio, "resolution": a.resolution,
        "refs": refs,
        "prompt_file": a.prompt,
        "credits_estimate": a.credits,
        "user_confirmed": False,
        "project_root": str(root.resolve()),
    }
    out.write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✓ 任务表已写：" + str(out))
    print("  下一步：python3 发镜头.py --表 " + str(out) + " --看")


if __name__ == "__main__":
    main()
