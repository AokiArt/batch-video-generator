---
name: batch-video-generator
description: Orchestrate batch AI video generation across three modes — Dreamina CLI, Dreamina International Web, and Grok browser. Mode A: batch generation from prompts+images with failover. Mode B: storyboard script parsing and sequential video generation with ffmpeg concatenation. Mode C: Dreamina International (dreamina.capcut.com) web automation via Playwright CDP for image2video with seedance2.0.
metadata:
  tags: video, batch, dreamina, grok, ai-generation, orchestration, dreamina-international
---

## When to use

This skill has **three modes**. Determine which mode matches the user's input:

### Mode A: 批量生成 (Batch Generation)
When the user gives you a **list of prompts + optional reference image paths** and asks to generate videos in batch. This mode handles the full lifecycle: first-round generation → monitoring → download → failure retry with the other tool.

### Mode B: 脚本生成 (Storyboard Script)
When the user provides a **formatted storyboard/shooting script** with numbered scenes using the format `序号｜画面提示词｜视频提示词` (or similar delimiter-separated format with scene number, image description, and camera motion), and asks to generate videos then **concatenate them in order**. This mode: parses the storyboard → merges image + motion prompts → generates videos sequentially → downloads with sequence numbers → concatenates into one combined video via ffmpeg.

**Key triggers for Mode B:** user mentions "分镜头脚本", "分镜", "按顺序连起来", "拼接", "storyboard", or provides a clearly formatted multi-scene script with camera motion descriptions.

### Mode C: Dreamina国际版 (Dreamina International Web)
When the user wants to use the **Dreamina international web interface** (dreamina.capcut.com) instead of the CLI. This is for accounts that work on the web but not via CLI (e.g., artisan accounts). Uses **Playwright CDP** to automate Chrome: connect to the logged-in Dreamina web page, upload reference images, set parameters (model/duration/ratio/resolution), enter prompts, and submit image2video tasks.

**Key triggers for Mode C:** user mentions "dreamina国际版", "网页版", "web端", "capcut.com", "不能用CLI", "artisan账号", or explicitly says the CLI doesn't work for their account.

---

## Mode B: 脚本生成 (Storyboard Script) — CHECK FIRST

If the user's input matches Mode B, **skip Mode A entirely** and follow this workflow.

### Step B.1: Parse the storyboard

Parse the storyboard format. Expected format:

```
序号｜画面提示词｜视频提示词
01｜<image description>｜<camera motion description>
02｜<image description>｜<camera motion description>
...
```

Delimiters may vary: `｜`, `|`, `||`, tabs, or numbered lines. Extract for each scene:
- `index`: the sequence number (01, 02, 03...)
- `image_prompt`: the visual description (what the scene looks like)
- `video_prompt`: the camera motion description (how the camera moves)

### Step B.2: Determine specs from user message

The user typically specifies specs inline (e.g. "seedance2.0模型生成5s的16:9横版720p"). Extract what's given. If any spec is missing, ask only for what's needed:

| 参数 | 从用户消息中提取 | 默认值 |
|------|-----------------|--------|
| 工具 | Dreamina / Grok | Dreamina（国内用户默认） |
| 模型 | seedance2.0 / seedance2.0_vip / etc. | seedance2.0 |
| 画幅 | 16:9 / 9:16 / 1:1 / etc. | 16:9 |
| 分辨率 | 720p / 1080p | 720p |
| 时长 | 4-15s (Dreamina) / 6s or 10s (Grok) | 5s |

**Do NOT re-ask for specs the user already provided.** If the user said "seedance2.0, 5s, 16:9, 720p", use those values directly.

### Step B.3: Check credits and verify tool

```bash
/Users/aoki/.local/bin/dreamina user_credit
```

If credits are insufficient, warn the user. If not logged in, ask the user to log in first.

### Step B.4: Merge prompts for text2video

Since there are no reference images, combine the image description and camera motion description into a single comprehensive prompt:

