import os
import sys
import apolo_sdk
import asyncio
from apolo_apps_postgresql.types import PostgresOutputs
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from apolo_apps_postgresql.scripts.type_search import find_instances_recursive_simple
from apolo_app_types.protocols.common import ApoloSecret

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(exp_base=2, multiplier=2),
)
async def delete_secret_with_retry(secret_key: str) -> None:
    """
    Attempt to delete a secret with retry logic using exponential backoff.
    Retries up to 5 times with delays: 2s, 4s, 8s, 16s, 32s.
    Logs warnings on failure but does not raise exceptions on final failure.
    """
    logger.info(f'Deleting secret "{secret_key}"')
    async with apolo_sdk.get() as client:
        await client.secrets.rm(key=secret_key)
    logger.info(f'Successfully deleted secret "{secret_key}"')


async def get_app_outputs(app_id: str) -> PostgresOutputs | None:
    async with apolo_sdk.get() as client:
        output = client.apps.get_output(app_id=app_id)
    if output:
        return PostgresOutputs.model_validate(output)
    return None

async def cleanup_secrets() -> int:
    app_id_str = os.environ.get("APP_ID")
    if not app_id_str:
        err = "APP_ID must be provided"
        raise Exception(err)

    app_outputs = await get_app_outputs(app_id=app_id_str)
    secrets = find_instances_recursive_simple(obj=app_outputs, target_type=ApoloSecret)
    
    for secret in secrets:
        try:
            await delete_secret_with_retry(
                secret_key=secret.key
            )
        except Exception as e:
            logger.error(
                f'Failed to delete secret "{secret.key}" '
                f"after all retries: {e}"
            )
    return 0


def main() -> int:
    """Entry point"""
    try:
        return asyncio.run(cleanup_secrets())
    except KeyboardInterrupt:
        logger.info("Cleanup interrupted by user")
        return 1


if __name__ == "__main__":
    sys.exit(main())


