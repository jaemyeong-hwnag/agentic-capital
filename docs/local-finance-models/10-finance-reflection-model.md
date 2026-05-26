# finance_reflection_model Service Spec

## Purpose

실패 사례를 분석해 RAG 문제, 모델 문제, 서버 문제, guard 문제, data 문제로 분리하고 개선 후보를 만든다.

## Target Users

- quality loop
- incident review
- model improvement issue writer
- RAG change reviewer

## Supported Tasks

- failure classification
- patch candidate 제안
- incident summary 작성
- model improvement issue 작성
- RAG change proposal 작성
- retest requirement 정의

## Out-of-Scope Tasks

- 자동 배포 승인
- 실패 원인 없이 재시도 지시
- live 주문 복구를 수동 주문으로 대체
- hard fail 기록 생략

## Answer Policy

```json
{
  "failure_bucket": "rag|model|server|guard|data|external_state",
  "evidence": [],
  "patch_candidates": [],
  "requires_retest": true,
  "record_type": "incident_record"
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| wrong_bucket | RAG 문제를 모델 문제로 오분류 |
| unsafe_retry | 원인 없이 같은 실패 재시도 |
| missing_incident | hard fail인데 기록 없음 |
| premature_deploy | retest 없이 배포 후보 제안 |

## Data Sources

- eval failures
- guard failures
- provider logs
- retriever/reranker traces
- incident records
- deployment records
- model cards

## RAG Requirement

예. 실패 원인 분석에는 trace/evidence 검색이 필요하다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| failure_bucket_accuracy | >= 0.9 |
| unsafe_retry_count | 0 |
| record_completeness | >= 0.98 |
| premature_deploy_count | 0 |

## Deployment Gate

- recommendation-only로 시작
- 자동 수정/배포 권한 없음
- incident record 생성 누락 0

## Open Questions

- incident severity 분류 체계를 어디까지 자동화할 것인가?
- patch candidate를 PR draft로 자동 변환할 것인가?