```
<image_prompt>。<video_prompt>。
```

This gives the model both visual and motion context in one prompt. Remove redundant connectors and keep the flow natural.

### Step B.5: Sequential submission

**Critical: Dreamina enforces a concurrency limit (only 1 task at a time).** Submitting multiple tasks simultaneously will result in `ExceedConcurrencyLimit` errors for all but the first.

Submit tasks **one at a time, sequentially**:

```bash
/Users/aoki/.local/bin/dreamina text2video \
  --model_version <model> \
  --ratio "<ratio>" \
  --duration <duration> \
  --video_resolution "<resolution>" \
  --prompt "<merged_prompt>"
```

Parse the JSON output:
- `submit_id`: save for polling
- `gen_status`: initial status
- If `fail` with `ExceedConcurrencyLimit`, wait for the previous task to finish, then retry.

### Step B.6: Monitor each task until completion

Poll every 30-60s:

```bash
/Users/aoki/.local/bin/dreamina query_result --submit_id=<id>
```

Track `gen_status` transitions:
- `querying` + `queue_status: Queueing` → in queue (note `queue_idx`)
- `querying` + `queue_status: Generating` → actively generating
- `success` → generation complete, extract `video_url`
- `fail` → generation failed, note `fail_reason`

**Timing reference:** Queue position typically starts at ~400-440 and advances at ~65/min. Generation after reaching front takes ~2-3 minutes. Total per task: ~7-8 minutes.

### Step B.7: Download each video as it completes

As soon as a task reaches `success`, download immediately with the sequence number as filename:

```bash
curl -o <output_dir>/<index>.mp4 "<video_url>" -L
```

Where `<index>` is the zero-padded scene number (01, 02, 03...).

### Step B.8: Submit next task

As soon as the current task finishes downloading, immediately submit the next one. This minimizes total wall-clock time.

### Step B.9: Concatenate all videos

After all scenes are downloaded, use ffmpeg concat demuxer to join them in sequence order:

```bash
# Create concat file list
echo "file '01.mp4'
file '02.mp4'
file '03.mp4'" > concat_list.txt

# Concatenate with stream copy (fast, no re-encode)
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy output_combined.mp4 -y
```

Verify the output:
```bash
ls -lh output_combined.mp4
ffprobe -v quiet -show_entries format=duration,size -of csv=p=0 output_combined.mp4
```

Clean up `concat_list.txt` after successful concatenation.

### Step B.10: Output final summary

Present a summary table:

```
| # | 场景 | 状态 | 文件 |
|---|------|------|------|
| 01 | 山脉俯冲推进 | ✅ 成功 | 01.mp4 (4.2MB) |
| 02 | 丁达尔光束平移 | ✅ 成功 | 02.mp4 (4.2MB) |
| 03 | 林冠雾气侧移 | ✅ 成功 | 03.mp4 (4.3MB) |

合并视频: output_combined.mp4 (13MB, 15.2s, 1280×720)
总消耗积分: 120
```

---

## Mode C: Dreamina国际版 (Dreamina International Web)

Use Playwright CDP to automate the **Dreamina international web interface** (`dreamina.capcut.com`). This mode bypasses the CLI entirely and controls the browser directly — useful for accounts where the CLI doesn't work (e.g., artisan-type accounts) but the web UI does.

### Prerequisites

- Chrome running with `--remote-debugging-port=9222` and a non-default `--user-data-dir`
- User must be **logged in** on the CDP-enabled Chrome instance
- Use `ditto` to copy the user's real Chrome profile to preserve login session:
  ```bash
  osascript -e 'quit app "Google Chrome"' 2>/dev/null; sleep 3
  ditto "$HOME/Library/Application Support/Google/Chrome" /tmp/chrome_full_profile
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --user-data-dir=/tmp/chrome_full_profile \
    --no-first-run --no-default-browser-check &
  ```
- Playwright Python: `pip install playwright`

### WebSocket auto-detection

