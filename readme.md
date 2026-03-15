# Agentic Capital

**AI-Driven Autonomous Fund Simulation with Persona-Based Investment Agents**

An AI multi-agent roleplay simulation where autonomous agents with distinct personality traits operate a virtual fund company. Each agent makes independent investment decisions shaped by psychological parameters that evolve through experience.

> **One Goal:** Make money.
> **One Constraint:** Capital.
> **Everything else:** Fully autonomous AI decisions.

---

## Key Concepts

- **Roleplay Simulation** — Agents are not scripted; they autonomously decide investment timing, asset selection, strategy, and organizational structure
- **Personality-Driven** — Each agent has a 10D personality vector (Big5 + HEXACO + Prospect Theory) that influences all decisions and evolves over time
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
| Agent Memory | A-MEM (Zettelkasten) | 2x multi-hop reasoning (NeurIPS 2025) |
| Main DB | PostgreSQL 16 + TimescaleDB | Structured + time-series, Gorilla compression |
| Vector DB | pgvector (Phase 1) → Qdrant (Phase 2) | HNSW index for similarity search |
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
| [19 - Design Summary](docs/19-design-summary.md) | Complete design overview |
| [20 - Milestones](docs/20-milestones.md) | Implementation roadmap (M1-M7) |
| [21 - Design Validation](docs/21-design-validation.md) | Paper-based DB/dataset AI-friendliness audit |

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

# Install
pip install -e ".[dev]"

# Infrastructure (PostgreSQL + Redis)
docker compose up -d

# Configure
cp .env.example .env
# Edit .env: set API keys, initial_capital

# Run simulation
agentic-capital
```

## License

Non-Commercial License — see [LICENSE](LICENSE)
