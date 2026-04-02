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

## 2. 整体架构

### 双模式设计

| | 纯 Agent 模式 | 混合模式（高级） |
|---|---|---|
| 依赖 | Claude API | 本地 ChatMusician + Claude API |
| 旋律生成 | Claude Composer | ChatMusician 本地快速生成 |
| 编配与迭代 | Claude Agent 体系 | Claude Agent 体系（不变） |
| 迭代中重新生成 | Composer 重写 | ChatMusician 基于反馈重新生成 |
| 质量 | 高 | 高 |
| 成本 | API 费用 | API 费用（减少） |
| 速度 | 慢（多轮 API） | 中等（本地生成 + API 编配） |

### 核心策略
**ChatMusician 作为灵感引擎，Claude Agent 作为质量守门人**：
- ChatMusician 做最擅长的事：和弦条件旋律生成
- Claude Agent 弥补弱点：格式修正、风格纠正、评审打磨

## 3. 目录结构

```
addons/clef/
├── chatmusician/                    # 新增模块
│   ├── chatmusician_server.py       # llama.cpp 进程管理
│   ├── chatmusician_client.py       # OpenAI-compatible API 封装
│   ├── chatmusician_prompt.py       # Prompt 模板
│   ├── chatmusician_config.py       # 配置管理
│   └── model/                       # GGUF 模型
│       └── ChatMusician.Q4_K_M.gguf
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

## 4. Python 集成层

### 4.1 配置管理（chatmusician_config.py）

```python
CHATMUSICIAN = {
    "model_path": "addons/clef/chatmusician/model/ChatMusician.Q4_K_M.gguf",
    "server_bin": "addons/clef/llamacpp/{platform}/llama-server{ext}",
    "host": "127.0.0.1",
    "port": 8080,
    "n_ctx": 4096,
    "n_gpu_layers": -1,     # -1=全部GPU, 0=纯CPU
    "temperature": 0.8,
    "top_p": 0.9,
    "max_tokens": 2048,
    "candidates": 3,
}
```

### 4.2 进程管理（chatmusician_server.py）

| 方法 | 功能 |
|------|------|
| `start()` | 启动 llama.cpp server 子进程，等待 health 端点就绪 |
| `stop()` | 优雅终止进程 |
| `is_ready()` | 健康检查 |
| `get_status()` | 返回状态（未启动/启动中/就绪/错误） |

使用 `subprocess.Popen` 后台管理，不阻塞 Godot。

### 4.3 API 封装（chatmusician_client.py）

使用 `openai` 库指向本地 llama.cpp server：

```python
client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="not-needed")

def generate_melody(chords, key, meter, style_hint="") -> list[str]:
    """生成 N 个旋律候选，返回 ABC 片段列表"""

def regenerate_melody(chords, key, meter, feedback, current_abc="") -> str:
    """基于反馈重新生成旋律，返回单个 ABC 片段"""
```

### 4.4 Prompt 模板（chatmusician_prompt.py）

基于论文稳定 prompt 格式，封装三种模板：
- `chord_to_melody(chords, key, meter, style)` — 主力模板
- `melody_harmonize(melody_abc, key)` — 辅助模板
- `motif_develop(motif_abc, form)` — 扩展模板

每个模板包含 1-2 个 few-shot 示例引导输出质量。

### 4.5 clef_tools.py 新增子命令

| 子命令 | 功能 |
|--------|------|
| `chatmusician start` | 启动 server |
| `chatmusician stop` | 停止 server |
| `chatmusician status` | 查询状态 |
| `chatmusician generate` | 初稿生成（Step 1b，3 候选） |
| `chatmusician regenerate` | 迭代中重新生成（Step 2b，1 个，带反馈） |

## 5. 混合模式工作流

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
          ├── 生成 3 个旋律候选（本地并行，~10-30秒）
          └── 输出: {name}_candidate_1/2/3.mid

Step 1c:  用户确认
          ├── 告知用户在 Godot 中试听 3 个候选 MIDI
          ├── 用户选择一个（或要求重新生成）
          └── 确认后进入 Step 2a

Step 2a:  完整编配
          ├── Harmonist 基于选中旋律生成和声 V:2
          ├── Rhythmist 生成低音 V:3 + 鼓 V:4
          └── 合并为完整 score.abc

Step 2b:  Leader 迭代（修改）
          ├── validate → revision → review（现有）
          └── 旋律评分 < 7/10 且非格式问题时：
               ├── 构造反馈 prompt → ChatMusician 重新生成 V:1
               ├── 替换 score.abc 旋律声部
               └── 重新 validate → review
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

## 6. Skill 层修改

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

## 7. 打包与分发

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
| 其余（Godot 模板 + SF2 + 代码） | ~75MB |
| **总计（单平台）** | **~4.1GB** |

### 启动脚本自动处理
- 检查 VRAM ≥ 6GB，自动选择 GPU/CPU 模式
- 安装 `openai` 依赖
- llama.cpp server 首次启动加载模型（~15秒）

### 商业保护
- ChatMusician prompt 模板（few-shot 示例 + 调优参数）为核心价值
- itch.io 付费下载，文档注明禁止转分发
- 产品价值：省去用户自行配置 llama.cpp + 模型 + prompt 的全部工作

## 8. 实现路线图

### Phase 1 — ChatMusician 本地跑通（验证可行性）
- 下载/编译 llama.cpp server
- ChatMusician GGUF 启动测试
- Python 端到端调用测试
- 调优 prompt 模板
- **里程碑**: 一条命令生成可播放的 ABC

### Phase 2 — Python 工具链集成
- 实现 chatmusician_server/client/prompt/config
- clef_tools.py 新增 5 个子命令
- 兼容性测试
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
