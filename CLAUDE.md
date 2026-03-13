# Agentic Capital - 프로젝트 규칙

## 프로젝트 개요
AI 페르소나 기반 투자 시뮬레이션 펀드 회사 운영 프로젝트

## 언어
- 코드: Python
- 문서: 한국어 (기술 용어 영문 병기)

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
