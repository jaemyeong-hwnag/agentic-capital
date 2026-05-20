---
name: source-command-self-recovery
description: Universal self-recovery workflow for any Codex-run command, shell script, Python process, test run, service, daemon, background screen/tmux job, automation, monitor, deployment, or live ops loop. Use whenever Codex starts, supervises, debugs, restarts, or observes an execution, and whenever a command errors, hangs, loops, crashes, produces bad output, creates duplicate processes, or enters an unintended state.
---

# Source Command Self Recovery

## Contract

Treat every execution as an ops loop, not a one-shot command.

For any shell, Python, test, service, background process, monitor, deployment, or automation:

1. Define expected success before running.
2. Set an adaptive timer and monitor output, exit status, process state, logs, and side effects.
3. If failure is clear, stop the failing/stale execution.
4. Diagnose the root cause from evidence.
5. Fix local code/config/docs/tests when safe.
6. Run the smallest relevant verification, then the required full verification.
7. Restart only after verification passes.
8. Report the final state with evidence.

Do not keep re-running a known-bad command without changing a cause or collecting new evidence.

## Before Running

Record mentally or in the user update:

- `owner`: command/service/process being started.
- `success`: concrete pass condition, such as exit 0, tests pass, health endpoint OK, DB row advances, or log reaches ready state.
- `failure`: concrete fail condition, such as nonzero exit, traceback, timeout, repeated same error, no log progress, duplicate process, unsafe live state, or invalid output.
- `rollback/stop`: how to stop it if it fails.
- `verification`: smallest useful check plus any repo-required full check.
- `timer`: initial check interval and adaptive criteria for waiting, stopping, or intervening.

For background jobs, always know the process identifier: screen/tmux session, PID, container, service name, run id, log file, or DB row.

## Adaptive Timer

Every execution must have a timer. Do not use one fixed timeout for everything. Choose and adjust the next check interval from the command's expected behavior.

Start with these defaults, then adapt:

| Work type | First check | Continue waiting when | Intervene when |
|----------|-------------|-----------------------|----------------|
| Fast command, lint, small unit test | 5-15s | output changes or test count advances | no output past expected duration, immediate traceback, repeated same failure |
| Full test suite, build, install | 30-60s | test/build progress advances, CPU/disk/network active, logs vary | no progress for multiple checks, dependency/network error, same failing test repeats |
| Dev server, service, daemon | 5-20s until ready, then 30-120s | health/log heartbeat advances | port not bound, crash loop, readiness timeout, duplicate process |
| Long training, migration, batch job | 60-300s | epoch/step/row count/checkpoint advances | metric/log frozen beyond normal cadence, resource exhaustion, irreversible error |
| Live ops/trading/production-like loop | 10-60s during startup, then task-specific heartbeat | DB cycle/run advances, logs show intended sleep/heartbeat, one process only | duplicate process, unsafe mode, repeated error, stale DB cycle, unclear order/account state |

Adaptive rules:

- Shorten the interval after errors, warnings, startup, or live-risk signals.
- Lengthen the interval only when progress is measurable and the process is in an intended wait/sleep state.
- On each timer tick, read enough evidence to choose one action: `wait`, `stop`, `diagnose`, `fix`, `restart`, or `report_blocked`.
- If there is no new output, check secondary signals: process state, CPU, log mtime, DB status, health endpoint, queue length, container health, or file growth.
- Do not wait just because a process exists. A live process with stale logs or stale DB rows is suspect.
- If the same error appears on two timer ticks, stop waiting and enter recovery.
- For live/production-like systems, prefer earlier intervention over extended uncertain waiting.

## Monitor

While running:

- Poll long-running commands instead of assuming progress.
- Use the adaptive timer to decide when to poll again.
- Inspect recent logs, not only process existence.
- Check external dependencies that affect the run: DB, Redis, Docker, network, credentials, ports, queues, broker/API availability.
- For DB-backed systems, query the latest run/cycle/job status using actual schema columns.
- Treat duplicate live processes as a failure. Stop duplicates before restarting.
- If output shows the same error twice with no new evidence, stop and repair.

## Recovery Decision Tree

When failure appears:

1. **Stop unsafe or stale execution**
   Stop crashed, hung, duplicate, or unintended processes before making changes. For live/production systems, prefer stopping over letting an unknown loop continue.

2. **Classify the cause**
   Use these buckets:
   - `local_code`: bug, wrong schema, wrong import, wrong argument, missing guard, bad parser.
   - `local_config`: env, path, port, version, dependency, migration, wrong mode.
   - `local_state`: stale PID, duplicate screen, dirty DB row, cache, lock, queue backlog.
   - `external`: credentials, broker/API outage, market closure, permission, rate limit, remote service.
   - `safety`: live trading risk, destructive command risk, unclear production blast radius.

3. **Act by bucket**
   - `local_code`: patch the smallest local fix, add or update tests, run verification.
   - `local_config`: correct config or report the missing external value if unavailable.
   - `local_state`: clean stale state only when safe and targeted; never broad-delete.
   - `external`: report evidence and stop retry loops; do not invent credentials or fake success.
   - `safety`: pause and report unless the user already explicitly authorized the risky action.

4. **Restart**
   Restart only after the fix is verified or after classifying the issue as external/non-local and choosing a safe degraded mode.

## Retry Limit

Use at most two blind retries. After that, a retry must include one of:

- A code/config/state change.
- A narrower diagnostic command.
- A different hypothesis being tested.
- A confirmed external recovery signal.

## Live Systems

For trading, deployments, production-like services, brokers, or paid APIs:

- Keep the current safety mode unless the user explicitly changes it.
- Do not place manual trades as a recovery shortcut.
- Stop duplicate engines immediately.
- Preserve logs and DB evidence before changing state when feasible.
- If a live order, credential, broker permission, market session, or account state is unclear, stop and report the blocker.
- Restart only one supervised process unless the architecture explicitly requires more.

## Verification

After a local fix:

- Run focused tests for the changed behavior.
- Run repo-required full tests or explain why they cannot run.
- For services, verify process exists, logs advance, health checks pass, and DB/run status changes.
- For background jobs, inspect the new log after restart.
- For this repository, follow project delivery rules: tests, docs, commit separation, version/tag when required, push when requested.

## Report Format

Keep final status concise:

```
self_recovery:
  timer: <intervals used and why wait/stop/restart was chosen>
  stopped: <what was stopped, if anything>
  cause: <root cause bucket + evidence>
  fixed: <files/config/state changed>
  verified: <tests/health/log/DB evidence>
  restarted: <process/session/run id>
  remaining_risk: <external blocker or none>
```