```python
import urllib.request, json
data = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5).read())
ws_url = data.get("webSocketDebuggerUrl")  # ws://127.0.0.1:9222/devtools/browser/...
```

### Page navigation and mode switching

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(ws_url)
    context = browser.contexts[0]
    page = await context.new_page()
    await page.goto('https://dreamina.capcut.com/ai-tool/generate', wait_until='domcontentloaded')
    await asyncio.sleep(8)
```

**Switch from AI 代理 to AI 影片 mode:**
```python
body = await page.evaluate('() => document.body.innerText')
if 'AI 影片' not in body:
    # Click AI 代理 to open mode selector (first combobox)
    comboboxes = page.locator('[role="combobox"]')
    await comboboxes.nth(0).click()
    await asyncio.sleep(2)
    # Click AI 影片 option
    await page.locator('[class*="lv-select-option"]:has-text("AI 影片")').first.click()
    await asyncio.sleep(3)
```

### Toolbar layout (left to right, y≈708)

| Element | Type | Combobox Index | Description |
|---------|------|---------------|-------------|
| AI 影片 | `lv-select` | `nth(0)` | Mode selector |
| Model (Dreamina Seedance 2.0) | `lv-select` | `nth(1)` | **Model selector** |
| 全方位參考 | `lv-select` | `nth(2)` | Reference type |
| 16:9 | `button` | — | Aspect ratio button |
| 8s | `lv-select` | `nth(3)` | **Duration selector** |
| Bookmark | `button` | — | Save/bookmark |
| Credits | `div` | — | Credit cost display |
| Submit | `button` | — | White circle, up-arrow icon, `lv-btn-primary.lv-btn-shape-circle.lv-btn-icon-only` |

### Selecting model (combobox index 1)

```python
comboboxes = page.locator('[role="combobox"]')
model_select = comboboxes.nth(1)  # Model = second combobox
await model_select.click()
await asyncio.sleep(2)

# Find and click "Dreamina Seedance 2.0" (NOT "Fast")
options = page.locator('[class*="lv-select-option"]')
for i in range(await options.count()):
    opt = options.nth(i)
    if await opt.is_visible():
        text = (await opt.inner_text()).strip()
        if text.startswith('Dreamina Seedance 2.0') and 'Fast' not in text[:30]:
            await opt.click()
            break
```

Available models in dropdown:
- Dreamina Seedance 2.0 Fast — 速度快、成本低
- **Dreamina Seedance 2.0 — 多模态参考 (standard, recommended)**
- Dreamina Seedance 1.5 Pro — 声音同步
- Dreamina Seedance 1.0 / 1.0 Fast / 1.0 Mini
- Sora 2

### Selecting duration (combobox index 3)

```python
dur_select = comboboxes.nth(3)  # Duration = fourth combobox
await dur_select.click()
await asyncio.sleep(2)
# Find and click target duration (e.g. "10s")
dur_opt = page.locator(f'[class*="lv-select-option"]:has-text("{duration}s")').first
if await dur_opt.is_visible():
    await dur_opt.click()
```

Available durations: 4s, 8s, 10s, 12s (varies by model).

### Selecting aspect ratio and resolution

Click the **16:9 button** (not a combobox) to open a panel with both ratio and resolution:
```python
ratio_btn = page.locator('button:has-text("16:9")').first
await ratio_btn.click()
await asyncio.sleep(2)
# Select 16:9 and 720P from the panel that appears
await page.locator('text="720P"').first.click()
```

Aspect ratios: 21:9, 16:9, 4:3, 1:1, 3:4, 9:16
Resolutions: 720P, 1080P

### Uploading reference image

The file input is hidden. Use `set_input_files`:
```python
file_input = page.locator('input[type="file"]').first
await file_input.set_input_files(os.path.abspath(image_path))
await asyncio.sleep(4)
# Verify: blob image preview should appear
blob_count = await page.locator('img[src*="blob"]').count()
```

### Entering prompt

The prompt area is a `contenteditable` div (not a textarea):
```python
editable = page.locator('[contenteditable="true"]').first
await editable.click()
await asyncio.sleep(0.5)
await editable.evaluate('el => el.innerText = ""')
await asyncio.sleep(0.3)
await editable.fill(prompt_text)
```

### Submitting

The submit button is the **white circle with up-arrow** at the bottom-right of the dialog:
```python
submit = page.locator('button.lv-btn-primary.lv-btn-shape-circle.lv-btn-icon-only').last
if not await submit.is_disabled():
    await submit.click()
    print("Submitted!")
