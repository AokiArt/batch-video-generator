# Batch Video Generator / 批量视频生成

<p align="center">
  <b>AI Batch Video Generation — Claude Code Skill</b><br>
  <b>AI 批量视频生成 — Claude Code 技能</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/claude_code-skill-8A2BE2" alt="Claude Code Skill">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT">
  <img src="https://img.shields.io/badge/dreamina-v2.0-blue" alt="Dreamina 2.0">
</p>

---

## Overview / 概述

**EN** — A Claude Code skill for orchestrating batch AI video generation across multiple tools. Automatically selects the right engine based on your content and handles the full lifecycle: submission, monitoring, download, and failover retry.

**CN** — 一个 Claude Code 技能，用于在多个 AI 视频生成工具之间进行编排。根据内容自动选择最佳引擎，处理完整的生命周期：提交、监控、下载和故障切换重试。

### Three Modes / 三种模式

| Mode / 模式 | Purpose / 用途 | Engine / 引擎 |
|-------------|----------------|----------------|
| **A — Batch Generation / 批量生成** | Multiple independent prompt+image → video / 多个独立提示词+图片生成视频 | Dreamina CLI / Grok browser |
| **B — Storyboard Script / 分镜脚本** | Scripted multi-scene → sequential video → concatenation / 多场景脚本→顺序生成→拼接 | Dreamina CLI |
| **C — Dreamina Intl. Web / 国际版网页** | Web UI automation via Playwright CDP / 通过 Playwright CDP 自动化网页操作 | dreamina.capcut.com |

---

## Features / 功能特性

- **Multi-engine orchestration / 多引擎编排** — Automatically routes between Dreamina CLI, Grok, and Dreamina International Web / 自动在 Dreamina CLI、Grok 和国际版网页之间路由
- **Smart failover / 智能故障切换** — Detects failures and retries with the alternative tool / 检测失败并使用另一工具自动重试
- **Prompt inversion / 提示词倒置** — Optional semantic inversion for failed tasks / 可选地对失败任务进行语义倒置处理
- **Storyboard-to-video / 分镜转视频** — Parse formatted scripts, generate sequentially, concatenate with ffmpeg / 解析格式化脚本，顺序生成，用 ffmpeg 拼接
- **Automated monitoring / 自动监控** — Polls generation status, downloads on completion / 轮询生成状态，完成后自动下载
- **Credit management / 积分管理** — Checks available credits before starting / 开始前检查可用积分
- **Web automation / 网页自动化** — Full Playwright CDP-based control of dreamina.capcut.com / 基于 Playwright CDP 的完整网页控制

---

## Quick Start / 快速开始

### Prerequisites / 前置条件

