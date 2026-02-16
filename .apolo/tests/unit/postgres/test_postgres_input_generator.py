from datetime import datetime
from unittest.mock import AsyncMock

import apolo_sdk
import pydantic
import pytest
from apolo_apps_postgresql.inputs_processor import PostgresInputsChartValueProcessor
from apolo_apps_postgresql.types import (
    PGBackupConfig,
    PGBackupSchedule,
    PGBouncer,
    PGDataSourceConfig,
    PostgresConfig,
    PostgresDBUser,
    PostgresInputs,
    PostgresSupportedVersions,
)

from apolo_app_types.protocols.common import Preset
from apolo_app_types.protocols.common.buckets import (
    Bucket,
    BucketProvider,
    GCPBucketCredentials,
)


DEFAULT_NAMESPACE = "default"
DEFAULT_PROJECT_NAME = "test-project"
APP_SECRETS_NAME = "apps-secrets"
APP_ID = "b1aeaf654526474ba22480d00e5b0109"


async def test_values_postgresql_generation(setup_clients, mock_get_preset_cpu):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    helm_params = await processor.gen_extra_values(
        input_=PostgresInputs(
            preset=Preset(
                name="cpu-large",
            ),
            postgres_config=PostgresConfig(
                postgres_version=PostgresSupportedVersions.v16,
                instance_replicas=3,
                instance_size=1,
                db_users=[PostgresDBUser(name="somename", db_names=["somedb"])],
            ),
            pg_bouncer=PGBouncer(
                preset=Preset(
                    name="cpu-large",
                ),
            ),
            backup=PGBackupConfig(
                backup_preset=Preset(
                    name="cpu-small",
                ),
                schedule=PGBackupSchedule(),
            ),
        ),
        app_name="psdb",
        namespace=DEFAULT_NAMESPACE,
        app_id=APP_ID,
        app_secrets_name=APP_SECRETS_NAME,
    )
    assert helm_params == {
        "metadata": {"labels": {"platform.apolo.us/component": "app"}},
        "features": {"AutoCreateUserSchema": "true"},
        "name": f"pg-{APP_ID}",
        "postgresVersion": "16",
        "databaseInitSQL": {
            "name": f"pg-{APP_ID}-init-sql",
            "key": "bootstrap.sql",
        },
        "apolo_app_id": APP_ID,
        "instances": [
            {
                "name": "instance1",
                "metadata": {
                    "labels": {
                        "platform.apolo.us/component": "app",
                        "platform.apolo.us/app": "crunchypostgresql",
                        "platform.apolo.us/preset": "cpu-large",
                    }
                },
                "replicas": 3,
                "dataVolumeClaimSpec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "1Gi"}},
                },
                "resources": {
                    "requests": {"cpu": "4000.0m", "memory": "0M"},
                    "limits": {"cpu": "4000.0m", "memory": "0M"},
                },
                "tolerations": [
                    {
                        "effect": "NoSchedule",
                        "key": "platform.neuromation.io/job",
                        "operator": "Exists",
                    },
                    {
                        "effect": "NoExecute",
                        "key": "node.kubernetes.io/not-ready",
                        "operator": "Exists",
                        "tolerationSeconds": 300,
                    },
                    {
                        "effect": "NoExecute",
                        "key": "node.kubernetes.io/unreachable",
                        "operator": "Exists",
                        "tolerationSeconds": 300,
                    },
                ],
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": "platform.neuromation.io/nodepool",
                                            "operator": "In",
                                            "values": ["cpu_pool"],
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                    "podAntiAffinity": {
                        "preferredDuringSchedulingIgnoredDuringExecution": [
                            {
                                "weight": 100,
                                "podAffinityTerm": {
                                    "topologyKey": "kubernetes.io/hostname",
                                    "labelSelector": {
                                        "matchExpressions": [
                                            {
                                                "key": "platform.apolo.us/component",
                                                "operator": "In",
                                                "values": ["app"],
                                            },
                                            {
                                                "key": "platform.apolo.us/app",
                                                "operator": "In",
                                                "values": ["crunchypostgresql"],
                                            },
                                        ]
                                    },
                                },
                            }
                        ]
                    },
                },
            }
        ],
        "pgBouncerConfig": {
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "platform.neuromation.io/nodepool",
                                        "operator": "In",
                                        "values": ["cpu_pool"],
                                    }
                                ]
                            }
                        ]
                    }
                },
                "podAntiAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": [
                        {
                            "weight": 100,
                            "podAffinityTerm": {
                                "topologyKey": "kubernetes.io/hostname",
                                "labelSelector": {
                                    "matchExpressions": [
                                        {
                                            "key": "platform.apolo.us/component",
                                            "operator": "In",
                                            "values": ["app"],
                                        },
                                        {
                                            "key": "platform.apolo.us/app",
                                            "operator": "In",
                                            "values": ["crunchypostgresql"],
                                        },
                                    ]
                                },
                            },
                        }
                    ]
                },
            },
            "metadata": {
                "labels": {
                    "platform.apolo.us/component": "app",
                    "platform.apolo.us/app": "crunchypostgresql",
                    "platform.apolo.us/preset": "cpu-large",
                }
            },
            "replicas": 2,
            "resources": {
                "requests": {"cpu": "4000.0m", "memory": "0M"},
                "limits": {"cpu": "4000.0m", "memory": "0M"},
            },
            "tolerations": [
                {
                    "effect": "NoSchedule",
                    "key": "platform.neuromation.io/job",
                    "operator": "Exists",
                },
                {
                    "effect": "NoExecute",
                    "key": "node.kubernetes.io/not-ready",
                    "operator": "Exists",
                    "tolerationSeconds": 300,
                },
                {
                    "effect": "NoExecute",
                    "key": "node.kubernetes.io/unreachable",
                    "operator": "Exists",
                    "tolerationSeconds": 300,
                },
            ],
        },
        "gcs": {"bucket": "test-bucket", "key": "bucket-access-key"},
        "pgBackRestConfig": {
            "configuration": [
                {
                    "secret": {
                        "name": f"pg-{APP_ID}-pgbackrest-secret",
                    },
                }
            ],
            "global": {
                "repo1-path": f"/pgbackrest/default/pg-{APP_ID}/repo1",
                "repo1-retention-full": "4",
                "repo1-retention-full-type": "count",
            },
            "repos": [
                {
                    "name": "repo1",
                    "gcs": {
                        "bucket": "test-bucket",
                    },
                    "schedules": {
                        "full": "0 2 * * 0",
                    },
                }
            ],
            "metadata": {
                "labels": {
                    "platform.apolo.us/component": "app",
                    "platform.apolo.us/app": "crunchypostgresql",
                    "platform.apolo.us/preset": "cpu-small",
                },
            },
            "jobs": {
                "resources": {
                    "requests": {"cpu": "2000.0m", "memory": "0M"},
                    "limits": {"cpu": "2000.0m", "memory": "0M"},
                },
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": "platform.neuromation.io/nodepool",
                                            "operator": "In",
                                            "values": ["cpu_pool"],
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                },
                "tolerations": [
                    {
                        "effect": "NoSchedule",
                        "key": "platform.neuromation.io/job",
                        "operator": "Exists",
                    },
                    {
                        "effect": "NoExecute",
                        "tolerationSeconds": 300,
                        "key": "node.kubernetes.io/not-ready",
                        "operator": "Exists",
                    },
                    {
                        "effect": "NoExecute",
                        "key": "node.kubernetes.io/unreachable",
                        "operator": "Exists",
                        "tolerationSeconds": 300,
                    },
                ],
            },
        },
        "users": [
            {"name": "postgres"},
            {
                "name": "somename",
                "password": {"type": "AlphaNumeric"},
                "databases": ["somedb"],
            },
        ],
        "apolo-hooks": {"image": {"tag": "latest"}},
    }