```

Submit is **disabled** until image + prompt are both provided.

### Waiting for generation

```python
# Poll for video elements
while time.time() - start < timeout:
    videos = page.locator('video')
    for i in range(await videos.count()):
        src = await videos.nth(i).get_attribute('src')
        if src and ('capcut' in src or 'alisg' in src):
            return src  # Video URL ready for download
    
    # Also check for download button
    dl_btn = page.locator('text="下载"').first
    if await dl_btn.count() > 0 and await dl_btn.is_visible():
        return await page.locator('video').first.get_attribute('src')
    
    await asyncio.sleep(5)
```

### Downloading

```bash
curl -L -o "<output_path>" "<video_url>"
```

### Reference automation script

See `/Users/aoki/Desktop/claude/ai动画/fast_telescope.py` for the complete end-to-end automation script implementing all the above patterns.

### Credit cost (web UI, seedance2.0 family)

| Model | 8s cost |
|-------|---------|
| Dreamina Seedance 2.0 Fast | ~152 |
| Dreamina Seedance 2.0 | ~192 |

---

## Mode A: 批量生成 (Batch Generation)

This is the original batch workflow for independent prompts (not a connected storyboard).

### Input format

```
User provides: [(image_path?, prompt), ...]

Phase 1 ── Ask: Dreamina or Grok first?
         └─ Execute ALL tasks with chosen tool
         └─ Monitor every task (submit → query → download)
         └─ Output status table

Phase 2 ── Identify failures from Phase 1
         └─ Ask: invert prompts? (倒置提示词)
         └─ Execute failures with the OTHER tool
         └─ Same monitor → download → table
```

### Phase 1: First round generation

#### Step 1.1: Parse input

User input format can vary:
- `图片名.jpg 提示词文本...` (image + prompt, inline)
- `[image_path, prompt]` (structured)
- Just a prompt without image (text-to-video)

Extract each task as `{image_path: str | None, prompt: str}`. If no output directory specified, default to `~/Desktop/claude/output`.

#### Step 1.2: Choose tool FIRST

Ask which tool before asking specs — because each tool supports different parameters.

```
AskUserQuestion:
  header: "生成工具"
  options:
    - "Dreamina CLI" — 本地命令行，积分消费，审核较严
      • multimodal2video: 4-15s, 720p, 6种画幅(1:1/3:4/16:9/4:3/9:16/21:9)
      • text2video: 4-15s, 720p, 同上画幅
      • image2video: 4-15s, 720p(seedance)/1080p(3.0pro), 画幅跟随输入图
    - "Grok 浏览器" — 本地 Chrome 操控 Grok 官网，免审核
      • 6s/10s, 480p/720p, 5种画幅(2:3/3:2/1:1/9:16/16:9)
