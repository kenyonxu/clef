# GDToolkit 集成指南

> 适用于任何 Godot 4.x 项目，配合 Claude Code 实现自动格式化 + 代码检查

## 概述

[GDToolkit](https://github.com/Scony/godot-gdscript-toolkit) 是独立于 Godot 引擎的 GDScript 工具链（MIT 协议），提供三个核心工具：

| 工具 | 功能 | 类比 (Python) |
|------|------|---------------|
| `gdformat` | 代码格式化 | black |
| `gdlint` | 代码质量检查 | flake8 |
| `gdparse` | 语法解析/验证 | 无（纯解析器） |

**核心优势**：不依赖 Godot 引擎，纯 Python 实现，适合 CI / Git Hook / 编辑器插件等场景。

## 安装

```bash
pip install gdtoolkit
```

验证：

```bash
gdformat --version   # 当前 4.5.0
gdlint --version
```

## 1. gdformat — 自动格式化

### 功能

统一缩进（Tab）、空格、换行、运算符间距、函数调用格式等。

**格式化前**：

```gdscript
func do_something( x:int, y:int )->bool:
    var result=x+y
    if result>10:
        print( "big" )
    return true
```

**格式化后**：

```gdscript
func do_something(x: int, y: int) -> bool:
	var result = x + y
	if result > 10:
		print("big")
	return true
```

### 用法

```bash
# 格式化单个文件
gdformat path/to/script.gd

# 格式化整个项目
gdformat addons/

# 检查哪些文件需要格式化（不修改）
gdformat --check addons/

# diff 模式（显示变化但不写入）
gdformat --diff addons/
```

### 局限

- 只能格式化**语法正确**的 GDScript，语法错误级别的缩进问题无法修复
- 不处理逻辑问题，只管格式

## 2. gdlint — 代码质量检查

### 内置规则

| 类别 | 规则 | 默认值 |
|------|------|--------|
| 命名规范 | class_name, 函数名, 变量名, 常量名, 信号名 | PascalCase / snake_case |
| 复杂度 | 单文件最大行数 | 1000 |
| 复杂度 | 函数最大参数数 | 10 |
| 复杂度 | 函数最大 return 数 | 6 |
| 复杂度 | 公开方法上限 | 20 |
| 复杂度 | 单行最大字符数 | 100 |
| 代码质量 | 未使用参数、混合 Tab/Space、行尾空白、不必要的 pass | 启用 |
| 结构 | 类成员声明顺序 | tool → extends → signals → enums → consts → vars → methods |

### 用法

```bash
# 检查单个文件
gdlint path/to/script.gd

# 检查整个项目
gdlint addons/

# 导出默认配置模板
gdlint --dump-default-config
```

### 自定义配置

在项目根目录创建 `gdlintrc` 文件（无扩展名）。以下是一个**推荐的实用配置**：

```yaml
# ============================================
# gdlintrc — GDToolkit 代码检查配置
# 适用于 Godot 4.x 项目，适配 AI 辅助开发
# ============================================

# 类成员声明顺序（保留参考，但已 disable）
class-definitions-order:
  - tools
  - classnames
  - extends
  - docstrings
  - signals
  - enums
  - consts
  - staticvars
  - exports
  - pubvars
  - prvvars
  - onreadypubvars
  - onreadyprvvars
  - others

# 命名规范（保持 Godot 社区惯例）
class-name: ([A-Z][a-z0-9]*)+
enum-name: ([A-Z][a-z0-9]*)+
enum-element-name: '[A-Z][A-Z0-9]*(_[A-Z0-9]+)*'
signal-name: '[a-z][a-z0-9]*(_[a-z0-9]+)*'
function-name: (_on_([A-Z][a-z0-9]*)+(_[a-z0-9]+)*|_?[a-z][a-z0-9]*(_[a-z0-9]+)*)
function-argument-name: _?[a-z][a-z0-9]*(_[a-z0-9]+)*
function-variable-name: '_?[a-z][a-z0-9]*(_[a-z0-9]+)*'
class-variable-name: _?[a-z][a-z0-9]*(_[a-z0-9]+)*
class-load-variable-name: (([A-Z][a-z0-9]*)+|_?[a-z][a-z0-9]*(_[a-z0-9]+)*)
function-preload-variable-name: ([A-Z][a-z0-9]*)+
load-constant-name: (([A-Z][a-z0-9]*)+|_?[A-Z][A-Z0-9]*(_[A-Z0-9]+)*)
constant-name: _?[A-Z][A-Z0-9]*(_[A-Z0-9]+)*
loop-variable-name: _?[a-z][a-z0-9]*(_[a-z0-9]+)*
sub-class-name: _?([A-Z][a-z0-9]*)+

# 复杂度阈值（根据项目实际情况调整）
max-file-lines: 1500        # 默认 1000，Godot 组件文件常较大
max-line-length: 120        # 默认 100，Godot API + 中文注释行长偏长
max-public-methods: 30      # 默认 20，Player/Manager 类公开方法多属正常
max-returns: 6
function-arguments-number: 10

# 格式
tab-characters: 1
trailing-whitespace: null
mixed-tabs-and-spaces: null

# 禁用的规则（对存量代码/AI 生成代码过于严格）
disable:
  - class-definitions-order    # 存量代码重排风险大
  - unused-argument            # Godot 回调常有未用参数
  - no-else-return             # 风格偏好
  - no-elif-return             # 风格偏好
  - expression-not-assigned    # Godot 模式：stream.get_u32() 跳过字段

# 排除目录
excluded_directories: !!set
  .git: null
```

> **提示**：将此文件复制到你的 Godot 项目根目录即可生效。根据项目需要调整阈值。

## 3. Claude Code Hook 集成

### 配置方法

在 `~/.claude/settings.json`（全局）或项目的 `.claude/settings.json` 中添加 PostToolUse hook：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "if [[ \"$CLAUDE_FILE_PATH\" == *.gd ]]; then gdformat \"$CLAUDE_FILE_PATH\" 2>&1 || true; fi"
          },
          {
            "type": "command",
            "command": "if [[ \"$CLAUDE_FILE_PATH\" == *.gd ]]; then gdlint \"$CLAUDE_FILE_PATH\" 2>&1 || true; fi"
          }
        ]
      }
    ]
  }
}
```

### 工作流程

```
Claude 写入/编辑 .gd 文件
  ↓
