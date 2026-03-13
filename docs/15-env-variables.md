# 환경 변수 (Environment Variables)

## `.env` 파일 구조

```env
# ============================================================
# LLM API
# ============================================================
GEMINI_API_KEY=                    # Google AI Studio API Key (Gemini Pro/Flash)
OPENAI_API_KEY=                    # OpenAI API Key (text-embedding-3-large) — 임베딩용, 선택

# ============================================================
# Database
# ============================================================
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/agentic_capital
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                    # Qdrant Cloud 사용 시

# ============================================================
# 거래소 API — 암호화폐
# ============================================================
BINANCE_API_KEY=                   # Binance API Key
BINANCE_SECRET_KEY=                # Binance Secret Key
UPBIT_ACCESS_KEY=                  # Upbit Access Key
UPBIT_SECRET_KEY=                  # Upbit Secret Key

# ============================================================
# 거래소 API — 미국 주식
# ============================================================
ALPACA_API_KEY=                    # Alpaca API Key
ALPACA_SECRET_KEY=                 # Alpaca Secret Key
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Paper Trading (기본)
# ALPACA_BASE_URL=https://api.alpaca.markets       # Live Trading

# ============================================================
# 거래소 API — 국내 주식
# ============================================================
KIS_APP_KEY=                       # 한국투자증권 App Key
KIS_APP_SECRET=                    # 한국투자증권 App Secret
KIS_ACCOUNT_NO=                    # 계좌번호 (예: 50012345-01)
KIS_IS_PAPER=true                  # 모의투자 여부

# ============================================================
# 시장 데이터
# ============================================================
YAHOO_FINANCE_ENABLED=true         # yfinance 사용 여부 (무료)

# ============================================================
# 시뮬레이션 설정
# ============================================================
SIMULATION_SEED=42                 # 랜덤 시드 (재현성)
INITIAL_CAPITAL=1000000            # 초기 자본금 (USD)
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR

# ============================================================
# LangSmith (선택 — 트레이싱/디버깅)
# ============================================================
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=agentic-capital
```

## 필수 vs 선택

| 변수 | 필수 | 설명 |
|------|------|------|
| `GEMINI_API_KEY` | **필수** | LLM 핵심 — 없으면 에이전트 동작 불가 |
| `DATABASE_URL` | **필수** | 메인 DB — 모든 기록 저장 |
| `REDIS_URL` | **필수** | Working Memory, 감정 상태, 이벤트 |
| `QDRANT_URL` | 선택 (Phase 2) | 초기에는 pgvector 사용, 확장 시 필요 |
| `BINANCE_*` | 시장별 선택 | 암호화폐 거래 시 필요 |
| `UPBIT_*` | 시장별 선택 | 국내 암호화폐 거래 시 필요 |
| `ALPACA_*` | 시장별 선택 | 미국 주식 거래 시 필요 |
| `KIS_*` | 시장별 선택 | 국내 주식 거래 시 필요 |
| `OPENAI_API_KEY` | 선택 | Gemini 임베딩 사용 시 불필요 |
| `LANGCHAIN_*` | 선택 | 개발/디버깅 시 트레이싱 |
| `SIMULATION_SEED` | 선택 | 재현성 필요 시 |

## Phase별 필요 환경 변수

### Phase 1: 모의투자 (Paper Trading)
```
GEMINI_API_KEY          ← 필수
DATABASE_URL            ← 필수
REDIS_URL               ← 필수
ALPACA_API_KEY          ← Paper Trading
ALPACA_SECRET_KEY       ← Paper Trading
ALPACA_BASE_URL=https://paper-api.alpaca.markets
SIMULATION_SEED=42
INITIAL_CAPITAL=100000
```

### Phase 2: 실거래 (Live Trading)
```
Phase 1 전부 +
BINANCE_API_KEY         ← 암호화폐
BINANCE_SECRET_KEY
UPBIT_ACCESS_KEY        ← 국내 암호화폐
UPBIT_SECRET_KEY
KIS_APP_KEY             ← 국내 주식
KIS_APP_SECRET
KIS_ACCOUNT_NO
KIS_IS_PAPER=false
QDRANT_URL              ← 벡터 DB 확장
```
