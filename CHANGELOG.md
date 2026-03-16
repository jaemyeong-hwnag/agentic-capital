# Changelog

## [0.15.0] - 2026-03-14

### Added
- `formats/compact.py`: AI-to-AI pipe-delimited message format (AutoGen 2023, MetaGPT, CAMEL 2023)
  - `msg_encode()`: `TYPE|FROM|TO|YYMMDDTHHMMZ|key:val,key:val` wire format
  - `msg_decode()`: pipe-delimited → routing dict
  - `LEGEND` updated with message schema: `SIG|INSTR|RPT|QRY|ACK|ERR fmt:TYPE|FROM|TO|TS|k:v,k:v`
- `protocol.py`: `MessageType` compact aliases (SIG, INSTR, RPT, QRY, ACK, ERR) with legacy backward-compat

### Changed
- `data_query.py` `send_message`: content changed from dict to compact k:v string; stores full wire format in messages_sink
- `AgentMessage.content`: `str | dict[str, object]` — supports compact wire format + legacy dict
- `SendMessageInput`: `content: str` (compact k:v), `type` default `"SIG"`

## [0.14.0] - 2026-03-14

### Added
- `formats/compact.py`: AI-to-AI compact encoding module (LLMLingua-2 + XML-tag + TOON)
  - `psych()`: `<P>O C E A N H LA RAG RAL PW</P>` + `<E>V AR D ST CF</E>` — ~75% token reduction
  - `bal/pos/fills/order/mem_entries()`: compact string tool outputs — 50-60% reduction
  - `LEGEND` schema defined once per session, implicit thereafter
  - `MANDATE`: `GOAL=profit|LIMIT=capital|METHOD=any|STOP=done`

### Changed
- System prompts (all agents + workflow): replaced verbose YAML-style personality blocks with compact XML tags
- Tool outputs (`data_query.py`): all tools now return compact strings instead of verbose dicts
  - `get_balance` → `"tot:X,avl:Y,ccy:Z"`
  - `get_positions` → TOON `@pos` table
  - `get_fills` → TOON `@fills` table
  - `submit_order` → `"oid:X,sym:Y,sd:B,qty:N,px:P,st:S,mkt:M"`
  - `save_memory/search_memory/send_message` → compact strings
- Prompt builders (`prompts.py`): compact KV, abbreviated TOON column names, minimal response schemas

## [0.13.0] - 2026-03-14

### Changed
- Agent tools: removed market data tools (`get_quote`, `get_ohlcv`, `get_order_book`, `get_symbols`) — AI now finds data autonomously from any source
- `build_agent_tools()`: only provides account/portfolio queries + order execution (8 tools total)
- `run_agent_cycle()`: removed `market_data` parameter; agents operate with full autonomy
- `TraderAgent`: removed `DecisionPipeline` and `market_data` dependency; simplified to pure ReAct loop
- `create_agent()`: removed `market_data` parameter from factory
- All agent system prompts: removed methodology constraints — rational, irrational, unconventional, any approach valid

### Removed
- KIS market data adapter (`adapters/market_data/kis.py`) — AI decides data sources autonomously
- KIS WebSocket adapter (`adapters/kis_websocket.py`) — real-time feed replaced by AI-driven search
- `DecisionPipeline` from `TraderAgent` — superseded by ReAct tool-use loop

## [0.12.0] - 2026-03-13

### Added
- KIS Market Data: overseas stock quotes (HHDFS00000300), overseas OHLCV (HHDFS76240000)
- KIS Market Data: domestic minute OHLCV (FHKST03010100) — 1m/3m/5m/10m/15m/30m/60m
- KIS Market Data: domestic order book / 호가창 (FHKST01010200)
- KIS Market Data: weekly/monthly candles via period code
- KIS Market Data: multi-market `get_symbols(market)` — kr_stock, us_stock, hk_stock, cn_stock, jp_stock, vn_stock
- KIS WebSocket adapter (`kis_websocket.py`): real-time subscriptions for domestic price (H0STCNT0), order book (H0STASP0), overseas price (HDFSCNT0)
- Agent tools (`build_agent_tools()`): 12 LangChain StructuredTools — get_balance, get_positions, get_quote, get_ohlcv, get_order_book, get_symbols, get_fills, submit_order, cancel_order, save_memory, search_memory, send_message
- Agent memory: per-agent `_memory` dict for cross-cycle persistence
- `OrderBook` / `OrderBookLevel` models in market_data port

### Changed
- Agent workflow: replaced fixed `gather_data → think → reflect → record` pipeline with ReAct free tool-use loop (`create_react_agent` + `ChatGoogleGenerativeAI`)
- Agents decide everything autonomously: what to check, when to trade, in what order — no system-imposed steps
- DB recording becomes transparent side effect of tool calls (submit_order auto-records, no forced record node)
- `graph/nodes.py`: simplified to single `record_cycle()` post-processing function
- `graph/state.py`: `AgentWorkflowState` → `AgentCycleResult` (backward-compat alias preserved)
- `paper.py`: Position includes `market` and `exchange` fields
- Config: `extra="ignore"` to allow additional env vars (DB_PASSWORD etc.)

## [0.11.0] - 2026-03-12

### Changed
- Removed all AI autonomy constraints from agent logic
