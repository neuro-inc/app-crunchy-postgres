import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


CHART_PATH = Path(__file__).parents[4] / "helm" / "postgres"
AUTHORIZE_REMOVAL_ANNOTATION = (
    "postgres-operator.crunchydata.com/authorizeBackupRemoval"
)

BASE_VALUES = {
    "name": "pg-testapp",
    "postgresVersion": "16",
    "instances": [
        {
            "name": "instance1",
            "replicas": 2,
            "dataVolumeClaimSpec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "10Gi"}},
            },
        }
    ],
    "users": [{"name": "postgres"}],
}

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm is required to render the chart"
)


def render_postgrescluster(tmp_path, **overrides):
    values = {**BASE_VALUES, **overrides}
    values_file = tmp_path / "values.yaml"
    values_file.write_text(yaml.safe_dump(values))

    output = subprocess.run(
        ["helm", "template", "pg", str(CHART_PATH), "-f", str(values_file)],
        capture_output=True,
        check=True,
        text=True,
    ).stdout

    for doc in yaml.safe_load_all(output):
        if doc and doc.get("kind") == "PostgresCluster":
            return doc
    pytest.fail("chart did not render a PostgresCluster")
    return None


def test_no_backup_repo_when_backups_are_not_configured(tmp_path):
    """Installing without backups must not provision a pgBackRest repo.

    Regression test for IT-94: the chart used to fall back to a 1Gi volume repo,
    so an app installed with backups off still got a PVC that later filled up.
    """
    cluster = render_postgrescluster(tmp_path)

    assert "backups" not in cluster["spec"]


def test_backup_removal_is_authorized_when_backups_are_not_configured(tmp_path):
    """Existing clusters need this annotation to drop a repo they already have.

    Without it the operator pauses reconciliation instead of removing the repo.
    """
    cluster = render_postgrescluster(tmp_path)

    annotations = cluster["metadata"]["annotations"]
    assert annotations[AUTHORIZE_REMOVAL_ANNOTATION] == "true"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"backupsSize": "5Gi"}, id="volume"),
        pytest.param(
            {"s3": {"bucket": "bkt", "endpoint": "s3.amazonaws.com", "region": "us"}},
            id="s3",
        ),
        pytest.param({"gcs": {"bucket": "bkt", "key": "{}"}}, id="gcs"),
        pytest.param({"azure": {"container": "cnt"}}, id="azure"),
    ],
)
def test_configured_backups_are_kept_and_not_authorized_for_removal(
    tmp_path, overrides
):
    cluster = render_postgrescluster(tmp_path, **overrides)

    assert cluster["spec"]["backups"]["pgbackrest"]["repos"]
    assert AUTHORIZE_REMOVAL_ANNOTATION not in cluster["metadata"]["annotations"]


def test_configured_backup_volume_uses_the_requested_size(tmp_path):
    cluster = render_postgrescluster(tmp_path, backupsSize="5Gi")

    repo = cluster["spec"]["backups"]["pgbackrest"]["repos"][0]
    assert (
        repo["volume"]["volumeClaimSpec"]["resources"]["requests"]["storage"] == "5Gi"
    )
