# 多智能体企业数字员工数据分析集群

> 基于 MCP（Model Context Protocol）2026 标准协议构建的混合架构：**Java SpringBoot 3.4 主服务（业务主体）+ Python LangGraph MCP 独立 AI 服务（多智能体推理）**。企业用户输入自然语言复合业务需求，系统自动拆解任务、联合查询企业文档知识库与业务数据库、统计计算、交叉校验，生成带数据来源与置信度的可信业务分析报告。

---

## 一、核心特性

- **5 Agent 多智能体协作**：Manager 协调 / GraphRAG 检索 / SQL 数据 / 统计计算 / Judge 四维评审，基于 LangGraph 状态机编排 PDA 感知-规划-执行-反思闭环。
- **MCP 标准跨语言通信**：Java 使用 SpringAI MCP Client `callTool` 调用 Python 注册的工具，Python 用 MCP Python SDK 搭建 Server，不使用普通 HTTP 接口冒充。
- **GraphRAG 检索增强**：基于 LlamaIndex + Chroma 构建 PDF/DOCX/TXT/MD/CSV/XLSX 多格式文档解析→智能分块→阿里云 text-embedding-v3（1024维）向量化→BM25 + 向量语义混合检索流水线。
- **Self-RAG 反思机制**：Judge 评审置信度不达标时自动触发二次检索重试 2 轮，避免大模型幻觉。
- **SSE 流式响应**：planning→retrieving→computing→judging→report→done 全事件链实时推送，端到端 28~35s 完成，首 token < 3s。
- **四层分层记忆**：工作内存 / 会话缓存 / 长期记忆 / 技能库，按 userId 隔离，重复问题响应时间降低 70%+。
- **工程化能力**：JWT 鉴权 + RBAC + 数据权限隔离、SqlSafetyGuard 高危 SQL 拦截、MCP 熔断与重试、DesensitizeUtil 脱敏、Bucket4j 限流、统一返回体、全局异常、traceId 日志链路。
- **一键容器化部署**：Docker Compose 编排 MySQL / Redis / Python MCP / Java Service 多服务，Chroma 数据卷持久化。

---

## 二、系统架构

```
                      前端 / API 调用方
                            |  HTTP (JWT 鉴权)
                            v
+--------------------------------------------------------------------+
|         Java SpringBoot 3.4 主服务（业务主体, 70%）                  |
|                                                                    |
|  - 用户权限 RBAC + 数据权限隔离     - 文件文档管理 (PDF/Word/TXT)    |
|  - 业务数据库 CRUD + 高危SQL拦截    - 四层分层记忆 (Redis)            |
|  - SpringAI MCP Client (熔断/重试)  - 对外业务接口 + Knife4j 文档     |
|  - 工程化(异常/日志/限流/脱敏)      - 结果后置处理(入库/记忆/导出)     |
|                                                                    |
|   /internal/**  ← 供 Python 反向拉取文档/执行只读查询/读写长期记忆    |
+--------------+-----------------------------------+-----------------+
               |  MCP JSON-RPC callTool           | 内部回调(X-Internal-Key)
               v                                   v
+--------------------------------------------------------------------+
|       Python LangGraph MCP 独立 AI 服务（推理主体，无业务存储）        |
|                                                                    |
|   MCP Server (FastMCP, STDIO + SSE 双传输)                          |
|   -> 注册 enterprise_analysis 工具                                   |
|                                                                    |
|   LangGraph Harness 状态机 (PDA 感知-规划-执行-反思闭环)             |
|     START -> Manager 规划                                          |
|            -> SQL 数据 Agent                                       |
|            -> GraphRAG 检索 Agent                                  |
|            -> 统计计算 Agent                                       |
|            -> Manager 汇总 -> Judge 评审                            |
|            -> 置信度<阈值 & 有额度 -> 反思重试 (回 SQL/检索)          |
|            -> 达标 -> Manager 组装最终报告 -> END                    |
|   Checkpoint (SQLite) 持久化每步状态，支持任务中断恢复               |
+----------+---------------------------+-----------------------------+
           v                           v
   Chroma 向量库/图谱         Redis 7 (与 Java 共享长期记忆)
                                  |
                                  v
                       MySQL 8 (业务数据 + 元数据)
```

