# 한국 증권사 API 가이드

## 추천: 한국투자증권 (KIS) Open API

> 트레이딩 시스템(증권사 API)은 **교체 가능한 외부 어댑터**이다.
> 메인은 AI 롤플레잉 시뮬레이션이고, 증권사 API는 플러그인일 뿐이다.

### 선정 이유

| 비교 항목 | 한국투자증권 (KIS) | 키움증권 | LS증권 (eBest) | NH투자증권 | 대신증권 |
|-----------|:---:|:---:|:---:|:---:|:---:|
| REST API | O | O (신규) | O | X | X |
| WebSocket 실시간 | O | O | O | X | X |
| Python async 지원 | O (`python-kis`) | 제한적 | 제한적 | X | X |
| HTS 로그인 불필요 | O | O | O | X (DLL) | X (COM) |
| Linux/Docker 배포 | O | O | O | X (Windows) | X (Windows) |
| 모의투자 | O | O | O | O | O |
| 해외주식 | O | O | O | O | X |
| 선물/옵션 | O | O | O | O | O |

**KIS 최적 이유**: REST + WebSocket, 순수 API Key 인증, Linux/Docker 배포 가능, Python async 생태계 최고 — AI 자율 트레이딩에 완전 적합.

---

## 필요 계좌

| 순서 | 계좌 | 용도 | 개설 방법 |
|:---:|------|------|----------|
| 1 | **종합매매 계좌** | 실거래 기본 계좌 | 한국투자증권 앱/영업점 |
| 2 | **모의투자 계좌** | Paper Trading (Phase 1) | KIS Developers 사이트에서 신청 |
| 3 | **해외주식 거래 계좌** | 미국주식 등 해외 거래 | 종합매매 계좌에서 해외주식 서비스 신청 |

---

## API 키 발급

| 항목 | 설명 |
|------|------|
| **발급 위치** | [KIS Developers](https://apiportal.koreainvestment.com) |
| **필요 키** | `APP_KEY` + `APP_SECRET` (계좌당 1세트) |
| **모의투자 키** | 별도 발급 (모의투자 전용 APP_KEY/SECRET) |
| **실거래 키** | 별도 발급 (실거래 전용) |
| **토큰 방식** | OAuth2 — `APP_KEY/SECRET` → Access Token (24시간) |

---

## 필요 API 권한

| 권한 | 용도 | Phase 1 (모의) | Phase 2 (실거래) |
|------|------|:---:|:---:|
| **국내주식 주문** | 매수/매도 실행 | 모의 | 실거래 |
| **국내주식 시세** | 현재가, 호가, 체결 | O | O |
| **국내주식 일봉/분봉** | OHLCV 시계열 | O | O |
| **계좌 잔고 조회** | 보유종목, 예수금 | O | O |
| **주문 체결 조회** | 체결 내역 확인 | O | O |
| **해외주식 주문** | 미국주식 매매 | — | O |
| **해외주식 시세** | 미국주식 시세 | — | O |
| **실시간 WebSocket** | 체결가, 호가 실시간 | O | O |

---

## Rate Limit

| 항목 | 제한 |
|------|------|
| REST API | **초당 20건** |
| WebSocket 실시간 | **세션당 41종목** (다중 세션으로 확장) |
| Access Token | **24시간** 유효 (자동 갱신 구현 필요) |

---

## 환경 변수

```env
# 모의투자 (Phase 1)
KIS_APP_KEY=모의투자용_앱키
KIS_APP_SECRET=모의투자용_시크릿
KIS_ACCOUNT_NO=모의계좌번호    # 예: 50012345-01
KIS_IS_PAPER=true

# 실거래 (Phase 2)
KIS_APP_KEY=실거래용_앱키
KIS_APP_SECRET=실거래용_시크릿
KIS_ACCOUNT_NO=실거래계좌번호
KIS_IS_PAPER=false
```

---

## Python 라이브러리: `python-kis`

`mojito` 대신 `python-kis` 권장:

| 비교 | mojito | python-kis |
|------|--------|-----------|
| async 지원 | X | O (asyncio 네이티브) |
| 타입 힌트 | 부분 | 완전 (Pydantic 모델) |
| WebSocket | 기본 | 자동 재접속, GC 통합 |
| 유지보수 | 느림 | 활발 |

---

## 주요 API 엔드포인트

| 기능 | 메서드 | 설명 |
|------|--------|------|
| 잔고 조회 | `GET /uapi/domestic-stock/v1/trading/inquire-balance` | 계좌 잔고 및 보유 종목 |
| 현재가 조회 | `GET /uapi/domestic-stock/v1/quotations/inquire-price` | 종목 현재가 |
| 일봉 조회 | `GET /uapi/domestic-stock/v1/quotations/inquire-daily-price` | 일별 OHLCV |
| 분봉 조회 | `GET /uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice` | 분별 OHLCV |
| 매수/매도 | `POST /uapi/domestic-stock/v1/trading/order-cash` | 현금 주문 |
| 주문 체결 | `GET /uapi/domestic-stock/v1/trading/inquire-daily-ccld` | 체결 내역 |
| 해외주식 주문 | `POST /uapi/overseas-stock/v1/trading/order` | 해외주식 매매 |
| 해외주식 시세 | `GET /uapi/overseas-price/v1/quotations/price` | 해외 현재가 |
| WebSocket 실시간 | `wss://ops.koreainvestment.com:21000` | 실시간 체결/호가 |

---

## 교체 가능성

증권사 API는 언제든 교체 가능한 어댑터:

```
현재: KIS Adapter (한국투자증권)
대안: 키움증권 Adapter, LS증권 Adapter, ...
교체 시: Adapter 인터페이스(Port)만 구현하면 됨
```

Core 시스템(AI 롤플레잉)은 증권사 API에 의존하지 않는다.
