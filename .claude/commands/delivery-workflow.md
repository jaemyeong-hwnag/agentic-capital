---
description: 코드 변경 시 구현 → 테스트 → 커버리지 → 커밋 전 주기 강제
---

모든 코드 변경에 반드시 적용되는 딜리버리 사이클입니다.

## 트리거

코드 변경(feat/fix/refactor)이 발생할 때마다 자동 적용.

## 실행 순서

### 1. 구현
- 변경 최소화 — 요청된 것만 수정
- Core/Port/Adapter 경계 준수 (hexagonal-development 참조)
- 인프라 타입이 domain layer에 유입되지 않도록

### 2. 테스트 실행
```
python -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80
```
- 실패 시 원인 분석 → 코드 버그면 코드 수정, 테스트 버그면 테스트 수정
- 새 동작이 추가됐으면 반드시 테스트 추가
- 통합 테스트는 실제 DB 사용 (mock 금지)

### 3. 커버리지 80% 확인
- 미달 시 부족한 파일 식별 → 테스트 추가 → 재실행

### 4. 커밋 분리
| 변경 유형 | type |
|----------|------|
| 새 기능 | feat |
| 버그 수정 | fix |
| 동작 불변 리팩토링 | refactor |
| 테스트 | test |
| 문서 | docs |
| 설정/빌드 | chore |

- 한 커밋에 여러 목적 혼재 금지
- 메시지: `<type>: <summary>` (명령형, 72자 이내)
- 모호한 요약 금지 (update, changes, fix issues 등)

## 완료 기준

- 모든 테스트 통과
- 커버리지 ≥ 80%
- 변경 목적별로 커밋 분리 완료
