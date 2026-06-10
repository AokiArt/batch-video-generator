#!/usr/bin/env python3
"""FAST Telescope image2video via Dreamina web automation — FINAL VERSION.

Toolbar layout (from left to right):
  AI影片 | model | 全方位參考 | 16:9 | duration | bookmark | credits | SUBMIT
"""
import asyncio, json, os, sys, time, subprocess
from playwright.async_api import async_playwright

OUTPUT_DIR = "/Users/aoki/Desktop/claude/output"
REF_DIR = "/Users/aoki/Desktop/claude/ai动画/ref_frames"        # per-shot reference frames (01.jpg, 02.jpg, ...)
DEFAULT_REF = os.path.join(OUTPUT_DIR, "fast_ref.png")           # fallback if per-shot missing
STATE_FILE = "/Users/aoki/Desktop/claude/ai动画/fast_telescope_state.json"

SHOTS = [
    {"id": 1, "name": "01 雾中天眼", "duration": 8,
     "prompt": "CG渲染三维动画，写实风格，清晨薄雾笼罩山谷，500米口径球面射电望远镜FAST中国天眼从雾中逐渐显现。柔和的晨光穿透薄雾，巨型反射面呈现金属质感，周围喀斯特山峰轮廓若隐若现。镜头从远景缓慢向前推进至中景，微俯角航拍视角。画面宁静神秘，光线柔和漫射，HDR质感。无字幕无水印。"},
    {"id": 2, "name": "02 日间全景", "duration": 10,
     "prompt": "CG渲染三维动画，航拍鸟瞰视角，FAST天眼全景，延时摄影风格。蓝天白云快速飘动，云影在巨型反射面上掠过。阳光明亮，反射面金属面板呈现均匀银白色光泽，中心馈源舱清晰可见。周围喀斯特地貌绿色山林环绕。镜头从高空俯冲下降至鸟瞰全景，广角到标准焦段，画面宏伟大气。无字幕无水印。"},
    {"id": 3, "name": "03 午后回望", "duration": 8,
     "prompt": "CG渲染三维动画，中景到远景，FAST天眼从山林掩映中显现。午后阳光温暖明亮，树木绿意葱茏，前景树木枝叶框住部分画面，透过树丛可见巨型反射面。镜头从树林间隙缓慢拉远加微摇，逐步展现完整天眼。自然光影对比，前景暗背景亮，有层次感。无字幕无水印。"},
    {"id": 4, "name": "04 黄昏降临", "duration": 10,
     "prompt": "CG渲染三维动画，延时摄影黄昏金色逆光，FAST天眼中景到仰视特写。太阳低角度照射，反射面被染成金橙色，金属边缘发光。天空从橙红渐变到淡紫，薄云被染成金色。镜头从仰角缓慢推进，焦点从前景反射面板移至远处天际线。逆光lens flare效果柔和，画面温暖壮丽。无字幕无水印。"},
    {"id": 5, "name": "05 宇宙之眼A", "duration": 8,
     "prompt": "CG渲染三维动画，FAST天眼夜景旋转环绕，延时摄影星轨银河。银河系横跨天际，星星形成同心圆星轨长时间曝光效果。天眼反射面在星光下呈现神秘蓝灰色光泽，馈源舱悬浮在反射面上方。镜头环绕天眼缓慢旋转，天眼如同连接大地与宇宙的通道。画面极致震撼，宇宙诗意感。无字幕无水印。"},
    {"id": 6, "name": "06 宇宙之眼B", "duration": 8,
     "prompt": "CG渲染三维动画，FAST天眼夜景旋转环绕，延时摄影星轨银河。银河系横跨天际，星星形成同心圆星轨长时间曝光效果。天眼反射面在星光下呈现神秘蓝灰色光泽，馈源舱悬浮在反射面上方。镜头环绕天眼缓慢旋转，天眼如同连接大地与宇宙的通道。画面极致震撼，宇宙尺度感。无字幕无水印。"},
]

def get_ws_url():
    import urllib.request
    try:
        data = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5).read())
        return data.get("webSocketDebuggerUrl", "")
    except:
        return ""

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

