# ChatMusician 混合模式设计方案

**日期**: 2026-04-02
**状态**: 已确认，待实施
**目标**: 在 clef 中引入 ChatMusician 本地 LLM，作为高级付费特性，支持混合模式作曲

## 1. 背景与动机

### ChatMusician 简介
- 基于 LLaMA2-7B 微调的音乐 LLM（ACL 2024 Findings）
- 核心能力：通过 ABC 记谱法理解和生成音乐，无需多模态组件
- 支持和弦条件生成（`[CHORD] → [MELODY]`），超越 GPT-4 的符号音乐生成能力
- Q4_K_M 量化 GGUF 格式，约 4GB，可本地推理

### 能力画像

| 强项 | 弱项 |
|------|------|
| 和弦条件旋律生成 | 风格偏向爱尔兰音乐（训练数据偏差） |
| 旋律→和声生成 | 存在幻觉，格式可能出错 |
| 文字描述→音乐 | 仅支持严格格式的封闭指令 |
| 基于动机/主题发展 | 音乐推理能力有限 |
| 超越 GPT-4 符号音乐生成 | 长篇幅结构连贯性不足 |

### 集成定位
ChatMusician 作为**独立高级模式**引入，与现有纯 Claude Agent 模式并存。通过 `/clef-compose --mode hybrid` 参数切换。

## 2. 许可证合规

