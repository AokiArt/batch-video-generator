# Batch Video Generator V2 — 批量 AI 视频生成管道

**版本**: 2.0 | **更新**: 2026-05-20

四段式 AI 视频生成管道，输入可以是视频/图片/文档/文本，产出拼接完成的视频文件。

```
用户输入
  │
  ▼
阶段1: 获取分镜头脚本 → ⏸ 人工确认
  │
  ▼ storyboard.json
阶段2: 获取参考图 → ⏸ 人工审核
  │
  ▼ ref_frames/
阶段3: 生成视频（内部重试 + Grok 兜底）
  │
  ▼ 全部生成完毕
阶段4: ffmpeg 拼接 → 最终视频
```

---

## 核心数据格式

### storyboard.json

阶段1 产出，阶段2/3 消费的统一分镜头数据格式。

```json
{
  "overview": {
    "title": "视频标题",
    "script": "全局叙事结构",
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
      "colors": "色调光影（光源方向+光照情况+明暗对比）",
      "content": "中文画面详细描述",
      "dynamics": "动态元素描述",
      "vfx": "视觉特效（粒子/光效/烟雾等）",
      "camera_movement": "运镜方式",
      "transition": "转场描述（最后一个为空）",
      "image_prompt": "Claude生成的图片提示词（侧重静态）",
      "video_prompt": "Claude生成的视频提示词（侧重动态）"
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

### raw_analysis.json / ref_frames/

- `raw_analysis.json` — 千问 VL 原始输出，仅含描述字段，不含 prompts
- `ref_frames/` — 每个镜头一张参考图，命名 `shot_01.jpg` ...

---

## 阶段1: 获取分镜头脚本

| 输入类型 | 处理方式 |
|---------|---------|
| **1A: 视频** | ffprobe → 智能压缩 → 千问 VL 分析 → raw_analysis.json → Claude 生成完整 storyboard |
| **1B: 图片** | 有模板→千问填充 / 无模板→询问用户，Claude 构建 storyboard |
| **1C: 文档** | 文本/Excel/Word 解析 → 标准化 storyboard |
| **1D: 纯文本** | 分析意图 → 展开镜头 → 构造 storyboard |

**出口**: 人工审核，9 个跳过触发词可全自动。

---

## 阶段2: 获取参考图

| 原始类型 | 获取方式 |
|---------|---------|
| **2A: 视频** | 截帧 + 默认去水印 |
| **2B: 图片** | 直接作为参考帧 |
| **2C: 文档/文本** | dreamina text2image 文生图 |

**出口**: 循环检测全部完成 → 格式校验 → 人工审核。8 个跳过触发词。

---

## 阶段3: 生成视频

| 参数 | 默认值 |
|------|--------|
| 后端 | Dreamina Web |
| 模式 | image2video / text2video |
| 模型 | seedance2.0 |
| 画幅 | 16:9 |
| 分辨率 | 720p |

**兜底链**: Dreamina 失败 → 重试 3 次 → Grok 兜底 → ❌

---

## 阶段4: 拼接

```bash
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy combined.mp4 -y
```

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Skill 主文件，给 Claude 执行用的完整指令 |
| `README.md` | 本文档 |
| `dreamina_web_automation.py` | Dreamina 国际版 Web 自动化脚本（Playwright CDP） |

---

## 相关 Skill

- `dreamina-cli` / `grok-video-batch` / `prompt-optimizer` / `dreamina-batch`