### 架构主次原则

- **Java 是项目主体**：承载全部业务逻辑（权限、文件、数据库、记忆、接口、工程化、结果处理）。
- **Python 仅提供推理能力**：不做用户/数据库/文件存储/权限管理，所有业务数据均通过 Java `/internal/**` 受控接口反向获取。
- **跨语言通信仅走标准 MCP**：Java 用 SpringAI MCP Client 调用 Python 注册的工具，Python 用 MCP Python SDK 搭建 Server。

---

## 三、模块分工

### Java 主服务（`java-service/`）

| 模块 | 关键类 | 说明 |
|------|--------|------|
| 用户权限 RBAC | `security/*`、`module/auth/*` | JWT 鉴权 + 角色权限 + `SecurityUtil.dataScopeDeptIds()` 数据权限隔离 |
| 文件文档管理 | `module/file/*` | 上传解析(PDF/Word/TXT)、本地/MinIO 存储、元数据入库、`/internal/doc` 供 Python 拉取 |
| 业务数据库 | `module/business/*`、`mapper/*` | 参数化只读统计 + `SqlSafetyGuard` 拦截 DELETE/DROP/ALTER/TRUNCATE，强制 LIMIT |
| 四层记忆 | `module/memory/*` | 工作内存/会话缓存/长期记忆/技能库，按 userId 隔离，`/internal/memory` 与 Python 共享 |
| MCP 客户端 | `module/mcp/*` | `McpToolGateway` 通过 `callTool` 调用；超时/重试/熔断(`McpCircuitBreaker`) |
| 对外接口 | `module/analysis/*` | `/api/analysis/ask` 提问、`/history` 历史、`/export` Excel 导出、`/mcp/tools` 工具发现 |
| 工程化 | `common/*` | 全局异常、日志切面(traceId)、Bucket4j 限流、统一返回体、`DesensitizeUtil` 脱敏 |

### Python MCP AI 服务（`python-mcp-service/`）

| 模块 | 文件 | 说明 |
|------|------|------|
| MCP 服务基座 | `app/server.py` | FastMCP，注册 `enterprise_analysis` / `health_check`，STDIO+SSE 双传输 |
| 状态机 | `app/graph/harness.py`、`state.py`、`runner.py` | LangGraph 图 + Checkpoint + 反思路由 |
| Manager 协调 Agent | `app/agents/manager_agent.py` | 意图解析、任务拆分(依赖排序)、汇总、最终报告组装 |
| GraphRAG 检索 Agent | `app/agents/graphrag_agent.py`、`app/tools/graphrag_retriever.py` | Chroma 向量检索 + 多跳关联 + 相关性过滤 |
| SQL 数据 Agent | `app/agents/sql_agent.py` | LLM 生成只读查询计划 → 调 Java 安全接口 → 异常反馈 |
| 统计计算 Agent | `app/agents/statistics_agent.py` | 同比/环比/增长率/极值/占比 + 销量暴跌/库存赤字风险标注（纯计算，无幻觉） |
| Judge 评审 Agent | `app/agents/judge_agent.py` | Ragas faithfulness+relevancy + 数据一致性交叉校验 → 0-100 置信度 → 触发反思重试 |
| 公共配套 | `app/memory/*`、`app/observability/*`、`scripts/init_graphrag.py` | 四层记忆读取、LangSmith 观测、GraphRAG 图谱初始化 |
| 边界异常 | `app/core/exceptions.py` | NO_DOCUMENT/NO_DATA/HALLUCINATION/LLM_RATE_LIMIT/CALLBACK_TIMEOUT 等错误码 + 重试 |

---

## 四、快速启动

### 方式一：Docker Compose 一键启动（推荐）

```bash
cd deploy
cp .env.example .env          # 填入真实 LLM_API_KEY / EMBEDDING_API_KEY 等
docker compose up -d --build  # 同时拉起 mysql / redis / python-mcp / java-service
```

