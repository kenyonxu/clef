# Clef 用户扩展知识

> 在此目录下添加自定义知识文件，`clef-compose` Skill 执行时会自动扫描加载。

## 支持的扩展文件格式

### 和弦进行扩展 (`chord_progressions_*.json`)

```json
{
  "category_name": {
    "I-bVII-IV-I": {
      "description": "自定义进行",
      "mood": ["情绪标签"],
      "notes": "使用说明"
    }
  }
}
```

### 风格模板扩展 (`styles_*.json`)

```json
{
  "style_name": {
    "scales": ["推荐音阶"],
    "chord_progressions": ["推荐进行"],
    "rhythm_patterns": ["节奏描述"],
    "instrumentation": ["配器方案"],
    "expression_hints": ["表现力提示"]
  }
}
```

### 节奏模式扩展 (`rhythm_*.json`)

```json
{
  "pattern_name": {
    "time_signature": "4/4",
    "description": "模式描述",
    "hits": [
      {"beat": 1, "subdivision": 0, "instrument": 36, "velocity": 110},
      {"beat": 1, "subdivision": 2, "instrument": 42, "velocity": 80}
    ]
  }
}
```

## 文件命名规范

- `chord_progressions_<名称>.json`
- `styles_<名称>.json`
- `rhythm_<名称>.json`

## 内置知识

核心乐理知识在 Skill 自带文件 `.claude/skills/clef-compose-theory.md` 中，包含音阶、和弦进行、GM 乐器、配器方案等。
