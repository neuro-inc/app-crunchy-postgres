import pydantic
import pytest
from apolo_apps_postgresql.types import (
    PGBackupConfig,
    PGBackupSchedule,
)

from apolo_app_types.protocols.common import Preset


async def test_values_backup_defaults():
    back = PGBackupConfig(
        backup_preset=Preset(
            name="cpu-small",
        ),
        schedule=PGBackupSchedule(),
    )
    assert back.schedule.full_backup_cron == "0 2 * * 0"
    assert back.schedule.full_backup_retention_count == 4
    assert back.schedule.differential_backup_cron is None
    assert back.schedule.differential_backup_retention_count == 7


async def test_values_backup_full_backup_no_cron():
    with pytest.raises(pydantic.ValidationError) as err:
        PGBackupConfig(
            backup_preset=Preset(
                name="cpu-small",
            ),
            schedule=PGBackupSchedule(
                full_backup_cron="",
            ),
        )
    assert err.value.errors()[0]["msg"] == "String should have at least 9 characters"


async def test_values_backup_full_backup_invalid_schedule():
    with pytest.raises(pydantic.ValidationError) as err:
        PGBackupConfig(
            backup_preset=Preset(
                name="cpu-small",
            ),
            schedule=PGBackupSchedule(
                full_backup_cron="0 2 * * 9",
            ),
        )
    assert (
        err.value.errors()[0]["msg"]
        == "Value error, Invalid cron expression: '0 2 * * 9'"
    )


async def test_values_backup_diff_backup_invalid_schedule():
    with pytest.raises(pydantic.ValidationError) as err:
        PGBackupConfig(
            backup_preset=Preset(
                name="cpu-small",
            ),
            schedule=PGBackupSchedule(
                differential_backup_cron="0 2 * * 9",
            ),
        )
    assert (
        err.value.errors()[0]["msg"]
        == "Value error, Invalid cron expression: '0 2 * * 9'"
    )