async def switch_to_ai_video(page):
    """Switch from AI 代理 to AI 影片 mode using the mode combobox (first combobox)."""
    body = await page.evaluate('() => document.body.innerText')
    if 'AI 影片' in body and 'AI 代理' not in body:
        print("  Already in AI 影片 mode")
        return True

    # Try up to 3 times
    for attempt in range(3):
        if attempt > 0:
            print(f"  Retry switch to AI 影片 (attempt {attempt+1})...")
            await asyncio.sleep(3)

        # Click the mode selector combobox
        comboboxes = page.locator('[role="combobox"]')
        count = await comboboxes.count()
        if count < 1:
            print(f"  No comboboxes found (attempt {attempt+1})")
            continue

        mode_select = comboboxes.nth(0)
        await mode_select.click()
        await asyncio.sleep(2)

        # Find and click AI 影片 option
        ai_video_opt = page.locator('[class*="lv-select-option"]:has-text("AI 影片")').first
        if await ai_video_opt.count() > 0 and await ai_video_opt.is_visible():
            await ai_video_opt.click()
            await asyncio.sleep(3)
            # Verify
            body = await page.evaluate('() => document.body.innerText')
            if 'AI 影片' in body:
                print("  Switched to AI 影片")
                return True

        # Close dropdown if still open
        await page.keyboard.press('Escape')
        await asyncio.sleep(0.5)

    return False

async def select_model(page, model_name="Dreamina Seedance 2.0"):
    """Select model from the model combobox (second combobox)."""
    comboboxes = page.locator('[role="combobox"]')
    if await comboboxes.count() < 2:
        return False

    model_select = comboboxes.nth(1)  # Second = model
    current = (await model_select.inner_text()).strip()
    if current == model_name:
        print(f"  Model already: {model_name}")
        return True

    # Click to open
    await model_select.click()
    await asyncio.sleep(2)

    # Find and click the desired model option
    options = page.locator('[class*="lv-select-option"]')
    for i in range(await options.count()):
        opt = options.nth(i)
        try:
            if await opt.is_visible():
                text = await opt.inner_text()
                if text.strip().startswith(model_name) and 'Fast' not in text.strip()[:len(model_name)+5]:
                    await opt.click()
                    await asyncio.sleep(2)
                    print(f"  Selected model: {model_name}")
                    return True
        except:
            pass

    # Fallback: close by pressing Escape
    await page.keyboard.press('Escape')
    await asyncio.sleep(0.5)
    return False

async def select_duration(page, duration_sec):
    """Select duration from the duration combobox (fourth combobox)."""
    target = f"{duration_sec}s"
    await asyncio.sleep(1)

    # First, close any open dropdowns
    await page.keyboard.press('Escape')
    await asyncio.sleep(0.5)

    comboboxes = page.locator('[role="combobox"]')
    cb_count = await comboboxes.count()
    print(f"  Found {cb_count} comboboxes")

    if cb_count < 4:
        print(f"  ERROR: Only {cb_count} comboboxes, need at least 4")
        return False

    # Print all combobox texts for debugging
    for i in range(cb_count):
        try:
            txt = (await comboboxes.nth(i).inner_text()).strip()
            print(f"    combobox[{i}]: '{txt}'")
        except:
            pass

    duration_select = comboboxes.nth(3)  # Fourth = duration
    current = (await duration_select.inner_text()).strip()
    print(f"  Current duration: '{current}', target: '{target}'")

    if current == target:
        print(f"  Duration already correct: {target}")
        return True

    # Open dropdown
    await duration_select.click()
    await asyncio.sleep(2)

    # Try multiple selector patterns for dropdown options
    option_selectors = [
        '[class*="lv-select-option"]',
        '[class*="select-option"]',
        '[class*="dropdown-option"]',
        '[class*="lv-option"]',
        '[role="option"]',
        'li[class*="option"]',
        'div[class*="option"]',
    ]

    for sel in option_selectors:
        options = page.locator(sel)
        count = await options.count()
        if count == 0:
            continue
        print(f"  Trying selector '{sel}' -> {count} options")
        for i in range(count):
            opt = options.nth(i)
            try:
                if not await opt.is_visible():
                    continue
                text = (await opt.inner_text()).strip()
                print(f"    option[{i}]: '{text}'")
                if text == target or (text.startswith(target) and len(text) <= len(target) + 2):
                    await opt.click()
                    await asyncio.sleep(2)
                    # Verify
                    new_current = (await duration_select.inner_text()).strip()
                    if new_current == target:
                        print(f"  ✅ Duration set: {target}")
                        return True
                    else:
                        print(f"  ⚠️ Clicked but duration still '{new_current}', retrying...")
            except:
                pass

    # Fallback: try clicking by text directly
    print(f"  Fallback: searching for text '{target}'...")
    try:
        text_el = page.locator(f'text="{target}"').first
        if await text_el.count() > 0 and await text_el.is_visible():
            await text_el.click()
            await asyncio.sleep(2)
            new_current = (await duration_select.inner_text()).strip()
            if new_current == target:
                print(f"  ✅ Duration set via text: {target}")
                return True
    except:
        pass

    # Close dropdown
    await page.keyboard.press('Escape')
    await asyncio.sleep(0.5)
    print(f"  ❌ Failed to set duration to {target}")
    return False

