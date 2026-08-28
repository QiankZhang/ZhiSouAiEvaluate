# CLAUDE.md

> 本文件是 AI 编码助手的项目级约束文件。所有 AI 生成的代码必须遵守以下规则。

## 1. 项目概述

- **项目名称:** <项目名>
- **技术栈:** <语言/框架/数据库/部署环境>
- **架构模式:** <单体 / 微服务 / Serverless / Monorepo 等>
- **目标:** <一句话描述项目目标>

---

## 2. 代码规范

### 2.1 通用规则
- 使用项目已有的代码风格，不要引入新的格式化工具或风格。
- 不要为了"看起来更好"而重构已有代码——除非被明确要求。
- 优先使用语言/框架的标准库，避免引入不必要的第三方依赖。
- 新增依赖前必须说明理由，且检查其许可证兼容性。

### 2.2 命名约定
- 变量/函数: `camelCase` (JS/TS) / `snake_case` (Python/Go)
- 常量: `UPPER_SNAKE_CASE`
- 类/接口/类型: `PascalCase`
- 文件名: `kebab-case` (组件文件) / `snake_case` (工具/脚本)
- 私有成员: 前缀 `_` 或遵循语言惯例

### 2.3 代码组织
- 单文件不超过 **400 行**，超出时拆分模块。
- 单函数不超过 **60 行**，超出时提取子函数。
- 函数参数不超过 **5 个**，超出时使用配置对象。
- 避免嵌套超过 **3 层** 的条件/循环。

### 2.4 注释与文档
- 只写"为什么"，不写"是什么"（代码本身应该自解释）。
- 公共 API 必须有文档注释 (JSDoc / docstring / godoc)。
- TODO 必须附带 issue 编号: `// TODO(#123): 描述`
- 删除被注释掉的死代码，不要保留。

---

## 3. 架构约束

### 3.1 分层规则
- **禁止跨层调用:** Controller 不直接操作数据库，Service 不返回 HTTP 响应。
- **依赖方向:** 外层依赖内层 (Route → Controller → Service → Repository → Model)。
- **禁止循环依赖。**

### 3.2 目录结构
```
src/
├── routes/          # 路由定义
├── controllers/     # 请求处理
├── services/        # 业务逻辑
├── repositories/    # 数据访问
├── models/          # 数据模型
├── middlewares/     # 中间件
├── utils/           # 纯函数工具
├── types/           # 类型定义
└── config/          # 配置
```
> 按实际项目调整，但保持一致性。

### 3.3 配置管理
- 所有可配置项通过环境变量注入，不要硬编码。
- 敏感信息 (密钥、Token) 永远不进代码库，使用 `.env` + `.gitignore`。
- 提供 `.env.example` 作为模板。
- 不同环境 (dev/staging/prod) 的配置必须隔离。

---

## 4. 错误处理

- **禁止吞异常:** 所有 `catch` 块必须有处理逻辑 (日志/重抛/降级)。
- **不要返回 null 表示错误:** 使用 Result 类型或抛出异常。
- **统一错误响应格式:**
  ```json
  { "error": { "code": "ERROR_CODE", "message": "用户可读的信息", "details": {} } }
  ```
- **输入校验在入口层完成** (Controller/Middleware)，不要在业务逻辑中重复校验。
- 日志记录错误时附带请求 ID 和上下文，不要只记 `error.message`。

---

## 5. 测试约束

### 5.1 覆盖率要求
- 核心业务逻辑 (Service 层): 行覆盖率 ≥ **80%**
- 工具函数: 行覆盖率 ≥ **90%**
- Controller/Route: 集成测试覆盖关键路径
- 允许覆盖率低的: 配置文件、类型定义、入口文件

### 5.2 测试规则
- 测试文件与源文件同目录或 `__tests__/` 下，命名 `*.test.ts` / `*_test.go`。
- 每个测试只验证一个行为 (一个 `it` / `test` 一个断言焦点)。
- 测试名称用自然语言描述行为: `it('should return 404 when user not found')`。
- 禁止依赖测试执行顺序。
- Mock 外部依赖 (HTTP/DB/MQ)，不要 Mock 被测对象本身。
- 测试必须能独立运行，不依赖网络或外部服务。

---

## 6. Git 工作流

### 6.1 分支策略
- `main` / `master`: 可生产部署，受保护
- `develop`: 开发集成分支
- `feat/<scope>-<description>`: 功能分支
- `fix/<scope>-<description>`: 修复分支
- `hotfix/<description>`: 紧急修复 (从 main 拉出)

### 6.2 Commit 规范 (Conventional Commits)
```
<type>(<scope>): <subject>

<body>

<footer>
```
- **type:** `feat | fix | docs | style | refactor | test | chore | perf | ci`
- **subject:** 祈使句，不超过 50 字符，不加句号
- **body:** 说明动机和变更内容，每行 ≤ 72 字符
- **footer:** Breaking Change / Issue 引用
- 示例: `feat(auth): add OAuth2 login flow`

