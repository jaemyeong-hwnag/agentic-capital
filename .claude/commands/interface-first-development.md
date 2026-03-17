---
description: 인터페이스 우선 개발 — Port 계약 먼저 정의 후 구현
---

새 기능 추가 또는 어댑터 변경 시 Port 인터페이스를 먼저 정의합니다.

## 적용 시점

- 새 외부 시스템 연동 추가 (새 증권사, 데이터 공급자 등)
- 기존 Port 계약 변경
- Core ↔ Adapter 경계에 새 메서드 추가

## 실행 순서

### 1. 계약 식별
`ports/` 에서 관련 Port 클래스 확인:
- `ports/trading.py` — 주문 실행, 잔고, 포지션
- `ports/market_data.py` — 시세, 종목 정보

### 2. 계약 정의/수정
```python
# ports/trading.py 예시
class TradingPort(ABC):
    @abstractmethod
    async def buy(self, symbol: str, quantity: int) -> OrderResult: ...

    @abstractmethod
    async def get_balance(self) -> Balance: ...
```
- 파라미터/반환 타입에 인프라 전용 타입 사용 금지
- 단일 책임 원칙 — 하나의 Port는 하나의 관심사
- 기존 계약 확장 우선 (신규 Port 생성 최소화)

### 3. 계약 안정화 확인
- Core에서 새 메서드 호출 코드 작성
- 컴파일/임포트 오류 없는지 확인

### 4. 어댑터 구현
```python
# adapters/trading/kis.py
class KISTradingAdapter(TradingPort):
    async def buy(self, symbol: str, quantity: int) -> OrderResult:
        # KIS 전용 로직
        ...
```

### 5. 의존성 주입
`simulation/engine.py` 또는 `graph/workflow.py` 에서 어댑터 주입

### 6. 계약 동작 테스트
- Port 인터페이스 기준으로 테스트 작성
- 어댑터 구현체는 통합 테스트로 검증

## 핵심 제약

- 계약 서명에 인프라 타입 노출 금지 (`KISResponse`, `RawDict` 등)
- 계약 변경 전 Core 호출부 먼저 작성 (인터페이스 주도)
- 각 계약은 단일 책임
- 신규 cross-layer 의존성 생성 금지 (기존 Port 확장)

## 완료 기준

- Port 서명에 인프라 타입 없음
- Core는 Port만 참조, 어댑터 직접 참조 없음
- 계약 동작을 검증하는 테스트 존재