```

Default recommendation: if prompts contain sensitive/historical/military content, recommend Grok. For clean creative content, Dreamina is faster.

#### Step 1.3: Ask specs (per-tool)

**Ask only for specs NOT specified by the user.** Questions vary by tool:

##### If Dreamina CLI:

| 参数 | 选项 | 说明 |
|------|------|------|
| 模型 | seedance2.0_vip / seedance2.0 / seedance2.0fast_vip / seedance2.0fast | seedance2.0_vip 最高质量 |
| 画幅 | 1:1 / 3:4 / 16:9 / 4:3 / 9:16 / 21:9 | multimodal2video, text2video 支持 |
| 分辨率 | 720p | seedance2.0 系列仅 720p |
| 时长 | 4-15s | 整数秒，默认5s |
| 子命令 | multimodal2video / text2video / image2video | 有参考图用 multimodal2video 或 image2video，无参考图用 text2video |

##### If Grok:

| 参数 | 选项 | 说明 |
|------|------|------|
| 分辨率 | 480p / 720p | |
| 时长 | 6s / 10s | 仅这两个选项 |
| 画幅 | 2:3 / 3:2 / 1:1 / 9:16 / 16:9 | 16:9 为 Widescreen |

#### Step 1.4: Execute with chosen tool

**Use the specs confirmed in Step 1.3.** Do not hardcode values.

##### If Dreamina CLI:

Choose the right subcommand:
- **有参考图**: `multimodal2video` (全能参考，旗舰模式)
- **无参考图**: `text2video` (文生视频)
- **单图简单动画**: `image2video`

```bash
dreamina <subcommand> \
  --image <image_path> \                   # only for multimodal2video / image2video
  --model_version <model> \
  --ratio "<ratio>" \                      # not for image2video (inferred from image)
  --duration <duration> \
  --video_resolution "720p" \
  --prompt "<prompt>"
```

Or for text-to-video only:
```bash
dreamina text2video --prompt "..." --ratio "16:9" ...
```

**Critical:** `dreamina` is at `/Users/aoki/.local/bin/dreamina`. Always verify login with `dreamina user_credit` before starting.

After each submit, parse the JSON output for `submit_id`. Save `{task, submit_id, status: "submitted"}`.

Monitor pattern (poll every 30-60s):
```bash
dreamina query_result --submit_id=<id>
```
Check `gen_status`: `querying` → still processing, `success` → done, `fail` → failed.

Download: when `gen_status == "success"`, extract video URL from result and download to output directory. Rename to match the reference image name: `重庆谈判2.mp4`.

##### If Grok browser:

Delegate to the `grok-video-batch` skill. Key steps:
1. Ensure Chrome is running with CDP port 9222
2. Connect via Playwright `connect_over_cdp()`
3. For each task: navigate to `grok.com/imagine` → activate query bar → set video mode → set user-specified `<resolution>`/`<duration>`/`<ratio>` → upload image → type prompt → submit
4. Monitor: after submit, URL changes to `/imagine/post/<uuid>`. Video generation takes 2-5 minutes.
5. Download: Grok provides a video element with `src` attribute after generation completes.

See `grok-video-batch/SKILL.md` for exact selectors and wait times.

#### Step 1.4: Monitor all tasks

For Dreamina:
- Poll `dreamina query_result --submit_id=<id>` every 60s
- Track: submitted → querying → success/fail

For Grok:
- Poll each post page (`grok.com/imagine/post/<id>`) every 60s
- Check for `<video>` element with valid `src`
- Check for error states on page

Continue monitoring until ALL tasks reach terminal state (success or fail). Timeout: 30 minutes per task.

#### Step 1.5: Download results

**Dreamina download:**
```bash
curl -o <output_dir>/<image_name>.mp4 "<video_url>"
```

**Grok download:**
```python
# Direct curl to imagine-public.x.ai often times out.
# Reliable: fetch inside browser via page.evaluate(), pipe base64 back.
video = await page.query_selector('video')
src = await video.get_attribute('src')

import base64
result = await page.evaluate('''async (url) => {
    const resp = await fetch(url);
    const blob = await resp.blob();
    const reader = new FileReader();
    return new Promise((resolve) => {
        reader.onloadend = () => resolve({ok: true, data: reader.result, size: blob.size});
        reader.onerror = () => resolve({ok: false});
        reader.readAsDataURL(blob);
    });
}''', src)

if result.get('ok') and result.get('data'):
    b64 = result['data'].split(',')[1]
    with open(output_path, 'wb') as f:
        f.write(base64.b64decode(b64))
