# deerflow.testing

The extension/agent author's test kit. It ships **inside** the harness package
(`deerflow-harness`) so downstream DeerFlow-based agent repos import it instead
of copying fakes.

## Ownership rules

- **Never import `app.*`.** The harness/app boundary (`tests/test_harness_boundary.py`)
  applies to this subpackage exactly as to the rest of `deerflow.*`. Gateway-level
  boot evidence (real `create_app()`, routers, services) belongs to the host
  repo's own tests; `docs/testing/` anchors those samples in `backend/tests/`.
- **One mock only: the scripted model.** Every helper drives real entry points —
  `extensions.loader.load_extensions`, `extensions.stack.compose_with_extensions`,
  `langchain.agents.create_agent`. Do not add helpers that hand-wire a registry
  or stub the isolation wrapper; that converts the kit from evidence into
  theatre.
- **Keep the surface small.** If a test needs more, it probably needs a real
  host fixture (see `backend/tests/`), not another kit function.
- **Test-only, but published.** This package is part of the wheel; version it
  conservatively and never import experimental internals from
  `deerflow.agents` package roots — import the concrete submodule (the
  package-root laziness contract in the backend guide).

## The five steps the kit covers

| Step | Kit entry points | Sample |
|---|---|---|
| ① entry-point guard | `load_extensions_for_test` | `examples/deerflow-extension-example/tests/test_entry_point.py` |
| ② behaviour spec | `ScriptedModel` + `build_test_agent` | `examples/deerflow-extension-example/tests/test_plugin.py` |
| ③ load containment | `load_extensions_for_test` + `extension_process_state` | `examples/deerflow-extension-example/tests/test_lifecycle.py` |
| ④ REAL composition, both faces | `compose_stack` + `describe_middleware` | `examples/deerflow-extension-example/tests/test_composition.py` |
| ⑤ model-visible transcript | `ScriptedModel.requests` | `examples/deerflow-extension-example/tests/test_model_surface.py` |

The strategy, playbook, and PR checklist live in `docs/testing/` (repository
root). Keep that set and this package in sync: a ladder step without a kit
entry point degrades into prose.
