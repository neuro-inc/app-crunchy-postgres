import base64
import logging
import os
import typing as t

import apolo_sdk

from apolo_app_types.helm.apps.base import BaseChartValueProcessor
from apolo_app_types.helm.apps.common import (
    get_preset,
    preset_to_affinity,
    preset_to_resources,
    preset_to_tolerations,
)
from apolo_app_types.helm.utils.buckets import get_or_create_bucket_credentials
from apolo_app_types.helm.utils.deep_merging import merge_list_of_dicts
from apolo_apps_postgresql.types import PostgresDBUser, PostgresInputs


logger = logging.getLogger(__name__)

POSTGRESQL_CRD_NAME_MAX_LENGTH = 37


class PostgresInputsChartValueProcessor(BaseChartValueProcessor[PostgresInputs]):
    def __init__(self, *args: t.Any, **kwargs: t.Any):
        super().__init__(*args, **kwargs)

    async def gen_extra_helm_args(self, *_: t.Any) -> list[str]:
        return ["--timeout", "30m"]

    async def _gen_instances_config(
        self,
        instance_preset_name: str,
        instance_replicas: int,
        instances_size: int,
    ) -> list[dict[str, t.Any]]:
        preset = get_preset(self.client, instance_preset_name)
        resources = preset_to_resources(preset)
        tolerations = await preset_to_tolerations(preset)
        affinity = preset_to_affinity(preset)

        pod_anti_afinity = {
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
        }
        affinity["podAntiAffinity"] = pod_anti_afinity

        instance = {
            "name": "instance1",
            "metadata": {
                "labels": {
                    "platform.apolo.us/component": "app",
                    "platform.apolo.us/app": "crunchypostgresql",
                    "platform.apolo.us/preset": instance_preset_name,
                },
            },
            "replicas": int(instance_replicas),
            "dataVolumeClaimSpec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": f"{instances_size}Gi"}},
            },
            "resources": resources,
            "tolerations": tolerations,
            "affinity": affinity,
        }
        return [instance]

    def _create_users_config(
        self, db_users: list[PostgresDBUser]
    ) -> list[dict[str, t.Any]]:
        # Set user[].password to "AlphaNumeric" since often non-alphanumberic
        # characters break client libs :(
        users_config: list[dict[str, t.Any]] = [{"name": "postgres"}]
        for db_user in db_users:
            users_config.append(
                {
                    "name": db_user.name,
                    "password": {"type": "AlphaNumeric"},
                    "databases": db_user.db_names,
                }
            )
        return users_config

    async def _get_bouncer_config(
        self,
        bouncer_preset_name: str,
        bouncer_repicas: int,
    ) -> dict[str, t.Any]:
        preset = get_preset(self.client, bouncer_preset_name)
        resources = preset_to_resources(preset)
        tolerations = await preset_to_tolerations(preset)
        affinity = preset_to_affinity(preset)
        pod_anti_afinity = {
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
        }

        affinity["podAntiAffinity"] = pod_anti_afinity

        return {
            "affinity": affinity,
            "metadata": {
                "labels": {
                    "platform.apolo.us/component": "app",
                    "platform.apolo.us/app": "crunchypostgresql",
                    "platform.apolo.us/preset": bouncer_preset_name,
                },
            },
            "replicas": bouncer_repicas,
            "resources": resources,
            "tolerations": tolerations,
        }

    @staticmethod
    def _build_provider_values(
        provider: apolo_sdk.Bucket.Provider,
        credentials: t.Mapping[str, t.Any],
    ) -> tuple[dict[str, t.Any], dict[str, t.Any], dict[str, t.Any]]:
        """Build provider-specific values from bucket credentials.

        Returns:
            Tuple of (secret_values, repo_config, extra_global) where:
            - secret_values: top-level s3/gcs dict for secret template
            - repo_config: provider-specific repo section
            - extra_global: additional pgBackRest global settings
        """
        if provider in (apolo_sdk.Bucket.Provider.AWS, apolo_sdk.Bucket.Provider.MINIO):
            secret_values = {
                "s3": {
                    "bucket": credentials["bucket_name"],
                    "endpoint": credentials["endpoint_url"],
                    "region": credentials["region_name"],
                    "key": credentials["access_key_id"],
                    "keySecret": credentials["secret_access_key"],
                }
            }
            repo_config = {
                "s3": {
                    "bucket": credentials["bucket_name"],
                    "endpoint": credentials["endpoint_url"],
                    "region": credentials["region_name"],
                }
            }
            extra_global = {"repo1-s3-uri-style": "path"}
            return secret_values, repo_config, extra_global
        if provider == apolo_sdk.Bucket.Provider.GCP:
            secret_values = {
                "gcs": {
                    "bucket": credentials["bucket_name"],
                    "key": base64.b64decode(credentials["key_data"]).decode("utf-8"),
                }
            }
            repo_config = {
                "gcs": {
                    "bucket": credentials["bucket_name"],
                }
            }
            return secret_values, repo_config, {}
        error = "Unsupported bucket provider, unable to configure pgBackRest"
        raise ValueError(error)

    async def _get_backup_config(
        self,
        input_: PostgresInputs,
        app_name: str,
        namespace: str,
        postgrescluster_crd_name: str,
    ) -> dict[str, t.Any]:
        logger.info("Getting backup config")
        if not input_.backup:
            return {}

        credentials_name = f"{app_name}-bkp"[:40]
        if not input_.backup.backup_bucket:
            bucket_name = credentials_name
            msg = (
                "No bucket for backup provided, creating one with name: " + bucket_name
            )
        else:
            bucket_name = input_.backup.backup_bucket.id
            msg = "Getting bucket credentials with id: " + bucket_name
        logger.info(msg)

        bucket_credentials = await get_or_create_bucket_credentials(
            client=self.client,
            bucket_name=bucket_name,
            credentials_name=credentials_name,
            supported_providers=[
                apolo_sdk.Bucket.Provider.AWS,
                apolo_sdk.Bucket.Provider.MINIO,
                apolo_sdk.Bucket.Provider.GCP,
            ],
        )
        logger.info("Got bucket credentials")

        provider = bucket_credentials.credentials[0].provider
        credentials = bucket_credentials.credentials[0].credentials

        secret_values, repo_config, extra_global = self._build_provider_values(
            provider, credentials
        )

        preset = get_preset(self.client, input_.backup.backup_preset.name)
        resources = preset_to_resources(preset)
        tolerations = await preset_to_tolerations(preset)
        affinity = preset_to_affinity(preset)

        global_config: dict[str, t.Any] = {
            "repo1-path": f"/pgbackrest/{namespace}/{postgrescluster_crd_name}/repo1",
            "repo1-retention-full": str(
                input_.backup.schedule.full_backup_retention_count
            ),
            "repo1-retention-full-type": "count",
            **extra_global,
        }
        if input_.backup.schedule.differential_backup_cron:
            global_config["repo1-retention-diff"] = str(
                input_.backup.schedule.differential_backup_retention_count
            )

        backup_schedules = {
            "full": input_.backup.schedule.full_backup_cron,
        }
        if input_.backup.schedule.differential_backup_cron:
            backup_schedules["differential"] = (
                input_.backup.schedule.differential_backup_cron
            )

        values: dict[str, t.Any] = {
            "pgBackRestConfig": {
                "configuration": [
                    {
                        "secret": {
                            "name": f"{postgrescluster_crd_name}-pgbackrest-secret",
                        },
                    }
                ],
                "global": global_config,
                "repos": [
                    {
                        "name": "repo1",
                        "schedules": backup_schedules,
                        **repo_config,
                    }
                ],
                "metadata": {
                    "labels": {
                        "platform.apolo.us/component": "app",
                        "platform.apolo.us/app": "crunchypostgresql",
                        "platform.apolo.us/preset": input_.backup.backup_preset.name,
                    },
                },
                "jobs": {
                    "resources": resources,
                    "affinity": affinity,
                    "tolerations": tolerations,
                },
            }
        }
        values.update(secret_values)
        return values

    async def _get_data_source_config(
        self,
        input_: PostgresInputs,
        pgcluster_crd_name: str,
    ) -> dict[str, t.Any]:
        assert input_.source
        logger.info("Getting data source config for clone")

        bucket_name = input_.source.source_bucket.id
        credentials_name = f"{pgcluster_crd_name}-src"[:40]

        logger.info("Getting source bucket credentials with id: %s", bucket_name)
        bucket_credentials = await get_or_create_bucket_credentials(
            client=self.client,
            bucket_name=bucket_name,
            credentials_name=credentials_name,
            supported_providers=[
                apolo_sdk.Bucket.Provider.AWS,
                apolo_sdk.Bucket.Provider.MINIO,
                apolo_sdk.Bucket.Provider.GCP,
            ],
        )
        logger.info("Got source bucket credentials")

        provider = bucket_credentials.credentials[0].provider
        credentials = bucket_credentials.credentials[0].credentials

        secret_values, repo_config, extra_global = self._build_provider_values(
            provider, credentials
        )
        preset = get_preset(self.client, input_.source.restore_preset.name)
        resources = preset_to_resources(preset)
        tolerations = await preset_to_tolerations(preset)
        affinity = preset_to_affinity(preset)

        values: dict[str, t.Any] = {
            "dataSourceSecret": secret_values,
            "dataSource": {
                "pgbackrest": {
                    "stanza": "db",
                    "configuration": [
                        {
                            "secret": {
                                "name": f"{pgcluster_crd_name}-src-pgbackrest-secret",
                            },
                        }
                    ],
                    "global": {
                        "repo1-path": input_.source.repo1_path,
                        **extra_global,
                    },
                    "repo": {
                        "name": "repo1",
                        **repo_config,
                    },
                    "options": input_.source.pgbackrest_options,
                    "affinity": affinity,
                    "tolerations": tolerations,
                    "resources": resources,
                },
            },
        }
        return values

    async def gen_extra_values(
        self,
        input_: PostgresInputs,
        app_name: str,
        namespace: str,
        app_id: str,
        app_secrets_name: str,
        *_: t.Any,
        **kwargs: t.Any,
    ) -> dict[str, t.Any]:
        """
        Generate extra Helm values for postgres configuration.
        """
        instances = await self._gen_instances_config(
            instance_preset_name=input_.preset.name,
            instance_replicas=input_.postgres_config.instance_replicas,
            instances_size=input_.postgres_config.instance_size,
        )

        pgbouncer_config = None
        if input_.pg_bouncer:
            pgbouncer_config = await self._get_bouncer_config(
                bouncer_preset_name=input_.pg_bouncer.preset.name,
                bouncer_repicas=int(input_.pg_bouncer.replicas),
            )

        postgrescluster_crd_name = f"pg-{app_id}"
        if len(postgrescluster_crd_name) > POSTGRESQL_CRD_NAME_MAX_LENGTH:
            postgrescluster_crd_name = postgrescluster_crd_name[
                :POSTGRESQL_CRD_NAME_MAX_LENGTH
            ]

        values: dict[str, t.Any] = {
            "metadata": {"labels": {"platform.apolo.us/component": "app"}},
            "features": {
                "AutoCreateUserSchema": "true",
            },
            # empirically measured, postgrescluster crd name is limited to 37 chars
            # otherwise it will fail to create STSs and other resources
            "name": postgrescluster_crd_name,
            "postgresVersion": input_.postgres_config.postgres_version.value,
            "databaseInitSQL": {
                "name": f"{postgrescluster_crd_name}-init-sql",
                "key": "bootstrap.sql",
            },
            "apolo_app_id": app_id,
        }
        users_config = self._create_users_config(input_.postgres_config.db_users)

        if instances:
            values["instances"] = instances
        if pgbouncer_config:
            values["pgBouncerConfig"] = pgbouncer_config
        if users_config:
            values["users"] = users_config

        data_source_values: dict[str, t.Any] = {}
        if input_.source:
            data_source_values = await self._get_data_source_config(
                input_, postgrescluster_crd_name
            )

        backup_values = await self._get_backup_config(
            input_, app_name, namespace, postgrescluster_crd_name
        )

        # Add image configuration for cleanup job
        image_values = {
            "apolo-hooks": {
                "image": {"tag": os.getenv("APP_IMAGE_TAG", "latest")},
            },
        }

        return merge_list_of_dicts(
            [backup_values, data_source_values, values, image_values]
        )
