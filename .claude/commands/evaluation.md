---
description: AI 에이전트 출력 품질 평가 — 결정 품질, 수익성, 행동 일관성 측정
---

에이전트 의사결정 품질과 시스템 개선 여부를 측정합니다.

## 평가 워크플로우

```
데이터셋 수집 → 평가자 작성 → 베이스라인 측정 → 변경 적용 → 재측정 → delta 비교 → 반복
```

## 평가 데이터셋 구조

### 결정 수준 (Decision-level)
| 입력 | 기대 출력 |
|------|----------|
| 시장 상태 + 에이전트 상태 | BUY/SELL/HOLD + 신뢰도 |

### 단계 수준 (Step-level)
| 입력 | 기대 중간 단계 |
|------|--------------|
| cycle trigger | 잔고 조회 → 포지션 확인 → 분석 → 결정 |

### 궤적 수준 (Trajectory-level)
| 입력 | 기대 행동 시퀀스 |
|------|----------------|
| 1시간 시장 데이터 | 수익 실현 궤적 |

## 평가 지표

### 코드 평가자 (결정론적)
```python
# 예시
def eval_has_decision(cycle_result: dict) -> tuple[float, str]:
    has = len(cycle_result["decisions"]) > 0
    return (1.0 if has else 0.0), "decision made" if has else "no decision"

def eval_profit_per_hour(trades: list) -> tuple[float, str]:
    pnl = sum(t["pnl"] for t in trades)
    return (1.0 if pnl > 0 else 0.0), f"PnL={pnl}"
```

### LLM-as-Judge (의미론적)
- 결정 근거의 논리성
- 퍼소날리티와 결정의 일관성 (성격 → 행동 정합)
- 1시간 수익 목표 달성 여부

## 핵심 규칙

- **코드 평가자 우선**: 측정 가능한 기준은 코드로 평가
- **score + reason 필수**: 모든 평가자는 `(float, str)` 반환
- **다른 모델로 판단**: LLM-as-Judge는 gemini-2.5-flash가 아닌 다른 모델 사용
- **베이스라인 먼저**: 변경 전 반드시 현재 성능 기록
- **회귀 감지**: 변경 후 주요 지표가 하락하면 롤백

## 평가 실행

```bash
# DB에서 최근 시뮬레이션 결과 조회 후 평가
python -m pytest tests/evaluation/ -v
```

## 완료 기준

- 대표 입력 커버하는 데이터셋 존재
- 각 평가자가 score + reason 반환
- 베이스라인 기록됨
- 회귀 감지 가능
