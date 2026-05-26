# 환경 변수 (Environment Variables)

## `.env` 파일 구조

```env
# ============================================================
# LLM API
# ============================================================
GEMINI_API_KEY=                    # Google AI Studio API Key (LLM_PROVIDER=gemini일 때만)
OPENAI_API_KEY=                    # OpenAI API Key (text-embedding-3-large) — 임베딩용, 선택
LLM_PROVIDER=local                 # local | gemini. LOCAL_LLM_PROVIDER alias도 지원
LOCAL_LLM_BASE_URL=http://127.0.0.1:8080/v1
LOCAL_LLM_MODEL=finance_decision_model
LOCAL_EMBEDDING_MODEL=finance_embedding_model
LOCAL_LLM_API_KEY=                 # 로컬 gateway 인증을 켠 경우에만 사용
LOCAL_LLM_TIMEOUT_SECONDS=30
LOCAL_LLM_TEMPERATURE=0.2
LOCAL_LLM_SEND_NATIVE_TOOLS=false  # OpenAI native tools payload 전송 opt-in
DOMAIN_LLM_FORGE_ROOT=/Users/tpirates/workspace-hjm/domain-llm-forge
DOMAIN_LLM_FORGE_ENV=/Users/tpirates/workspace-hjm/domain-llm-forge/.env
DOMAIN_MODEL_FORGE_ENV=/Users/tpirates/workspace-hjm/domain-model-forge/.env
RAG_SERVICE=finance_decision_model

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
| `GEMINI_API_KEY` | Gemini 모드 필수 | `LLM_PROVIDER=gemini`일 때 에이전트 reasoning provider |
| `LLM_PROVIDER` | **필수** | 기본값은 `local`. `gemini` 또는 `local` 계열만 허용하며, 알 수 없는 값은 Gemini로 fallback하지 않고 실패한다. `LOCAL_LLM_PROVIDER`도 호환 alias로 읽음 |
| `LOCAL_LLM_BASE_URL` | local 모드 필수 | OpenAI-compatible 로컬 서버 또는 domain-llm-forge RAG Gateway `/v1` base URL |
| `LOCAL_LLM_MODEL` | local 모드 필수 | 기본값 `finance_decision_model` |
| `LOCAL_AGENT_LLM_MODEL` | local 모드 선택 | CEO/Analyst 등 일반 ReAct agent용 로컬 모델. 기본값 `agentic_capital_react_model`. Trader finance 전용 flow는 `LOCAL_LLM_MODEL`의 finance sidecar 모델들을 단계별로 호출한다 |
| `LOCAL_EMBEDDING_MODEL` | local 모드 필수 | 기본값 `finance_embedding_model` |
| `LOCAL_LLM_API_KEY` | 선택 | 로컬 gateway 인증이 있을 때만 사용. 공백이면 Authorization header 미전송 |
| `LOCAL_LLM_TIMEOUT_SECONDS` | 선택 | 로컬 LLM/RAG 요청 timeout |
| `LOCAL_LLM_TEMPERATURE` | 선택 | 로컬 chat completion temperature |
| `LOCAL_LLM_SEND_NATIVE_TOOLS` | 선택 | 기본값 `false`. domain-llm-forge RAG Gateway처럼 OpenAI native tool payload를 받지 않는 서버에는 tool schema를 compact system prompt로만 전달한다. vLLM/llama-server 등 native tool calling을 검증한 서버에서만 `true`로 켠다 |
| `LOCAL_FINANCE_PIPELINE_ENABLED` | 선택 | 기본값 `true`. local provider + finance model + Trader cycle이면 ReAct 대신 `rag_query -> tool_plan -> tool 결과 -> decision -> risk_guard` 전용 flow 사용 |
| `LOCAL_FINANCE_DEFAULT_SYMBOL` | 선택 | finance sidecar payload에 symbol이 없을 때 쓰는 기본 종목. 기본값 `005930` |
| `LOCAL_FINANCE_RISK_PER_TRADE_PCT` | 선택 | finance sidecar용 risk metadata 기본값. 실제 주문 권한은 부여하지 않음 |
| `DOMAIN_LLM_FORGE_ROOT` | sidecar 실행 시 필수 | `scripts/run_local_finance_sidecar.sh`가 실행할 domain-llm-forge root |
| `DOMAIN_LLM_FORGE_ENV` | 선택 | domain-llm-forge `.env` 경로. 값은 source만 하고 출력/커밋하지 않음 |
| `DOMAIN_MODEL_FORGE_ENV` | 선택 | domain-model-forge `.env` 경로. 값은 source만 하고 출력/커밋하지 않음 |
| `RAG_SERVICE` | sidecar 실행 시 필수 | 기본값 `finance_decision_model` |
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
LLM_PROVIDER=local      ← 로컬 sidecar 사용 시. Gemini 기준선은 gemini
LOCAL_LLM_BASE_URL=http://127.0.0.1:8080/v1
LOCAL_LLM_MODEL=finance_decision_model
LOCAL_EMBEDDING_MODEL=finance_embedding_model
LOCAL_LLM_SEND_NATIVE_TOOLS=false
GEMINI_API_KEY          ← LLM_PROVIDER=gemini일 때 필수
DATABASE_URL            ← 필수
REDIS_URL               ← 필수
KIS_APP_KEY             ← 필수
KIS_APP_SECRET          ← 필수
KIS_ACCOUNT_NO          ← 필수
KIS_IS_PAPER=true       ← 모의투자
INITIAL_CAPITAL=10000000
FUTURES_LIVE_ORDERS_ENABLED=false  ← 실전 모드에서도 기본값은 주문 차단(read-only)
```

