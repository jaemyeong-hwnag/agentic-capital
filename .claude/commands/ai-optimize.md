---
description: AI 소비 최적화 — 토큰 최소화, AI 이해도 극대화 (LLMLingua-2, TOON, XML-tag 적용)
---

env, md 등 사람이 직접 입력하거나 읽는 파일을 제외한 모든 소스 코드를 AI 친화적으로 최적화합니다.

## 적용 범위

**포함** (AI가 소비하는 것):
- `src/` 내 Python 소스 파일
- 에이전트 시스템 프롬프트, 프롬프트 빌더
- 에이전트 간 통신 포맷, 툴 반환값
- DB 저장 포맷, 인메모리 데이터 구조

**제외** (사람이 입력/읽는 것):
- `.env`, `.env.*` 환경변수 파일
- `*.md` 문서 파일 (README, CHANGELOG, CLAUDE.md 등)
- `pyproject.toml`, `alembic.ini` 등 설정 파일
- `tests/` — 테스트는 사람이 작성/검토

## 최적화 원칙 (논문 기반)

### 1. LLMLingua-2 (Microsoft 2024, arXiv:2403.12968)
- 80%+ 토큰 절감, <2% 성능 손실
- 중복 자연어 레이블 제거 → 약어/키 사용
- 반복 패턴은 한 번 정의 후 재사용 (LEGEND 패턴)

### 2. XML 태그 (Anthropic 학습 데이터)
- Claude 네이티브 포맷 — 1토큰 오버헤드
- 구조화 데이터에 `<P>`, `<E>`, `<agent>`, `<schema>` 등 사용
- 장황한 JSON/YAML 레이블 대신 속성으로 압축

### 3. TOON 포맷 (프로젝트 내장)
- 테이블형 데이터 40-60% 절감: `@name[n](col1,col2)|row1|row2`
- 위치 참조 헤더 → 값만 나열
- `agentic_capital.formats.toon.to_toon()` 사용

### 4. 콤팩트 k:v (AutoGen 2023, CAMEL 2023)
- JSON 대비 ~70% 절감: `sym:005930,act:BUY,cf:0.87`
- 파이프 구분 메시지: `TYPE|FROM|TO|TS|k:v,k:v`
- `agentic_capital.formats.compact` 모듈 활용

### 5. "Lost in the Middle" (Stanford 2023, arXiv:2307.03172)
- 중요 정보를 프롬프트 시작/끝에 배치
- 성격/역할 → 시스템 프롬프트 최상단
- `LEGEND` 스키마를 세션 시작에 한 번만 주입

## 실행 절차

### Step 1: 최적화 대상 스캔
`src/` 를 전체 탐색하여 다음을 식별:
- 에이전트 프롬프트 문자열 (시스템 프롬프트, 사이클 트리거)
- 툴 반환값 (dict/list 반환 → compact string 변환 대상)
- 에이전트 간 메시지 content 필드
- 하드코딩된 장황한 설명/레이블

### Step 2: 카테고리별 최적화

**프롬프트/시스템 메시지:**
- 반복 자연어 → 약어 (Big5: `openness` → `O`, `loss_aversion` → `LA`)
- 구조 레이블 → XML 태그 (`<agent>`, `<P>`, `<E>`, `<phi>`)
- `LEGEND`를 세션 상단에 1회 주입, 이후 약어만 사용
- `MANDATE = "GOAL=profit|LIMIT=capital|METHOD=any|STOP=done"` 재사용

**툴 반환값:**
- dict 반환 → compact string (`"tot:X,avl:Y,ccy:Z"`)
- list[dict] 반환 → TOON 테이블
- 에러 → `"ERR:reason"` 형식

**에이전트 간 통신:**
- content: dict → compact k:v 문자열
- 메시지 wire: `TYPE|FROM|TO|TS|k:v,k:v`
- `formats/compact.msg_encode()` 사용

**데이터 구조 필드명:**
- AI가 처리하는 dict/dataclass 키 → 약어 (`symbol` → `sym`, `quantity` → `qty`)
- DB 컬럼은 유지 (마이그레이션 영향)

### Step 3: 검증
최적화 후 반드시:
1. 테스트 실행: `.venv/bin/pytest tests/ -v --tb=short`
2. 의미 동등성 확인 (동일 정보, 더 적은 토큰)
3. AI 파싱 가능성 확인 (약어가 LEGEND에 정의되어 있는지)

### Step 4: 커밋
- `refactor: optimize AI token efficiency in <module>` 형식
- 파일/모듈 단위로 분리 커밋

## 빠른 체크리스트

```
[ ] 시스템 프롬프트에 LEGEND 주입?
[ ] 성격 벡터가 <P>O C E A N H LA RAG RAL PW</P> 형식?
[ ] 감정 상태가 <E>V AR D ST CF</E> 형식?
[ ] 툴이 dict 대신 compact string 반환?
[ ] 테이블 데이터에 TOON 포맷?
[ ] 에이전트 메시지에 TYPE|FROM|TO|TS|k:v 형식?
[ ] 장황한 JSON/YAML 레이블 → k:v 압축?
[ ] MANDATE 상수 재사용?
```

## 참고 모듈

- `agentic_capital.formats.compact` — LEGEND, MANDATE, psych(), bal(), pos(), fills(), order(), msg_encode()
- `agentic_capital.formats.toon` — to_toon()
- `agentic_capital.core.communication.protocol` — MessageType (SIG/INSTR/RPT/QRY/ACK/ERR)
