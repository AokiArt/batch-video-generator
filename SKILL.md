---
name: batch-video-generator-v2
description: 四段式管道：①获取分镜头脚本(人工确认)→②获取参考图(人工审核)→③生成(含内部重试+完成度校验)→④拼接。输入视频/图片/文档/文本均可。
metadata:
  tags: video, batch, dreamina, grok, ai-generation, storyboard, video-analysis, pipeline
---

# Batch Video Generator V2

四段式管道，每阶段有明确目标，阶段分割点卡在人工干预节点：

**① 获取分镜头脚本 → ② 获取参考图 → ③ 生成（含内部重试） → ④ 拼接**

---

## 统一数据格式

阶段1 产出 `storyboard.json`，阶段2 产出 `ref_frames/`，阶段3 消费这两者。

### storyboard.json

> **说明**：`raw_analysis.json` 是千问 VL 的原始输出（仅含 overview + shots 的描述字段）。
> `storyboard.json` 是完整版 = `raw_analysis.json` + Claude 生成的 `image_prompt` / `video_prompt`。
> `grouping` 不在阶段1生成，若需分组在阶段3处理。

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
      "timecode": "00:00-00:03",                // MM:SS
      "duration_sec": 3.2,
      "shot_type": "景别",
      "composition": "构图方式（含元素位置信息）",
      "colors": "色调光影（含光源方向、光照情况、明暗对比）",
      "content": "中文画面详细描述",
      "dynamics": "动态元素",
      "vfx": "视觉特效和包装（粒子、光效、烟雾等）",
      "camera_movement": "运镜方式",
      "transition": "本镜头结尾到下一个镜头之间的转场描述（最后一个为空）",
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

### ref_frames/

每个镜头一张参考图，命名 `shot_01.jpg`, `shot_02.jpg`...

---

## 阶段总览

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
│  → ⏸ 人工审核确认（无明确指令时暂停，有"直接做完"则跳过）         │
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
│  去水印：统一中文提示词，按原图比例，2K，每镜头1张                   │
│  文生图：默认执行，仅"不用生图"时才跳过                             │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ ref_frames/ 产出
┌─────────────────────────────────────────────────────────────┐
│ 🔍 阶段2 出口：生图任务完整性检测 → 格式校验 → 人工审核            │
│  □ 循环检测 dreamina 生图任务，失败自动重试直至全部成功            │
│  □ 输出校验报告（每个镜头有图/有prompt，打勾打叉）                  │
│                                                             │
│  格式不通过 → 报告缺失 → 询问用户（无论何时都暂停）                │
│  格式通过 → ⏸ 展示参考图 → 人工审核图片质量                        │
│    · 无明确指令 → 暂停询问                                       │
│    · 用户确认/有明确指令 → 进入阶段3                              │
│    · 用户要求修改某张图 → 重新生成该镜头参考图 → 再次审核           │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ 校验通过 + 人工确认
┌─────────────────────────────────────────────────────────────┐
│ 阶段3: 生成（含内部重试 + 兜底链）                                │
│                                                             │
│  默认：Dreamina Web，逐镜头 image2video，shot.duration_sec      │
│  分组：仅用户明确提出时，multi image2video + 合并时长              │
│  积分：>1000 暂停确认                                           │
│                                                             │
│  → 逐镜头提交 → 监控 → 下载                                     │
│  → 失败重试 3 次 → 仍失败换 Grok 兜底                            │
│  → Grok 也失败 → 标记 ❌                                       │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ 全部生成完毕
┌─────────────────────────────────────────────────────────────┐
│ 🔍 阶段3 出口：完成度校验 + 人工决策                             │
│  □ 所有镜头是否全部生成成功？                                     │
│                                                             │
│  全部成功 → 自动进入阶段4                                      │
│  有失败项 → ⏸ 暂停，列出失败原因，询问用户：                     │
│    1. 不管失败项，直接用已成功的视频拼接                         │
│    2. 倒置提示词后用 Grok 再试一次                               │
│    3. 手动修改提示词后重新生成失败项                               │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ 用户确认拼接
┌─────────────────────────────────────────────────────────────┐
│ 阶段4: 拼接                                                   │
│  ffmpeg concat → 最终汇总输出                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 阶段1: 获取分镜头脚本

**目标**：不管输入是什么，产出经人工确认的定稿 `storyboard.json`。

**通用流程**：识别输入类型 → 对应方式产出脚本 → ⏸ 人工审核 → 定稿

---

### 1A: 视频 → 千问VL分析

#### 1A.1 视频预检：获取信息 + 文件大小判断

```bash
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=width,height,r_frame_rate \
  -of json "<video_path>"
```

提取关键参数：`duration`（秒）、`size`（字节）、`width×height`、`fps`。

**计算画面比例**：`width / height` → 映射到最接近的预设比例。

比例映射表（按 width/height 值从窄到宽）：
| 比例 | 比值 | 说明 |
|------|------|------|
| 1:1 | 1.0 | 正方形 |
| 3:4 | 0.75 | 竖屏 |
| 4:3 | 1.33 | 传统横屏 |
| 9:16 | 0.56 | 手机竖屏 |
| 16:9 | 1.78 | 标准宽屏 |
| 21:9 | 2.33 | 超宽屏 |

选取规则：计算 `w/h`，找到比值差最小的预设。若差值相等则选更宽的。
此比例用于阶段2生图和阶段3生视频的 `--ratio` 参数。**不在提示词中写比例关键词**。

#### 1A.2 视频预检 + 智能压缩

**千问 VL 视频上传限制**（通过 API 实际查询 `get_upload_certificate` 确认）：

| 项目 | qwen3-vl-plus | 说明 |
|------|-------------|------|
| SDK 临时上传上限 | **1024 MB** | `max_file_size_mb: 1024`，OSS policy `content-length-range: 0-1073741824` |
| 推荐安全值 | **300 MB** | 上传超时 300s，控制在 300MB 以内保证上传速度 |
| 视频时长上限 | 1 小时 | 原生视频理解，支持 fps 参数控制帧采样 |

**压缩规则**：

1. 获取视频参数：宽度、高度、文件大小
2. 短边 < 720px 且文件 ≤ 300MB → 直接发送
3. 短边 ≥ 720px → 压缩到 720p
4. 文件 > 300MB → 压缩到 300MB 以内

