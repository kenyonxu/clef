# Skills 技能参考手册

本文档列出当前环境中可用的 Superpowers 和 everything-claude-code 技能，包括触发条件和功能说明。

## Superpowers（v5.0.7）

Superpowers 是一组面向 Claude Code 工作流的元技能，覆盖从规划、实现到验证的完整开发周期。

### 规划与设计

| 技能 | 说明 |
|------|------|
| `brainstorming` | 在任何创意工作前必须使用——探索用户意图、需求和设计方案，再进入实现阶段 |
| `writing-plans` | 拥有规格或需求时，在写代码前先撰写分步实施计划 |
| `executing-plans` | 在独立 session 中执行已编写的实施计划，带审查检查点 |

### 实现与开发

| 技能 | 说明 |
|------|------|
| `test-driven-development` | 实现任何功能或修复 bug 前，先写测试（TDD 工作流） |
| `subagent-driven-development` | 在当前 session 中用子 Agent 并行执行实施计划中的独立任务 |
| `dispatching-parallel-agents` | 面对 2 个以上无共享状态、无顺序依赖的独立任务时，并行分派 Agent |
| `using-git-worktrees` | 启动需要隔离的特性开发时，创建 git worktree 并自动选择目录 |

### 代码审查

| 技能 | 说明 |
|------|------|
| `requesting-code-review` | 完成任务或实现主要功能后，请求代码审查以验证工作质量 |
| `receiving-code-review` | 收到代码审查反馈后，在实施建议前先进行技术验证，不盲目同意 |
| `verification-before-completion` | 在声明工作完成前，必须运行验证命令并确认输出，证据先于断言 |

### 调试与质量

| 技能 | 说明 |
|------|------|
| `systematic-debugging` | 遇到任何 bug、测试失败或异常行为时，在提出修复前使用系统化调试流程 |

### 收尾与发布

| 技能 | 说明 |
|------|------|
| `finishing-a-development-branch` | 实现完成且测试通过后，引导完成合并、PR 或清理的结构化选项 |

### 元技能

| 技能 | 说明 |
|------|------|
| `using-superpowers` | 每次对话开始时的入口技能，建立技能发现和使用规则 |
| `writing-skills` | 创建新技能、编辑现有技能或验证技能部署 |

---

## everything-claude-code（v1.2.0）

everything-claude-code 提供编程语言模式、安全审查、TDD 工作流、持续学习等领域的技能。

### 通用工作流

| 技能 | 说明 |
|------|------|
| `tdd-workflow` | 编写新功能、修复 bug 或重构时强制 TDD，要求 80%+ 覆盖率 |
| `security-review` | 涉及认证、用户输入、密钥、API 端点或支付等敏感功能时的安全审查清单 |
| `continuous-learning` | 自动从 Claude Code session 中提取可复用模式，保存为技能供后续使用 |
| `continuous-learning-v2` | 基于 instinct 的学习系统——通过 hooks 观察 session，创建带置信度评分的原子 instinct，演进为技能/命令/Agent |
| `eval-harness` | 为 Claude Code session 实现评估驱动开发（EDD）的正式评估框架 |
| `strategic-compact` | 在逻辑间隔点建议手动上下文压缩，避免自动压缩丢失关键信息 |
| `iterative-retrieval` | 渐进式精炼上下文检索，解决子 Agent 上下文问题 |

### 前端

| 技能 | 说明 |
|------|------|
| `frontend-patterns` | React、Next.js 状态管理、性能优化和 UI 最佳实践 |
| `coding-standards` | TypeScript、JavaScript、React 和 Node.js 的通用编码标准和最佳实践 |

### 后端

| 技能 | 说明 |
|------|------|
| `backend-patterns` | Node.js、Express、Next.js API 路由的后端架构模式和 API 设计 |
| `postgres-patterns` | PostgreSQL 查询优化、Schema 设计、索引和安全，基于 Supabase 最佳实践 |
| `clickhouse-io` | ClickHouse 高性能分析工作负载的查询优化和数据库模式 |

### Go

| 技能 | 说明 |
|------|------|
| `golang-patterns` | 惯用 Go 模式和最佳实践 |
| `golang-testing` | 表驱动测试、子测试、基准测试、模糊测试，遵循 TDD 方法论 |

### Java / Spring Boot

| 技能 | 说明 |
|------|------|
| `coding-standards` | Java 编码标准：命名、不可变性、Optional、流、异常、泛型和项目布局 |
| `springboot-patterns` | Spring Boot 架构模式：REST API、分层服务、数据访问、缓存、异步处理 |
| `springboot-security` | Spring Security 认证授权、CSRF、密钥、限流和依赖安全 |
| `springboot-tdd` | Spring Boot 的 TDD：JUnit 5、Mockito、MockMvc、Testcontainers、JaCoCo |
| `springboot-verification` | Spring Boot 验证循环：构建、静态分析、测试覆盖率、安全扫描、diff 审查 |
| `jpa-patterns` | JPA/Hibernate 实体设计、关系映射、查询优化、事务、审计、索引、分页 |

### 模板

| 技能 | 说明 |
|------|------|
| `project-guidelines-example` | 项目专属技能的示例模板 |
| `verification-loop` | Claude Code session 的综合验证系统 |
