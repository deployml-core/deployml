"""Characterize GCP cloud_run template rendering. No GCP calls, no subprocess."""
import hashlib

import pytest
from jinja2 import Environment, FileSystemLoader

from deployml.utils.constants import TEMPLATE_DIR


@pytest.fixture
def render_cloud_run():
    """Render templates/gcp/cloud_run/main.tf.j2 the same way cli.py's deploy
    command does, with the minimal kwargs the template can reference."""

    def _render(provider: str, stack: list[dict], stack_name: str = "test-stack") -> str:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template(f"{provider}/cloud_run/main.tf.j2")
        name_hash = hashlib.sha1(f"{stack_name}:test-project".encode("utf-8")).hexdigest()[:6]
        return template.render(
            cloud=provider,
            stack=stack,
            deployment_type="cloud_run",
            create_artifact_bucket=False,
            bucket_configs={},
            project_id="test-project",
            stack_name=stack_name,
            name_hash=name_hash,
            teardown_config=None,
            teardown_cron_schedule="",
            teardown_scheduled_timestamp=0,
        )

    return _render


def test_cloud_run_grafana_is_rendered_once(render_cloud_run):
    rendered = render_cloud_run(
        provider="gcp",
        stack=[
            {
                "model_monitoring": {
                    "name": "grafana",
                    "params": {"service_name": "grafana-server"},
                }
            }
        ],
    )
    assert rendered.count('module "model_monitoring_grafana"') == 1