async def upload_image(page, path):
    """Upload reference image and verify it appeared as preview."""
    file_input = page.locator('input[type="file"]').first
    if await file_input.count() > 0:
        await file_input.set_input_files(os.path.abspath(path))
        await asyncio.sleep(4)
        # Verify: look for blob preview images or uploaded image indicators
        blob_imgs = await page.locator('img[src*="blob"]').count()
        preview_imgs = await page.locator('img[src*="alisg"], img[src*="tos"], img[src*="pstatp"]').count()
        total = blob_imgs + preview_imgs
        if total > 0:
            print(f"  Image upload verified ({total} preview(s))")
            return True
        else:
            print(f"  WARNING: No image preview found after upload!")
            # Take screenshot for debugging
            await page.screenshot(path=os.path.join(OUTPUT_DIR, "fast_upload_debug.png"))
            # Still return True — the upload might have worked without visible preview
            return True
    return False

async def enter_prompt(page, prompt):
    """Enter generation prompt and verify it was set correctly."""
    editable = page.locator('[contenteditable="true"]').first
    if await editable.count() > 0 and await editable.is_visible():
        # Clear first via evaluate, then fill
        await editable.click()
        await asyncio.sleep(0.5)
        await editable.evaluate('el => el.innerText = ""')
        await asyncio.sleep(0.3)
        await editable.fill(prompt)
        await asyncio.sleep(1)

        # Verify the prompt was actually entered
        actual = await editable.inner_text()
        if actual.strip()[:30] == prompt.strip()[:30]:
            print(f"  Prompt entered: {prompt[:50]}...")
            return True
        else:
            # Try again with keyboard input as fallback
            print(f"  Prompt fill failed (got: '{actual[:50]}'), retrying with keyboard...")
            await editable.click()
            await asyncio.sleep(0.3)
            # Select all and delete
            if sys.platform == 'darwin':
                await page.keyboard.press('Meta+a')
            else:
                await page.keyboard.press('Control+a')
            await asyncio.sleep(0.2)
            await page.keyboard.press('Backspace')
            await asyncio.sleep(0.3)
            await page.keyboard.type(prompt, delay=10)
            await asyncio.sleep(1)

            actual = await editable.inner_text()
            if actual.strip()[:30] == prompt.strip()[:30]:
                print(f"  Prompt entered (keyboard): {prompt[:50]}...")
                return True
            else:
                print(f"  ERROR: Prompt still wrong! Got: '{actual[:50]}'")
                return False
    return False

async def click_generate(page):
    """Click the submit button. Waits/retries if disabled."""
    submit_btn = page.locator('button.lv-btn-primary.lv-btn-shape-circle.lv-btn-icon-only').last
    if await submit_btn.count() == 0:
        return False

    # Wait up to 30s for button to become enabled
    for attempt in range(15):
        try:
            if not await submit_btn.is_visible(timeout=2000):
                print(f"  Submit button not visible (attempt {attempt+1})")
                await asyncio.sleep(2)
                continue
            disabled = await submit_btn.is_disabled()
            if not disabled:
                await submit_btn.click(timeout=5000)
                print("  Generate clicked!")
                return True
            else:
                if attempt == 0:
                    print("  Submit button disabled, waiting for form to be ready...")
                await asyncio.sleep(2)
        except Exception as e:
            print(f"  Submit button error (attempt {attempt+1}): {e}")
            await asyncio.sleep(2)

    print(f"  Submit button still disabled after waiting")
    return False

