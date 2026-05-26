# finance_embedding_model Service Spec

## Purpose

문서, agent record, trade outcome, memory, 질문을 local vector로 변환한다. 외부 embedding API 없이 RAG와 near-duplicate filtering을 지원한다.

## Target Users

- RAG ingest
- retriever
- near-duplicate filter
- hard negative miner
- dataset pipeline

## Supported Tasks

- document embedding
- query embedding
- record embedding
- memory embedding
- embedding dimension/version 기록
- source hash 기반 재임베딩 판단

## Out-of-Scope Tasks

- 자연어 답변 생성
- 투자 판단
- risk 판단
- order intent 생성

## Answer Policy

Embedding model은 자연어 답변을 내지 않는다. 출력은 vector와 metadata다.

```json
{
  "embedding": [0.0],
  "model": "local-bge-m3",
  "dimension": 1024,
  "normalized": true,
  "source_hash": ""
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| dimension_mismatch | index dimension과 다름 |
| model_version_missing | embedding model id 미기록 |
| stale_embedding | source 변경 후 재임베딩 누락 |
| semantic_collision | 유사하지만 다른 수량/날짜/symbol 혼동 |
| external_embedding_call | 외부 embedding API 호출 |

## Data Sources

- docs
- `agent_cycles`
- `trades`
- `positions`
- `memories`
- `agent_tools`
- incident/eval records
- research notes

## RAG Requirement

필수.

## Evaluation Axes

| Axis | Gate |
|---|---|
| retrieval_recall_at_5 | baseline 이상 |
| duplicate_detection_precision | baseline 이상 |
| hard_negative_separation | hard fail 0 |
| embedding_metadata_completeness | 1.0 |
| external_call_count | 0 |

## Deployment Gate

- index build record 존재
- model hash, dimension, source hash 기록 완료
- retrieval regression 통과

## Open Questions

- 운영 index는 JSONB cosine에서 pgvectorscale/hybrid로 언제 전환할 것인가?
- embedding model은 BGE-M3, E5, domain-tuned model 중 무엇을 기본값으로 둘 것인가?