gdformat 自动格式化（统一缩进、空格、换行）
  ↓
gdlint 输出质量警告（不阻断，仅提示）
  ↓
格式化后的文件保存到磁盘
```

### 效果

- AI 生成的代码自动统一格式，消除缩进/空格不统一问题
- 代码质量警告实时反馈在 Claude Code 终端
- 不影响非 .gd 文件

## 4. .editorconfig 配置（推荐配合使用）

在 Godot 项目根目录添加 `.editorconfig`：

```ini
# top-most EditorConfig file
root = true

# GDScript
[*.gd]
indent_style = tab
indent_size = 4
charset = utf-8
insert_final_newline = true
trim_trailing_whitespace = true

# Godot 场景/资源
[*.{tscn,tres}]
indent_style = tab
charset = utf-8

# JSON
[*.json]
indent_style = tab
indent_size = 4
```

确保 Godot 编辑器、VS Code、Claude Code 三者的缩进策略一致。

## 5. CI 集成（可选）

```yaml
# GitHub Actions 示例
name: GDScript Quality
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install gdtoolkit
      - run: gdformat --check addons/
      - run: gdlint addons/
```

## 快速部署清单

新项目要启用时，按顺序执行：

- [ ] `pip install gdtoolkit`
- [ ] 复制 `gdlintrc` 到项目根目录（按需调整阈值）
- [ ] 复制 `.editorconfig` 到项目根目录
- [ ] 在 Claude Code `settings.json` 中添加 PostToolUse hook
- [ ] 重启 Claude Code 会话

## 参考链接

- 项目主页：https://github.com/Scony/godot-gdscript-toolkit
- Godot 官方推荐：https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html
- pip 包：https://pypi.org/project/gdtoolkit/