def _is_valid_result_video(src):
    """Check if a video URL is an actual generated result (not a UI loading animation)."""
    if not src:
        return False
    # Exclude static assets, loading animations, login pages
    bad = ['static', 'loading', 'animation', 'login', 'sf16-web-login', 'capcutstatic']
    for b in bad:
        if b in src:
            return False
    # Must be from a real video CDN
    return ('alisg' in src or 'tos' in src or ('capcut' in src and 'capcutstatic' not in src))


async def get_existing_video_srcs(page):
    """Get all existing video src URLs on the page before generation."""
    existing = set()
    videos = page.locator('video')
    for i in range(await videos.count()):
        try:
            src = await videos.nth(i).get_attribute('src') or ''
            if _is_valid_result_video(src):
                existing.add(src)
        except:
            pass
    return existing


async def wait_for_generation(page, existing_srcs=None, timeout=600):
    """Wait for generation to complete. Returns NEW video URL or None.

    existing_srcs: set of video URLs that were already on the page before submit.
                   These are ignored so we don't re-download a previous shot's video.
    """
    if existing_srcs is None:
        existing_srcs = set()

    print(f"  Waiting for generation (max {timeout}s, ignoring {len(existing_srcs)} existing videos)...")
    start = time.time()
    saw_generating = False

    while time.time() - start < timeout:
        body = await page.evaluate('() => document.body.innerText')

        # Track if we've seen generation in progress
        if '生成中' in body or '正在生成' in body or '排队' in body:
            saw_generating = True
            elapsed = int(time.time() - start)
            if elapsed % 30 < 5:
                print(f"    [{elapsed}s] generating...")
            await asyncio.sleep(5)
            continue

        # Check for completion indicators first
        complete = False
        for btn_text in ['下载', '下載', '查看結果', '查看结果']:
            btn = page.locator(f'text="{btn_text}"').first
            try:
                if await btn.count() > 0 and await btn.is_visible(timeout=1000):
                    complete = True
                    print(f"  Generation complete! Found '{btn_text}' button")
                    break
            except:
                pass

        # Only look for new videos if generation was in progress AND is now complete
        # OR if we've been waiting a while (90s+) without seeing generating text
        if saw_generating or (time.time() - start > 90):
            videos = page.locator('video')
            for i in range(await videos.count()):
                try:
                    src = await videos.nth(i).get_attribute('src') or ''
                    if src and src not in existing_srcs and _is_valid_result_video(src):
                        if complete or (saw_generating and '生成中' not in body and '正在生成' not in body):
                            print(f"  New video found! src={src[:80]}...")
                            return src
                except:
                    pass

        # Check for errors
        if '失败' in body or 'failed' in body.lower():
            print("  Generation may have failed!")
            return None

        elapsed = int(time.time() - start)
        if elapsed % 30 < 5:
            print(f"    [{elapsed}s] still waiting...")

        await asyncio.sleep(5)

    print("  Timeout waiting for generation")
    return None

async def download_video(url, out_path):
    """Download video from URL."""
    if not url:
        return False
    print(f"  Downloading: {url[:60]}...")
    result = subprocess.run(f'curl -L -o "{out_path}" "{url}"', shell=True, capture_output=True, text=True)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"  Downloaded: {size_mb:.1f}MB")
        return True
    return False

