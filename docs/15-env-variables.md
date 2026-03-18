# 환경 변수 (Environment Variables)

## `.env` 파일 구조

```env
# ============================================================
# LLM API
# ============================================================
GEMINI_API_KEY=                    # Google AI Studio API Key (Gemini 2.5 Flash)
OPENAI_API_KEY=                    # OpenAI API Key (text-embedding-3-large) — 임베딩용, 선택

# ============================================================
# Database
# ============================================================
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/agentic_capital
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                    # Qdrant Cloud 사용 시

# ============================================================
# 거래소 API — 한국투자증권 (1차 어댑터 — 국내 주식 + 선물 + 해외주식 잔고)
# ============================================================
KIS_APP_KEY=                       # 한국투자증권 App Key
KIS_APP_SECRET=                    # 한국투자증권 App Secret
KIS_ACCOUNT_NO=                    # 계좌번호 (예: 50012345-01)
KIS_IS_PAPER=true                  # 모의투자=true, 실전=false

# ============================================================
# 거래소 API — 암호화폐 (Phase 2)
# ============================================================
BINANCE_API_KEY=                   # Binance API Key
BINANCE_SECRET_KEY=                # Binance Secret Key
UPBIT_ACCESS_KEY=                  # Upbit Access Key
UPBIT_SECRET_KEY=                  # Upbit Secret Key

# ============================================================
# 거래소 API — 미국 주식 직접 연동 (Phase 2)
# ============================================================
ALPACA_API_KEY=                    # Alpaca API Key
ALPACA_SECRET_KEY=                 # Alpaca Secret Key
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Paper Trading (기본)
# ALPACA_BASE_URL=https://api.alpaca.markets       # Live Trading

# ============================================================
# 시장 데이터
# ============================================================
YAHOO_FINANCE_ENABLED=true         # yfinance 사용 여부 (무료)

# ============================================================
# 시뮬레이션 설정
# ============================================================
SIMULATION_SEED=42                 # 랜덤 시드 (재현성)
INITIAL_CAPITAL=10000000           # 초기 자본금 (KRW)
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
| `KIS_APP_KEY` | **필수** | 1차 트레이딩 어댑터 — 국내 주식 + 선물 |
| `KIS_APP_SECRET` | **필수** | KIS 인증 |
| `KIS_ACCOUNT_NO` | **필수** | KIS 계좌번호 |
| `KIS_IS_PAPER` | **필수** | `true`=모의투자, `false`=실전 |
| `QDRANT_URL` | 선택 (Phase 2) | 초기에는 pgvector 사용, 확장 시 필요 |
| `BINANCE_*` | 선택 (Phase 2) | 암호화폐 거래 시 필요 |
| `UPBIT_*` | 선택 (Phase 2) | 국내 암호화폐 거래 시 필요 |
| `ALPACA_*` | 선택 (Phase 2) | 미국 주식 직접 거래 시 필요 |
| `OPENAI_API_KEY` | 선택 | Gemini 임베딩 사용 시 불필요 |
| `LANGCHAIN_*` | 선택 | 개발/디버깅 시 트레이싱 |
| `SIMULATION_SEED` | 선택 | 재현성 필요 시 |

## 실행 모드별 최소 환경 변수

### 주식 모드 (기본)
```
GEMINI_API_KEY          ← 필수
DATABASE_URL            ← 필수
REDIS_URL               ← 필수
KIS_APP_KEY             ← 필수
KIS_APP_SECRET          ← 필수
KIS_ACCOUNT_NO          ← 필수
KIS_IS_PAPER=true       ← 모의투자
INITIAL_CAPITAL=10000000
```

```bash
python -m agentic_capital.main
```

### 선물 단타 모드
```
GEMINI_API_KEY          ← 필수
DATABASE_URL            ← 필수
REDIS_URL               ← 필수
KIS_APP_KEY             ← 필수
KIS_APP_SECRET          ← 필수
KIS_ACCOUNT_NO          ← 필수
KIS_IS_PAPER=true       ← 모의투자
INITIAL_CAPITAL=10000000
```

```bash
python -m agentic_capital.main --futures
```

### Phase 2: 암호화폐 + 미국 주식 직접 연동
```
Phase 1 전부 +
BINANCE_API_KEY         ← 암호화폐
BINANCE_SECRET_KEY
UPBIT_ACCESS_KEY        ← 국내 암호화폐
UPBIT_SECRET_KEY
ALPACA_API_KEY          ← 미국 주식 직접
ALPACA_SECRET_KEY
KIS_IS_PAPER=false      ← 실전 전환
QDRANT_URL              ← 벡터 DB 확장
```