- Claude Code CLI
- [Dreamina CLI](https://dreamina.cn/) installed at `~/.local/bin/dreamina`
- (Optional) Google Chrome with `--remote-debugging-port=9222` for Mode C / 用于模式 C
- (Optional) Python 3 + Playwright for Grok automation / 用于 Grok 自动化

### Installation / 安装

**Option 1: Claude Code plugin / 通过插件安装**

```bash
claude plugin add batch-video-generator
```

**Option 2: Manual install / 手动安装**

```bash
cd ~/.claude/skills/
git clone https://github.com/527998482-jpg/batch-video-generator.git
```

---

## Usage Guide / 使用指南

### Mode A: Batch Generation / 批量生成

**EN** — Use when you have a list of prompts ± reference images and want to generate multiple independent videos.

**CN** — 当你有多个提示词（及可选的参考图片）并希望批量生成视频时使用。

**Workflow / 工作流程:**
1. Choose tool (Dreamina or Grok) and confirm specs / 选择工具并确认参数
2. Submit all tasks in parallel / 并行提交所有任务
3. Monitor until completion (polling every 60s) / 监控至完成（每 60 秒轮询）
4. Download results + retry failures with the other tool / 下载结果 + 用另一工具重试失败任务

### Mode B: Storyboard Script / 分镜脚本

**EN** — Use when you have a formatted script with numbered scenes and want one combined video.

**CN** — 当你有带编号场景的格式化脚本，并希望生成一个合并视频时使用。

```
01｜Waterfall cascading, mist rising｜Push up from low-angle mountain view
02｜Sunlight piercing canopy, god rays｜Pan right across the forest
```

**Workflow / 工作流程:**
1. Parse storyboard / 解析分镜脚本
2. Submit tasks one-at-a-time (Dreamina limit: 1 concurrent) / 逐一提交任务
3. Download each as it completes, named `01.mp4`, `02.mp4`... / 完成后逐个下载
4. Concatenate all via ffmpeg stream copy / 用 ffmpeg 流复制拼接

### Mode C: Dreamina International Web / 国际版网页

**EN** — Use when your account works on the web UI but not via CLI (e.g., artisan accounts).

**CN** — 当你的账号在网页端可用但 CLI 不行时使用（如 artisan 账号）。

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 --user-data-dir=/tmp/chrome_profile &
```

**Workflow / 工作流程:**
1. Connect via Playwright `connect_over_cdp()` / 通过 CDP 连接浏览器
2. Navigate to dreamina.capcut.com / 导航到 Dreamina 国际版
3. Upload reference image, set model/duration/ratio / 上传参考图，设置模型/时长/画幅
4. Submit and monitor until video ready / 提交并监控至视频生成完成

---

## File Structure / 文件结构

```
batch-video-generator/
├── SKILL.md                # Skill definition / 技能定义
├── README.md               # Documentation (this file) / 说明文档
├── dreamina_monitor.py     # Polling & download automation / 轮询下载自动化
└── LICENSE                 # MIT license / 许可证
```

---

## Configuration Reference / 参数配置

### Dreamina CLI Parameters

| Parameter / 参数 | Options / 选项 | Default / 默认 | Notes / 说明 |
|----------------|----------------|----------------|--------------|
| model_version | seedance2.0_vip / seedance2.0 / seedance2.0fast | seedance2.0 | _vip = highest quality / 最高质量 |
| ratio / 画幅 | 1:1 / 3:4 / 16:9 / 4:3 / 9:16 / 21:9 | 16:9 | Depends on subcommand / 取决于子命令 |
| duration / 时长 | 4–15 (seconds / 秒) | 5 | Per model limit may vary / 各模型可能不同 |
| resolution / 分辨率 | 720p | 720p | seedance2.0 series only |
| subcommand / 子命令 | multimodal2video / text2video / image2video | — | Depends on input type / 取决于输入类型 |

### Dreamina International Web Parameters

| Parameter / 参数 | Options / 选项 |
|----------------|----------------|
| Model / 模型 | Dreamina Seedance 2.0 / 2.0 Fast / 1.5 Pro / 1.0 / Sora 2 |
| Duration / 时长 | 4s / 8s / 10s / 12s |
| Aspect Ratio / 画幅 | 21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16 |
| Resolution / 分辨率 | 720P / 1080P |
| Credit Cost (8s) / 积分消耗 | ~152 (Fast) / ~192 (Standard) |

### Grok Parameters

| Parameter / 参数 | Options / 选项 |
|----------------|----------------|
| Duration / 时长 | 6s / 10s |
| Resolution / 分辨率 | 480p / 720p |
| Aspect Ratio / 画幅 | 2:3 / 3:2 / 1:1 / 9:16 / 16:9 |

---

## Tool Selection Guide / 工具选择指南

| Scenario / 场景 | Recommended / 推荐工具 | Reason / 原因 |
|----------------|----------------------|--------------|
| Creative content / 创意内容 | Dreamina CLI | Faster, lower cost / 更快、成本更低 |
| Sensitive / historical content / 敏感/历史内容 | Grok | Lighter moderation / 审核更宽松 |
| CLI auth failing / CLI 无法登录 | Dreamina Intl. Web | Web UI alternative / 网页端替代方案 |
| Multi-scene storyboard / 多场景分镜 | Dreamina CLI | Sequential + ffmpeg concat / 顺序提交+拼接 |
| Maximum quality / 最高质量 | Dreamina seedance2.0_vip | Best output quality / 最佳输出质量 |

---

## Troubleshooting / 常见问题

| Issue / 问题 | Solution / 解决方法 |
|-------------|-------------------|
| `ExceedConcurrencyLimit` | Dreamina allows 1 task at a time. Submit sequentially. / 每次只能提交一个任务，请逐一提交 |
| `post-TNS check did not pass` | Content blocked. Try Grok or invert prompts. / 内容被拦截，尝试 Grok 或倒置提示词 |
| WebSocket connection failed | Ensure Chrome is running with `--remote-debugging-port=9222` / 确保 Chrome 已开启远程调试端口 |
| Queue stuck / 队列卡住 | Advances ~65 positions/min. Wait patiently. / 每分钟前进约 65 位，请耐心等待 |
| Download timeout / 下载超时 | Retry; Grok can use CDP base64 pipe fallback / 重试，Grok 可用 CDP base64 管道下载 |

---

## License / 许可证

MIT — see [LICENSE](LICENSE) / 详见 [LICENSE](LICENSE).
