# Graphify 知识图谱使用指南

本项目已构建 graphify 知识图谱，将代码库转化为可查询、可遍历的结构化图。

## 图谱概览

| 指标 | 数值 |
|------|------|
| 节点数 | 1,664 |
| 边数 | 3,416 |
| 社区数 | 142 |
| Token 压缩比 | 14.4x |
| 来源 | AST 代码提取 + 文档语义提取 |

## 输出文件

```
graphify-out/
  graph.html        ← 浏览器打开，交互式图谱可视化
  GRAPH_REPORT.md   ← 审计报告（God Nodes、社区、建议问题）
  graph.json        ← 原始图数据（GraphRAG / 查询用）
  cost.json         ← 累计 token 消耗
```

## 常用命令

### 快速查阅（推荐日常使用）

```bash
/graphify query "how does the repair loop work"        # BFS 广度搜索
/graphify query "repair loop" --dfs                     # DFS 深度追踪
/graphify explain "ComposeOrchestrator"                 # 单模块详解
/graphify path "AgentConfig" "ProviderRateLimiter"      # 两模块间依赖链
```

### 维护图谱

```bash
/graphify . --update          # 增量更新（只处理变更文件，推荐）
/graphify . --no-semantic     # 仅 AST 提取（秒级，代码结构变更后用）
/graphify .                   # 全量重建（耗时较长）
```

### 进阶

```bash
/graphify . --update --wiki    # 更新并生成 wiki 索引页
/graphify . --svg              # 额外导出 SVG（可嵌入 Notion/GitHub）
```

## 推荐工作流

1. **改代码后** → `/graphify . --update` 保持图谱同步
2. **问架构问题前** → 先读 `graphify-out/GRAPH_REPORT.md` 的 God Nodes
3. **重构模块前** → `/graphify path "模块A" "模块B"` 查依赖链
4. **新会话开始** → 直接用 `/graphify query` 查询，无需重新探索代码库

## 核心模块（God Nodes）

按连接度排序的核心节点：

| 节点 | 度数 | 说明 |
|------|------|------|
| SessionManager | 240 | 会话管理器 |
| ComposeOrchestrator | 214 | 作曲编排器 |
| ComposeSession | 105 | 作曲会话 |
| ToolSafety | 103 | 工具安全 |
| ClefContextMiddleware | 88 | Clef 上下文中间件 |
| ProviderRateLimiter | 81 | LLM 提供者限流器 |

这些节点是系统的"枢纽"，修改时需要格外注意影响范围。

## 注意事项

- `--no-semantic` 只提取代码结构（AST），不含文档中的设计决策
- 全量构建（`/graphify .`）对 200 文件的语料库耗时较长
- 图谱结果中的 `EXTRACTED` 边来自源码明确关系，`INFERRED` 边为推断关系
