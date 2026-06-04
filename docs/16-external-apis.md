# 외부 API 정리

## 1. LLM API

| API | 용도 | 인증 | 비용 모델 | 비고 |
|-----|------|------|----------|------|
| **DeepSeek API** | hosted 에이전트 추론 | API Key | 토큰 기반 (입력+출력) | `LLM_PROVIDER=deepseek`일 때 사용. 기본 모델 `deepseek-v4-flash` |
| **Google Gemini API** | Gemini batch/eval 또는 명시 baseline | API Key | 토큰 기반 (입력+출력) | `LLM_PROVIDER=gemini`일 때만 사용 |
| Local embedding server | 로컬 임베딩 | 로컬 gateway 설정에 따름 | 로컬 운영비 | hosted embedding API를 추가하지 않는다 |

### Hosted LLM 정책

| Provider | 기본 모델 | 사용 조건 |
|----------|----------|----------|
| `local` | `agentic_capital_react_model` + finance sidecars | 기본. 외부 LLM 비용/쿼터 없이 운영 |
| `deepseek` | `deepseek-v4-flash` | Gemini batch/eval이 아닌 hosted reasoning이 필요할 때 |
| `gemini` | `gemini-2.5-flash` | 명시적 Gemini baseline, batch/eval, 비교 실험 |

---

## 2. 거래소 API

### 암호화폐

| API | 시장 | 기능 | Python 패키지 | API 문서 |
|-----|------|------|-------------|---------|
| **Binance API** | 글로벌 암호화폐 | 현물/선물 매매, 잔고, 시세 | `ccxt` | https://binance-docs.github.io/apidocs |
| **Upbit API** | 국내 암호화폐 | 현물 매매, 잔고, 시세 | `ccxt` | https://docs.upbit.com |

#### 주요 엔드포인트 (ccxt 통합)

| 기능 | ccxt 메서드 | 설명 |
|------|-----------|------|
| 잔고 조회 | `exchange.fetch_balance()` | 계좌 잔고 |
| 시세 조회 | `exchange.fetch_ticker(symbol)` | 현재가, 거래량 |
| OHLCV | `exchange.fetch_ohlcv(symbol, timeframe)` | 시계열 캔들 데이터 |
| 매수 | `exchange.create_order(symbol, 'market', 'buy', amount)` | 시장가 매수 |
| 매도 | `exchange.create_order(symbol, 'market', 'sell', amount)` | 시장가 매도 |
| 주문 내역 | `exchange.fetch_orders(symbol)` | 주문 이력 |

### 미국 주식

| API | 시장 | 기능 | Python 패키지 | API 문서 |
|-----|------|------|-------------|---------|
| **Alpaca API** | 미국 주식 | 현물 매매, Paper Trading, 시세 | `alpaca-py` | https://docs.alpaca.markets |

#### 주요 엔드포인트

| 기능 | 메서드 | 설명 |
|------|--------|------|
| 잔고 조회 | `trading_client.get_account()` | 계좌 정보 |
| 시세 조회 | `data_client.get_stock_latest_quote(symbol)` | 실시간 시세 |
| 과거 데이터 | `data_client.get_stock_bars(symbol, timeframe)` | OHLCV |
| 매수/매도 | `trading_client.submit_order(order_data)` | 주문 실행 |
| 포지션 | `trading_client.get_all_positions()` | 보유 종목 |

### 국내 주식

| API | 시장 | 기능 | Python 패키지 | API 문서 |
|-----|------|------|-------------|---------|
| **한국투자증권 Open API** | KOSPI/KOSDAQ | 현물 매매, 잔고, 시세 | `python-kis` | https://apiportal.koreainvestment.com |

#### 주요 엔드포인트

| 기능 | 설명 |
|------|------|
| 잔고 조회 | 계좌 잔고 및 보유 종목 |
| 현재가 조회 | 종목 현재가, 호가 |
| 일봉 조회 | 일별 OHLCV |
| 매수/매도 | 지정가/시장가 주문 |
| 주문 체결 | 체결 내역 조회 |

---

## 3. 시장 데이터 API

| API | 용도 | 비용 | Python 패키지 |
|-----|------|------|-------------|
| **Yahoo Finance** | 글로벌 시세, 재무제표, 뉴스 | 무료 | `yfinance` |
| **Binance/Upbit** (시세) | 암호화폐 실시간 시세 | 무료 (거래소 API) | `ccxt` |
| **Alpaca Data** (시세) | 미국 주식 실시간/과거 데이터 | 무료 (기본) / 유료 (SIP) | `alpaca-py` |

---

## 4. 뉴스/감성 데이터 API (선택)

| API | 용도 | 비용 | 비고 |
|-----|------|------|------|
| **Alpaca News API** | 미국 주식 뉴스 | Alpaca 계정 포함 | Sentiment Analyst용 |
| **CryptoPanic API** | 암호화폐 뉴스/감성 | 무료 티어 | 암호화폐 감성 분석 |
| **NewsAPI** | 글로벌 뉴스 | 무료 100건/일 | 범용 뉴스 수집 |

---

## 5. API 사용량 정리

### 일일 예상 (에이전트 10명 기준)

| API | 일일 호출 | 제한 | 비고 |
|-----|----------|------|------|
| DeepSeek | provider 설정에 따른 agent cycle 수 | 계정/모델별 제한 | hosted reasoning opt-in |
| Local LLM/Embedding | agent cycle + sidecar 호출 | 로컬 하드웨어 제한 | 기본 runtime |
| Gemini | batch/eval 실행 수 | 계정/모델별 제한 | 명시 opt-in |
| 거래소 시세 | ~200회 | 1,200/분 (Binance) | 시장 데이터 수집 |
| 거래소 주문 | ~50회 | 10/초 (Binance) | 매매 실행 |
| Yahoo Finance | ~50회 | 비공식 (제한 없음) | 재무 데이터 |

### Rate Limit 대응

| 거래소 | 제한 | 대응 |
|--------|------|------|
| Binance | 1,200 req/min (시세), 10 orders/sec | ccxt rate limiter 자동 적용 |
| Upbit | 30 req/sec (시세), 8 req/sec (주문) | ccxt rate limiter |
| Alpaca | 200 req/min | alpaca-py 내장 throttle |
| 한국투자증권 | 초당 20건 | python-kis 내장 throttle |
