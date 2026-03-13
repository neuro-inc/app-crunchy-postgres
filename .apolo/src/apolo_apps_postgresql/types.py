from __future__ import annotations

import enum
import typing as t
from datetime import datetime

from croniter import croniter
from pydantic import (
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from apolo_app_types.protocols.common import (
    AbstractAppFieldType,
    AppInputs,
    AppOutputs,
    Bucket,
    Preset,
    SchemaExtraMetadata,
    SchemaMetaType,
)
from apolo_app_types.protocols.postgres import (
    BasePostgresUserCredentials,
    CrunchyPostgresUserCredentials,
)


POSTGRES_ADMIN_DEFAULT_USER_NAME = "postgres"


class PostgresSupportedVersions(enum.StrEnum):
    v12 = "12"
    v13 = "13"
    v14 = "14"
    v15 = "15"
    v16 = "16"


POSTGRES_RESOURCES_PATTERN = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"


PostgresName = t.Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=63,
        pattern=POSTGRES_RESOURCES_PATTERN,
    ),
]


class PostgresDBUser(AbstractAppFieldType):
    name: PostgresName = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            description=(
                "Name of the database user. "
                "Must be 1-63 characters long, start and end with a lowercase letter "
                "or number, and contain only lowercase letters, numbers, or hyphens."
            ),
            title="Database user name",
        ).as_json_schema_extra(),
    )

    db_names: list[PostgresName] = Field(
        default_factory=list,
        json_schema_extra=SchemaExtraMetadata(
            description=(
                "List of databases this user should have access to. "
                "Databases will be created if they do not exist."
            ),
            title="Databases",
        ).as_json_schema_extra(),
    )


class PostgresConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Postgres",
            description="Configuration for Postgres.",
        ).as_json_schema_extra(),
    )
    postgres_version: PostgresSupportedVersions = Field(
        default=PostgresSupportedVersions.v16,
        json_schema_extra=SchemaExtraMetadata(
            description="Set version of the Postgres server to use.",
            title="Postgres version",
            is_configurable=False,
        ).as_json_schema_extra(),
    )
    instance_replicas: int = Field(
        default=3,
        gt=0,
        json_schema_extra=SchemaExtraMetadata(
            description="Set number of replicas for the Postgres instance.",
            title="Postgres instance replicas",
        ).as_json_schema_extra(),
    )
    instance_size: int = Field(
        default=1,
        gt=0,
        json_schema_extra=SchemaExtraMetadata(
            description="Set size of the Postgres instance disk (in GB).",
            title="Postgres instance disk size",
        ).as_json_schema_extra(),
    )
    db_users: list[PostgresDBUser] = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            description=(
                "Configure list of users and databases they have access to. "
                "Multiple users could have access to the same database."
                "Postgres user 'postgres' is always created and has access "
                "to all databases."
            ),
            title="Database users",
        ).as_json_schema_extra(),
        min_length=1,
    )

    @model_validator(mode="after")
    def check_db_users_not_empty(self) -> PostgresConfig:
        if not self.db_users:
            err_msg = "Database Users list must not be empty."
            raise ValueError(err_msg)

        for user in self.db_users:
            if user.name.lower() == POSTGRES_ADMIN_DEFAULT_USER_NAME:
                err_msg = (
                    f"User name '{POSTGRES_ADMIN_DEFAULT_USER_NAME}'"
                    f" is reserved and this user will be created automatically."
                )
                raise ValueError(err_msg)
        return self


class PGBouncer(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="PG Bouncer",
            description="Configuration for PG Bouncer.",
        ).as_json_schema_extra(),
    )
    preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            description="Preset to use for the PGBouncer instance. "
            "Minimal resources: 0.1 CPU cores, 256 MiB memory.",
            title="Preset",
        ).as_json_schema_extra(),
    )
    replicas: int = Field(
        default=2,
        gt=0,
        description="Number of replicas for the PGBouncer instance.",
        title="PGBouncer replicas",
    )