ChatMusician 基于 LLaMA2-7B 微调，自动继承 [LLaMA2 Community License Agreement](https://ai.meta.com/llama/license/)（非开源，商业合同性质）。

### 商用条件

| 条件 | 说明 |
|------|------|
| MAU < 7 亿 | 独立开发者/小团队自动满足，门槛针对 Meta 级巨头 |
| 不违反 AUP | 游戏/音乐生成属于允许用途 |
| 保留 LLaMA2 许可证 | 不可改为 MIT/Apache，产品中需附带声明 |
| 许可证不可转让 | 终端用户也受 LLaMA2 条款约束 |
| AUP 可单方变更 | Meta 有权随时修改使用政策，需持续关注 |

### 风险提示

- Meta 可因违反条款终止许可（非传统开源许可的保护）
- 许可证具有传染性——下游用户也需同意 LLaMA2 条款
- 如需法律确定性，建议咨询专业律师

### 合规要求

- itch.io 产品页附带 LLaMA2 Community License 全文链接和声明
- 安装包内包含 `LICENSE-LLaMA2.txt` 文件
- 首次启动时展示简短许可摘要，用户确认后继续

## 3. 整体架构

### 3.1 双模式设计

| | 纯 Agent 模式 | 混合模式（高级） |
|---|---|---|
| 依赖 | Claude API | 本地 ChatMusician + Claude API |
| 旋律生成 | Claude Composer | ChatMusician 本地快速生成 |
| 编配与迭代 | Claude Agent 体系 | Claude Agent 体系（不变） |
| 迭代中重新生成 | Composer 重写 | ChatMusician 基于反馈重新生成 |
| 质量 | 高 | 高 |
| 成本 | API 费用 | API 费用（减少） |
| 速度 | 慢（多轮 API） | 中等（本地生成 + API 编配） |

### 3.2 核心策略
**ChatMusician 作为灵感引擎，Claude Agent 作为质量守门人**：
- ChatMusician 做最擅长的事：和弦条件旋律生成
- Claude Agent 弥补弱点：格式修正、风格纠正、评审打磨

### 3.3 优雅降级机制

混合模式在以下场景自动回退到纯 Agent 模式，确保用户永远不会卡住：

| 触发条件 | 降级行为 | 用户提示 |
|----------|---------|---------|
| ChatMusician server 启动失败（超时 60s） | 回退纯 Agent 模式 | "本地模型启动失败，已切换为云端 AI 模式" |
| ChatMusician server 运行时崩溃 | 回退纯 Agent 模式 | "本地模型运行中断，已切换为云端 AI 模式" |
| VRAM 检测 < 4 GB（无法运行） | 直接使用纯 Agent 模式 | "显存不足，已使用云端 AI 模式" |
| 连续 3 次 regenerate 输出均被 Revision 判定为格式错误 | 回退纯 Agent 模式 | "本地模型输出不稳定，已切换为云端 AI 模式" |
| 单次生成超时（>120s） | 重试 1 次，仍超时则回退 | "本地模型响应超时，已切换为云端 AI 模式" |

实现要求：
- `chatmusician_server.py` 的 `start()` 和 `generate()` 返回 Result 类型（`Ok(value)` / `Err(fallback_reason)`）
- `clef_tools.py` 的 `chatmusician generate/regenerate` 命令返回退出码 `2` 表示需要回退
- Skill 层（clef-composer.md）检查退出码，收到 `2` 时切换为 Claude Composer 生成

### 3.4 目录结构

```
addons/clef/
├── chatmusician/                    # 新增模块
│   ├── chatmusician_server.py       # llama.cpp 进程管理
│   ├── chatmusician_client.py       # OpenAI-compatible API 封装
│   ├── chatmusician_prompt.py       # Prompt 模板
│   ├── chatmusician_config.py       # 配置管理
│   └── model/                       # GGUF 模型（symlink 或复制自 E:\GitHub\ChatMusician\）
│       └── ChatMusician.Q4_K_M.gguf  # 源文件位于 E:\GitHub\ChatMusician\
├── llamacpp/                        # llama.cpp 二进制（按平台分发）
│   ├── windows/
│   │   └── llama-server.exe
│   └── linux/
│       └── llama-server
├── scripts/                         # 现有工具链（不变）
├── player/                          # 现有播放引擎（不变）
└── ui/                              # 现有 UI（不变，零 UI 改动）
```

Godot 插件端零改动，全部新增代码在 Python 层和 Skill 层。

## 4. VRAM 需求与推理策略

### VRAM 用量分析

LLaMA2-7B 使用 MHA（32 KV heads，非 GQA），KV cache 较大。Q4_K_M 量化下：

| 组件 | 计算依据 | 大小 |
|------|----------|------|
| 模型权重 | 7B × ~0.64 bytes/param (Q4_K_M) | ~4.4 GB |
| KV Cache（单请求） | 2 × 32层 × 32 heads × 128 dim × 4096 ctx × 2B (FP16) | ~2.0 GB |
| CUDA 运行时开销 | activations / allocator | ~0.5 GB |
| **单请求合计** | | **~6.9 GB** |
| 每增加并行请求 | 独立 KV cache | **+2.0 GB** |

### 推理策略：默认串行生成

| 模式 | 并行槽数 | VRAM 需求 | 适用 GPU |
|------|---------|-----------|---------|
| 串行（默认） | 1 | ~6.9 GB | 8 GB+ |
| 2 并行 | 2 | ~8.9 GB | 10 GB+ |
| 3 并行 | 3 | ~10.9 GB | 12 GB+ |

**设计决策：默认串行生成**（`-np 1`），3 个候选逐个生成（总计 30-90 秒），原因：
- 大多数消费级显卡为 8GB，无法承载并行
- 作曲场景无需实时响应，串行延迟可接受
- 通过配置允许高端用户启用并行

### GPU Offload 降级策略

VRAM 不足时自动减少 GPU offload 层数：

| 配置 | GPU VRAM | 推理速度 | 适用场景 |
|------|----------|---------|---------|
| `n_gpu_layers=-1`（全 GPU） | ~6.9 GB | ~30 tok/s | 8 GB+ GPU |
| `n_gpu_layers=20`（62% GPU） | ~4.5 GB | ~5-10 tok/s | 6 GB GPU |
| `n_gpu_layers=0`（纯 CPU） | ~0.5 GB | ~1-3 tok/s | 无 GPU / 集显 |

> 注意：部分 offload 引入 PCIe 传输瓶颈，速度显著下降。

## 5. Python 集成层

### 5.1 配置管理（chatmusician_config.py）

```python
CHATMUSICIAN = {
    "model_path_dev": "E:/GitHub/ChatMusician/ChatMusician.Q4_K_M.gguf",  # 开发环境
    "model_path_prod": "addons/clef/chatmusician/model/ChatMusician.Q4_K_M.gguf",  # 生产环境
    "server_bin": "addons/clef/llamacpp/{platform}/llama-server{ext}",
    "host": "127.0.0.1",
    "port": 8080,
    "port_range": (8080, 8090),  # 端口冲突时自动尝试范围内的下一个端口
    "n_ctx": 4096,
    "n_gpu_layers": -1,     # -1=全部GPU, 0=纯CPU（启动时自动检测降级）
    "temperature": 0.8,
    "top_p": 0.9,
    "max_tokens": 2048,
    "candidates": 3,        # 生成候选数量
    "parallel_slots": 1,    # 并行槽数（默认1=串行，需12GB+才建议改为3）
    "max_regenerate": 10,   # Step 1c 候选重新生成上限
    "generation_timeout": 120,  # 单次生成超时（秒）
}
```

### 5.2 进程管理（chatmusician_server.py）

| 方法 | 功能 |
|------|------|
| `detect_vram()` | 检测 GPU VRAM，返回建议的 `n_gpu_layers` 和 `parallel_slots` |
| `start()` | 根据 `detect_vram()` 结果配置参数，启动 llama.cpp server 子进程 |
| `stop()` | 优雅终止进程 |
| `is_ready()` | 健康检查 |
| `get_status()` | 返回状态（未启动/启动中/就绪/错误） |

**VRAM 自动降级逻辑**（`detect_vram()`）：
- VRAM ≥ 12 GB → `n_gpu_layers=-1`, `parallel_slots=3`
- VRAM ≥ 8 GB → `n_gpu_layers=-1`, `parallel_slots=1`（默认）
- VRAM ≥ 6 GB → `n_gpu_layers=20`, `parallel_slots=1`
- VRAM < 6 GB → `n_gpu_layers=0`（纯 CPU），警告用户速度较慢

使用 `subprocess.Popen` 后台管理，不阻塞 Godot。

**端口冲突处理**：启动时检测 8080 端口是否被占用，若被占用则尝试 `port_range`（8080-8090）中的下一个可用端口。`chatmusician_client.py` 读取 server 实际绑定端口（通过 `server.pid` 文件或 stdout 解析），不使用硬编码端口。

### 5.3 API 封装（chatmusician_client.py）

使用 `openai` 库指向本地 llama.cpp server：

```python
client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="not-needed")

def generate_melody(chords, key, meter, style_hint="") -> list[str]:
    """生成 N 个旋律候选，返回 ABC 片段列表"""

def regenerate_melody(chords, key, meter, feedback, current_abc="") -> str:
    """基于反馈重新生成旋律，返回单个 ABC 片段"""
```

### 5.4 Prompt 模板（chatmusician_prompt.py）

基于论文稳定 prompt 格式，封装三种模板：
- `chord_to_melody(chords, key, meter, style)` — 主力模板
- `melody_harmonize(melody_abc, key)` — 辅助模板
- `motif_develop(motif_abc, form)` — 扩展模板

每个模板包含 1-2 个 few-shot 示例引导输出质量。

### 5.4.1 ABC 格式适配层

ChatMusician 输出的 ABC 可能与 clef 现有 score.abc 格式存在差异，需在 `chatmusician_client.py` 中做适配：

| 差异项 | ChatMusician 输出 | clef 要求 | 适配处理 |
|--------|-----------------|-----------|---------|
| 声部标签 | `V: 1`（有空格） | `V:1`（无空格） | `V: *` → `V:{number}` |
| 节拍线 | 可能省略 `\|` | 每小节必须有 `\|` | 根据 meter 自动补全 |
| 重复记号 | `\|:\|` 自由使用 | 需与 plan.json form 一致 | 后处理统一 |
| 装饰音 | `~` `.` 等 | 支持，但频率需控制 | 保留，validate 检查 |
| 调号标记 | `K:C` / `K:Cmaj` | `K:C` 标准格式 | 统一为短格式 |

适配函数 `normalize_abc(abc_str: str, plan: dict) -> str` 在 `generate_melody()` 返回前自动调用。

### 5.5 clef_tools.py 新增子命令

| 子命令 | 功能 |
|--------|------|
| `chatmusician start` | 启动 server |
| `chatmusician stop` | 停止 server |
| `chatmusician status` | 查询状态 |
| `chatmusician generate` | 初稿生成（Step 1b，3 候选） |
| `chatmusician regenerate` | 迭代中重新生成（Step 2b，1 个，带反馈） |

## 6. 混合模式工作流

### 模式切换

```
/clef-compose [需求描述]
  --mode agent    # 纯 Agent 模式（默认）
  --mode hybrid   # 混合模式
```

### 完整流程

```
Step 0:   需求解析（不变）

Step 0.5: 模式选择
          ├── agent → 走现有 Step 1a-3
          └── hybrid → 走以下流程

Step 1a:  plan.json（复用现有）
          Leader 解析需求 → 和弦进行、调号、速度、结构等

Step 1b:  ChatMusician 灵感生成（新增）
          ├── chatmusician generate(chords, key, meter, style)
          ├── 生成 3 个旋律候选（串行，每候选 ~10-30秒，总计 ~30-90秒）
          └── 输出: {name}_candidate_1/2/3.mid

Step 1c:  用户确认
          ├── 告知用户在 Godot 中试听 3 个候选 MIDI
          ├── 用户选择一个（或要求重新生成，上限 10 次）
          ├── 达到上限时提示用户从已有候选中选择或手动编辑
          └── 确认后进入 Step 2a

Step 2a:  完整编配
          ├── Harmonist 基于选中旋律生成和声 V:2
          ├── Rhythmist 生成低音 V:3 + 鼓 V:4
          └── 合并为完整 score.abc

Step 2b:  Leader 迭代（修改）
          ├── validate → revision → review（现有）
          └── 旋律维度 (melody) 评分 < 7.0 且非格式问题时：
               ├── 从 review_report.json 提取旋律相关问题 → 构造反馈
               ├── ChatMusician regenerate(current_abc, feedback)
               ├── 替换 score.abc 旋律声部 → validate → review
               └── 仍不达标则回退 Claude Composer 修改
          安全限制：每轮最多重新生成1次，总迭代上限3轮

Step 3:   表现力注入（复用现有）
```

### 与纯 Agent 模式对比

| 步骤 | 纯 Agent | 混合模式 |
|------|---------|---------|
| 1a plan | Claude | Claude |
| 1b 旋律生成 | Claude Composer | ChatMusician 本地 |
| 1c 用户确认 | 方向小样 | 3 候选 MIDI 试听 |
| 2a 编配 | Composer+Harmonist+Rhythmist | Harmonist+Rhythmist |
| 2b 迭代 | 同 | 新增 ChatMusician 重新生成 |
| 3 表现力 | 同 | 同 |

## 7. Skill 层修改

### SKILL.md
- 新增 `--mode` 参数说明
- 新增 Step 0.5 模式选择步骤

### clef-composer.md
- 混合模式下角色变为 "ChatMusician prompt 构造器 + 候选筛选器"
- 新增：构造 ChatMusician prompt 的指令
- 新增：解析 ChatMusician 输出、提取 ABC 的指令

### clef-leader.md
- 新增混合模式调度规则
- 新增迭代中 ChatMusician 重新生成的判断逻辑和触发条件

### 其他 Agent
Harmonist、Rhythmist、Orchestrator、Reviewer、Revision — 无需修改。

### 7.1 ChatMusician 反馈构造逻辑

当 Step 2b 触发 ChatMusician 重新生成时，从 `review_report.json` 的六个维度中提取与旋律相关的问题，映射为 ChatMusician 可理解的反馈 prompt。

#### 维度→反馈映射规则

仅 `melody` 维度直接触发 ChatMusician regenerate；其他维度的问题由对应 Claude Agent 处理。

| review 维度 | 权重 | 是否触发 ChatMusician | 反馈构造方式 |
|-------------|------|----------------------|-------------|
| melody（旋律质量） | 0.30 | **是**，score < 7.0 时触发 | 从 M1-M6 子检查提取具体问题（见下方） |
| harmony（和声质量） | 0.20 | 否 | → clef-harmonist |
| rhythm（节奏质量） | 0.16 | 否 | → clef-rhythmist |
| structure（结构质量） | 0.13 | 仅当结构问题导致旋律需重写时 | 附加结构约束到 feedback |
| style（风格一致性） | 0.11 | 仅当风格偏差来自旋律时 | 附加风格提示到 feedback |
| orchestration（配器平衡） | 0.10 | 否 | → clef-orchestrator |

#### 旋律子检查→反馈 prompt 映射

基于 clef-reviewer.md 的 M1-M6 检查项，将 issues 转化为 ChatMusician 可理解的英文指令：

| 子检查 | issue 示例 | 反馈 prompt 模板 |
|--------|-----------|-----------------|
| M1 轮廓平滑度 | "连续大跳无级进解决" | "Reduce large interval jumps. After any leap > P5, resolve with stepwise motion in opposite direction." |
| M2 强拍和弦音 | "强拍非和弦音" | "Place chord tones (root, 3rd, 5th) on strong beats (beat 1 and 3). Use passing tones only on weak beats." |
| M3 乐句呼吸 | "缺少乐句呼吸" | "Add clear phrase endings every 2-4 bars using rests or longer notes. Balance phrase lengths symmetrically." |
| M4 动机一致性 | "缺乏统一动机" | "Develop a recognizable motif in the first phrase and reuse it with variation (sequence, inversion, rhythmic change) in later phrases." |
| M5 高潮位置 | "高潮偏离" | "Place the highest note in the {target_section} section. Keep {other_sections} in a lower register." |
| M6 音区舒适度 | "高音区停留过多" | "Keep melody mainly within {register_low}-{register_high}. Use high notes sparingly, only for climactic points." |

#### 反馈 prompt 组装流程

```python
def build_regenerate_feedback(review_report: dict, plan: dict) -> str:
    """从 review_report 构造 ChatMusician 反馈 prompt"""
    melody_dim = review_report["dimensions"]["melody"]
    feedback_parts = []

    for issue in melody_dim["issues"]:
        # 将 issue.description/suggestion 映射为英文指令模板
        template = MELODY_FEEDBACK_MAP[map_issue_to_check(issue)]
        feedback_parts.append(template.format(**extract_params(issue, plan)))

    # 附加结构/风格约束（如果有）
    if review_report["dimensions"]["structure"]["score"] < 7.0:
        feedback_parts.append(f"Overall form: {plan['form']}. Respect section boundaries.")
    if review_report["dimensions"]["style"]["score"] < 7.0:
        feedback_parts.append(f"Style: {plan['style']}. Maintain consistent character throughout.")

    return "\n".join(feedback_parts)
```

输出为 `chatmusician regenerate` 命令的 `--feedback` 参数。

## 8. 打包与分发

### itch.io 安装包结构

```
clef-dev-v1.x.zip
├── clef-project/                  # Godot 项目（含 addons/clef/）
├── python-runtime/                # 嵌入式 Python（免安装）
├── start.bat                      # Windows 启动脚本
└── start.sh                       # Linux 启动脚本
```

### 体积估算

| 组件 | 大小 |
|------|------|
| ChatMusician Q4_K_M | ~4GB |
| llama.cpp 二进制（单平台） | ~30MB |
| 嵌入式 Python | ~30MB |
| Python 依赖（openai 等，离线包） | ~15MB |
| 其余（Godot 模板 + SF2 + 代码） | ~75MB |
| **总计（单平台）** | **~4.15GB** |

### 启动脚本自动处理
- 检测 GPU VRAM，根据阈值自动选择 `n_gpu_layers` 和 `parallel_slots`：
  - ≥ 12 GB → 全 GPU + 3 并行
  - ≥ 8 GB → 全 GPU + 串行（默认）
  - ≥ 6 GB → 部分 GPU offload (20 层) + 串行
  - < 6 GB → 纯 CPU + 串行（警告用户速度较慢）
- 安装 `openai>=1.0` 依赖（嵌入式 Python 通过 bundled `requirements.txt` + `pip install --no-index --find-links=deps/` 离线安装）
- llama.cpp server 首次启动加载模型（~15秒）
- 首次启动展示 LLaMA2 许可证摘要，用户确认后继续

### 商业保护
- ChatMusician prompt 模板（few-shot 示例 + 调优参数）为核心价值
- itch.io 付费下载，文档注明禁止转分发
- 安装包内包含 `LICENSE-LLaMA2.txt`，产品页附带 LLaMA2 许可证链接
- 产品价值：省去用户自行配置 llama.cpp + 模型 + prompt 的全部工作

## 9. 实现路线图

### Phase 1 — ChatMusician 本地跑通（验证可行性）
- 下载/编译 llama.cpp server
- ChatMusician GGUF 启动测试
- Python 端到端调用测试
- 调优 prompt 模板
- **里程碑**: 一条命令生成可播放的 ABC

### Phase 2 — Python 工具链集成
- 实现 chatmusician_server/client/prompt/config
- clef_tools.py 新增 5 个子命令
- ABC 适配层 normalize_abc() 及单测
- 反馈构造 build_regenerate_feedback() 及单测
- 兼容性测试
- **测试计划**：新增 `tests/test_chatmusician.py`，覆盖：
  - `test_server_detect_vram_fallback()` — 模拟各级 VRAM 返回值
  - `test_server_port_conflict()` — 模拟端口占用，验证自动切换
  - `test_normalize_abc()` — 各类 ABC 差异输入 → 标准化输出
  - `test_build_feedback_from_review()` — 构造 mock review_report，验证反馈生成
  - `test_generate_timeout()` — 模拟超时，验证优雅降级
  - `test_regenerate_limit()` — 验证 10 次上限
- **里程碑**: `clef_tools.py chatmusician generate` → 3 个 MIDI 文件

### Phase 3 — Skill 层混合模式
- 修改 SKILL.md、clef-composer.md、clef-leader.md
- 端到端混合模式测试
- **里程碑**: `/clef-compose --mode hybrid` → 完整作品

### Phase 4 — 打包与分发
- 嵌入式 Python 打包
- llama.cpp 跨平台二进制
- 启动脚本
- itch.io 上架
- **里程碑**: 用户下载 → 一键启动 → 完整体验

### 优先级
Phase 1 优先验证 ChatMusician 实际输出质量，确认可行后再推进后续 Phase。

## 参考资料

- [ChatMusician 论文 (ACL 2024)](https://arxiv.org/abs/2402.16153)
- [ChatMusician GitHub](https://github.com/hf-lin/ChatMusician)
- [ChatMusician HuggingFace](https://huggingface.co/m-a-p/ChatMusician)
- [ChatMusician GGUF (HuggingFace)](https://huggingface.co/MaziyarPanahi/ChatMusician-GGUF)
- [Godot 本地 LLM 集成实践](https://dev.to/ykbmck/running-local-llms-in-game-engines-heres-my-journey-with-godot-ollama-4hhd)
