from __future__ import annotations

import enum
import typing as t

from pydantic import ConfigDict, Field, StringConstraints, model_validator

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
        description="Preset to use for the PGBouncer instance.",
        title="Preset",
    )
    replicas: int = Field(
        default=2,
        gt=0,
        description="Number of replicas for the PGBouncer instance.",
        title="PGBouncer replicas",
    )


class PGBackupConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Enable Backups",
            description="Enable backup for your Postgres cluster.",
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
            description="Select the resource preset used for running the backup job.",
        ).as_json_schema_extra(),
    )


class PostgresInputs(AppInputs):
    preset: Preset
    postgres_config: PostgresConfig
    pg_bouncer: PGBouncer
    backup: PGBackupConfig | None = None


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
