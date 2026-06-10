# Batch Video Generator V2 — 批量 AI 视频生成管道

**版本**: 2.0 | **更新**: 2026-05-20

四段式 AI 视频生成管道，输入可以是视频/图片/文档/文本，产出拼接完成的视频文件。每阶段有明确分割点，人工参与节点可选（支持关键词跳过实现全自动）。

## 目录

1. [管道概览](#1-管道概览)
2. [核心数据格式](#2-核心数据格式)
3. [阶段1: 获取分镜头脚本](#3-阶段1-获取分镜头脚本)
4. [阶段2: 获取参考图](#4-阶段2-获取参考图)
5. [阶段3: 生成视频](#5-阶段3-生成视频)
6. [阶段4: 拼接输出](#6-阶段4-拼接输出)
7. [用户指令判断规则](#7-用户指令判断规则)
8. [关键常量](#8-关键常量)
9. [相关 Skill](#9-相关-skill)
10. [文件说明](#10-文件说明)

---

## 1. 管道概览

```
用户输入（视频/图片+模板/分镜文档/纯文本创意）
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 阶段1: 获取分镜头脚本（目标：storyboard.json 定稿）              │
│                                                             │
│  1A 视频          → 千问VL分析                                │
│  1B 图片+模板     → 千问VL逐张填充                             │
│  1C 分镜文档      → 解析(文本/Excel/Word)                      │
│  1D 纯文本创意    → 分析意图 + 展开                             │
│                                                             │
│  → ⏸ 人工审核确认（无明确指令时暂停，有跳过触发词则全自动）       │
│  → 输出定稿 storyboard.json                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ storyboard.json 定稿
┌─────────────────────────────────────────────────────────────┐
│ 阶段2: 获取参考图（目标：ref_frames/ 完整）                     │
│                                                             │
│  2A 原始是视频 → 从原视频截帧 + 默认去水印                        │
│  2B 原始是图片 → 图片本身作为参考帧（默认不去水印）                 │
│  2C 原始是文档/文本 → dreamina text2image（用 image_prompt）     │
│                                                             │
│  → 循环检测生图任务，失败自动重试直到全部成功                       │
│  → 格式校验（每个镜头有图/有prompt）                             │
│  → ⏸ 人工审核图片质量                                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ 校验通过 + 人工确认
┌─────────────────────────────────────────────────────────────┐
│ 阶段3: 生成（含内部重试 + 兜底链）                                │
│                                                             │
│  默认：Dreamina Web，逐镜头 image2video                        │
│  积分检查 >1000 暂停确认                                       │
│                                                             │
│  → 逐镜头提交 → 监控 → 下载                                    │
│  → 失败重试 3 次 → 仍失败换 Grok 兜底                            │
│  → Grok 也失败 → 标记 ❌                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ 全部生成完毕
┌─────────────────────────────────────────────────────────────┐
│ 阶段3 出口：完成度校验 + 人工决策                                │
│  全部成功 → 自动进入阶段4                                      │
│  有失败项 → ⏸ 暂停，询问用户处理方式                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ 用户确认拼接
┌─────────────────────────────────────────────────────────────┐
│ 阶段4: 拼接                                                  │
│  ffmpeg concat → 最终汇总输出                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 核心数据格式

### 2.1 storyboard.json

阶段1 产出，阶段2/3 消费的统一分镜头数据格式。`raw_analysis.json` 是千问 VL 的原始输出（仅含 overview + shots 的描述字段）；`storyboard.json` 是完整版 = raw_analysis.json + Claude 生成的 image_prompt / video_prompt。

```json
{
  "overview": {
    "title": "视频标题",
    "script": "整体剧本描述（叙事结构、各阶段逻辑、情绪递进）",
    "style": "全局视觉风格",
    "color_palette": ["主色1", "主色2"],
    "overall_rhythm": "整体节奏描述"
  },
  "shots": [
    {
      "id": 1,
      "timecode": "00:00:00-00:03:05",
      "duration_sec": 3.2,
      "shot_type": "景别",
      "composition": "构图方式（含元素位置）",
      "colors": "色调光影（含光源方向、光照情况、明暗对比）",
      "content": "中文画面详细描述",
      "dynamics": "动态元素描述",
      "vfx": "视觉特效（粒子、光效、烟雾等）",
      "camera_movement": "运镜方式",
      "transition": "转场描述（最后一个为空）",
      "image_prompt": "Claude生成的图片提示词（中文，侧重静态画面）",
      "video_prompt": "Claude生成的视频提示词（中文，侧重动态/运镜/转场）"
    }
  ],
  "meta": {
    "total_duration_sec": 44.3,
    "total_shots": 11,
    "source_type": "video|images|storyboard_doc|text_prompt",
    "has_reference_frames": false
  }
}
```

**字段说明**:
- `script`: 全局叙事结构，影响各阶段运镜节奏和色调倾向分配
- `vfx`: 视觉特效描述，主要用于 video_prompt（特效本质上是动态的）
- `image_prompt`: 侧重静态画面（主要参考 content, composition, colors, shot_type）
- `video_prompt`: 侧重动态表现（主要参考 content, composition, dynamics, camera_movement, transition, vfx）
- 两者有重叠是正常的，AI 参与生成时根据各自侧重自动调整，不做机械拼接

### 2.2 raw_analysis.json

千问 VL 的原始输出，仅含 overview + shots 的描述字段（不含 image_prompt / video_prompt / grouping）。Claude 在本地读取此文件，AI 参与生成 image_prompt 和 video_prompt。

### 2.3 ref_frames/

每个镜头一张参考图，命名 `shot_01.jpg`, `shot_02.jpg` ... `shot_NN.jpg`。

---

## 3. 阶段1: 获取分镜头脚本

目标：不管输入是什么，产出经人工确认的定稿 `storybook.json`。

### 3.1 1A: 视频 → 千问VL分析

#### 3.1.1 视频预检

```bash
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=width,height,r_frame_rate \
  -of json "<video_path>"
```

提取：duration（秒）、size（字节）、width×height、fps、画面比例。

#### 3.1.2 智能压缩

| 条件 | 操作 |
|------|------|
| 短边 < 720px 且 ≤ 300MB | 直接发送 |
| 短边 ≥ 720px | 压缩到 720p |
| 文件 > 300MB | crf 23 压缩，仍超则 crf 26 兜底 |

```bash
ffmpeg -i "$VIDEO" -vf "scale='min(1280,iw)':-2" \
  -c:v libx264 -crf 23 -preset fast \
  -c:a aac -b:a 128k -movflags +faststart "$COMPRESSED" -y
```

#### 3.1.3 发送千问 VL

```python
from dashscope import MultiModalConversation
response = MultiModalConversation.call(
    model="qwen3-vl-plus",
    messages=[{"role": "user", "content": [
        {"video": f"file://{path}"},
        {"text": ANALYSIS_PROMPT}
    ]}],
    temperature=0.3, max_tokens=32768
)
```

`qwen3-vl-plus` 拥有 256K 上下文和 32K+ 输出限制，一般情况下不需要分段。

#### 3.1.4 分析提示词

千问只负责**画面描述 + 动态识别 + 元素识别 + 特效识别**，不生成 prompts、不分组、不输出英文。

输出 JSON 字段：id, timecode, duration_sec, shot_type, composition, colors, content, dynamics, vfx, camera_movement, transition

#### 3.1.5 JSON 修复 + 保存

```python
import re, json
text = response_text[text.find('{'):text.rfind('}')+1]
text = re.sub(r'}\s*\n\s*{', '},\n    {', text)
text = re.sub(r',\s*}', '}', text)
text = re.sub(r',\s*]', ']', text)
raw_data = json.loads(text)
```

保存为 `raw_analysis.json`。meta.source_type = "video"。

#### 3.1.6 覆盖率验证

验证 `coverage_end_sec ≥ total_duration * 0.95`。qwen3-vl-plus 绝大多数情况一次覆盖完整。若覆盖率不足则自动触发分段循环：

```python
while coverage < total_duration * 0.95:
    remaining = trim_video(video_path, coverage - 2.0, total_duration)
    raw_data_2 = call_qwen_vl(remaining)
    raw_data = merge_raw_data(raw_data, raw_data_2, offset=coverage - 2.0)
    coverage = raw_data.get("coverage_end_sec", 0)
```

#### 3.1.7 Claude 本地生成完整 storyboard.json

六步处理：

1. **读取 overview 全局约束** — script（叙事结构）、style（视觉风格）、color_palette（色调约束）、overall_rhythm（节奏分配）
2. **去水印/Logo/字幕过滤** — 扫描 content 中含「水印」「logo」「字幕」的子句并排除
3. **生成 image_prompt**（侧重静态）— 基于 content, composition, colors, shot_type
4. **生成 video_prompt**（侧重动态）— 基于 content, composition, dynamics, camera_movement, transition, vfx。末尾必须包含音效描述
5. **施加 script 全局影响** — 按叙事阶段调整运镜速度和色调：

| Script 阶段 | image_prompt 调整 | video_prompt 调整 |
|------------|------------------|------------------|
| 开场/引入 | 强调暗调、神秘感 | 运镜缓慢、柔和淡入 |
| 发展/展开 | 元素层次丰富、空间感强 | 运镜逐渐加速 |
| 高潮/核心 | 高对比度、强光 | 快速运镜、震撼转场 |
| 结尾/升华 | 亮度提升、开放性空间 | 缓慢拉远、渐隐淡出 |

6. **组装 storyboard.json**（不含 grouping，grouping 在阶段3处理）

### 3.2 1B: 图片输入

判断是否有提示词模板（含 `[占位符]`）：
- **B1 有模板** → 千问逐张填充描述，按模板结构
- **B2 无模板** → 询问用户选择（提供模板 / 千问自动描述 / 取消）

千问输出后，Claude 按 1A.7 逻辑生成 image_prompt / video_prompt。

### 3.3 1C: 分镜文档解析

| 子场景 | 输入 | 处理 |
|--------|------|------|
| C1 文本脚本 | 序号｜画面｜运镜 格式 | 直接解析分隔符 |
| C2 Excel | .xlsx | openpyxl 读取表格 |
| C3 Word | .docx | python-docx 提取文本/表格 |

### 3.4 1D: 纯文本创意

用户只给了创意描述（如"帮我做一个科技感片头，40秒"）：
1. 分析意图 → 提取主题、风格、时长、段数
2. 展开为具体镜头列表
3. 构造 storyboard.json

### 3.5 阶段1 出口：人工审核

输出分镜头摘要表格（中文提示词），无明确指令时暂停。

| # | 时间码 | 时长 | 内容简述 | vfx | transition | image_prompt | video_prompt |
|---|--------|------|---------|-----|-----------|-------------|-------------|

用户可：通过 / 修改（合并/拆分/优化提示词）/ 取消（只保留脚本不继续）

**跳过审核触发词（9个）**：
`直接做完` | `不用看脚本` | `不用审核` | `跳过审核` | `跳过人工` | `跳过脚本审核` | `直接继续` | `全部做完` | `自动继续`

---

## 4. 阶段2: 获取参考图

目标：基于定稿 storyboard.json，为每个镜头产出一张参考图 → `ref_frames/`。

### 4.1 跳过阶段2

若用户初始指令包含以下关键词，跳过整个阶段2：

`文生视频` | `不要参考图` | `不用生图` | `不用参考图` | `不用截图` | `纯文字生成` | `text2video` | `text to video` | `不要图`

### 4.2 2A: 原始是视频 → 截帧 + 默认去水印

**截帧**：根据定稿 storyboard 中每个镜头的起始时间码，提取 `start_time + 1s`：
```bash
ffmpeg -ss <start_time + 1s> -i <video> -vframes 1 -q:v 2 ref_frames/shot_01_original.jpg
```

**默认去水印**（视频通常带水印）：
```bash
dreamina image2image --images <frame> \
  --prompt "保持原图画面内容完全不变，去除图片中的水印、logo、字幕，画面清晰干净" \
  --ratio <原图比例> --resolution_type 2k --model_version 5.0 --poll 300
```

输出覆盖写入 `ref_frames/shot_01.jpg`。每个镜头独立提交为后台任务，通过 task_id → shot_NN 映射确保命名正确。

### 4.3 2B: 原始是图片 → 直接作为参考帧

图片文件直接复制到 `ref_frames/shot_01.jpg`。默认不去水印，仅用户明确说"去水印"时才执行（逻辑同 2A.2）。

### 4.4 2C: 原始是文档/文本 → 文生图（默认执行）

用 storyboard.json 中每个 shot 的 `image_prompt`（中文）：
```bash
dreamina text2image --prompt "<shot.image_prompt>" \
  --ratio <VIDEO_RATIO> --resolution_type 2k --model_version 5.0 --poll 120
```

### 4.5 阶段2 出口

**第零步：生图任务完整性检测** — 循环检测所有 dreamina 生图任务，失败自动重试，不设上限直到全部成功

**第一步：格式校验**
- storyboard.json 存在？shots 非空？每个 shot 有 prompt？
- ref_frames/ 存在？数量与 shots 一致？
- 不通过 → 暂停报告；通过 → 有跳过指令时不报告

**第二步：人工审核图片质量**
- 展示参考图列表，出口逻辑同阶段1

**跳过审核触发词（8个）**：
`直接做完` | `不用审核` | `跳过审核` | `跳过人工` | `不用看` | `直接继续` | `全部做完` | `自动继续`

---

## 5. 阶段3: 生成视频

### 5.1 默认流程（无明确指令时）

| 项目 | 默认值 |
|------|--------|
| 后端 | Dreamina Web（浏览器操控） |
| 生成方式 | 有参考图 → image2video / 无参考图（跳过阶段2） → text2video |
| 单位 | 按单个分镜头逐一生成，时长 = shot.duration_sec |
| 画幅 | 阶段1计算的最接近预设比例 |
| 分辨率 | 720p |
| 模型 | seedance2.0 |

### 5.2 积分检查

总积分 = Σ(每个镜头的积分消耗)。text2video ~12-24分，image2video ~25-50分（依时长）。
- ≤ 1000 → 直接生成
- > 1000 → ⏸ 暂停确认

### 5.3 生成模式

**模式 A: text2video**（无参考图）
```bash
dreamina text2video --prompt "<shot.video_prompt>" \
  --model_version <model> --ratio <ratio> \
  --video_resolution 720p --duration <shot.duration_sec>
```

**模式 B: image2video**（默认，有参考图）
```bash
dreamina image2video --image <ref_frame> --prompt "<shot.video_prompt>" \
  --model_version <model> --ratio <ratio> \
  --video_resolution 720p --duration <shot.duration_sec>
```

**模式 C: multi image2video**（仅用户明确说"分组"时触发）
- 按用户指定的时长上限，将连续镜头累加分组
- 每组收集所有参考图 + 融合 video_prompt
- 提示词融合：按时间轴分段（0-Xs / X-Ys），组内转场写入，组间断点双向衔接

### 5.4 后端参数

| 参数 | Dreamina (CLI / Web) | Grok |
|------|---------------------|------|
| 模型 | seedance2.0 / fast / etc. | — |
| 画幅 | 1:1 / 3:4 / 16:9 / 4:3 / 9:16 / 21:9 | 2:3 / 3:2 / 1:1 / 9:16 / 16:9 |
| 分辨率 | 480p / 720p / 1080p | 480p / 720p |
| 时长 | 4s / 6s / 8s / 10s / 12s | 6s / 10s |

### 5.5 逐镜头重试 + 兜底链

```
for shot in shots:
    attempt = 0
    while attempt < 3:
        submit to Dreamina → monitor
        if success → download → mark ✅ → break
        elif fail_reason in [upload_timeout, network_error, transient]:
            attempt += 1  # 瞬时错误，同模型重试
        else:
            break  # 审核拦截/内容策略，跳出
    if shot still failed:
        submit to Grok  # 兜底，不倒置提示词
        if success → download → mark ✅
        else → mark ❌
```

### 5.6 阶段3 出口

全部成功 → 自动进入阶段4。有失败项 → ⏸ 暂停，提供 3 个选项：
1. 不管失败项，直接用已成功的视频拼接
2. 倒置提示词后用 Grok 再试一次
3. 手动修改提示词后重新生成失败项

---

## 6. 阶段4: 拼接输出

### 拼接

```bash
echo "file '<output_dir>/01.mp4'
file '<output_dir>/02.mp4'..." > concat_list.txt
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy <combined>.mp4 -y
```

### 最终汇总

| # | 场景 | 时长 | 状态 | 文件 |
|---|------|------|------|------|
| 1 | ... | 3.2s | ✅ | 01.mp4 (X MB) |
| ... | ... | ... | ... | ... |

合并视频: combined.mp4 (XX MB, XXs, 1280×720)
总消耗积分: XXX

---

## 7. 用户指令判断规则

1. **有明确跳过指令** → 严格按指令，不在中间询问
2. **无明确指令** → 每个阶段结束后询问
3. **例外（无论何时都暂停）**：
   - 格式校验不通过（阶段2出口第一步）
   - 阶段3 积分阈值 > 1000（除非用户说"不管积分"）
   - 阶段3出口有失败项
4. **跳过阶段2**：用户指令含文生视频相关关键词

---

## 8. 关键常量

| 项目 | 值 |
|------|-----|
| 千问 VL 模型 | qwen3-vl-plus |
| 千问 VL 上下文 | 256K 上下文, 32K+ 输出 |
| 千问 VL 视频上传上限 | 1024 MB (SDK OSS), 推荐 ≤ 300MB |
| 视频压缩阈值 | 300 MB |
| 视频分辨率上限 | 720p（短边） |
| Dreamina 默认模型 | seedance2.0 |
| 参考帧截取偏移 | +1s |
| 分组默认时长 | 12s（≤18s） |
| Chrome CDP 端口 | 9222 |

---

## 9. 相关 Skill

- `dreamina-cli` — Dreamina CLI 基础操作
- `grok-video-batch` — Grok 浏览器自动化批量生成
- `prompt-optimizer` — 提示词优化和倒置
- `dreamina-batch` — 即梦批量视频生成工具

---

## 10. 文件说明

| 文件名 | 说明 |
|--------|------|
| `SKILL.md` | Skill 主文件，给 Claude 执行用的完整指令（53KB） |
| `README.md` | 本文档，给人阅读的流程说明 |
| `dreamina_web_automation.py` | Dreamina 国际版 Web 自动化脚本（Playwright CDP，23KB） |
