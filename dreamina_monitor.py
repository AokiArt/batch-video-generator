#!/usr/bin/env python3
"""
Dreamina batch monitor & download helper.
Poll all pending submit_ids, download videos when ready, output status.

Usage:
  python3 dreamina_monitor.py --state state.json --output ./output

state.json format:
{
  "tasks": [
    {
      "image": "重庆谈判2.jpg",
      "submit_id": "xxx-xxx-xxx",
      "prompt": "...",
      "status": "submitted",
      "tool": "dreamina"
    }
  ]
}
"""
import subprocess, json, time, sys, os, argparse
from pathlib import Path
from urllib.request import urlretrieve

DREAMINA = "/Users/aoki/.local/bin/dreamina"
POLL_INTERVAL = 60  # seconds between polls
MAX_WAIT = 1800  # 30 min timeout per task


def dreamina_query(submit_id):
    """Query dreamina for task result. Returns parsed JSON or None."""
    try:
        r = subprocess.run(
            [DREAMINA, "query_result", f"--submit_id={submit_id}"],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(r.stdout)
    except Exception as e:
        return {"error": str(e)}


def download_video(url, output_path):
    """Download video from URL to path."""
    try:
        urlretrieve(url, str(output_path))
        return True
    except Exception as e:
        print(f"  Download error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, help="Task state JSON file")
    parser.add_argument("--output", required=True, help="Output directory for videos")
    parser.add_argument("--oneshot", action="store_true", help="Poll once and exit")
    args = parser.parse_args()

    state_path = Path(args.state)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        if not state_path.exists():
            print("State file not found, waiting...")
            time.sleep(POLL_INTERVAL)
            continue

        state = json.load(open(state_path, encoding="utf-8"))
        tasks = state.get("tasks", [])
        pending = [t for t in tasks if t.get("status") not in ("downloaded", "failed", "cancelled")]

        if not pending:
            print(f"[{time.strftime('%H:%M:%S')}] All tasks resolved!")
            break

        print(f"\n[{time.strftime('%H:%M:%S')}] Polling {len(pending)} pending tasks...")

        for task in pending:
            sid = task.get("submit_id")
            if not sid:
                continue

            result = dreamina_query(sid)

            if not result or "error" in result:
                print(f"  [{task['image']}] Query error: {result.get('error', 'unknown')}")
                continue

            gen_status = result.get("gen_status", "unknown")
            print(f"  [{task['image']}] {gen_status}")

            if gen_status == "success":
                # Extract video URL
                video_url = result.get("video_url") or result.get("result_url") or ""
                if video_url:
                    safe_name = Path(task["image"]).stem + ".mp4"
                    out_path = output_dir / safe_name
                    print(f"    Downloading → {out_path}")
                    if download_video(video_url, out_path):
                        task["status"] = "downloaded"
                        task["video_path"] = str(out_path)
                        print(f"    ✅ Downloaded")
                    else:
                        task["status"] = "download_failed"
                else:
                    task["status"] = "no_video_url"

            elif gen_status == "fail":
                task["status"] = "failed"
                task["fail_reason"] = result.get("fail_reason", "unknown")
                print(f"    ❌ {task['fail_reason']}")

            elif gen_status == "querying":
                pass  # still processing

            # Check timeout
            elapsed = time.time() - task.get("submit_time", time.time())
            if elapsed > MAX_WAIT:
                task["status"] = "timeout"
                print(f"    ⏰ Timeout after {MAX_WAIT}s")

        json.dump(state, open(state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

        if args.oneshot:
            break

        remaining = [t for t in state["tasks"] if t.get("status") not in ("downloaded", "failed", "cancelled", "timeout")]
        if remaining:
            print(f"  Next poll in {POLL_INTERVAL}s ({len(remaining)} remaining)...")
            time.sleep(POLL_INTERVAL)
        else:
            break

    # Final summary
    tasks = state.get("tasks", [])
    ok = sum(1 for t in tasks if t.get("status") == "downloaded")
    fail = sum(1 for t in tasks if t.get("status") in ("failed", "download_failed", "no_video_url", "timeout"))
    print(f"\n{'='*50}")
    print(f"Done: {ok} downloaded, {fail} failed, {len(tasks)} total")
    for t in tasks:
        s = "✅" if t.get("status") == "downloaded" else "❌"
        print(f"  {s} {t['image']}: {t.get('status','?')}")


if __name__ == "__main__":
    main()
