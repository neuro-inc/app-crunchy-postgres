import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from apolo_apps_postgresql.scripts.cleanup_secrets import (
    cleanup_secrets,
    delete_secret_with_retry,
    get_app_outputs,
    main,
)
from apolo_apps_postgresql.types import (
    PostgresOutputs,
    PostgresUsers,
    PostgresAdminUser,
)
from apolo_app_types import CrunchyPostgresUserCredentials, ApoloSecret


@pytest.fixture
def complete_postgres_outputs():
    """
    Complete PostgresOutputs structure with all fields populated.
    This follows Anti-Pattern 4: provide complete mock structures.
    """
    return PostgresOutputs(
        postgres_users=PostgresUsers(
            postgres_admin_user=PostgresAdminUser(
                user="postgres",
                password=ApoloSecret(key="postgres-admin-password"),
                host="postgres-primary",
                port=5432,
                pgbouncer_host="postgres-pgbouncer",
                pgbouncer_port=5432,
            ),
            users=[
                CrunchyPostgresUserCredentials(
                    user="appuser",
                    password=ApoloSecret(key="postgres-appuser-password"),
                    host="postgres-primary",
                    port=5432,
                    pgbouncer_host="postgres-pgbouncer",
                    pgbouncer_port=5432,
                    dbname="appdb",
                    pgbouncer_uri=ApoloSecret(key="postgres-appuser-pgbouncer-uri"),
                    postgres_uri=ApoloSecret(key="postgres-appuser-connection-uri"),
                ),
            ],
        )
    )


@pytest.fixture
def mock_apolo_client():
    """Mock apolo_sdk.get() context manager."""
    mock_client = MagicMock()
    mock_client.secrets.rm = AsyncMock()
    mock_client.apps.get_output = MagicMock()

    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_client
    mock_context.__aexit__.return_value = None

    return mock_client, mock_context


class TestCleanupSecrets:
    """Tests for the cleanup_secrets function."""

    @pytest.mark.asyncio
    async def test_raises_exception_when_app_id_missing(self, monkeypatch):
        """Test that cleanup_secrets raises exception when APP_ID env var is not set."""
        # Ensure APP_ID is not set
        monkeypatch.delenv("APP_ID", raising=False)

        with pytest.raises(Exception, match="APP_ID must be provided"):
            await cleanup_secrets()

    @pytest.mark.asyncio
    async def test_deletes_all_secrets_from_outputs(
        self, complete_postgres_outputs, mock_apolo_client, monkeypatch
    ):
        """
        Test that cleanup_secrets finds and deletes all secrets in outputs.

        This tests REAL BEHAVIOR: that secrets are actually deleted,
        not just that mocks were called. (Anti-Pattern 1)
        """
        monkeypatch.setenv("APP_ID", "test-app-123")

        mock_client, mock_context = mock_apolo_client
        mock_client.apps.get_output.return_value = complete_postgres_outputs.model_dump()

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            result = await cleanup_secrets()

        # Verify behavior: all 4 secrets should be deleted
        assert result == 0
        assert mock_client.secrets.rm.call_count == 4

        # Verify the correct secrets were targeted
        deleted_keys = {call.kwargs["key"] for call in mock_client.secrets.rm.call_args_list}
        assert deleted_keys == {
            "postgres-admin-password",
            "postgres-appuser-password",
            "postgres-appuser-pgbouncer-uri",
            "postgres-appuser-connection-uri",
        }

    @pytest.mark.asyncio
    async def test_handles_empty_outputs(self, mock_apolo_client, monkeypatch):
        """Test cleanup_secrets when outputs contain no secrets."""
        monkeypatch.setenv("APP_ID", "test-app-123")

        empty_outputs = PostgresOutputs(postgres_users=None)

        mock_client, mock_context = mock_apolo_client
        mock_client.apps.get_output.return_value = empty_outputs.model_dump()

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            result = await cleanup_secrets()

        # Should complete successfully without attempting deletions
        assert result == 0
        assert mock_client.secrets.rm.call_count == 0

    @pytest.mark.asyncio
    async def test_continues_on_deletion_errors(
        self, complete_postgres_outputs, mock_apolo_client, monkeypatch, caplog
    ):
        """
        Test that cleanup_secrets continues processing when individual
        secret deletions fail.
        """
        monkeypatch.setenv("APP_ID", "test-app-123")

        mock_client, mock_context = mock_apolo_client
        mock_client.apps.get_output.return_value = complete_postgres_outputs.model_dump()

        # Make first deletion fail, rest succeed
        call_count = 0
        async def mock_rm_with_failure(key):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary API error")

        mock_client.secrets.rm.side_effect = mock_rm_with_failure

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            result = await cleanup_secrets()

        # Should complete and attempt all deletions despite errors
        assert result == 0
        # First secret fails once then succeeds (2 calls), plus 3 other secrets = 5 total
        assert mock_client.secrets.rm.call_count == 5

    @pytest.mark.asyncio
    async def test_handles_null_output_from_api(self, mock_apolo_client, monkeypatch):
        """Test cleanup_secrets when get_output returns None."""
        monkeypatch.setenv("APP_ID", "test-app-123")

        mock_client, mock_context = mock_apolo_client
        mock_client.apps.get_output.return_value = None

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            result = await cleanup_secrets()

        assert result == 0
        assert mock_client.secrets.rm.call_count == 0


