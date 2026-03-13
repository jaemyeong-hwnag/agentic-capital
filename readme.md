# Agentic Capital

**AI-Driven Autonomous Fund Simulation with Persona-Based Investment Agents**

An AI multi-agent roleplay simulation where autonomous agents with distinct personality traits operate a virtual fund company. Each agent makes independent investment decisions shaped by psychological parameters that evolve through experience.

> **One Goal:** Make money.
> **One Constraint:** Capital.
> **Everything else:** Fully autonomous AI decisions.

---

## Key Concepts

- **Roleplay Simulation** — Agents are not scripted; they autonomously decide investment timing, asset selection, strategy, and organizational structure
- **Personality-Driven** — Each agent has a 15D personality vector (Big5 + HEXACO + Prospect Theory) that influences all decisions and evolves over time
- **Dynamic Organization** — Roles, permissions, hierarchy are created/modified/abolished by agents themselves
- **AI-Native Data** — All data formats optimized for AI consumption (TOON, NumeroLogic, LACP protocol), not human readability
- **Research-Grade Logging** — Every decision, state change, and interaction is recorded for reproducibility and academic analysis

## Architecture

```
┌─────────────────────────────────────────────────┐
│  CORE (Main — Immutable Purpose)                │
│  AI Roleplay Simulation                         │
│  Agent personality/emotion/decision/org autonomy │
│  Purpose: Make money (no restrictions on         │
│  assets, methods, research approaches)           │
│                                                  │
│  CEO Agent (full autonomy)                       │
│  ├── Portfolio Manager                           │
│  ├── Risk Manager                                │
│  ├── Analyst Team (dynamic)                      │
│  └── Trader                                      │
│  ※ CEO reshapes structure autonomously           │
├─────────────────────────────────────────────────┤
│  ADAPTERS (Plugins — Swappable)                  │
│  Trading APIs are replaceable external adapters  │
│  ┌───────┐ ┌─────────┐ ┌────────┐             │
│  │  KIS  │ │ Binance │ │ Alpaca │  ...        │
│  └───────┘ └─────────┘ └────────┘             │
└─────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.12+ | AI ecosystem standard |
| Agent Framework | LangGraph v1.0 | Stateful graph workflows, proven in finance (FinCon, TradingAgents) |
| Agent Memory | A-MEM (Zettelkasten) + Mem0 | 2x multi-hop reasoning (NeurIPS 2025) |
| Main DB | PostgreSQL 16 + TimescaleDB | Structured + time-series, Gorilla compression |
| Vector DB | pgvector → Qdrant | float8, SQ int8, HNSW |
| Cache/State | Redis 7+ | Working memory, emotion state, event streams |
| Analytics | DuckDB + Parquet + Arrow IPC | Offline analysis, backtesting, data export |
| LLM | Gemini 2.5 Pro / Flash | Pro: key decisions, Flash: routine tasks |
| Prompt Format | TOON + Markdown-KV + YAML | 40-60% token reduction |
| Agent Comms | LACP protocol + MessagePack | Structured messages (PLAN/ACT/OBSERVE/SIGNAL) |

## Data Pipeline

```
LLM ↔ Agent     TOON (arrays) + Markdown-KV (records) + YAML (nested) + NumeroLogic (numbers)
Agent ↔ Agent    LACP protocol (PLAN/ACT/OBSERVE/SIGNAL) + MessagePack serialization
Agent ↔ Memory   A-MEM Zettelkasten notes (context + keywords + links + q_value)
Agent ↔ DB       PostgreSQL JSONB + TimescaleDB compressed hypertables
Analysis         Arrow IPC (in-memory) → Parquet (persistence) → DuckDB (OLAP)
```

## Documentation

| Doc | Content |
|-----|---------|
| [01 - Project Overview](docs/01-project-overview.md) | Core concept, principles, how it works |
| [02 - AI Trends](docs/02-ai-trends-research.md) | Agentic workflows, multi-agent systems |
| [03 - Psychology Models](docs/03-psychology-models.md) | Big5, HEXACO, Prospect Theory, personality drift |
| [04 - Feasibility](docs/04-feasibility.md) | Feasibility analysis, challenges |
| [05 - Tech Stack](docs/05-tech-stack.md) | Full tech stack with paper references |
| [06 - Cost Estimation](docs/06-cost-estimation.md) | Daily/monthly cost projections |
| [07 - References](docs/07-references-papers.md) | Key papers, search portals |
| [08 - Investment API](docs/08-investment-api-guide.md) | API pipeline, target markets |
| [09 - Persona Rules](docs/09-persona-investment-rules.md) | How personality drives investment behavior |
| [10 - Org Autonomy](docs/10-organization-autonomy.md) | Dynamic roles, permissions, HR autonomy |
| [11 - Data Model](docs/11-data-model.md) | AI-optimized database schema |
| [12 - Data Formats](docs/12-data-format-research.md) | Serialization, vector, time-series research |
| [13 - Tech Research](docs/13-detailed-tech-research.md) | Extended technology comparison |
| [14 - Dependencies](docs/14-dependencies.md) | Python packages by category |
| [15 - Env Variables](docs/15-env-variables.md) | Environment variables, .env template |
| [16 - External APIs](docs/16-external-apis.md) | LLM, exchange, market data APIs |
| [17 - Infrastructure](docs/17-infrastructure.md) | Docker Compose, Phase 1/2/3 infra |
| [18 - Korean Broker API](docs/18-korean-broker-api.md) | KIS API setup, accounts, permissions |

## Key Papers

| Paper | Venue | Applied To |
|-------|-------|-----------|
| FinCon | NeurIPS 2024 | Agent org structure (Manager-Analyst hierarchy) |
| TradingAgents | arXiv 2024 | Multi-agent trading framework |
| A-MEM | NeurIPS 2025 | Zettelkasten agent memory |
| REMEMBERER | 2025 | Q-value experience retention |
| StockTime | arXiv 2024 | Time-series tokenization for LLMs |
| NumeroLogic | EMNLP 2024 | Numerical representation for LLMs |
| TOON | 2025 | Token-optimized data serialization |
| LACP | NeurIPS 2025 | Agent communication protocol |
| C2C | 2025 | KV-cache semantic communication |
| Generative Agents | UIST 2023 | Observation-Reflection-Planning loop |

## Getting Started

```bash
# Clone
git clone https://github.com/your-org/agentic-capital.git
cd agentic-capital

