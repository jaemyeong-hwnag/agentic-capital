# Agentic Capital - 프로젝트 규칙

## 프로젝트 개요
AI 페르소나 기반 투자 롤플레잉 시뮬레이션. 유일한 목적: 돈 벌기. 유일한 제약: 자산/자본.

## 최상위 원칙 (위계 순서)
1. **돈을 번다** — 유일한 목적, 변경 불가 (최상위)
2. **모든 것은 AI 친화적이다** — #1 아래에서, 모든 설계/데이터/소통/DB/포맷/인프라가 AI 소비 최적화 (대주제)
3. **데이터셋 최대 최적화** — #1, #2 아래에서, 최신 논문 기반 토큰 효율/정확도 극대화

## 핵심 설계 원칙
- **메인은 AI 롤플레잉** — 돈 버는 게 목적, 투자 종목/방법/조사방법 등 일체 제한 없음, 제약은 자산/자본만
- **트레이딩 시스템(증권사 API)은 교체 가능한 어댑터** — Core와 Adapter를 Port 인터페이스로 분리
- 롤플레잉 → 모든 AI 에이전트는 최대 자율성 (직급, 권한, 인사, 전략 등 전부 AI가 자율 결정)
- 에이전트 소통 언어/포맷은 AI 친화적이면 자유 (영어, 바이너리, 벡터, TOON 등)
- 모든 기록은 논문 참고 가능 수준으로 DB에 저장 (재현성, 추적성, 스냅샷)

## 언어
- 코드: Python 3.12+
- 문서: 한국어 (기술 용어 영문 병기)
- 에이전트 소통: AI 친화적 포맷 자유 선택

## 작업 완료 후 필수 후처리

**모든 코드 변경 명령어 완료 후 반드시 순차 실행:**

1. **테스트** → `pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80`
2. **커버리지 80% 미달 시** → 부족한 테스트 작성 후 재실행
3. **문서 정리** → 변경된 코드에 영향받는 docs/ 파일 업데이트, README 동기화
4. **커밋** → 목적별 분리 커밋 (코드/테스트/문서 각각)

> `/finalize` 명령어로 위 과정을 한 번에 실행할 수 있음

## 테스트 규칙
- 테스트 프레임워크: pytest
- **테스트 커버리지 80% 이상 필수** (`--cov-fail-under=80`)
- 통합 테스트는 실제 DB 사용 (mock 금지)
- 테스트 파일: `tests/` 디렉토리, `test_` 접두사

## 커밋 규칙

- 작업이 완료되면 반드시 커밋까지 수행한다 (사용자가 별도 요청하지 않아도)
- 서로 다른 목적을 한 커밋에 섞지 않는다
- 테스트 통과 확인 후에만 커밋한다

### 커밋 메시지 형식

`<type>: <summary>`

- summary는 명령형, 72자 이내
- 허용 type: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- 모호한 요약 금지 (`update`, `changes`, `fix issues` 등)

예시:
- `feat: add latest-by-status shorts query API`
- `fix: prevent duplicate news topic collection`
- `refactor: simplify asset creation flow`
- `test: add NewsCollectionService coverage`
- `docs: update IMPLEMENTATION.md news collection strategy`

### 커밋 분리 기준

| 변경 유형 | type | 분리 여부 |
|----------|------|----------|
| 새 기능 추가 | feat | 독립 커밋 |
| 버그 수정 | fix | 독립 커밋 |
| 리팩토링 (동작 불변) | refactor | 독립 커밋 |
| 테스트 추가/수정 | test | 기능과 함께 또는 독립 |
| 문서 변경 | docs | 독립 커밋 |
| 설정/빌드 변경 | chore | 독립 커밋 |

## 버저닝 규칙

Semantic Versioning (`MAJOR.MINOR.PATCH`)을 따른다.

### 버전 올리는 시점

작업 완료 커밋 후 반드시 버전을 갱신하고 git tag를 생성한다.

### 버전 변경 기준

| 변경 유형 | 버전 증가 | 예시 |
|----------|----------|------|
| 기존 API/동작 호환 깨지는 변경 | MAJOR | 1.0.0 → 2.0.0 |
| 새 기능 추가 (`feat`) | MINOR | 1.0.0 → 1.1.0 |
| 버그 수정, 성능 개선, 리팩토링 (`fix`, `perf`, `refactor`) | PATCH | 1.0.0 → 1.0.1 |
| 테스트, 문서, 설정만 변경 (`test`, `docs`, `chore`) | 버전 변경 없음 | - |

## 문서 구조
- `docs/` 폴더에 주제별 분리
- 파일명: `XX-topic-name.md` (번호순)
- 코드 변경 시 관련 문서 동기화

## 슬래시 커맨드
- `/test` - 테스트 실행 및 커버리지 확인
- `/coverage` - 커버리지 분석 및 80% 달성
- `/version` - 시맨틱 버저닝 관리
- `/docs` - 문서 자동 정리 및 동기화
- `/security` - 보안 이슈 검토 및 감사
- `/finalize` - 작업 완료 후 테스트 → 커버리지 → 문서 정리 → 커밋 일괄 실행
- `/ai-optimize` - AI 소비 최적화 (토큰 최소화, AI 이해도 극대화) — env/md 제외, LLMLingua-2·TOON·XML-tag 적용
