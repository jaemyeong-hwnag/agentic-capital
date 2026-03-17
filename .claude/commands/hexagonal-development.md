---
description: Hexagonal Architecture 준수 — Core/Port/Adapter 경계 유지
---

agentic-capital의 계층 구조를 설계하거나 수정할 때 적용합니다.

## 레이어 구조

```
core/          ← 도메인 (AI 롤플레잉, 에이전트, 의사결정)
  agents/      — 에이전트 페르소나, 감정, 성격
  decision/    — 의사결정 파이프라인
  tools/       — 에이전트가 사용하는 도구 (port 경유)
  organization/— HR, 조직 관리

ports/         ← 추상 인터페이스 (계약)
  trading.py   — 매수/매도/잔고/포지션 계약
  market_data.py — 시세/데이터 계약

adapters/      ← 외부 시스템 구현체
  trading/kis.py    — KIS 증권사 API
  trading/paper.py  — 페이퍼 트레이딩

formats/       ← AI 친화적 포맷 유틸리티
graph/         ← LangGraph 워크플로우 (orchestration)
simulation/    ← 시뮬레이션 엔진 (entry point)
```

## 변경 방향

내부 → 외부 순서로 변경 전파:
1. `core/` 도메인 로직 변경
2. `ports/` 인터페이스 계약 변경 (필요 시)
3. `adapters/` 구현체 변경
4. `graph/`, `simulation/` 조율 레이어 변경

## 핵심 제약

- **도메인 zero-dep**: `core/` 는 `adapters/`, `graph/`, `simulation/` import 금지
- **Port만 의존**: `core/tools/` 에서 trading/market_data 사용 시 반드시 port 인터페이스 경유
- **인프라 타입 격리**: KIS 전용 타입이 `core/` 나 `ports/` 에 나타나면 안 됨
- **어댑터 교체 가능**: KIS → 다른 증권사로 교체 시 `ports/` 구현체만 교환, core 변경 없음
- **명시적 변환**: 어댑터 응답 → 도메인 모델 변환 레이어 반드시 존재

## 검증 방법

```bash
# core가 adapters를 직접 import하는지 확인
grep -r "from agentic_capital.adapters" src/agentic_capital/core/
# 결과가 없어야 정상

# port가 adapters를 import하는지 확인
grep -r "from agentic_capital.adapters" src/agentic_capital/ports/
# 결과가 없어야 정상
```

## 완료 기준

- `core/` → `adapters/` 직접 의존 없음
- 모든 외부 시스템 접근은 `ports/` 인터페이스 경유
- 어댑터 교체 시 core 코드 무변경