```bash
# 获取视频参数
WIDTH=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$VIDEO")
HEIGHT=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO")
FILE_SIZE_MB=$(du -m "$VIDEO" | cut -f1)
SHORT_SIDE=$(( WIDTH < HEIGHT ? WIDTH : HEIGHT ))

NEED_COMPRESS=false
SCALE_FILTER=""

if [ "$SHORT_SIDE" -ge 720 ]; then
    NEED_COMPRESS=true
    SCALE_FILTER="scale='min(1280,iw)':-2"   # 压缩到 720p
fi

if [ "$FILE_SIZE_MB" -gt 300 ]; then
    NEED_COMPRESS=true
fi

if [ "$NEED_COMPRESS" = true ]; then
    echo "压缩中（短边=${SHORT_SIDE}px, ${FILE_SIZE_MB}MB）..."

    if [ -z "$SCALE_FILTER" ]; then
        # 短边已 < 720px，只需降码率
        ffmpeg -i "$VIDEO" \
          -c:v libx264 -crf 23 -preset fast \
          -c:a aac -b:a 128k \
          -movflags +faststart "$COMPRESSED" -y
    else
        # 缩到 720p + 降码率
        ffmpeg -i "$VIDEO" \
          -vf "$SCALE_FILTER" \
          -c:v libx264 -crf 23 -preset fast \
          -c:a aac -b:a 128k \
          -movflags +faststart "$COMPRESSED" -y
    fi

    NEW_SIZE=$(du -m "$COMPRESSED" | cut -f1)
    if [ "$NEW_SIZE" -gt 300 ]; then
        # 仍超 300MB，用 crf 26 二次压缩
        ffmpeg -i "$COMPRESSED" \
          -c:v libx264 -crf 26 -preset fast \
          -c:a aac -b:a 128k \
          -movflags +faststart "${COMPRESSED%.mp4}_v2.mp4" -y
        mv "${COMPRESSED%.mp4}_v2.mp4" "$COMPRESSED"
    fi

    echo "压缩完成: $(du -m "$COMPRESSED" | cut -f1)MB"
else
    echo "直接发送（短边=${SHORT_SIDE}px, ${FILE_SIZE_MB}MB）"
fi
```

#### 1A.2b ffmpeg 镜头检测（仅在用户明确要求时启用）

> **默认不使用。** 千问 VL 直接输出时间码是常规流程。仅当用户明确说"用 ffmpeg 切分""本地检测镜头""不用千问分镜"时才启用此方法。

```bash
ffmpeg -i "$VIDEO" -filter_complex "scdet=threshold=8" -an -f null /dev/null 2>&1 \
  | grep "scdet" | awk '{print $NF}' | sed 's/.*://'
```

输出每帧的 scene change score 和时间，按阈值过滤出切点。threshold 默认 8，可按视频平滑度调整（转场流畅则降低至 5-6，硬切为主则升至 10-12）。

检测到的切点时间列表作为精确时间码，再发给千问做内容描述。此时千问提示词中**不要求输出时间码**，仅填充每个已确定时间段的 content/composition/colors 等描述字段。

#### 1A.3 发送视频给千问 VL 分析