async def process_shot(page, shot):
    """Process a single shot end-to-end."""
    shot_id = str(shot["id"])
    out_path = os.path.join(OUTPUT_DIR, f"FAST_{shot['name']}.mp4")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        print(f"[SKIP] Shot {shot_id}: already exists ({os.path.getsize(out_path)/1024/1024:.1f}MB)")
        return "skipped"

    print(f"\n{'='*60}")
    print(f"[Shot {shot_id}] {shot['name']} ({shot['duration']}s)")
    print(f"{'='*60}")

    # 1. Navigate fresh — MUST include ?type=video to get full creation UI with comboboxes
    print("  Loading page...")
    await page.goto('https://dreamina.capcut.com/ai-tool/generate?type=video', wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(5)
    try:
        await page.wait_for_load_state('networkidle', timeout=30000)
    except:
        pass
    await asyncio.sleep(5)
    # Verify we're on the right page
    current_url = page.url
    if '/home' in current_url or '/login' in current_url:
        print(f"  WARNING: Redirected to {current_url}, navigating back...")
        await page.goto('https://dreamina.capcut.com/ai-tool/generate', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

    # 2. Switch to AI 影片 mode
    if not await switch_to_ai_video(page):
        print("  ERROR: Could not switch to AI 影片")
        return False

    # 3. Select model: Dreamina Seedance 2.0 (standard, NOT Fast)
    if not await select_model(page, "Dreamina Seedance 2.0"):
        print("  WARNING: Could not select standard Seedance 2.0, continuing anyway...")

    # 4. Select duration
    if not await select_duration(page, shot["duration"]):
        print("  WARNING: Could not set duration")

    # 5. Upload reference image (per-shot, with fallback)
    ref_path = os.path.join(REF_DIR, f"{shot_id}.jpg")
    if not os.path.exists(ref_path):
        ref_path = os.path.join(REF_DIR, f"{shot_id}.png")
    if not os.path.exists(ref_path):
        print(f"  WARNING: Per-shot ref not found ({shot_id}.jpg), using default ref")
        ref_path = DEFAULT_REF
    print(f"  Uploading reference: {os.path.basename(ref_path)}")
    if not await upload_image(page, ref_path):
        print("  ERROR: Image upload failed")
        await page.screenshot(path=os.path.join(OUTPUT_DIR, f"fast_error_upload_{shot_id}.png"))
        return False

    # 6. Enter prompt
    print("  Entering prompt...")
    if not await enter_prompt(page, shot["prompt"]):
        print("  ERROR: Could not enter prompt")
        await page.screenshot(path=os.path.join(OUTPUT_DIR, f"fast_error_prompt_{shot_id}.png"))
        return False

    # 7. Screenshot before submit AND capture existing video URLs
    await page.screenshot(path=os.path.join(OUTPUT_DIR, f"fast_pre_submit_{shot_id}.png"))
    existing_videos = await get_existing_video_srcs(page)
    print(f"  Existing video URLs on page: {len(existing_videos)}")

    # 8. Click generate
    print("  Submitting generation...")
    if not await click_generate(page):
        print("  ERROR: Could not click generate")
        await page.screenshot(path=os.path.join(OUTPUT_DIR, f"fast_error_submit_{shot_id}.png"))
        return False

    await asyncio.sleep(5)

    # 9. Wait for generation (ignoring pre-existing videos)
    video_url = await wait_for_generation(page, existing_srcs=existing_videos, timeout=900)

    # 10. Download
    if video_url:
        await download_video(video_url, out_path)
        state = load_state()
        state[shot_id] = {
            "name": shot["name"],
            "duration": shot["duration"],
            "downloaded": os.path.exists(out_path),
            "time": time.time(),
            "video_url": video_url
        }
        save_state(state)
        print(f"  [DONE] {out_path}")
        return True
    else:
        print(f"  [FAILED] No video URL found for shot {shot_id}")
        state = load_state()
        state[shot_id] = {"name": shot["name"], "submitted": True, "failed": True, "time": time.time()}
        save_state(state)
        return False

async def main():
    ws_url = get_ws_url()
    if not ws_url:
        print("ERROR: Chrome CDP not available!")
        sys.exit(1)

    print(f"=== FAST Telescope Image2Video ===")
    print(f"CDP: {ws_url[:80]}...")
    print(f"Reference dir: {REF_DIR}  (default: {DEFAULT_REF})")
    print(f"Output: {OUTPUT_DIR}")

    state = load_state()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        for shot in SHOTS:
            success = await process_shot(page, shot)
            if not success:
                print(f"\nShot {shot['id']} failed. Continuing to next...")
                continue

            # Wait between shots — only if actually generated (not skipped)
            if shot["id"] < 6 and success is True:
                wait_time = 600
                print(f"\n[Waiting {wait_time}s before next shot...]")
                for remaining in range(wait_time, 0, -60):
                    print(f"  {remaining//60} min remaining...")
                    await asyncio.sleep(60)

        print("\n=== ALL DONE! ===")
        print(f"Videos saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
