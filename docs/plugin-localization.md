# Clef 插件本地化方案

本文档说明 Clef Godot 插件的本地化技术方案，基于 Godot 4.6 内置的 `TranslationDomain` 机制。

## 背景

Godot 4.6 的 `TranslationServer` 提供了完整的国际化支持。翻译资源存储在 `TranslationDomain` 中，每个域是一个独立的翻译集合。Godot 4.6 文档明确指出：

> Custom translation domains are mainly for advanced usages like editor plugins.

这意味着 Godot 原生支持编辑器插件的本地化，无需引入第三方方案。

## 架构概览

```
TranslationServer（全局单例）
├── 主域 ""          ← 项目翻译，tr() 默认查这里
├── "godot.editor"   ← 引擎编辑器内置翻译（保留前缀）
└── "clef"           ← Clef 插件翻译域（自定义）
    ├── clef.zh_CN.translation
    └── clef.ja.translation
```

使用自定义域的好处：插件翻译与项目翻译完全隔离，不会互相干扰。域名以 `godot.` 开头的保留给引擎内部使用。

## 核心类与 API

### TranslationServer

| 方法 | 说明 |
|------|------|
| `get_or_add_domain(name)` | 获取或创建自定义翻译域 |
| `remove_domain(name)` | 移除自定义翻译域 |
| `get_tool_locale()` | 获取编辑器当前语言 |
| `get_locale()` | 获取项目当前语言 |

### TranslationDomain

| 方法 | 说明 |
|------|------|
| `add_translation(Translation)` | 添加一个翻译资源 |
| `remove_translation(Translation)` | 移除一个翻译资源 |
| `clear()` | 清空所有翻译 |
| `translate(message, context)` | 翻译查找 |
| `translate_plural(message, plural, n, context)` | 带复数形式的翻译 |
| `set_locale_override(locale)` | 域级别语言覆盖 |
| `enabled` | 是否启用此域 |

### Translation

翻译资源类，支持两种来源格式：

- **CSV** — 简单表格格式，适合少量翻译
- **PO (gettext)** — 工业标准格式，支持复数形式和上下文，推荐用于正式项目

## 实现方案

### 文件结构

```
addons/clef/
  locales/
    clef.pot                 # 翻译模板（所有可翻译字符串的来源）
    clef.zh_CN.translation   # 简体中文
    clef.zh_TW.translation   # 繁体中文
    clef.ja.translation      # 日语
  plugin.gd                   # 插件入口
```

### 插件入口代码

```gdscript
# addons/clef/plugin.gd
@tool
extends EditorPlugin

const DOMAIN_NAME = &"clef"
var _domain: TranslationDomain

func _enter_tree() -> void:
    _setup_translations()
    # ... 其他初始化逻辑

func _exit_tree() -> void:
    _cleanup_translations()
    # ... 其他清理逻辑

func _setup_translations() -> void:
    _domain = TranslationServer.get_or_add_domain(DOMAIN_NAME)
    _domain.set_locale_override(TranslationServer.get_tool_locale())

    var dir := DirAccess.open("res://addons/clef/locales/")
    if dir:
        dir.list_dir_begin()
        var file_name := dir.get_next()
        while file_name != "":
            if file_name.ends_with(".translation"):
                var translation = load("res://addons/clef/locales/" + file_name)
                if translation is Translation:
                    _domain.add_translation(translation)
            file_name = dir.get_next()
        dir.list_dir_end()

func _cleanup_translations() -> void:
    if _domain:
        _domain.clear()
        TranslationServer.remove_domain(DOMAIN_NAME)
        _domain = null

func t(message: String, context: String = "") -> String:
    """插件内翻译辅助函数。"""
    if _domain:
        return _domain.translate(message, context)
    return message
```

### UI 中使用

```gdscript
# 在插件 UI 脚本中
play_button.text = plugin.t("Play")
stop_button.text = plugin.t("Stop")
title_label.text = plugin.t("MIDI Player", "WindowTitle")

# 带占位符
status_label.text = plugin.t("Playing: {file}").format({file = midi_name})

# 带上下文（消除歧义）
# "Close" 作为动作
close_btn.text = plugin.t("Close", "Action")
# "Close" 作为距离
distance_label.text = plugin.t("Close", "Distance")
```

### 响应编辑器语言切换

编辑器语言可能在使用过程中切换。可以通过监听信号或定时检查来响应：

```gdscript
var _last_locale: String = ""

func _process(_delta: float) -> void:
    var current_locale := TranslationServer.get_tool_locale()
    if current_locale != _last_locale:
        _last_locale = current_locale
        if _domain:
            _domain.set_locale_override(current_locale)
        _refresh_ui_texts()
```

## 翻译文件格式

### PO (gettext) 格式（推荐）

使用 Godot 编辑器生成 POT 模板：

1. **Project > Project Settings > Localization > Translations** 中添加翻译
2. **Project > Tools > Generate Translation** 自动从场景和脚本中提取可翻译字符串
3. 使用 gettext 工具从 `.pot` 创建各语言 `.po` 文件

Godot 4.6 支持 PO 文件的完整特性：复数形式、翻译上下文、翻译注释。

### CSV 格式（简单场景）

CSV 格式适合翻译量较少的情况：

```csv
keys,zh_CN,ja
Play,播放,再生
Stop,停止,停止
Pause,暂停,一時停止
Resume,继续,再開
```

在 Godot 中通过 **Project > Project Settings > Localization > Translations** 导入后，会自动生成 `.translation` 资源文件。

## 需要本地化的字符串范围

Clef 插件中需要本地化的字符串主要包括：

- **播放器 UI** — 播放/停止/暂停按钮、状态文本、时间显示
- **Inspector 插件** — 属性名称、提示信息
- **文件右键菜单** — 菜单项文本
- **错误/警告信息** — 用户可见的运行时提示

不包含：
- 内部调试日志（使用 `push_warning`/`push_error`，保持英文便于排查）
- MIDI 技术术语（如 Note, Velocity, CC 等保留英文）

## 注意事项

- 翻译域的 `set_locale_override` 让插件跟随编辑器语言，而非项目语言。这对编辑器插件是正确的行为
- 导出的游戏中不包含编辑器插件代码，因此插件本地化只影响编辑器体验
- 翻译资源文件使用 `.translation` 扩展名，是 Godot 的资源格式（本质是序列化的 `Translation` 对象）
- 清理时务必调用 `remove_domain`，避免插件停用后翻译残留

## 参考资料

- [TranslationServer — Godot 4.6 文档](https://docs.godotengine.org/en/4.6/classes/class_translationserver.html)
- [TranslationDomain — Godot 4.6 文档](https://docs.godotengine.org/en/4.6/classes/class_translationdomain.html)
- [Internationalizing games — Godot 4.6 文档](https://docs.godotengine.org/en/4.6/tutorials/i18n/internationalizing_games.html)
- [Localization using gettext — Godot 4.6 文档](https://docs.godotengine.org/en/4.6/tutorials/i18n/localization_using_gettext.html)