> **时间码精度说明**：千问 VL 输出时间码精度约为 0.1s（很少到帧级），属于 AI 语义分镜的正常误差范围。
> 若用户明确要求帧级精确切分，见下方 [1A.2b ffmpeg 镜头检测（仅在用户明确要求时启用）](#1a2b-ffmpeg)。

qwen3-vl-plus 拥有 256K 上下文和 32K+ 输出限制，**一般情况下不需要分段**，直接全视频发送即可。

```python
from dashscope import MultiModalConversation

response = MultiModalConversation.call(
    api_key=DASHSCOPE_KEY,
    model="qwen3-vl-plus",
    messages=[{"role": "user", "content": [
        {"video": f"file://{VIDEO_PATH}"},
        {"text": ANALYSIS_PROMPT}
    ]}],
    temperature=0.3,
    max_tokens=32768
)
```

#### 1A.4 分析提示词模板（精简版，中文为主）

千问只负责**画面描述 + 动态识别 + 元素识别 + 特效识别**，不生成 prompts、不分组、不输出英文。

```
请逐镜头分析这段视频，输出完整的分镜头脚本。

## 一、全局剧本
- title: 视频标题
- script: 整体剧本描述，概括视频的完整叙事结构：从哪个场景开始，经过哪些阶段，
  到哪个场景结束，各阶段之间的逻辑关系和情绪递进
- style: 全局视觉风格（如"实拍写实风格""2.5D视差风格""全息投影风格""赛博朋克风格"等）
- color_palette: 主色调列表
- overall_rhythm: 整体节奏（如"前缓后急，高潮升华""快速切镜""平稳叙事"等）

## 二、逐镜头详细分析
对每个镜头输出以下字段：
- id: 镜头序号
- timecode: 时间码，格式 MM:SS-MM:SS（秒级精度即可，千问无法稳定输出帧级时间码）
- duration_sec: 时长（秒）
- shot_type: 景别（远景/全景/中景/近景/特写）
- composition: 画面内元素的布局方式和位置关系（如"中心对称构图，主体居中""人物在左侧约1/3处，背景右侧留白""对角线构图，光源在右上角"等）
- colors: 色调光影，需包含：①光源方向（顺光/逆光/侧光/顶光/底光）②光照情况（强光/柔光/暗光/剪影）③明暗对比描述
- content: 画面详细描述（中文）。必须描述清楚画面中每个元素的外观、位置、状态
- dynamics: 画面中哪些元素在动、怎么动
- vfx: 画面中的视觉特效和包装元素（如粒子特效、光效、闪电、火星、光晕、烟雾等）。若无特效则填空字符串。
- camera_movement: 运镜方式
- transition: 本镜头结尾到下一镜头的转场效果。若硬切则为空字符串。
  注意：≤1s 的抽象光效/粒子运动归入 transition，不单独列为镜头。

## 三、JSON 格式
{
  "overview": {
    "title":"",
    "script":"整体剧本描述",
    "style":"",
    "color_palette":[],
    "overall_rhythm":""
  },
  "shots": [
    {"id":1,"timecode":"00:00-00:03","duration_sec":3.2,
     "shot_type":"","composition":"","colors":"","content":"",
     "dynamics":"","vfx":"","camera_movement":"","transition":""}
  ],
  "coverage_end_sec": 数字
}

每个镜头必须包含，确保覆盖到视频结尾。
coverage_end_sec 必须等于最后镜头的结束时间。
```

#### 1A.5 JSON 修复 + 保存

```python
import re, json

text = response_text[text.find('{'):text.rfind('}')+1]
text = re.sub(r'}\s*\n\s*{', '},\n    {', text)
text = re.sub(r',\s*}', '}', text)
text = re.sub(r',\s*]', ']', text)
raw_data = json.loads(text)
```

保存千问原始返回为 `raw_analysis.json`。`meta.source_type = "video"`。

> 时间码为 `MM:SS` 格式（千问精度 ~0.1s，不追求帧级）。若用户要求帧级精确切分，使用 [1A.2b ffmpeg](#1a2b-ffmpeg)。

验证覆盖率：`coverage_end_sec ≥ total_duration * 0.95`。qwen3-vl-plus 绝大多数情况一次覆盖完整，若覆盖率不足则触发分段循环（见下方后备方案）。

#### 1A.6 后备：分段循环（覆盖率不足时自动触发）

1A.5 验证覆盖率后，若 `coverage_end_sec < total_duration * 0.95`（无论视频长短），自动触发分段循环：

```python
def analyze_video_with_fallback(video_path, total_duration):
    raw_data = call_qwen_vl(video_path)  # 第一次发送
    coverage = raw_data.get("coverage_end_sec", 0)
    
    while coverage < total_duration * 0.95:
        # 从 coverage 位置 - 2s 重叠处裁剪，继续分析剩余部分
        remaining = trim_video(video_path, coverage - 2.0, total_duration)
        raw_data_2 = call_qwen_vl(remaining)
        raw_data = merge_raw_data(raw_data, raw_data_2, offset=coverage - 2.0)
        coverage = raw_data.get("coverage_end_sec", 0)
    
    return raw_data
```

> 目的：确保视频被完全分析，不管多长。只要没分析完就继续分段，直到覆盖全部时长。

#### 1A.7 Claude 本地生成完整 storyboard.json

千问返回 `raw_analysis.json`（仅含 overview + shots 的描述字段）之后，**由 Claude 在本地完成以下工作**：

**输入**：千问返回的 `raw_analysis.json`
**输出**：完整的 `storyboard.json`（含 image_prompt、video_prompt、grouping）

**核心原则**：

两个提示词都基于千问返回的画面描述字段，但**侧重点不同**：
- `image_prompt`：侧重**静态画面**，从零生成一张图，需要详细的画面内容描述
- `video_prompt`：侧重**动态表现**，在已有画面的基础上描述运动，但也需要一部分画面描述来支撑运动方向（如"人从左边走到右边"需要知道人在左）

> 两者有重叠是正常的，AI 参与生成时根据各自侧重自动调整，不做机械拼接。

---

**Claude 生成步骤**：

**1. 读取 overview 全局约束**

提取以下字段作为全局约束，影响所有 shot 的提示词生成：
- `script`：全局叙事结构（开场→发展→高潮→结尾），决定各阶段的运镜节奏和色调倾向
- `style`：全局视觉风格，每个提示词末尾固定追加
- `color_palette`：主色调列表，约束 image_prompt 的色调描述
- `overall_rhythm`：整体节奏曲线，决定运镜速度的分配

---

**2. 去水印/Logo/字幕过滤**

扫描每个 shot 的 `content` 字段，若含以下关键词，在生成提示词时排除相关子句：

触发词：`水印` `logo` `Logo` `字幕`

> `文字叠加` 不排除——有些镜头的画面内文字叠加是场景本身的一部分。

**过滤方式**：提取 content 中描述水印/logo/字幕的子句 → 排除该子句 → 用剩余内容生成提示词。

---

**3. 为每个 shot 生成 image_prompt（中文，AI 参与）**

**目标**：生成文生图提示词，从零创建画面。

**主要参考字段**（侧重静态描述）：
- `content`：画面主体描述（主要）
- `composition`：构图/元素位置
- `colors`：色调光影（含光源方向、光照情况、明暗对比）
- `shot_type`：景别

**辅助参考**（可选择性融入）：
- `vfx`：若有静态光效（如光晕、光斑），可融入画面描述

**生成要求**：
- 保留千问 `content` 中的**全部关键元素**，不简写、不丢失
- 千问已描述清楚的部分**原样保留**，不凭空想象增加额外细节
- 千问未描述清楚的部分（如材质、空间关系、光影方向模糊）补充说明使其明确
- 每个元素的外观、位置、状态需清晰，但不是越长越好——精准优先

**格式参考**：
```
{精准画面描述，含构图、色调、景别}。电影级光影，高质量，{style}风格。
```

**倾向**：多用静态场景描述词汇，少用运动描述。但若有动态词自然出现，不需强制去除。

---

**4. 为每个 shot 生成 video_prompt（中文，AI 参与）**

**目标**：生成文生视频/图生视频提示词，在画面基础上描述运动。

**主要参考字段**（侧重动态描述）：
- `content`：画面描述（用于支撑运动方向和空间关系，如"人在左、苹果在右"→"人从左走向右拿苹果"）
- `composition`：元素位置信息（用于描述运动的空间方向）
- `dynamics`：画面内元素的运动方式（主要）
- `camera_movement`：运镜方式（主要）
- `transition`：本镜头的入场转场（取上一镜头的 transition 值，首镜用"渐显入场"）
- `vfx`：视觉特效（主要——特效本质上是动态的，如粒子飞散、光效闪烁、烟雾扩散）

**格式参考**：
```
{画面空间关系简述 + 动态描述 + 运镜 + 特效 + 转场入场}。{style}风格，一镜到底，8K高清，无背景音乐，只需音效：{根据画面内容列出对应音效}。
```

**音效描述规则**（video_prompt 末尾必须包含）：
- 每个 video_prompt 末尾必须加一句：`无背景音乐，只需音效：{音效列表}`
- 音效列表根据镜头画面内容动态生成，例如：
  - 火箭发射 → `无背景音乐，只需音效：火箭引擎轰鸣声、火焰喷射燃烧声、发射台震动低频`
  - 水下鱼群 → `无背景音乐，只需音效：水下气泡声、水流涌动低频、鱼群游动划水声`
  - 时钟转动 → `无背景音乐，只需音效：指针滴答声、机械齿轮转动声、星尘飘移的微弱风鸣`
  - 隧道穿越 → `无背景音乐，只需音效：高速风噪声、电子脉冲声、结构震颤低频`
  - 文字淡入/UI出现 → `无背景音乐，只需音效：轻微电子提示音、光效嗡鸣声`
  - 爆炸/强光 → `无背景音乐，只需音效：爆炸轰鸣声、能量释放低频冲击波、玻璃破碎声`
  - 人物行走 → `无背景音乐，只需音效：脚步声、衣物摩擦声、环境空间混响`
  - 自然环境（海浪/风/雨）→ `无背景音乐，只需音效：海浪拍打声、风声、雾气流动的微弱沙沙声`
  - 纯白结尾/渐隐 → `无背景音乐，只需音效：低频逐渐消失的白噪音、微弱的呼吸声`
- 音效数量控制在 2-4 个，简洁精准，不堆砌
- 音效应反映画面中具体的动态元素，不写与画面无关的音效
- 音效之间用顿号分隔

**倾向**：多用动态、运镜、特效、转场词汇。画面描述只需支撑运动方向，不需要像 image_prompt 那样详细。

---

**5. 全局 script 对提示词的影响方案**

根据 `overview.script` 识别的叙事阶段，自动调整每个 shot 的提示词：

| script 阶段 | image_prompt 调整 | video_prompt 调整 |
|------------|------------------|------------------|
| 开场/引入 | 强调暗调、神秘感、渐显氛围 | 运镜缓慢、柔和淡入、低速度感 |
| 发展/展开 | 元素层次丰富、空间感强 | 运镜逐渐加速、流动感增强 |
| 高潮/核心 | 强调中心光源、高对比度、强光 | 快速运镜、震撼转场（爆炸/快速切镜） |
| 结尾/升华 | 强调亮度提升、开放性空间、上升感 | 缓慢上升/拉远、光晕扩散、渐隐淡出 |

**overall_rhythm 影响规则**：
- "前缓后急" → 前 1/3 shot 的 video_prompt 倾向慢速运镜，后 1/3 倾向快速运镜
- "快速切镜" → transition 描述强调"硬切""快速切换"
- "平稳叙事" → 运镜保持"缓慢""平稳"，少用剧烈转场
- "缓急交替" → 奇数 shot 缓、偶数 shot 急，交替分配运镜速度

**color_palette 影响规则**：
- 每个 image_prompt 的色调描述应与全局 `color_palette` 一致
- 若某 shot 的原始 colors 偏离全局调色板（如千问输出了"暖黄色"但全局是蓝调），生成时修正为全局色系

**具体操作**：Claude 读取 `overview.script` → 分析叙事阶段划分 → 为每个 shot 分配阶段标签 → 按上表施加对应调整。

---

**6. 组装 storyboard.json**

将所有字段写入，含 `overview`、`shots`（含 image_prompt / video_prompt）、`meta`。

> **grouping 不在阶段1生成**。默认按单个分镜头各自生成。若用户在阶段3明确提出分组（如"按12s分组"），在阶段3按 multi image2video 方式处理。

---

### 1B: 图片 → 千问分析 + 生成分镜脚本

#### 情况判断：用户是否提供了提示词模板？

```
用户给了图片文件夹
        │
        ▼
  有提示词模板吗？
   ├── 有（含 [占位符]）→ 模式 B1：填充模板
   └── 没有            → ⏸ 询问用户：
                           ① 提供一个提示词模板
                           ② 让千问自动描述图片并生成 video_prompt
                           ③ 取消
```

### 1B: 图片 → 千问描述 + Claude 生成完整 storyboard

#### 情况判断

```
用户给了图片文件夹
        │
        ▼
  有提示词模板吗？
   ├── 有（含 [占位符]）→ 模式 B1：千问填充模板中的描述部分
   └── 没有            → ⏸ 询问用户：
                           ① 提供一个提示词模板
                           ② 让千问自动描述图片（不套模板）
                           ③ 取消
```

#### B1: 有模板 → 千问逐张填充描述

用户发图片文件夹 + 提示词模板（含 `[占位符]`），如：
```
"2.5D视差风格，一镜到底。[主要人物特征]。[场景氛围]。[运镜方式]。8K高清。"
```

对每张图片调用千问 VL **只输出描述字段**（不含 prompts）：

```python
response = MultiModalConversation.call(
    model="qwen3-vl-plus",
    messages=[{"role": "user", "content": [
        {"image": f"file://{image_path}"},
        {"text": f"""请详细描述这张图片的内容，然后按模板填充占位符。

模板：{template}

输出 JSON：
{{"id":序号,"duration_sec":5,"shot_type":"景别",
  "composition":"构图方式（含元素位置）","colors":"色调光影",
  "content":"中文详细描述（填充模板后的完整画面描述）",
  "dynamics":"画面动态元素",
  "camera_movement":"运镜建议"}}"""}
    ]}],
    api_key=DASHSCOPE_KEY,
    vl_high_resolution_images=True,
)
```

#### B2: 无模板（用户选择"自动生成"）→ 千问自动描述

```python
response = MultiModalConversation.call(
    model="qwen3-vl-plus",
    messages=[{"role": "user", "content": [
        {"image": f"file://{image_path}"},
        {"text": """请详细描述这张图片的内容。

输出 JSON：
{"id":序号,"duration_sec":5,"shot_type":"景别（远景/全景/中景/近景/特写）",
 "composition":"构图方式，描述元素在画面中的位置关系",
 "colors":"色调光影",
 "content":"中文详细描述，包含所有元素的外观、位置、状态",
 "dynamics":"画面中可运动元素的描述",
 "camera_movement":"运镜建议"}"""}
    ]}],
    api_key=DASHSCOPE_KEY,
    vl_high_resolution_images=True,
)
```

#### 千问返回后：Claude 本地生成完整 storyboard

千问输出仅含 `id, duration_sec, shot_type, composition, colors, content, dynamics, camera_movement`。

Claude 接收后，按与 1A 相同的逻辑（见 1A.7）生成 `image_prompt`、`video_prompt`、`grouping`，组装为完整 `storyboard.json`。`meta.source_type = "images"`。

---

### 1C: 分镜文档 → 解析

| 子场景 | 输入 | 处理 |
|--------|------|------|
| C1 文本脚本 | `序号｜画面｜运镜` 格式 | 直接解析分隔符 |
| C2 Excel | `.xlsx` | `openpyxl` 读取表格 |
| C3 Word | `.docx` | `python-docx` 提取文本/表格 |

解析后标准化为 storyboard.json，`meta.source_type = "storyboard_doc"`。

---

### 1D: 纯文本创意 → 展开构造

用户只给了创意描述（不是脚本格式），如："帮我做一个科技感片头，40秒"。

1. 分析意图：提取主题、风格、时长、段数
2. 展开为具体镜头列表（不具体时用千问协助）
3. 构造 storyboard.json，`meta.source_type = "text_prompt"`

---

### ⏸ 人工审核（阶段1 出口）

输出分镜摘要表格（中文提示词），**无明确指令时暂停**。

审核要点：image_prompt 侧重静态画面描述，video_prompt 侧重动态/运镜/特效/转场。两者有部分重叠正常，检查侧重点是否正确。

```
| # | 时间码 | 时长 | 内容简述 | vfx | transition(转场) | image_prompt（侧重静态） | video_prompt（侧重动态） |
|---|--------|------|---------|-----|------------------|----------------------|----------------------|
| 1 | 00:00:00-00:03:05 | 3.2s | 同心圆数据隧道 | 光晕扩散 | 爆炸式转场，隧道切换到数据核心 | 深蓝背景，蓝色同心圆轨道围绕中心亮点... | 光点沿圆形轨迹旋转，光晕脉动扩散，镜头缓慢推进... |
| 2 | 00:03:05-00:08:10 | 5.2s | 地球全球网络 | - | 平滑推移，数据核心过渡到地球 | 半透明蓝色地球悬浮深蓝空间... | 地球缓慢自转，轨道线流动，镜头环绕旋转... |
...
```

用户可：
- 通过（"继续""没问题""跳过""OK""可以"）→ 定稿，进入阶段2
- 提出修改（合并/拆分镜头、优化提示词、调整风格）→ 修改后定稿
- 只保留脚本不继续 → 流程结束

**跳过审核触发词**：`直接做完` `不用看脚本` `不用审核` `跳过审核` `跳过人工` `跳过脚本审核` `直接继续` `全部做完` `自动继续`

---

## 阶段2: 获取参考图

**目标**：基于定稿 storyboard.json，为每个镜头产出一张参考图 → `ref_frames/`。

### ⚠️ 跳过阶段2

若用户初始指令中包含以下关键词，**跳过整个阶段2**，直接从阶段1进入阶段3：

触发词：`文生视频` `不要参考图` `不用生图` `不用参考图` `不用截图` `纯文字生成` `text2video` `text to video` `不要图`

> 文生视频模式不需要参考图，2A/2B/2C 全部跳过。

---

根据**原始输入类型**选获取方式：

### 2A: 原始是视频 → 从原视频截帧 + 默认去水印

**2A.1 截帧**

根据定稿 storyboard 中每个镜头的起始时间码，提取 `start_time + 1s`：

```bash
ffmpeg -ss <start_time + 1s> -i <video> -vframes 1 -q:v 2 ref_frames/shot_01_original.jpg
```

**2A.2 默认去水印**（视频通常带水印，默认执行）

```bash
# 先获取原图比例
RATIO=$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height -of csv=p=0 shot_01_original.jpg \
  | awk -F',' '{printf "%.0f:%.0f\n", $1, $2}')

dreamina image2image \
  --images ref_frames/shot_01_original.jpg \
  --prompt "保持原图画面内容完全不变，去除图片中的水印、logo、字幕，画面清晰干净" \
  --ratio "$RATIO" \
  --resolution_type 2k \
  --model_version 5.0 \
  --poll 300
```

输出覆盖写入 `ref_frames/shot_01.jpg`。每个镜头只生成 1 张。

**多镜头去水印提交规则**（防命名错乱）：
- **每个镜头独立提交为一个后台任务**，绝不将多个镜头合并在同一个 shell 进程中并行提交
- dreamina 任务完成顺序 ≠ 提交顺序，先提交的未必先生成
- 每个任务的 task_id 必须与镜头编号一一绑定，下载时通过 task_id → shot_NN 映射，确保输出文件命名正确
- 禁止使用 `&` + `wait` 方式合并多个提交，因为合并后的 JSON 输出顺序不可控
- 正确做法：逐个提交 `run_in_background: true`，每个任务完成后立刻通过该 task_id 的输出文件提取 URL 下载，命名为对应的 `shot_NN.jpg`

> 仅当用户明确提出"不去水印""保留水印"时才跳过此步骤。

### 2B: 原始是图片 → 图片本身（默认不去水印）

图片文件直接复制/链接到 `ref_frames/shot_01.jpg`...

默认不去水印（用户提供的图片通常已处理过）。仅当用户明确提出"去水印""去除Logo"时才执行去水印，逻辑同 2A.2。

### 2C: 原始是文档/纯文本 → 文生图（默认）

⚠️ **默认用 dreamina text2image 为每个镜头生成参考图**。仅当用户明确提出"不用生图""不需要参考图"时才跳过。

直接使用 storyboard.json 中每个 shot 的 `image_prompt`（中文，已在阶段1由 Claude 生成）：

```bash
dreamina text2image \
  --prompt "<shot.image_prompt>" \
  --ratio <VIDEO_RATIO> \
  --resolution_type 2k \
  --model_version 5.0 \
  --poll 120
```

> `<VIDEO_RATIO>` 取阶段1 1A.1 计算的最接近预设比例（如 21:9、16:9 等）。

下载到 `ref_frames/shot_01.jpg`...

---

### 去水印统一模板

无论 2A 还是 2B，去水印使用同一提示词（中文，不描述原图内容）：

```
保持原图画面内容完全不变，去除图片中的水印、logo、字幕，画面清晰干净
```

图生图参数：比例按原图实际比例，2K 清晰度，每镜头只生成 1 张。

---

## 阶段2 出口：生图任务完整性检测 + 格式校验 + 人工审核

### 第零步：生图任务完整性检测（循环重试）

针对 2A（去水印）、2C（文生图）这类 dreamina 生图任务，**在校验前先循环检测**：

```
for shot in all_shots:
    if 需要生图(去水印或文生图):
        提交 dreamina 任务 → 记录 submit_id
    else:
        标记 ✅（直接截帧/复制，无需生图）

for shot in all_shots:
    while True:
        if shot 已标记 ✅:
            break
        status = dreamina query_result --submit_id=<id>
        if status == "success":
            下载 → 标记 ✅ → break
        elif status == "fail":
            重新提交 → 更新 submit_id → 继续循环
        else:
            等待 → 继续轮询
```

> ⚠️ **循环不设上限**，直到所有生图任务成功为止。确保在进入格式校验之前，所有参考图都已生成完毕。

### 第一步：格式校验

```
□ storyboard.json 存在？shots 非空？每个 shot 有 image_prompt 和 video_prompt？
□ ref_frames/ 存在？数量与 shots 一致？
```

校验完成后，**有明确跳过指令时不报告，直接进入阶段3**。无明确指令时才输出报告：

```
| # | 镜头时间 | 内容简述 | 参考图 | 有图 | 有image_prompt | 有video_prompt |
|---|---------|---------|--------|------|---------------|---------------|
| 1 | 00:00-00:03 | 同心圆数据隧道 | shot_01.jpg | ✅ | ✅ | ✅ |
| 2 | 00:03-00:08 | 地球全球网络 | shot_02.jpg | ✅ | ✅ | ✅ |
| 3 | 00:08-00:14 | 未来城市夜景 | shot_03.jpg | ❌ 缺失 | ✅ | ✅ |
| ... | ... | ... | ... | ... | ... | ... |
```

缺失项清晰列出，方便定位问题。

⚠️ **规则**：格式校验不通过**无论何时都暂停** → 根据报告定位缺失项 → 询问用户：返回补充 / 手动修正 / 跳过校验

### 第二步：人工审核图片质量

格式校验通过后，展示参考图列表，进入人工审核。**出口逻辑与阶段1相同**——无明确指令时暂停，有跳过触发词时直接进入阶段3。

| # | 镜头 | 参考图 | 内容简述 |
|---|------|--------|---------|
| 1 | 00:00-00:03 | shot_01.jpg | 同心圆数据隧道 |
| 2 | 00:03-00:08 | shot_02.jpg | 地球全球网络 |
| ... | ... | ... | ... |

用户可：
- 确认通过（"没问题""继续""OK"）→ 进入阶段3
- 要求修改某张图（"第N张重新生成""换一张"）→ 重新生成 → 再次审核
- 要求批量修改（"全部重新生成""换风格"）→ 回到 2C 重新执行

**跳过审核触发词**：`直接做完` `不用审核` `跳过审核` `跳过人工` `不用看` `直接继续` `全部做完` `自动继续`

---

## 阶段3: 生成

---

### 3.0 默认流程（无明确指令时）

若用户未指定后端/方式/参数，按以下默认值执行：

| 项目 | 默认值 |
|------|--------|
| 后端 | **Dreamina Web**（浏览器操控） |
| 生成方式 | 有参考图 → `image2video` / 无参考图（跳过阶段2）→ `text2video` |
| 单位 | **按单个分镜头逐一生成**，时长 = `shot.duration_sec` |
| 画幅 | 取阶段1计算的**最接近预设比例**（见 1A.1 比例映射表） |
| 分辨率 | 720p |
| 模型 | seedance2.0 |

**异常处理默认链**（逐镜头）：
1. 提交任务 → 监控 → 下载
2. 失败 → 同模型重试最多 3 次（上传失败/超时等瞬时错误）
3. 仍失败且非瞬时错误（审核拦截/内容策略等）→ 换 **Grok** 重试（不倒置提示词）
4. Grok 也失败 → 标记 `❌`，交由出口统一处理

---

### 3.0.1 积分阈值检查

生成前，估算总积分消耗：

```
总积分 = Σ(每个镜头的积分消耗)

Dreamina 积分估算（单次生成）：
  - text2video (4s): ~12 分
  - text2video (8s): ~24 分
  - image2video (4s): ~25 分
  - image2video (8s): ~50 分
```

| 总积分 | 行为 |
|--------|------|
| ≤ 1000 | 直接生成 |
| > 1000 | ⏸ 暂停，提示人工确认后再继续 |

> 若用户明确说"不管积分""直接生成"，跳过阈值检查。

---

### 3.1 生成模式

#### 模式 A: text2video（文生视频）

无参考图，纯提示词生成。适用场景：跳过阶段2 / 纯文本创意。

```bash
dreamina text2video \
  --prompt "<shot.video_prompt>" \
  --model_version <model> \
  --ratio <VIDEO_RATIO> \
  --video_resolution 720p \
  --duration <shot.duration_sec>
```

每个 shot 单独生成，时长 = `shot.duration_sec`。

#### 模式 B: image2video（图生视频）

有参考图 + 提示词生成。默认模式。

```bash
dreamina image2video \
  --image <ref_frames/shot_XX.jpg> \
  --prompt "<shot.video_prompt>" \
  --model_version <model> \
  --ratio <VIDEO_RATIO> \
  --video_resolution 720p \
  --duration <shot.duration_sec>
```

每个 shot 单独生成，时长 = `shot.duration_sec`。

#### 模式 C: multi image2video（多图生视频，仅分组时使用）

**仅当用户明确提出分组时触发**。如"按15秒分组生成"。

**分组逻辑**：
1. 按用户指定的时长上限（如 ≤15s），将连续镜头累加，直到下一镜头会使总时长超限则断开
2. 每组：收集组内所有镜头的参考图 + 融合 video_prompt
3. 时长 = 组内所有 shot 的 `duration_sec` 之和
4. 用 `multimodal2video` 传入多张参考图 + 融合提示词 + 组时长

**提示词融合规则**（核心）：

1. **时间轴分段**：按组内各镜头的累计时长，在提示词中用 `0-Xs：...` `X-Ys：...` 格式标明每个时间段对应的画面内容和运动方式
2. **组内转场写入**：组内各镜头之间的 transition 必须写入提示词，作为相邻时间段的衔接动作
3. **组间断点双向衔接**（关键）：
   - 分组断开处，前一组最后一个镜头的 transition 是**断开点**，这个转场动作需要在**两边各写一次**，保证两组视频可拼接：
     - **前一组结尾（出去）**：将最后一个镜头的 transition 写入该组提示词末尾，描述画面如何离开（如"镜头紧贴玻璃幕墙，穿越窗户进入室内"）
     - **后一组开头（进来）**：将**同一个 transition 的入境端**写入下一组提示词开头（0s位置），描述画面如何进入（如"从窗外穿梭进入室内，画面展开——指挥中心场景..."）
   - 两边描述的是**同一个转场动作**但视角不同（出 vs 入），确保生成的两段视频首尾能自然拼接
4. **首组例外**：第一组开头无需 entry transition（视频从该处自然起始）
5. **末组例外**：最后一组结尾按原始 transition 处理（如淡出/穿越光门/纯白结束），无需为衔接下一组做 exit action

**融合提示词格式模板**：
```
# 第一组（无 entry transition）
0-Xs：[镜头1内容+动态+运镜]
X-Ys：[镜头2内容+动态+运镜，组内转场]
Y-Zs：[镜头3内容+动态+运镜，组内转场]
Z-Ws：[末镜头内容+动态+运镜，结尾：disconnect_transition_exit]

# 中间组（有 entry + exit transition）
0s-开头：disconnect_transition_enter——[从上一组穿梭进入的画面描述]
0-Xs：[镜头1内容+动态+运镜]
X-Ys：[镜头2内容+动态+运镜，组内转场]
Y-Zs：[末镜头内容+动态+运镜，结尾：disconnect_transition_exit]

# 末组（有 entry transition，无 exit）
0s-开头：disconnect_transition_enter——[从上一组穿梭进入的画面描述]
0-Xs：[镜头1内容+动态+运镜]
X-Ys：[末镜头内容+动态+运镜，原始终止方式]
全局风格词，一镜到底，8K高清，无背景音乐，只需音效：{根据全组画面内容列出对应音效}。
```

```bash
dreamina multimodal2video \
  --image <ref_frames/shot_03.jpg> --image <ref_frames/shot_04.jpg> --image <ref_frames/shot_05.jpg> \
  --prompt "<融合后的 video_prompt>" \
  --model_version <model> \
  --ratio <VIDEO_RATIO> \
  --video_resolution 720p \
  --duration <组总时长>
```

> **grouping 仅在阶段3处理，且仅在用户明确说"分组""按Xs合并"时才执行。默认不分组。**

---

### 3.2 统一后端参数

Dreamina CLI 和 Dreamina Web 能力相同，仅操作方式不同：

| 参数 | Dreamina (CLI / Web) | Grok |
|------|---------------------|------|
| 模型 | seedance2.0 / fast | — |
| 画幅 | 1:1 / 3:4 / 16:9 / 4:3 / 9:16 / 21:9 | 2:3 / 3:2 / 1:1 / 9:16 / 16:9 |
| 分辨率 | 480p / 720p / 1080p | 480p / 720p |
| 时长 | 4s / 6s / 8s / 10s / 12s | 6s / 10s |
| text2video | ✅ | ✅ |
| image2video | ✅ | ✅ |

---

### 3.3 Dreamina CLI

顺序提交（一次一个任务），逐镜头处理：

```bash
# 提交
dreamina <subcommand> \
  --prompt "<prompt>" \
  [--image <ref_image> | --images <img1> <img2> ...] \
  --model_version <model> \
  --ratio <ratio> \
  --video_resolution <resolution> \
  --duration <duration>

# 监控
dreamina query_result --submit_id=<submit_id>

# 下载
curl -o <output_dir>/<shot_id>.mp4 "<video_url>" -L
```

`gen_status`: `querying`(+Queueing/Generating) → `success`(提取 video_url) / `fail`(记录 fail_reason)

---

### 3.4 Dreamina Web（默认后端）

Playwright CDP 浏览器自动化，控制 `dreamina.capcut.com` 国际版网页。参数与 CLI 一致，通过页面操作提交。

自动化脚本：`dreamina_web_automation.py`（本 skill 目录下），基于 `fast_telescope.py` 验证过的模式。

#### 前置条件

- Chrome 运行并开启 `--remote-debugging-port=9222`，使用非默认 `--user-data-dir`
- 用户需在 CDP Chrome 实例上**已登录** Dreamina 国际版
- 用 `ditto` 复制真实 Chrome profile 保留登录态：
  ```bash
  osascript -e 'quit app "Google Chrome"' 2>/dev/null; sleep 3
  ditto "$HOME/Library/Application Support/Google/Chrome" /tmp/chrome_full_profile
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --user-data-dir=/tmp/chrome_full_profile \
    --no-first-run --no-default-browser-check &
  ```
- Playwright Python: `pip install playwright`

#### WebSocket 自动检测

```python
import urllib.request, json
data = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5).read())
ws_url = data.get("webSocketDebuggerUrl")  # ws://127.0.0.1:9222/devtools/browser/...
```

#### 页面导航 + 模式切换

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(ws_url)
    context = browser.contexts[0]
    page = await context.new_page()
    # 必须带 ?type=video 才能获得完整 AI 影片 UI（含 combobox）
    await page.goto('https://dreamina.capcut.com/ai-tool/generate?type=video', wait_until='domcontentloaded')
    await asyncio.sleep(8)
```

**从 AI 代理切换到 AI 影片模式：**
```python
body = await page.evaluate('() => document.body.innerText')
if 'AI 影片' not in body:
    comboboxes = page.locator('[role="combobox"]')
    await comboboxes.nth(0).click()  # 第一个 combobox = 模式选择
    await asyncio.sleep(2)
    await page.locator('[class*="lv-select-option"]:has-text("AI 影片")').first.click()
    await asyncio.sleep(3)
```

#### 工具栏布局（从左到右，y≈708）

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

#### 选择模型（combobox index 1）

```python
comboboxes = page.locator('[role="combobox"]')
model_select = comboboxes.nth(1)  # 第二个 = 模型
await model_select.click()
await asyncio.sleep(2)

# 找到并点击 "Dreamina Seedance 2.0"（排除 Fast）
options = page.locator('[class*="lv-select-option"]')
for i in range(await options.count()):
    opt = options.nth(i)
    if await opt.is_visible():
        text = (await opt.inner_text()).strip()
        if text.startswith('Dreamina Seedance 2.0') and 'Fast' not in text[:30]:
            await opt.click()
            break
```

可用模型：
- Dreamina Seedance 2.0 Fast — 速度快、成本低
- **Dreamina Seedance 2.0 — 多模态参考（推荐）**
- Dreamina Seedance 1.5 Pro — 声音同步
- Dreamina Seedance 1.0 / 1.0 Fast / 1.0 Mini
- Sora 2

#### 选择时长（combobox index 3）

```python
dur_select = comboboxes.nth(3)  # 第四个 = 时长
await dur_select.click()
await asyncio.sleep(2)
dur_opt = page.locator(f'[class*="lv-select-option"]:has-text("{duration}s")').first
if await dur_opt.is_visible():
    await dur_opt.click()
```

可用时长：4s, 8s, 10s, 12s（因模型而异）

#### 选择画幅和分辨率

```python
# 点击 16:9 按钮（非 combobox）打开画幅+分辨率面板
ratio_btn = page.locator('button:has-text("16:9")').first
await ratio_btn.click()
await asyncio.sleep(2)
# 选择分辨率
await page.locator('text="1080P"').first.click()  # 或 "720P"
```

画幅：21:9, 16:9, 4:3, 1:1, 3:4, 9:16
分辨率：720P, 1080P

#### 上传参考图（支持多图）

文件 input 是隐藏的，用 `set_input_files`：
```python
file_input = page.locator('input[type="file"]').first
# 单图
await file_input.set_input_files(os.path.abspath(image_path))
# 多图（multi image2video / 全方位參考）
await file_input.set_input_files([os.path.abspath(p) for p in image_paths])
await asyncio.sleep(4)
# 验证：检查 blob 预览出现
blob_count = await page.locator('img[src*="blob"]').count()
```

#### 输入提示词

提示词区域是 `contenteditable` div（非 textarea）：
```python
editable = page.locator('[contenteditable="true"]').first
await editable.click()
await asyncio.sleep(0.5)
await editable.evaluate('el => el.innerText = ""')
await asyncio.sleep(0.3)
await editable.fill(prompt_text)
```

#### 提交生成

提交按钮是右下角白色圆形上箭头：
```python
submit = page.locator('button.lv-btn-primary.lv-btn-shape-circle.lv-btn-icon-only').last
if not await submit.is_disabled():
    await submit.click()
```
Submit 在图片+提示词都提供后才变为可用。

#### 等待生成完成

```python
while time.time() - start < timeout:
    videos = page.locator('video')
    for i in range(await videos.count()):
        src = await videos.nth(i).get_attribute('src')
        if src and ('capcut' in src or 'alisg' in src):
            return src  # 视频 URL，可以下载
    
    # 也检查下载按钮
    dl_btn = page.locator('text="下载"').first
    if await dl_btn.count() > 0 and await dl_btn.is_visible():
        return await page.locator('video').first.get_attribute('src')
    
    await asyncio.sleep(5)
```

#### 下载

```bash
curl -L -o "<output_path>" "<video_url>"
```

#### 积分消耗（Web UI，seedance2.0 系列）

| Model | 8s cost |
|-------|---------|
| Dreamina Seedance 2.0 Fast | ~152 |
| Dreamina Seedance 2.0 | ~192 |

#### 完整自动化脚本

见本 skill 目录下的 `dreamina_web_automation.py`，包含所有上述模式的端到端实现。

---

### 3.5 Grok（兜底后端）

Chrome CDP 9222 → navigate `grok.com/imagine` → imagine video → upload → prompt → submit → monitor → download。

**Grok 仅作为兜底**：Dreamina 反复失败（非瞬时错误）后才用 Grok 重试。默认不倒置提示词，仅当用户明确说"倒置""反转提示词""反向生成"时才调用 `prompt-optimizer` 倒置。

---

### 3.6 逐镜头重试 + 兜底链

```
for shot in shots:
    attempt = 0
    while attempt < 3:
        submit to Dreamina → monitor
        if success:
            download → mark ✅ → break
        elif fail_reason in [upload_timeout, network_error, transient]:
            attempt += 1  # 瞬时错误，同模型重试
        else:
            break  # 审核拦截/内容策略，跳出 Dreamina 循环
    
    if shot still failed:
        submit to Grok  # 兜底，不倒置提示词
        if success:
            download → mark ✅
        else:
            mark ❌
```

> **不倒置提示词**：默认不调 `prompt-optimizer` 倒置。仅用户明确指令中包含"倒置""反转提示词""反向生成"时才倒置后重试。

---

## 阶段3 出口：完成度校验 + 人工决策

全部提交处理完毕后，输出完成度报告：

| # | 镜头 | 时长 | 状态 | 文件 | 失败原因 |
|---|------|------|------|------|---------|
| 1 | 同心圆数据隧道 | 3.2s | ✅ | 01.mp4 (X MB) | - |
| 2 | 地球全球网络 | 5.2s | ❌ | - | Grok 也失败 |
| 3 | 未来城市夜景 | 4.0s | ✅ | 03.mp4 (X MB) | - |
| ... | ... | ... | ... | ... | ... |

- **全部成功** → 自动进入阶段4
- **有失败项** → ⏸ 暂停，列出失败原因，询问用户：

```
① 不管失败项，直接用已成功的视频拼接
② 调 prompt-optimizer 倒置提示词后用 Grok 再试一次
③ 手动修改提示词后重新生成失败项
```

用户选择后执行对应操作，最终进入阶段4。

---

## 阶段4: 拼接

### 拼接

```bash
echo "file '<output_dir>/01.mp4'
file '<output_dir>/02.mp4'..." > concat_list.txt
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy <combined>.mp4 -y
```

### 最终汇总

```
| # | 场景 | 时长 | 状态 | 文件 |
|---|------|------|------|------|
| 1 | 数据隧道 | 10s | ✅ | 01.mp4 (8.0MB) |
...
合并视频: combined.mp4 (42MB, 40.5s, 1280×720)
总消耗积分: 560
```

---

## 用户指令判断规则

1. **有明确指令**（"全部做完""不用看直接生成""做到拼接"）→ 严格按指令，不在中间询问
2. **无明确指令** → 每个阶段结束后询问
3. **例外**：以下情况无论何时都暂停：
   - 格式校验不通过（阶段2出口第一步）
   - 阶段3 积分阈值 > 1000（除非用户说"不管积分"）
   - 阶段3出口有失败项（Dreamina → Grok 全部失败）
4. **跳过阶段2**：用户指令含"文生视频""不要参考图"等 → 跳过阶段2，1→3

---

## 关键常量

```
DREAMINA = "/Users/aoki/.local/bin/dreamina"
DASHSCOPE_KEY = "sk-6c78b940401948cc82797d86074c95cb"
Qwen VL 模型 = "qwen3-vl-plus"       # 原生视频理解，256K上下文，32K+输出
Qwen VL 视频上传上限 = 1024           # SDK临时上传 max_file_size_mb，单位 MB
视频压缩阈值 = 300                    # 超过此值则压缩到该值以内
视频分辨率上限 = 720                   # 短边超过此值则缩到 720p
Dreamina 默认模型 = "seedance2.0"
参考帧截取偏移 = +1s
Dreamina Web 自动化脚本 = dreamina_web_automation.py  # 本 skill 目录下
Chrome CDP 端口 = 9222
```

## 相关 Skill

- `dreamina-batch`: 图片文件夹 → 千问分析 → dreamina 命令
- `grok-video-batch`: Grok 浏览器自动化
- `prompt-optimizer`: 提示词优化和倒置
- `dreamina-cli`: Dreamina CLI 基础操作
