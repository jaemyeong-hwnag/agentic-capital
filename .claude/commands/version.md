---
description: 시맨틱 버저닝 관리 및 git tag 생성
---

프로젝트의 버전을 시맨틱 버저닝(SemVer) 규칙에 따라 관리합니다.

## 버전 변경 기준

| 변경 유형 | 버전 증가 | 예시 |
|----------|----------|------|
| 기존 API/동작 호환 깨지는 변경 | MAJOR | 1.0.0 → 2.0.0 |
| 새 기능 추가 (`feat`) | MINOR | 1.0.0 → 1.1.0 |
| 버그 수정, 성능 개선, 리팩토링 (`fix`, `perf`, `refactor`) | PATCH | 1.0.0 → 1.0.1 |
| 테스트, 문서, 설정만 변경 (`test`, `docs`, `chore`) | 버전 변경 없음 | - |

## 실행 순서

1. 현재 버전을 확인합니다:
   - `pyproject.toml` 또는 `setup.cfg`의 version 필드
   - `src/__version__.py` 또는 `__init__.py`의 `__version__`
   - `CHANGELOG.md` 최신 항목
   - `git tag --list 'v*' --sort=-v:refname | head -5`

2. 사용자가 지정한 버전 타입에 따라 버전을 올립니다.
   인자가 없으면 최근 커밋을 분석하여 자동 결정:
   - `fix:` / `refactor:` / `perf:` → PATCH
   - `feat:` → MINOR
   - `BREAKING CHANGE:` → MAJOR
   - `test:` / `docs:` / `chore:` → 버전 변경 없음 (안내만)

3. 다음 파일들을 업데이트합니다:
   - `pyproject.toml` (version 필드)
   - `src/__version__.py` (있는 경우)
   - `CHANGELOG.md` (새 버전 섹션 추가)

4. CHANGELOG.md 작성 규칙:
   - 날짜 포함: `## [1.2.0] - 2026-03-13`
   - 카테고리 구분: Added, Changed, Fixed, Removed
   - 최근 커밋 메시지 기반으로 항목 자동 생성

5. 버전 변경 커밋 및 태그 생성:
   - 커밋 메시지: `chore: bump version to X.Y.Z`
   - 태그 생성: `git tag vX.Y.Z`

## 사용법
- `/version` - 자동 감지하여 버전 업
- `/version patch` - 패치 버전 업
- `/version minor` - 마이너 버전 업
- `/version major` - 메이저 버전 업