```bash
python -m agentic_capital.main
```

로컬 finance RAG Gateway를 사용할 때는 별도 터미널에서 다음처럼 sidecar를 먼저 띄운다. 실제 secret 값은
`/Users/tpirates/workspace-hjm/domain-llm-forge/.env` 또는
`/Users/tpirates/workspace-hjm/domain-model-forge/.env`에서 해당 프로젝트가 직접 읽게 두고, 이 저장소에는 값 자체를 복사하지 않는다.

```bash
bash scripts/run_local_finance_sidecar.sh
```

이 스크립트는 기본적으로 `finance_decision_model` RAG Gateway를 `127.0.0.1:8080`에 띄운다. 포트를 바꾸려면 `PORT=18000 bash scripts/run_local_finance_sidecar.sh`처럼 실행하고, 앱 쪽은 `LOCAL_LLM_BASE_URL=http://127.0.0.1:18000/v1`로 맞춘다.

### 선물 단타 모드
```
LLM_PROVIDER=local      ← 로컬 sidecar 사용 시
LOCAL_LLM_BASE_URL=http://127.0.0.1:8080/v1
LOCAL_LLM_MODEL=finance_decision_model
LOCAL_EMBEDDING_MODEL=finance_embedding_model
LOCAL_LLM_SEND_NATIVE_TOOLS=false
GEMINI_API_KEY          ← LLM_PROVIDER=gemini일 때 필수
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
KIS_IS_PAPER=false      ← 실전 계좌 조회 전환
FUTURES_LIVE_ORDERS_ENABLED=true   ← 실전 선물 주문 명시적 허용
QDRANT_URL              ← 벡터 DB 확장
```

## 실전 주식 실행 체크

`KIS_IS_PAPER=false`인 주식 모드는 KIS 실전 계좌를 사용한다. 실행 전 최소 검증은 다음 순서로 한다.

```
1. KIS token 발급 성공
2. get_balance로 total/available 조회 성공
3. get_positions로 보유 종목 조회 성공
4. 매수 주문은 price 또는 quote 기반 예상 주문금액이 available/capital_limit 이하인지 확인
```

시장가 매수처럼 `price`가 비어 있는 주문은 `market_data.get_quote()`로 현재가를 가져와 위험 한도를 계산한다. 현재가 조회도 실패하면 주문은 `price_required_for_buy_risk_check`로 거절된다.

주식 모드의 유효 주문 가능액은 다음 값이다.

```
effective_available = min(kis_available_cash, capital_limit)
```

따라서 계좌 총평가액이 크더라도 이미 보유 주식에 묶여 현금 주문가능액이 작으면 신규 매수는 제한된다. 기존 보유 주식 매도는 실전 주문이므로, 실전 실행 전 `get_positions` 결과를 반드시 확인한다.
