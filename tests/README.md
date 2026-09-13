# Tests

Unit tests for the pure-Python helpers, validators, and cost logic in
`deployml.cli` and `deployml.utils`. These tests do NOT touch GCP. Subprocess
calls and HTTP calls are mocked.

Run with:

```bash
PYTHONPATH=src pytest tests/ -v
```

Or, if the package is installed in your environment:

```bash
conda run -n ml pytest tests/ -v
```

## Layout

| File | Covers |
|---|---|
| `test_helpers.py` | config loading/validation, GCP validators, tool + auth probes |
| `test_doctor.py` | the prereq checker's tool-detection pattern |
| `test_infracost.py` | infracost invocation, cost parsing, and the estimate/actual display views |
| `test_measured_usage.py` | reading real usage from Cloud Monitoring and mapping it to infracost keys |
| `test_platform_compat.py` | `run_tool` / `resolve_tool` cross-platform behaviour |
| `test_gke_destroy.py` | GKE teardown manifest and disk cleanup logic |

## Conventions

- Plain module-level `def test_*` functions. No test classes.
- Only built-in fixtures (`tmp_path`, `capsys`); no `conftest.py`.
- `unittest.mock.patch` used as a **context manager**, not a decorator.
- External tools are mocked at the `run_tool` import site in the module under
  test, returning `SimpleNamespace(returncode=, stdout=, stderr=)` — not by
  patching `subprocess.run`.
- HTTP is mocked at `requests.get` in the module under test.

## Notable regression guards

- `test_inspect_is_pinned_to_the_scan_file`: `infracost inspect` must be passed
  `--file`. Without it, inspect reads infracost's global "most recent scan" cache
  and can report a different workspace's costs.
- `test_nothing_measured_means_notes_not_invented_numbers`: unmeasurable usage
  must stay at $0 *with a printed reason*, never fall back to a guessed profile.
- `test_bigquery_storage_splits_evenly_but_the_total_stays_exact`: BigQuery
  metrics are project-scoped, so per-table attribution is an even split; the test
  pins the property that makes this acceptable — linear pricing keeps the total exact.

## What is NOT covered

- Anything requiring a real GCP project (deploy, destroy, init API enable) or a
  real infracost API call. Those are validated by the end-to-end walkthrough.
- The Typer command bodies themselves; there is no `CliRunner` harness yet.