async def test_values_postgresql_generation_invalid_name(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    with pytest.raises(pydantic.ValidationError) as err:
        await processor.gen_extra_values(
            input_=PostgresInputs(
                preset=Preset(
                    name="cpu-large",
                ),
                postgres_config=PostgresConfig(
                    postgres_version=PostgresSupportedVersions.v16,
                    instance_replicas=3,
                    instance_size=1,
                    db_users=[PostgresDBUser(name="some_name", db_names=["somedb"])],
                ),
                pg_bouncer=PGBouncer(
                    preset=Preset(
                        name="cpu-large",
                    ),
                ),
                backup=PGBackupConfig(
                    backup_preset=Preset(
                        name="cpu-small",
                    ),
                ),
            ),
            app_name="psdb",
            namespace=DEFAULT_NAMESPACE,
            app_secrets_name=APP_SECRETS_NAME,
            app_id=APP_ID,
        )
    assert (
        err.value.errors()[0]["msg"]
        == "String should match pattern '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'"
    )


async def test_values_postgresql_generation_with_user(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    helm_params = await processor.gen_extra_values(
        input_=PostgresInputs(
            preset=Preset(
                name="cpu-large",
            ),
            postgres_config=PostgresConfig(
                postgres_version=PostgresSupportedVersions.v16,
                instance_replicas=3,
                instance_size=1,
                db_users=[PostgresDBUser(name="user1", db_names=["db1"])],
            ),
            pg_bouncer=PGBouncer(
                preset=Preset(
                    name="cpu-large",
                ),
            ),
            backup=None,
        ),
        app_name="psdb",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )
    assert helm_params["features"] == {"AutoCreateUserSchema": "true"}
    assert len(helm_params["instances"]) == 1
    assert helm_params["instances"][0]["name"] == "instance1"
    assert helm_params["instances"][0]["replicas"] == 3
    assert helm_params["instances"][0]["dataVolumeClaimSpec"] == {
        "accessModes": ["ReadWriteOnce"],
        "resources": {"requests": {"storage": "1Gi"}},
    }
    assert helm_params["instances"][0]["metadata"]["labels"] == {
        "platform.apolo.us/app": "crunchypostgresql",
        "platform.apolo.us/component": "app",
        "platform.apolo.us/preset": "cpu-large",
    }
    assert "nodeAffinity" in helm_params["instances"][0]["affinity"]
    assert "podAntiAffinity" in helm_params["instances"][0]["affinity"]
    assert helm_params["users"] == [
        {"name": "postgres"},
        {"databases": ["db1"], "name": "user1", "password": {"type": "AlphaNumeric"}},
    ]
    assert "s3" not in helm_params
    assert "gcs" not in helm_params
    assert "azure" not in helm_params


async def test_values_postgresql_generation_without_user(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    with pytest.raises(pydantic.ValidationError):
        await processor.gen_extra_values(
            input_=PostgresInputs(
                preset=Preset(
                    name="cpu-large",
                ),
                postgres_config=PostgresConfig(
                    postgres_version=PostgresSupportedVersions.v16,
                    instance_replicas=3,
                    instance_size=1,
                    db_users=[],
                ),
                pg_bouncer=PGBouncer(
                    preset=Preset(
                        name="cpu-large",
                    ),
                ),
                backup=None,
            ),
            app_name="psdb",
            namespace=DEFAULT_NAMESPACE,
            app_secrets_name=APP_SECRETS_NAME,
            app_id=APP_ID,
        )


async def test_values_postgresql_generation_with_postgres_user(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    with pytest.raises(pydantic.ValidationError):
        await processor.gen_extra_values(
            input_=PostgresInputs(
                preset=Preset(
                    name="cpu-large",
                ),
                postgres_config=PostgresConfig(
                    postgres_version=PostgresSupportedVersions.v16,
                    instance_replicas=3,
                    instance_size=1,
                    db_users=[PostgresDBUser(name="postgres", db_names=["postgres"])],
                ),
                pg_bouncer=PGBouncer(
                    preset=Preset(
                        name="cpu-large",
                    ),
                ),
                backup=None,
            ),
            app_name="psdb",
            namespace=DEFAULT_NAMESPACE,
            app_secrets_name=APP_SECRETS_NAME,
            app_id=APP_ID,
        )


async def test_values_postgresql_generation_with_minio(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    mock_bucket = apolo_sdk.Bucket(
        id="bucket-id",
        owner="owner",
        cluster_name="cluster",
        org_name="test-org",
        project_name="test-project",
        provider=apolo_sdk.Bucket.Provider.MINIO,
        created_at=datetime.today(),
        imported=False,
        name="test-bucket",
    )
    apolo_client.buckets.get = AsyncMock(return_value=mock_bucket)

    p_credentials = apolo_sdk.PersistentBucketCredentials(
        id="cred-id",
        owner="owner",
        cluster_name="cluster",
        name="test-creds",
        read_only=False,
        credentials=[
            apolo_sdk.BucketCredentials(
                bucket_id="bucket-id",
                provider=apolo_sdk.Bucket.Provider.MINIO,
                credentials={
                    "bucket_name": "test-bucket",
                    "endpoint_url": "test-endpoint",
                    "region_name": "test-region",
                    "access_key_id": "test-access-key",
                    "secret_access_key": "test-secret-key",
                },
            ),
        ],
    )
    apolo_client.buckets.persistent_credentials_get = AsyncMock(
        return_value=p_credentials
    )

    helm_params = await processor.gen_extra_values(
        input_=PostgresInputs(
            preset=Preset(name="cpu-large"),
            postgres_config=PostgresConfig(
                postgres_version=PostgresSupportedVersions.v16,
                instance_replicas=3,
                instance_size=1,
                db_users=[PostgresDBUser(name="user1", db_names=["db1"])],
            ),
            pg_bouncer=PGBouncer(preset=Preset(name="cpu-large")),
            backup=PGBackupConfig(
                backup_preset=Preset(
                    name="cpu-small",
                ),
                schedule=PGBackupSchedule(
                    full_backup_cron="0 1 * * 0",
                    full_backup_retention_count=40,
                    differential_backup_cron="0 1 * * 1",
                    differential_backup_retention_count=10,
                ),
            ),
        ),
        app_name="psdb",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )
    assert helm_params["features"] == {"AutoCreateUserSchema": "true"}
    assert len(helm_params["instances"]) == 1
    assert helm_params["instances"][0]["name"] == "instance1"
    assert helm_params["instances"][0]["replicas"] == 3
    assert helm_params["instances"][0]["dataVolumeClaimSpec"] == {
        "accessModes": ["ReadWriteOnce"],
        "resources": {"requests": {"storage": "1Gi"}},
    }
    assert helm_params["instances"][0]["metadata"]["labels"] == {
        "platform.apolo.us/app": "crunchypostgresql",
        "platform.apolo.us/component": "app",
        "platform.apolo.us/preset": "cpu-large",
    }
    assert "nodeAffinity" in helm_params["instances"][0]["affinity"]
    assert "podAntiAffinity" in helm_params["instances"][0]["affinity"]
    assert helm_params["users"] == [
        {"name": "postgres"},
        {"databases": ["db1"], "name": "user1", "password": {"type": "AlphaNumeric"}},
    ]
    assert helm_params["s3"] == {
        "bucket": "test-bucket",
        "endpoint": "test-endpoint",
        "key": "test-access-key",
        "keySecret": "test-secret-key",
        "region": "test-region",
    }
    assert helm_params["pgBackRestConfig"]["global"] == {
        "repo1-path": f"/pgbackrest/default/pg-{APP_ID}/repo1",
        "repo1-retention-full": "40",
        "repo1-retention-full-type": "count",
        "repo1-retention-diff": "10",
        "repo1-s3-uri-style": "path",
    }
    assert helm_params["pgBackRestConfig"]["repos"][0]["schedules"] == {
        "full": "0 1 * * 0",
        "differential": "0 1 * * 1",
    }


async def test_values_postgresql_generation_without_matching_bucket_and_creds(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    with pytest.raises(pydantic.ValidationError):
        await processor.gen_extra_values(
            input_=PostgresInputs(
                preset=Preset(
                    name="cpu-large",
                ),
                postgres=PostgresConfig(
                    postgres_version=PostgresSupportedVersions.v16,
                    instance_replicas=3,
                    instance_size=1,
                    db_users=[],
                ),
                pg_bouncer=PGBouncer(
                    preset=Preset(
                        name="cpu-large",
                    ),
                ),
                backup_bucket=Bucket(
                    id="some_id",
                    owner="some_owner",
                    details={},
                    credentials=[
                        GCPBucketCredentials(
                            name="some_name",
                            key_data="U29tZSB0ZXh0",
                        )
                    ],
                    bucket_provider=BucketProvider.AWS,
                ),
            ),
            app_name="psdb",
            namespace=DEFAULT_NAMESPACE,
            app_secrets_name=APP_SECRETS_NAME,
        )


async def test_values_postgresql_generation_no_bouncer(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    helm_params = await processor.gen_extra_values(
        input_=PostgresInputs(
            preset=Preset(
                name="cpu-large",
            ),
            postgres_config=PostgresConfig(
                postgres_version=PostgresSupportedVersions.v16,
                instance_replicas=3,
                instance_size=1,
                db_users=[PostgresDBUser(name="somename", db_names=["somedb"])],
            ),
            backup=None,
        ),
        app_name="psdb",
        namespace=DEFAULT_NAMESPACE,
        app_id=APP_ID,
        app_secrets_name=APP_SECRETS_NAME,
    )
    assert helm_params == {
        "metadata": {"labels": {"platform.apolo.us/component": "app"}},
        "features": {"AutoCreateUserSchema": "true"},
        "name": f"pg-{APP_ID}",
        "postgresVersion": "16",
        "databaseInitSQL": {
            "name": f"pg-{APP_ID}-init-sql",
            "key": "bootstrap.sql",
        },
        "apolo_app_id": APP_ID,
        "instances": [
            {
                "name": "instance1",
                "metadata": {
                    "labels": {
                        "platform.apolo.us/component": "app",
                        "platform.apolo.us/app": "crunchypostgresql",
                        "platform.apolo.us/preset": "cpu-large",
                    }
                },
                "replicas": 3,
                "dataVolumeClaimSpec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "1Gi"}},
                },
                "resources": {
                    "requests": {"cpu": "4000.0m", "memory": "0M"},
                    "limits": {"cpu": "4000.0m", "memory": "0M"},
                },
                "tolerations": [
                    {
                        "effect": "NoSchedule",
                        "key": "platform.neuromation.io/job",
                        "operator": "Exists",
                    },
                    {
                        "effect": "NoExecute",
                        "key": "node.kubernetes.io/not-ready",
                        "operator": "Exists",
                        "tolerationSeconds": 300,
                    },
                    {
                        "effect": "NoExecute",
                        "key": "node.kubernetes.io/unreachable",
                        "operator": "Exists",
                        "tolerationSeconds": 300,
                    },
                ],
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": "platform.neuromation.io/nodepool",
                                            "operator": "In",
                                            "values": ["cpu_pool"],
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                    "podAntiAffinity": {
                        "preferredDuringSchedulingIgnoredDuringExecution": [
                            {
                                "weight": 100,
                                "podAffinityTerm": {
                                    "topologyKey": "kubernetes.io/hostname",
                                    "labelSelector": {
                                        "matchExpressions": [
                                            {
                                                "key": "platform.apolo.us/component",
                                                "operator": "In",
                                                "values": ["app"],
                                            },
                                            {
                                                "key": "platform.apolo.us/app",
                                                "operator": "In",
                                                "values": ["crunchypostgresql"],
                                            },
                                        ]
                                    },
                                },
                            }
                        ]
                    },
                },
            }
        ],
        "users": [
            {"name": "postgres"},
            {
                "name": "somename",
                "password": {"type": "AlphaNumeric"},
                "databases": ["somedb"],
            },
        ],
        "apolo-hooks": {"image": {"tag": "latest"}},
    }


async def test_values_postgresql_generation_source_data(
    setup_clients, mock_get_preset_cpu
):
    apolo_client = setup_clients
    processor = PostgresInputsChartValueProcessor(apolo_client)

    helm_params = await processor.gen_extra_values(
        input_=PostgresInputs(
            preset=Preset(
                name="cpu-large",
            ),
            postgres_config=PostgresConfig(
                postgres_version=PostgresSupportedVersions.v16,
                instance_replicas=3,
                instance_size=1,
                db_users=[PostgresDBUser(name="somename", db_names=["somedb"])],
            ),
            backup=None,
            source=PGDataSourceConfig(
                source_bucket=Bucket(
                    id="some_id",
                    owner="some_owner",
                    details={},
                    bucket_provider=BucketProvider.GCP,
                ),
                repo1_path="/pgbackrest/default/pg-123/repo1",
                restore_preset=Preset(name="cpu-small"),
                pgbackrest_options=["--some-flag", "--option=value"],
            ),
        ),
        app_name="psdb",
        namespace=DEFAULT_NAMESPACE,
        app_id=APP_ID,
        app_secrets_name=APP_SECRETS_NAME,
    )
    tolerations = [
        {
            "effect": "NoSchedule",
            "key": "platform.neuromation.io/job",
            "operator": "Exists",
        },
        {
            "effect": "NoExecute",
            "tolerationSeconds": 300,
            "key": "node.kubernetes.io/not-ready",
            "operator": "Exists",
        },
        {
            "effect": "NoExecute",
            "key": "node.kubernetes.io/unreachable",
            "operator": "Exists",
            "tolerationSeconds": 300,
        },
    ]
    affinity = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "platform.neuromation.io/nodepool",
                                "operator": "In",
                                "values": ["cpu_pool"],
                            }
                        ]
                    }
                ]
            }
        }
    }
    back_resources = {
        "requests": {"cpu": "2000.0m", "memory": "0M"},
        "limits": {"cpu": "2000.0m", "memory": "0M"},
    }
    assert helm_params == {
        "metadata": {"labels": {"platform.apolo.us/component": "app"}},
        "features": {"AutoCreateUserSchema": "true"},
        "name": f"pg-{APP_ID}",
        "postgresVersion": "16",
        "databaseInitSQL": {
            "name": f"pg-{APP_ID}-init-sql",
            "key": "bootstrap.sql",
        },
        "apolo_app_id": APP_ID,
        "instances": [
            {
                "name": "instance1",
                "metadata": {
                    "labels": {
                        "platform.apolo.us/component": "app",
                        "platform.apolo.us/app": "crunchypostgresql",
                        "platform.apolo.us/preset": "cpu-large",
                    }
                },
                "replicas": 3,
                "dataVolumeClaimSpec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "1Gi"}},
                },
                "resources": {
                    "requests": {"cpu": "4000.0m", "memory": "0M"},
                    "limits": {"cpu": "4000.0m", "memory": "0M"},
                },
                "tolerations": tolerations,
                "affinity": {
                    "nodeAffinity": affinity["nodeAffinity"],
                    "podAntiAffinity": {
                        "preferredDuringSchedulingIgnoredDuringExecution": [
                            {
                                "weight": 100,
                                "podAffinityTerm": {
                                    "topologyKey": "kubernetes.io/hostname",
                                    "labelSelector": {
                                        "matchExpressions": [
                                            {
                                                "key": "platform.apolo.us/component",
                                                "operator": "In",
                                                "values": ["app"],
                                            },
                                            {
                                                "key": "platform.apolo.us/app",
                                                "operator": "In",
                                                "values": ["crunchypostgresql"],
                                            },
                                        ]
                                    },
                                },
                            }
                        ]
                    },
                },
            }
        ],
        "users": [
            {"name": "postgres"},
            {
                "name": "somename",
                "password": {"type": "AlphaNumeric"},
                "databases": ["somedb"],
            },
        ],
        "apolo-hooks": {"image": {"tag": "latest"}},
        "dataSource": {
            "pgbackrest": {
                "stanza": "db",
                "configuration": [
                    {
                        "secret": {
                            "name": f"pg-{APP_ID}-src-pgbackrest-secret",
                        },
                    }
                ],
                "global": {
                    "repo1-path": "/pgbackrest/default/pg-123/repo1",
                },
                "repo": {
                    "name": "repo1",
                    "gcs": {
                        "bucket": "test-bucket",
                    },
                },
                "options": ["--some-flag", "--option=value"],
                "affinity": affinity,
                "tolerations": tolerations,
                "resources": back_resources,
            }
        },
        "dataSourceSecret": {
            "gcs": {
                "bucket": "test-bucket",
                "key": "bucket-access-key",
            },
        },
    }
