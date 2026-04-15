# MiniMax 音乐生成原型设计

## 目标

验证 MiniMax 音乐生成 API 能否替代 clef 多 agent 管线的 create+iterate 阶段。原型是一个独立 Python 脚本，从用户文字描述（或已有 plan.json）出发，经过 clef planner 生成结构化规划，再调用 MiniMax API 生成完整音乐。

## 背景

clef 多 agent 管线（Composer → Harmonist → Rhythmist → Leader → Reviewer → Orchestrator）链路长、Bug 多、对低成本模型（DeepSeek/GLM）的音乐判断力要求高。MiniMax music-2.6 模型直接生成高质量音频，跳过 ABC→MIDI→SF2 合成链路，可大幅简化管线。

Sample 阶段（方向小样）已验证稳定，plan.json 的结构化规划（调性、风格、段落、乐器）质量可靠。原型保留 clef 的规划能力，用 MiniMax 替代创作和迭代。

## 架构

```
用户文字描述
    │
    ▼
clef planner prompt → LLM → plan.json（复用现有规划能力）
    │
    ├──────────────────────┐
    ▼                      ▼
mode=text              mode=cover
plan → MiniMax prompt  plan → MiniMax prompt
is_instrumental=true   + sample_r0.mid → wav → base64
    │                      │
    ▼                      ▼
MiniMax music-2.6-free  MiniMax music-cover-free
    │                      │
    ▼                      ▼
minimax_text.mp3        minimax_cover.mp3
```

## 组件

### 1. Prompt 构造器：plan → MiniMax prompt

从 plan.json 提取以下字段拼成中文 prompt 字符串（MiniMax 对中文 prompt 支持更好）：

- `genre` / `style`：音乐风格
- `mood` / `emotion`：情绪
- `tempo` / `bpm`：速度描述（"快板"、"中板"等）
- `instrumentation`：主要乐器
- `form`：曲式（ABA、ABABC 等）

输出示例：`"轻快乡村风格, 明亮活泼, 吉他和口琴为主, 中板节奏"`

### 2. Plan 生成器（模式 A）

当用户提供 `--prompt` 文字描述时，复用 clef 现有的 planner prompt 模板，调用 LLM 生成 plan.json。

具体做法：
- 读取 `server/config/providers.yaml` 获取 provider 配置（API base、key、model）
- 构造精简版 prompt，要求 LLM 输出和 clef 管线一致的 plan.json 结构（key/scale/bpm/form/sections/orchestration/style/mood）
- 默认使用 providers.yaml 中第一个可用 provider
- 将生成的 plan.json 保存到输出目录

plan.json 结构保持和 clef 管线一致，方便后续对比。

### 3. 参考音频转换（cover 模式）

当 `--mode cover` 或 `--mode both` 时：
1. 检查用户指定的 `--reference` 路径，或自动查找 `sample_r0.wav`/`sample_r0.mp3`（优先直接可用的音频文件）
2. 如果只有 MIDI 文件（`.mid`），复用 clef 现有的 `clef_tools.py midi-to-audio` 子命令（底层 FluidSynth + SF2）将 MIDI 转为 WAV
3. 读取音频文件并 base64 编码（WAV 或 MP3 均可，MiniMax 两者都支持）

如果参考音频不存在或转换失败，自动降级为 text 模式并打印警告。

### 4. API 调用

**text 模式**（`music-2.6-free`）：
```json
{
  "model": "music-2.6-free",
  "prompt": "<构造的中文 prompt>",
  "is_instrumental": true,
  "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"}
}
```

**cover 模式**（`music-cover-free`）：
```json
{
  "model": "music-cover-free",
  "prompt": "<构造的中文 prompt，描述目标翻唱风格>",
  "audio_base64": "<参考音频 base64>",
  "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"}
}
```

### 5. 结果保存

- API 返回 `data.audio` 为 hex 编码的音频数据
- 解码 hex → 二进制，保存为 mp3 文件
- 同时打印 `extra_info` 中的时长、采样率等信息

## 脚本接口

```bash
# 端到端：文字 → plan → 音乐
python scripts/minimax_prototype.py \
  --prompt "轻快的乡村风格，吉他为主，30秒左右" \
  --mode both \
  --api-key $MINIMAX_API_KEY

# 使用已有 plan.json
python scripts/minimax_prototype.py \
  --plan .clef-work/plan.json \
  --mode text \
  --api-key $MINIMAX_API_KEY

# cover 模式，指定参考音频
python scripts/minimax_prototype.py \
  --plan .clef-work/plan.json \
  --mode cover \
  --reference .clef-work/sample_r0.wav \
  --api-key $MINIMAX_API_KEY
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--prompt` | 二选一 | 用户文字描述，会触发 plan 生成 |
| `--plan` | 二选一 | 已有 plan.json 路径，跳过规划 |
| `--mode` | 否 | `text`（默认）/ `cover` / `both` |
| `--reference` | 否 | 参考音频路径（cover 模式），默认自动查找 |
| `--api-key` | 是 | MiniMax API Key |
| `--output-dir` | 否 | 输出目录，默认当前目录 |

### 输出文件

- `minimax_text_output.mp3` — text 模式产出
- `minimax_cover_output.mp3` — cover 模式产出
- `plan.json` — 生成的规划文件（`--prompt` 模式时）

## 文件结构

```
scripts/
  minimax_prototype.py    # 单文件原型脚本（~200 行）
```

## 依赖

- Python 3.11+
- `requests`（HTTP 调用，`pip install requests`）
- `pyyaml`（读取 providers.yaml，`pip install pyyaml`）
- clef 现有工具链（`clef_tools.py midi-to-audio`，cover 模式需要，已有 FluidSynth 支持）
- 标准 JSON/argparse/base64

## 不在范围内

- 不修改 server 代码
- 不修改 clef 现有 agent/skill
- 不做音频后处理（不反算回 ABC/MIDI）
- 不做批量测试或自动化评估
- 不做 Web UI
