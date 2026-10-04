# Backend Tests

Backend tests must preserve the runtime invariants they exercise without changing production execution topology.

## Test-asset naming rules (full text: docs/testing/04-test-asset-naming.md)

- **Never import one collected test module from another** (`from test_X import ...`). Shared fixtures live in `_`-prefixed helper modules (e.g. `_router_auth_helpers.py`, `_opensandbox_helpers.py`), data assets in `tests/fixtures/`.
- **Lane membership is the `live` marker's job; guards are the test's job.** Any test that calls real external APIs carries `pytest.mark.live` (so `make test` excludes it) plus an in-test key/env guard (so `make test-live` skips gracefully without credentials). A `_live` filename suffix without the marker is a bug; an ad-hoc env gate without the marker is a bug. Mixed files (some LLM cases, some offline) mark per test, not per module.

## Executor starvation tests

`test_executor_starvation.py` covers the deterministic starvation semantics from RFC #4560:

- default-executor saturation and queueing;
- cancellation of an awaiter while an already-started synchronous worker continues;
- isolation between the asyncio default executor and DeerFlow's dedicated file-I/O executor.

Use explicit synchronization such as `threading.Event` rather than sleep-based timing thresholds for worker lifecycle assertions. Every test must release blocked workers and restore any process-global monkeypatches so teardown cannot leak threads or state into later tests.

Stress/soak testing, AnyIO worker instrumentation, Uvicorn multi-process behavior, and broad production executor redesign are separate concerns and should not be folded into these deterministic regressions.
