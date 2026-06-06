# MathMentor

**[English](#english)** · **[中文](#中文)**

---

<a id="english"></a>

## English

AI Socratic tutor for university Calculus (I–II). Guides students through structured questioning — **never gives answers directly**.

> Canonical architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

### Features

- **Multi-agent orchestration** — Orchestrator → Analyzer → Teaching → Student Model → Practice
- **SSE streaming chat** — live token output + `agent_trace` debug panel
- **Mastery tracking** — EMA scores for limits / derivatives / integrals
- **Personalized practice** — post-session exercises with spaced repetition
- **Answer-leak guard** — LLM check + deterministic heuristics
- **Standalone analyze endpoint** — `POST /v1/analyze` for demo-only classification
- **Rate limiting** — quotas on messages, sessions, and analyze calls
- **i18n** — English / Chinese UI (react-i18next)

### Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 · FastAPI · Vertex AI (Gemini) / DeepSeek (optional) |
| Frontend | React 19 · Vite · Tailwind CSS · KaTeX · MathLive |
| Database | MongoDB Atlas |
| Auth | Google OAuth 2.0 → JWT |
| Deploy | Google Cloud Run (API + Web) |

### Architecture

```
┌─────────────────────────────────────────┐
│  React SPA (Chat · Mastery · Exercises) │
└──────────────────┬──────────────────────┘
                   │ HTTPS / SSE
┌──────────────────▼──────────────────────┐
│  FastAPI + Multi-agent Orchestrator     │
│  Analyzer · Teaching · StudentModel ·   │
│  Practice · Analytics                   │
└──────┬───────────────────────┬──────────┘
       │                       │
  Vertex AI / DeepSeek    MongoDB Atlas
  (Gemini Pro / Flash)
```

### Prerequisites

- **Python** ≥ 3.12
- **Node.js** ≥ 18 (20+ recommended)
- **MongoDB Atlas** cluster (or local MongoDB)
- **Google Cloud** project with Vertex AI API enabled (or DeepSeek API as alternative)
- **Google OAuth Client ID** (optional — use Dev Login locally)

### Quick start

#### 1. Clone

```bash
git clone <repo-url>
cd math_mentor_agent
```

#### 2. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env   # fill in required values
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running:

- Swagger UI (dev): http://localhost:8000/docs
- Health check: http://localhost:8000/v1/health

#### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 — Vite proxies `/api` → `localhost:8000`.

#### 4. Sign in

- **Local dev** — use **Dev Login** on the login page (`APP_ENV≠production`)
- **Google OAuth** — set the same Client ID in backend and frontend:

```bash
# backend/.env
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com

# frontend/.env
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

#### 5. Seed problem library (optional)

```bash
cd backend
python ../infra/scripts/seed_problem_library.py
```

### Environment variables

#### Backend (`backend/.env`)

Copy `backend/.env.example` to `.env`:

| Variable | Description | Required |
|----------|-------------|----------|
| `MONGODB_URI` | MongoDB connection string | ✅ |
| `MONGODB_DB_NAME` | Database name (default `mathmentor`) | ✅ |
| `JWT_SECRET` | JWT signing secret | ✅ |
| `GCP_PROJECT` | Google Cloud project ID | For Vertex AI |
| `VERTEX_LOCATION` | Vertex AI region | For Vertex AI |
| `GEMINI_MODEL_PRO` | Reasoning / planning model | ✅ |
| `GEMINI_MODEL_FLASH` | Tutoring / routing model | ✅ |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | Optional |
| `CORS_ORIGINS` | Allowed frontend origins | ✅ |
| `DEEPSEEK_API_KEY` | DeepSeek API key | Optional LLM alt |

**Vertex AI setup:**

1. Enable [Vertex AI API](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com)
2. Billing enabled on the project
3. Service account with `roles/aiplatform.user`, or run `gcloud auth application-default login`

#### Frontend (`frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | API URL for production builds (local dev uses Vite proxy) |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth Client ID |

### Project structure

```
math_mentor_agent/
├── backend/                 # FastAPI API
│   ├── app/
│   │   ├── agents/          # Multi-agent implementations
│   │   ├── api/v1/          # REST + SSE endpoints
│   │   ├── db/              # MongoDB client + repositories
│   │   ├── models/          # Pydantic models
│   │   └── services/        # Vertex AI / session services
│   ├── tests/
│   └── openapi.yaml
├── frontend/                # React + Vite SPA
│   └── src/
│       ├── pages/           # Chat · Dashboard · Exercises …
│       ├── components/      # UI incl. AgentTracePanel
│       └── hooks/           # SSE consumer, etc.
├── docs/
│   ├── ARCHITECTURE.md      # Canonical design doc
│   └── DEMO_SCRIPT.md       # 5-minute demo script
└── infra/
    ├── cloudbuild.yaml
    ├── deploy/              # Cloud Run manifests
    └── scripts/             # Seed scripts
```

### Tests

```bash
cd backend
pytest tests/ -q
```

### Deploy (Google Cloud Run)

```bash
gcloud builds submit --config=infra/cloudbuild.yaml
```

Services in [`infra/deploy/`](infra/deploy/):

| Service | Description |
|---------|-------------|
| `mathmentor-api` | FastAPI backend |
| `mathmentor-web` | Vite build + nginx (static + `/api` reverse proxy) |

### API reference

| Resource | URL |
|----------|-----|
| Swagger UI | http://localhost:8000/docs (non-production) |
| OpenAPI spec | [`backend/openapi.yaml`](backend/openapi.yaml) |

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/sessions` | Create tutoring session |
| `POST` | `/v1/sessions/{id}/messages` | Send message (SSE stream) |
| `POST` | `/v1/sessions/{id}/stuck` | Request stronger hint |
| `POST` | `/v1/analyze` | Standalone problem analysis (demo) |
| `GET` | `/v1/me` | Student profile + mastery |
| `GET` | `/v1/exercises/due` | Due practice queue |

### Demo

See [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — 5-minute hackathon walkthrough covering Reasoning, Planning, Memory, and Multi-agent collaboration.

### Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — agents, database, API, roadmap
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — live demo script
- [`backend/openapi.yaml`](backend/openapi.yaml) — OpenAPI specification

---

<a id="中文"></a>

## 中文

面向大学微积分（Calculus I–II）的 AI 苏格拉底式辅导系统。通过结构化提问引导学生自行发现解法，**从不直接给出最终答案**。

> 架构设计详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

### 核心功能

- **多智能体协作**：Orchestrator → Analyzer → Teaching → Student Model → Practice
- **SSE 流式对话**：实时 token 输出 + `agent_trace` 调试面板
- **掌握度追踪**：limits / derivatives / integrals 三主题的 EMA 评分
- **个性化练习**：会话结束后生成针对性习题，支持间隔重复
- **答案泄露防护**：LLM 检测 + 确定性启发式双重拦截
- **独立分析接口**：`POST /v1/analyze` 可单独演示题目分类
- **速率限制**：消息、会话、分析接口均有配额控制
- **国际化**：前端支持中文 / 英文（react-i18next）

### 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12 · FastAPI · Vertex AI (Gemini) / DeepSeek（可选） |
| 前端 | React 19 · Vite · Tailwind CSS · KaTeX · MathLive |
| 数据库 | MongoDB Atlas |
| 认证 | Google OAuth 2.0 → JWT |
| 部署 | Google Cloud Run（API + Web 双服务） |

### 系统架构概览

```
┌─────────────────────────────────────────┐
│  React SPA（Chat · Mastery · Exercises） │
└──────────────────┬──────────────────────┘
                   │ HTTPS / SSE
┌──────────────────▼──────────────────────┐
│  FastAPI + 多智能体 Orchestrator         │
│  Analyzer · Teaching · StudentModel ·    │
│  Practice · Analytics                    │
└──────┬───────────────────────┬──────────┘
       │                       │
  Vertex AI / DeepSeek    MongoDB Atlas
  (Gemini Pro / Flash)
```

### 环境要求

- **Python** ≥ 3.12
- **Node.js** ≥ 18（推荐 20+）
- **MongoDB Atlas** 集群（或本地 MongoDB）
- **Google Cloud** 项目（启用 Vertex AI API，或使用 DeepSeek API 作为替代）
- **Google OAuth Client ID**（可选，本地开发可用 Dev Login）

### 快速开始

#### 1. 克隆仓库

```bash
git clone <repo-url>
cd math_mentor_agent
```

#### 2. 启动后端

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env   # 编辑 .env，填入必要配置
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端启动后访问：

- API 文档（开发环境）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/v1/health

#### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：http://localhost:5173（Vite 开发服务器会将 `/api` 代理到 `localhost:8000`）

#### 4. 登录

- **本地开发**：在登录页使用 **Dev Login**（`APP_ENV≠production` 时始终可用）
- **Google 登录**：在前后端配置相同的 Client ID：

```bash
# backend/.env
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com

# frontend/.env
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

#### 5. 导入题库（可选）

```bash
cd backend
python ../infra/scripts/seed_problem_library.py
```

### 环境变量

#### 后端（`backend/.env`）

复制 `backend/.env.example` 为 `.env`，主要配置项：

| 变量 | 说明 | 必填 |
|------|------|------|
| `MONGODB_URI` | MongoDB 连接字符串 | ✅ |
| `MONGODB_DB_NAME` | 数据库名（默认 `mathmentor`） | ✅ |
| `JWT_SECRET` | JWT 签名密钥 | ✅ |
| `GCP_PROJECT` | Google Cloud 项目 ID | Vertex AI 必填 |
| `VERTEX_LOCATION` | Vertex AI 区域 | Vertex AI 必填 |
| `GEMINI_MODEL_PRO` | 推理/规划模型 | ✅ |
| `GEMINI_MODEL_FLASH` | 辅导/路由模型 | ✅ |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | 可选 |
| `CORS_ORIGINS` | 允许的前端来源 | ✅ |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 可选替代 LLM |

**Vertex AI 前置条件：**

1. 启用 [Vertex AI API](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com)
2. 项目已开通计费
3. 服务账号具备 `roles/aiplatform.user` 权限，或执行 `gcloud auth application-default login`

#### 前端（`frontend/.env`）

| 变量 | 说明 |
|------|------|
| `VITE_API_URL` | 生产构建时的 API 地址（本地开发无需设置，使用 Vite 代理） |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth Client ID |

### 项目结构

```
math_mentor_agent/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── agents/          # 多智能体实现
│   │   ├── api/v1/          # REST + SSE 接口
│   │   ├── db/              # MongoDB 连接与 Repository
│   │   ├── models/          # Pydantic 数据模型
│   │   └── services/        # Vertex AI / 会话服务
│   ├── tests/               # 单元测试
│   └── openapi.yaml         # OpenAPI 规范
├── frontend/                # React + Vite 前端
│   └── src/
│       ├── pages/           # 页面（Chat · Dashboard · Exercises …）
│       ├── components/      # UI 组件（含 AgentTracePanel）
│       └── hooks/           # SSE 消费等 Hooks
├── docs/
│   ├── ARCHITECTURE.md      # 架构设计（权威文档）
│   └── DEMO_SCRIPT.md       # 5 分钟演示脚本
└── infra/
    ├── cloudbuild.yaml      # Cloud Build 流水线
    ├── deploy/              # Cloud Run 服务配置
    └── scripts/             # 数据种子脚本
```

### 测试

```bash
cd backend
pytest tests/ -q
```

### 部署（Google Cloud Run）

```bash
gcloud builds submit --config=infra/cloudbuild.yaml
```

Cloud Run 服务配置见 [`infra/deploy/`](infra/deploy/)：

| 服务 | 说明 |
|------|------|
| `mathmentor-api` | FastAPI 后端 |
| `mathmentor-web` | Vite 构建产物 + nginx（静态资源 + `/api` 反向代理） |

### API 文档

| 资源 | 地址 |
|------|------|
| Swagger UI | http://localhost:8000/docs（非生产环境） |
| OpenAPI 规范 | [`backend/openapi.yaml`](backend/openapi.yaml) |

主要接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/sessions` | 创建辅导会话 |
| `POST` | `/v1/sessions/{id}/messages` | 发送消息（SSE 流式响应） |
| `POST` | `/v1/sessions/{id}/stuck` | 请求更强提示 |
| `POST` | `/v1/analyze` | 独立题目分析（演示用） |
| `GET` | `/v1/me` | 学生档案 + 掌握度 |
| `GET` | `/v1/exercises/due` | 到期练习队列 |

### 演示指南

参见 [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)，包含 5 分钟 Hackathon 演示路径，涵盖 Reasoning、Planning、Memory、Multi-agent 四个支柱的讲解要点。

### 相关文档

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 完整架构设计（智能体、数据库、API、路线图）
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — 现场演示脚本
- [`backend/openapi.yaml`](backend/openapi.yaml) — OpenAPI 接口规范