class TestDeleteSecretWithRetry:
    """Tests for the delete_secret_with_retry function."""

    @pytest.mark.asyncio
    async def test_deletes_secret_successfully(self, mock_apolo_client):
        """Test successful secret deletion on first attempt."""
        mock_client, mock_context = mock_apolo_client

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            await delete_secret_with_retry("test-secret-key")

        mock_client.secrets.rm.assert_called_once_with(key="test-secret-key")

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, mock_apolo_client):
        """Test that function retries with exponential backoff on failure."""
        mock_client, mock_context = mock_apolo_client

        # Fail twice, then succeed
        mock_client.secrets.rm.side_effect = [
            Exception("Temporary failure"),
            Exception("Temporary failure"),
            None,  # Success
        ]

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            await delete_secret_with_retry("test-secret-key")

        # Should have retried 3 times total
        assert mock_client.secrets.rm.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, mock_apolo_client):
        """Test that function raises exception after maximum retry attempts."""
        mock_client, mock_context = mock_apolo_client

        # Fail all 5 attempts
        mock_client.secrets.rm.side_effect = Exception("Persistent failure")

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            with pytest.raises(Exception):
                await delete_secret_with_retry("test-secret-key")

        # Should have attempted 5 times
        assert mock_client.secrets.rm.call_count == 5


class TestGetAppOutputs:
    """Tests for the get_app_outputs function."""

    @pytest.mark.asyncio
    async def test_returns_postgres_outputs_when_available(
        self, complete_postgres_outputs, mock_apolo_client
    ):
        """Test get_app_outputs returns valid PostgresOutputs."""
        mock_client, mock_context = mock_apolo_client
        mock_client.apps.get_output.return_value = complete_postgres_outputs.model_dump()

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            result = await get_app_outputs("test-app-123")

        assert isinstance(result, PostgresOutputs)
        assert result.postgres_users is not None
        assert result.postgres_users.postgres_admin_user is not None
        mock_client.apps.get_output.assert_called_once_with(app_id="test-app-123")

    @pytest.mark.asyncio
    async def test_returns_none_when_no_output(self, mock_apolo_client):
        """Test get_app_outputs returns None when API returns no output."""
        mock_client, mock_context = mock_apolo_client
        mock_client.apps.get_output.return_value = None

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.apolo_sdk.get",
            return_value=mock_context,
        ):
            result = await get_app_outputs("test-app-123")

        assert result is None


class TestMain:
    """Tests for the main entry point."""

    def test_returns_zero_on_success(self, monkeypatch):
        """Test main returns 0 when cleanup succeeds."""
        monkeypatch.setenv("APP_ID", "test-app-123")

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.cleanup_secrets",
            new_callable=AsyncMock,
            return_value=0,
        ):
            result = main()

        assert result == 0

    def test_returns_one_on_keyboard_interrupt(self, monkeypatch, caplog):
        """Test main returns 1 and logs message on KeyboardInterrupt."""
        monkeypatch.setenv("APP_ID", "test-app-123")

        async def raise_keyboard_interrupt():
            raise KeyboardInterrupt()

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.cleanup_secrets",
            side_effect=raise_keyboard_interrupt,
        ):
            result = main()

        assert result == 1
        assert "Cleanup interrupted by user" in caplog.text

    def test_propagates_exceptions(self, monkeypatch):
        """Test main propagates non-KeyboardInterrupt exceptions."""
        monkeypatch.setenv("APP_ID", "test-app-123")

        async def raise_exception():
            raise ValueError("Test error")

        with patch(
            "apolo_apps_postgresql.scripts.cleanup_secrets.cleanup_secrets",
            side_effect=raise_exception,
        ):
            with pytest.raises(ValueError, match="Test error"):
                main()