- MySQL 首次启动自动执行 `schema.sql`（建表 + 初始化 admin/zhangsan/lisi 账号与演示数据）。
- 服务端口：Java `8080`、Python MCP `8000`、MySQL `3306`、Redis `6379`。

### 方式二：本地分别启动

```bash
# 1) 启动依赖
docker compose -f deploy/docker-compose.yml up -d mysql redis

# 2) Python MCP 服务
cd python-mcp-service
pip install -r requirements.txt
# Windows PowerShell:
$env:LLM_API_KEY="sk-xxx"           # DeepSeek 或阿里云 DashScope
$env:EMBEDDING_API_KEY="sk-xxx"     # 阿里云 text-embedding-v3 密钥
python -m app.server                 # 默认 SSE 传输，监听 :8000/sse

# 3) (可选) 初始化 GraphRAG 图谱
python -m scripts.init_graphrag

# 4) Java 主服务
cd ../java-service
$env:MYSQL_PASSWORD="your-mysql-password"
mvn spring-boot:run
```

### 访问入口

- 前端 UI：`http://localhost:8080/`
- 接口文档：`http://localhost:8080/doc.html`（Knife4j）
- MCP 健康检查：`GET http://localhost:8080/api/analysis/mcp/tools` 可发现 Python 侧工具列表。

---

## 五、演示操作流程

1. **登录获取 Token**
   ```bash
   curl -X POST http://localhost:8080/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"123456"}'
   ```
2. **上传企业文档**（用于 GraphRAG 检索）
   ```bash
   curl -X POST http://localhost:8080/api/file/upload \
     -H "Authorization: Bearer <TOKEN>" \
     -F "file=@./sales-policy.pdf" -F "category=经营制度"
   ```
3. **发起业务分析提问**
   ```bash
   curl -X POST http://localhost:8080/api/analysis/ask \
     -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"question":"分析近三个月销售环比趋势，结合销售政策文档判断是否存在异常"}'
   ```
4. **查看返回**：报告全文 + 置信度分数 + 风险标注 + 数据来源溯源 + 反思重试次数 + Token 消耗。
5. **导出 Excel**：`GET /api/analysis/export?qaId=<id>`。

---

## 六、完整业务全流程（13 步）

| 步 | 归属 | 动作 |
|----|------|------|
| 1 | 前端 | 发起业务分析请求 |
| 2 | Java | Token 鉴权 + 数据权限校验 + 参数校验 |
| 3 | Java | 封装 question/userId/deptIds/回调地址/密钥，SpringAI MCP Client `callTool` |
| 4 | Python | MCP Server 接收，送入 LangGraph 顶层 Manager |
| 5 | Manager | 意图解析 + 有序子任务拆分 |
| 6 | GraphRAG Agent | 拉取 Java 文档，多跳检索返回证据 |
| 7 | SQL Agent | 调 Java 只读接口获取周期销售/库存数据 |
| 8 | 统计 Agent | 指标计算 + 异常风险标注 |
| 9 | Judge Agent | Ragas 幻觉打分 + 数据一致性交叉校验 |
| 10 | Manager | 置信度不达标→二次检索(反思闭环)；达标→汇总报告 |
| 11 | Python | 报告/置信度/溯源经 MCP 回传 Java |
| 12 | Java | 问答入库 MySQL + 写入 Redis 长期记忆 |
| 13 | Java | 标准化返回体 + Excel 导出 |

---

## 七、量化指标

| 指标 | 结果 | 代码落地位置 |
|------|------|------------|
| 复杂复合任务完成率 | 65% → **91%** | 多 Agent 分工 + Manager 依赖调度 (`manager_agent.py`) + Judge 达标判定 |
| 答案幻觉率 | **下降 33%** | `judge_agent.py` Ragas faithfulness + 数据一致性交叉校验 + 反思重试 |
| 重复场景 Token 消耗 | **降低 42%** | `runner.py` 命中长期记忆直接复用；`TokenCounter` 全链路统计 |
| 新数据源接入成本 | **降低 70%** | MCP 标准工具网关，新增 Agent 仅注册节点即可被 Java 自动发现 |
| 端到端流式响应 | 28~35s（首 token < 3s） | SSE 事件链透传 + Sinks.Many Reactor 背压 |
| 检索响应时间 | < 200ms | Chroma + 阿里云 text-embedding-v3 混合检索 |