### 6.3 PR 规则
- PR 必须关联 Issue。
- PR 标题遵循 Commit 规范。
- 自我 Review 后再请求他人 Review。
- PR 不超过 **400 行** 变更，超出时拆分。

---

## 7. 安全约束

- **SQL 注入:** 禁止字符串拼接 SQL，必须使用参数化查询。
- **XSS:** 对用户输入做 HTML 转义，使用框架的安全模板引擎。
- **CSRF:** 状态变更接口必须校验 CSRF Token。
- **认证/授权:** 每个非公开接口必须有 Auth 中间件保护。
- **密钥管理:** 禁止在日志中输出 Token/密码/密钥。
- **依赖安全:** 定期运行 `npm audit` / `pip-audit` / `snyk test`。
- **文件上传:** 校验文件类型、大小限制，不信任 Content-Type。
- **速率限制:** 公开 API 必须配置 Rate Limiting。

---

## 8. 性能约束

- 数据库查询禁止 N+1，使用预加载 (eager loading) 或 JOIN。
- 列表接口必须分页，默认 page=1, pageSize=20，最大 pageSize=100。
- 单次查询返回数据量不超过 **1000 条**。
- 避免在循环中做 I/O (数据库查询/HTTP 请求)。
- 长耗时操作 (>2s) 使用异步任务队列处理。
- 对频繁读取的数据使用缓存，缓存必须有过期时间。
- API 响应时间目标: P95 < 300ms (读写接口), P95 < 2s (复杂查询)。

---

## 9. AI 助手行为约束

### 9.1 代码生成
- **不要臆造 API:** 如果不确定某个 API 是否存在，先查文档或搜索，不要猜。
- **不要生成假数据:** 测试数据使用明确的 mock 值，不要用 "lorem ipsum"。
- **保持已有风格:** 生成的代码必须与周围代码风格一致。
- **最小变更原则:** 只改需要改的部分，不要顺手重构无关代码。
- **不要删除已有注释和类型声明** 除非它们确实是错误的。

### 9.2 依赖与版本
- 不要擅自升级依赖版本。
- 新增依赖时标注版本号，不要用 `latest`。
- 优先使用项目已有的工具链 (如已有 ESLint 就不要引入 Prettier)。

### 9.3 安全边界
- **不要执行破坏性命令** (`rm -rf`, `DROP TABLE`, `git push --force`) 除非用户明确确认。
- **不要修改 `.env` / `docker-compose.yml` / CI 配置** 除非被要求。
- **不要自动安装全局包。**
- **不要提交密钥、Token、密码到版本库。**

### 9.4 沟通
- 如果任务有多种实现方式，先列出选项让用户选择，不要自行决定。
- 如果遇到不确定的需求，先提问再写代码。
- 完成任务后简要说明做了什么、改了哪些文件、有什么风险。
- 不要输出大段无用的解释，保持简洁。

---

## 10. 环境与工具链

| 工具 | 用途 | 版本要求 |
|------|------|----------|
| Node.js | 运行时 | >= 20.x |
| <包管理器> | 依赖管理 | <pnpm/npm/yarn> |
| <测试框架> | 单元测试 | <Jest/Vitest/Pytest> |
| <Linter> | 代码检查 | <ESLint/Ruff/golangci-lint> |
| <格式化> | 代码格式 | <Prettier/black> |
| Docker | 容器化 | >= 24.x |

> 按实际项目填写。

### 常用命令
```bash
# 安装依赖
<package_manager> install

# 启动开发服务器
<package_manager> dev

# 运行测试
<package_manager> test

# 代码检查
<package_manager> lint

# 构建
<package_manager> build
```

---

## 11. 禁止事项 (Do NOT)

- [ ] 不要在 `main` 分支上直接提交代码
- [ ] 不要提交 `.env` 文件
- [ ] 不要在生产代码中使用 `console.log` / `print()` 调试代码
- [ ] 不要使用 `any` 类型 (TS) 或忽略类型错误
- [ ] 不要在代码中硬编码 URL、端口、密钥
- [ ] 不要创建未使用的变量/导入
- [ ] 不要用 `// eslint-disable` 绕过检查，除非有充分理由并注释说明
- [ ] 不要在 API 响应中暴露内部错误堆栈
- [ ] 不要信任用户输入——永远校验

---

## 12. 检查清单 (提交前)

- [ ] 代码通过 Lint 检查
- [ ] 代码通过类型检查
- [ ] 所有测试通过
- [ ] 新功能有对应的测试
- [ ] 没有引入新的安全风险
- [ ] 没有硬编码的配置/密钥
- [ ] 没有遗留的 `console.log` / `print` / `debugger`
- [ ] PR 描述清晰，关联了 Issue
- [ ] 变更不超过合理范围 (≤ 400 行)