```

Rename: use the reference image filename stem. E.g. `重庆谈判2.jpg` → `重庆谈判2.mp4`.

#### Step 1.6: Output Phase 1 status table

Format as markdown table:

```
| # | 图片名 | 提示词 | 状态 |
|---|--------|--------|------|
| 1 | 重庆谈判2.jpg | 采用2.5D视差风格... | ✅ 成功 |
| 2 | 日本投降.jpeg | 采用2.5D视差风格... | ❌ 提交失败 |
| 3 | 南昌起义.jpeg | 采用2.5D视差风格... | ⏳ 生成中 |
```

Status values: `✅ 成功` (video downloaded), `❌ 提交失败` (submit error), `❌ 生成失败` (gen failed), `❌ 审核拦截` (TNS/content block), `⏳ 超时` (timeout).

### Phase 2: Retry failures with the other tool

#### Step 2.1: Identify failures

Failed = any task where video was NOT successfully downloaded. This includes:
- Submit failed
- Generation failed (Dreamina: `gen_status == "fail"`)
- Content moderation blocked (Dreamina: `post-TNS check did not pass`)
- Timed out (no result after 30 min)
- Grok: no video element appears, or error page

#### Step 2.2: Ask about prompt inversion

```
AskUserQuestion:
  header: "倒置提示词"
  question: "是否需要对失败任务的提示词进行倒置处理？"
  options:
    - "是，倒置提示词后重试" — 对每个失败任务的提示词做语义倒置
    - "否，使用原提示词重试" — 保持提示词不变
```

#### Step 2.3: Prompt inversion via prompt-optimizer skill

When user requests inversion, delegate to the **`prompt-optimizer`** skill's "模式二：倒置提示词" mode.

The `prompt-optimizer` skill uses a **【宏观→微观】两步法**:

1. **First**: Read the entire prompt, understand the overall narrative arc (起点/终点/整体趋势/中间关键状态)
2. **Then**: Under the inverted arc framework, apply the detailed mapping table to each sub-motion

It covers: camera push/pull/pan/tilt, character movement, physical effects (smoke/fire/water/explosion), object transformations, and more — all with a comprehensive direction inversion table.

**Do NOT apply ad-hoc inversion rules.** Always invoke `prompt-optimizer` for consistent, high-quality prompt inversion. The skill outputs:
- 倒置后的提示词 (inverted prompt, ready to use)
- 倒置变更清单 (change log showing what was inverted)

**Important:** After inversion, show a comparison table BEFORE submitting:
```
| # | 任务 | 原始提示词（摘要） | 倒置提示词（摘要） |
|---|------|-------------------|-------------------|
| 1 | 南昌起义 | 从全景定格1秒...推进到特写 | 从特写开始...拉远到全景定格1秒 |
```

#### Step 2.4: Execute with the OTHER tool

If Phase 1 used Dreamina → Phase 2 uses Grok.
If Phase 1 used Grok → Phase 2 uses Dreamina.

Same execution/monitor/download pattern as Phase 1, using the (optionally inverted) prompts.

#### Step 2.5: Output Phase 2 status table

Same format as Phase 1 table. Also include a combined summary:

```
### 最终汇总
| 轮次 | 工具 | 成功 | 失败 | 成功率 |
|------|------|------|------|--------|
| Phase 1 | Grok | 8 | 2 | 80% |
| Phase 2 | Dreamina | 1 | 1 | 50% |
| **合计** | | **9** | **1** | **90%** |
```

### Concurrent execution guidelines

- Dreamina: submit all tasks first (fast), then poll in parallel batches of 5
- Grok: must be sequential (single browser tab), ~25s per task
- Monitoring: poll ALL pending tasks every 60s regardless of tool
- Download: as soon as any task completes, download immediately

### Helper script

See `dreamina_monitor.py` in this skill directory for Dreamina polling/download automation.