# Setup (TBD)
pip install -e ".[dev]"

# Run simulation (TBD)
python -m agentic_capital.run
```

## License

TBD

---

# Agentic Capital (한국어)

**AI 페르소나 기반 자율 투자 펀드 시뮬레이션**

각각 고유한 성격 특성을 가진 AI 에이전트들이 가상 펀드 회사를 자율 운영하는 멀티 에이전트 롤플레잉 시뮬레이션. 각 에이전트는 심리학적 파라미터에 기반하여 독립적으로 투자 판단을 내리며, 경험을 통해 성격이 진화한다.

> **유일한 목적:** 돈을 번다.
> **유일한 제약:** 자본.
> **나머지 전부:** AI가 자율적으로 결정.

---

## 핵심 특징

- **롤플레잉 시뮬레이션** — 에이전트는 자율 판단으로 투자 시점, 종목, 전략, 조직 구조를 결정
- **성격 기반** — 15차원 성격 벡터 (Big5 + HEXACO + 전망이론)가 모든 판단에 영향, 경험으로 변동
- **동적 조직** — 직급, 권한, 조직 구조를 에이전트가 직접 생성/변경/폐지
- **AI 네이티브 데이터** — 모든 데이터 포맷이 AI 소비에 최적화 (TOON, NumeroLogic, LACP)
- **논문급 기록** — 모든 결정, 상태 변화, 상호작용을 재현 가능하게 기록

## 설계 원칙

1. **목표: 돈을 번다** — 유일한 목적, 변경 불가
2. **모든 것은 AI 친화적** — 최상위 규칙 외 전부 AI 최적화
3. **데이터셋 최대 최적화** — 최신 논문 (2024-2026) 기반 스펙

## 문서

| 문서 | 내용 |
|------|------|
| [01 - 프로젝트 개요](docs/01-project-overview.md) | 핵심 컨셉, 원칙, 동작 방식 |
| [02 - AI 트렌드 조사](docs/02-ai-trends-research.md) | 에이전틱 워크플로우, 멀티 에이전트 |
| [03 - 심리학 모델](docs/03-psychology-models.md) | Big5, HEXACO, 전망이론, 성격 변동 |
| [04 - 가능성 분석](docs/04-feasibility.md) | 구현 가능성, 도전 과제 |
| [05 - 기술 스택](docs/05-tech-stack.md) | 확정 기술 스택 + 논문 근거 |
| [06 - 비용 계산](docs/06-cost-estimation.md) | 일별/월별 비용 추정 |
| [07 - 참고 논문](docs/07-references-papers.md) | 핵심 논문, 검색 포털 |
| [08 - 투자 API 가이드](docs/08-investment-api-guide.md) | API 파이프라인, 대상 시장 |
| [09 - 페르소나 투자 규칙](docs/09-persona-investment-rules.md) | 성격이 투자에 미치는 영향 |
| [10 - 조직 자율성](docs/10-organization-autonomy.md) | 동적 직급, 권한, 인사 자율 |
| [11 - 데이터 모델](docs/11-data-model.md) | AI 최적화 DB 스키마 |
| [12 - 데이터 포맷 연구](docs/12-data-format-research.md) | 직렬화, 벡터, 시계열 포맷 |
| [13 - 기술 상세 연구](docs/13-detailed-tech-research.md) | 기술 비교 상세 |
| [14 - 기술 스택 의존성](docs/14-dependencies.md) | Python 패키지 카테고리별 정리 |
| [15 - 환경 변수](docs/15-env-variables.md) | 환경 변수, .env 템플릿 |
| [16 - 외부 API](docs/16-external-apis.md) | LLM, 거래소, 시장 데이터 API |
| [17 - 인프라](docs/17-infrastructure.md) | Docker Compose, Phase 1/2/3 인프라 |
| [18 - 한국 증권사 API](docs/18-korean-broker-api.md) | KIS API 설정, 계좌, 권한 |
