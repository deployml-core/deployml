# Tests

Unit tests for the pure-Python helpers and validators in `deployml.cli` and
`deployml.utils.helpers`. These tests do NOT touch GCP. Subprocess calls are
mocked.

Run with:

```bash
conda run -n ml pytest tests/ -v
```

Or from the project root:

```bash
pytest tests/
```

What is covered:
- `_load_config_or_exit`: valid mapping, malformed YAML, non-mapping, empty.
- `_validate_deploy_config_or_exit`: every documented error path.
- `validate_gcp_project`, `validate_gcp_region`: subprocess mocked.
- `get_missing_iam_roles`: owner short-circuit and the diff path.
- `check_gcp_adc`, `check_bq`, `check_docker_daemon`, `get_terraform_version`: subprocess mocked.

What is NOT covered:
- Anything that requires a real GCP project (deploy, destroy, init API enable).
  Those are validated by the end-to-end walkthrough in CLAUDE_INSTRUCTIONS.