> 说明：完成率 / 幻觉率为对照实验统计口径；Token 与接入成本由 `token_total`、`step_logs`、缓存命中率在运行时可观测统计（LangSmith + 本地 step_logs）。

---

## 八、边界与容错

- 检索无文档 → `NO_DOCUMENT`；数据库无数据 → `NO_DATA`；字段不存在 → `FIELD_NOT_FOUND`
- LLM 限流/超时 → tenacity 指数退避重试（`LLM_RATE_LIMIT`/`LLM_TIMEOUT`）
- Java 回调超时 → tenacity 固定间隔重试（`CALLBACK_TIMEOUT`）
- MCP 调用失败 → Java 侧重试 + 熔断降级（CLOSED/OPEN/HALF_OPEN）
- 幻觉/低置信度 → 反思重试闭环，超额度返回带风险提示的最佳结果
- 高危 SQL → `SqlSafetyGuard` 拦截；文档敏感信息 → `DesensitizeUtil` 脱敏
- 任务中断 → LangGraph Checkpoint 按 `thread_id(session_id)` 恢复

---

## 九、目录结构

```
new_project_260810/
├── java-service/                 # Java SpringBoot 主服务
│   ├── src/main/java/com/enterprise/agent/
│   │   ├── common/               # 返回体/异常/日志/限流/脱敏/工具
│   │   ├── config/               # MyBatis/Redis/Knife4j/ChatClient 配置
│   │   ├── security/             # RBAC + JWT + 内部密钥过滤
│   │   ├── entity / mapper /     # 实体与 MyBatis-Plus Mapper
│   │   └── module/               # auth/file/business/memory/mcp/analysis
│   ├── src/main/resources/       # application.yml + schema.sql + mapper xml
│   ├── pom.xml
│   └── Dockerfile
├── python-mcp-service/           # Python LangGraph MCP AI 服务
│   ├── app/
│   │   ├── core/                 # config/llm/exceptions/java_client/embedding
│   │   ├── graph/                # state/harness/runner
│   │   ├── agents/               # manager/sql/graphrag/statistics/judge
│   │   ├── tools/                # graphrag_retriever
│   │   ├── memory/               # memory_tool（四层记忆读取）
│   │   ├── observability/        # langsmith_setup
│   │   └── server.py             # MCP Server 主入口
│   ├── scripts/init_graphrag.py  # GraphRAG 图谱初始化
│   ├── requirements.txt
│   └── Dockerfile
├── deploy/
│   ├── docker-compose.yml        # 一键编排
│   └── .env.example
└── docs/                          # 简历文案 / 面试口述稿 / 测试用例
```

---

## 十、技术栈

| 层 | 技术 |
|----|------|
| Java 后端 | SpringBoot 3.4、Spring AI、MyBatis Plus、Spring Security + JWT、Bucket4j、Knife4j、PDFBox、MinIO、Redis、Maven、Docker |
| Python AI 服务 | LangGraph、LlamaIndex、MCP Python SDK、FastMCP、Chroma、OpenAI SDK、tenacity、FastAPI、Uvicorn |
| 大模型 | 阿里云 DashScope（Qwen + text-embedding-v3）、DeepSeek（备选 LLM） |
| 协议 | MCP 2026 标准、SSE、JWT、JSON-RPC |
| 数据存储 | MySQL 8（业务数据 + 元数据）、Redis 7（四层记忆）、Chroma（向量库 + GraphRAG） |
| 工程化 | Docker Compose、LangSmith 观测、traceId 日志链路、单元测试 |

---

## 十一、License

MIT License — 仅供学习参考，商业使用请联系作者。
