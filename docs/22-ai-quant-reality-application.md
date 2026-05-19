# AI 퀀트 현실 적용 정의

## 핵심 재정의

`Agentic Capital`은 **AI가 바로 종목을 맞히는 봇**이 아니다.

이 프로젝트는 자율 투자 AI 에이전트가 실제 비용을 이기며 돈을 벌 수 있는지 검증하고, 실패한 행동을 빠르게 폐기하며, 살아남은 행동만 재사용 가능한 자산으로 축적하는 **AI-native 투자 실험 인프라**다.

```
목적: 돈을 번다
1차 실행 기준: 비용 포함 순수익이 양수인 행동만 생존
2차 실행 기준: 실패한 판단을 완전히 기록하고 반복하지 않음
3차 실행 기준: 수익성 있는 에이전트/전략/도구를 재사용 가능한 자산으로 축적
```

## 현실 인식

한국 AI 퀀트/로보어드바이저 시장은 알파 자체보다 다음 항목에서 돈이 난다.

| 영역 | 현실 |
|------|------|
| 직접 알파 운용 | AUM 확보가 어렵고 운용보수만으로 사업 유지가 어렵다 |
| AI ETF/펀드 | 트랙레코드와 마케팅 신뢰 자산 역할이 크다 |
| B2B 솔루션 | 은행, 보험, 운용사에 모델/시그널/엔진을 공급하는 구조가 현실적이다 |
| 퇴직연금 일임 | 정합성, 감사 로그, 리밸런싱, 위험성향 관리가 핵심 가치다 |
| 트레이딩 인프라 | 시세, 주문, 리스크, 회계, 관측성이 장기 가치다 |

따라서 이 프로젝트의 장기 가치는 단일 전략 수익률이 아니라 **검증 가능한 AI 투자 운영 기록과 실행 인프라**에 있다.

## 프로젝트 적용 원칙

### 1. 알파보다 비용 먼저

모든 성과 평가는 총손익이 아니라 비용 차감 후 순손익 기준이다.

```
real_pnl =
  gross_pnl
  - brokerage_fee
  - tax
  - slippage
  - spread_cost
  - ai_api_cost
  - infra_cost
```

현재 시스템은 `net_today`로 일일 AI 운영비를 에이전트에게 노출하고, `agent_cycles`에 사이클 단위 AI 비용 추정치를 기록한다.

### 2. No-Trade Alpha 인정

거래하지 않는 판단도 수익 행동이다.

```
No-Trade Alpha:
기대값이 음수인 거래를 회피하여 자본, 수수료, AI 호출 비용을 보존하는 의사결정 수익.
```

에이전트는 거래를 강제받지 않는다. 유효한 결론은 `trade`, `wait`, `skip_trade`, `observe`, `request_wakeup` 모두가 될 수 있다.

### 3. Decision ROI

AI 판단은 호출 비용 대비 성과로 평가한다.

```
decision_roi = net_pnl_generated / ai_cost_spent
```

사이클 시점에 실현 손익이 없으면 `ai_cost_krw`만 먼저 기록하고, 사후 분석에서 체결/포지션/수익 데이터를 조인해 실현 ROI를 계산한다.

### 4. Agent Survival Rule

에이전트의 자율성은 결과 평가를 피하지 못한다.

```
일정 기간 net_pnl <= 0 이고 decision_roi <= 1 이면
전략 수정, 권한 축소, 자본 회수, 해고 후보가 된다.
```

CEO 에이전트는 이 데이터를 바탕으로 채용, 해고, 역할 생성, 자본 배분을 결정해야 한다.

### 5. Evidence-Based Autonomy

AI는 자유롭게 결정하지만 모든 행동은 증거로 남는다.

| 기록 대상 | 이유 |
|----------|------|
| tool_sequence | 어떤 정보를 보고 행동했는지 추적 |
| llm_reasoning | 판단 논리와 사후 결과 비교 |
| emotion_snapshot | 성격/감정이 성과에 미친 영향 분석 |
| economics_snapshot | AI 비용과 decision ROI 계산 |
| trades/fills/positions | 실제 손익 검증 |
| HR events | 조직 변화와 성과 연결 |

## 구현 반영

| 컴포넌트 | 적용 |
|----------|------|
| `SimulationRecorder.record_agent_cycle` | 사이클별 `ai_cost_krw`, `net_pnl_krw`, `decision_roi`, `economics_snapshot` 기록 |
| `AgentCycleModel` | AI 비용/ROI 분석 컬럼 보유 |
| `formats.compact.bal` | `AI_DAILY_OP_COST_KRW` 기반 `op_cost`, `net_today` 노출 |
| `build_agent_tools` | 비용 인식 잔고, 자유 거래/비거래, HR, 동적 도구 생성 제공 |
| `FuturesSessionGuard` | 자본 제약을 물리적 리스크 가드로 구현 |
| `FuturesVirtualAdapter` | KIS 모의투자 미니 선물 조회가 실패할 때 자본 한도 내 가상 미니 계약으로 paper loop 지속 |
| `build_futures_tools.get_futures_symbols` | 현재 자본으로 즉시 거절될 표준 선물 대신 거래 가능한 계약을 우선 노출 |

## 선물 스캘핑 운영 보정

최근 무매매 원인은 알파 부재가 아니라 **실행 가능한 상품 유니버스 부재**였다. 500만원 자본 한도에서 표준 KOSPI200 선물 1계약은 손실 가정 기준 자본 한도를 초과했고, KIS 모의투자는 미니 선물(`A30xxx`) 조회를 실패시켜 AI가 선택할 수 있는 작은 계약이 사라졌다.

수정된 운영 기준은 다음과 같다.

```
1. KIS paper mode에서는 실계좌 API를 유지하되, 미니 선물 조회 실패 시 가상 미니 계약을 추가한다.
2. AI에게 노출되는 심볼은 capital_limit, multiplier, futures_stop_loss_pct 기준으로 필터링한다.
3. 표준 선물은 자본 한도 초과 시 숨기고, 미니 선물이 감당 가능하면 미니를 우선 노출한다.
4. 실제 KIS 체결 조회는 선물/옵션 API가 요구하는 주문일자 파라미터로 호출한다.
```

이 보정은 실전 주문 우회가 아니다. `kis_is_paper=True`이고 `futures_virtual_paper_fallback=True`인 경우에만 시뮬레이션 지속성을 위해 적용된다. 실전 모드에서는 브로커가 실제 제공하는 계약과 체결만 사용한다.

## 로드맵 보정

| 단계 | 목표 |
|------|------|
| M6.1 | LLM 호출 비용, tool call 비용, 일일 운영비 계측 |
| M6.2 | 에이전트별 net PnL, decision ROI, turnover, drawdown 리더보드 |
| M6.3 | `skip_trade`, `wait`, `observe` 같은 비거래 판단을 명시 기록 |
| M6.4 | backtest, paper, live가 동일 recorder schema 사용 |
| M6.5 | CEO가 성과 데이터 기반으로 자본 회수, 권한 축소, 해고 결정 |
| M6.6 | 비용 포함 전략 생존성 리포트 생성 |

## 최종 정의

```
Agentic Capital은 AI 에이전트가 돈을 벌 수 있는지 낙관적으로 가정하는 프로젝트가 아니다.
돈 못 버는 AI를 빠르게 죽이고, 비용을 이기는 행동만 축적하는 투자 실험 인프라다.
```