class PGBackupSchedule(AbstractAppFieldType):
    full_backup_cron: str = Field(
        default="0 2 * * 0",
        min_length=9,
        description=(
            "Cron expression for scheduling full backups. "
            "Supports standard cron syntax.\n"
            "Example: '0 2 * * *' for daily backups at 2 AM. "
            "Default - weekly on Sundays at 2 AM."
        ),
        title="Full backup schedule",
    )
    full_backup_retention_count: int = Field(
        default=4,
        gt=0,
        title="Full backup retention count",
        description=(
            "Number of full backups to retain. "
            "Older backups beyond this count will be automatically deleted.\n"
            "Default is 4, "
            "which means approximately one month of weekly backups will be retained."
        ),
    )
    differential_backup_cron: str | None = Field(
        default=None,
        description=(
            "Cron expression for scheduling differential backups. "
            "If not provided, only full backups will be scheduled.\n"
            "Example: '0 2 * * 1-6' for daily backups at 2 AM from Monday to Saturday. "
            "Default - not scheduled."
        ),
        title="Differential backup schedule",
    )
    differential_backup_retention_count: int = Field(
        default=7,
        gt=0,
        title="Differential backup retention count",
        description=(
            "Number of differential backups to retain. "
            "Older backups beyond this count will be automatically deleted.\n"
            "Default is 7, which is enough to keep diffs between full backups."
        ),
    )

    @field_validator("full_backup_cron", "differential_backup_cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if v is None:
            return v
        if not croniter.is_valid(v):
            msg = f"Invalid cron expression: '{v}'"
            raise ValueError(msg)
        if not croniter(v, datetime.now()).get_next(datetime):
            msg = f"Cron expression does not schedule any runs: '{v}'"
            raise ValueError(msg)
        return v


class PGBackupConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Enable Backups",
            description="Enable backups of your PostgreSQL cluster.",
        ).as_json_schema_extra(),
    )
    backup_bucket: Bucket | None = Field(
        default=None,
        title="Custom backup bucket",
        description=(
            "Optionally provide your own bucket for backups. "
            "If not provided, a default bucket will be created."
        ),
    )
    backup_preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Backup job preset",
            description="Select the resource preset used for running the backup job. "
            "Minimal resources: 0.5 CPU cores, 512 MiB memory.",
        ).as_json_schema_extra(),
    )
    schedule: PGBackupSchedule = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Backup schedule",
            description=(
                "Configure schedule for full, differential, and incremental backups."
            ),
        ).as_json_schema_extra(),
    )


class PGDataSourceConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Configure data source for clone",
            description="Use other PostgreSQL instance backups to clone the database.",
        ).as_json_schema_extra(),
    )
    source_bucket: Bucket = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Set source bucket",
            description=(
                "Provide a bucket of PostgreSQL instance to restore from. "
                "Use source PostgreSQL app instance backup bucket for cloning."
            ),
        ).as_json_schema_extra(),
    )
    repo1_path: str = Field(
        ...,
        title="Provide backup path in source bucket",
        description=(
            "Specify path in the source bucket where backups are stored by pgBackRest.\n"  # noqa: E501
            "Typically follows the pattern: /pgbackrest/{namespace}/pg-{id}/repo1"
        ),
    )
    restore_preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Restore job preset",
            description="Select the resource preset used for running the restore job. "
            "Minimal resources: 0.5 CPU cores, 512 MiB memory.",
        ).as_json_schema_extra(),
    )
    pgbackrest_options: list[str] = Field(
        default=["--type=default"],
        min_length=1,
        title="Overwrite options for pgBackRest",
        description=(
            "Control how pgBackRest rolles out your database copy.\n"
            "See Apolo Documentation page dedicated to for Disaster recovery & Clonning"
            " for PostgreSQL application.\n"
            "If not changed, we perform 'Clone to the latest state'."
        ),
    )


class PostgresInputs(AppInputs):
    preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Postgres cluster preset",
            description="Select the resource preset used for the Postgres "
            "database server instance. "
            "Minimal resources: 0.5 CPU cores, 512 MiB memory.",
        ).as_json_schema_extra(),
    )
    postgres_config: PostgresConfig
    pg_bouncer: PGBouncer | None = None
    backup: PGBackupConfig | None = None
    source: PGDataSourceConfig | None = None


class PostgresAdminUser(BasePostgresUserCredentials):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Postgres Admin User",
            description="Configuration for the Postgres admin user.",
            meta_type=SchemaMetaType.INTEGRATION,
        ).as_json_schema_extra(),
    )
    user_type: t.Literal["admin"] = "admin"


class PostgresUsers(AbstractAppFieldType):
    postgres_admin_user: PostgresAdminUser | None = Field(
        default=None,
        json_schema_extra=SchemaExtraMetadata(
            title="Postgres Admin User",
            description="Admin user for the Postgres instance.",
        ).as_json_schema_extra(),
    )
    users: list[CrunchyPostgresUserCredentials] = Field(
        default_factory=list,
        json_schema_extra=SchemaExtraMetadata(
            title="Postgres Users",
            description="List of Postgres users with their credentials.",
        ).as_json_schema_extra(),
    )


class PostgresOutputs(AppOutputs):
    postgres_users: PostgresUsers | None = None
