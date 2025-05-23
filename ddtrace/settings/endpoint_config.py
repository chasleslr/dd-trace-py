"""
This module contains the logic to configure ddtrace products from a configuration endpoint.
The configuration endpoint is a URL that returns a JSON object with the configuration for the products.
It takes precedence over environment variables and configuration files.
"""
import os

from ddtrace.constants import _CONFIG_ENDPOINT_ENV
from ddtrace.constants import _CONFIG_ENDPOINT_RETRIES_ENV
from ddtrace.constants import _CONFIG_ENDPOINT_TIMEOUT_ENV
from ddtrace.internal.constants import DEFAULT_TIMEOUT
from ddtrace.internal.logger import get_logger
from ddtrace.internal.utils.http import Response
from ddtrace.internal.utils.http import get_connection
from ddtrace.internal.utils.http import verify_url
from ddtrace.internal.utils.retry import fibonacci_backoff_with_jitter


log = get_logger(__name__)

RETRIES = 1
try:
    if _CONFIG_ENDPOINT_RETRIES_ENV in os.environ:
        RETRIES = int(os.getenv(_CONFIG_ENDPOINT_RETRIES_ENV, str(RETRIES)))
except ValueError:
    log.error("Invalid value for %s. Using default value: %s", _CONFIG_ENDPOINT_RETRIES_ENV, RETRIES)


def _get_retries():
    return RETRIES


TIMEOUT = DEFAULT_TIMEOUT
try:
    if _CONFIG_ENDPOINT_TIMEOUT_ENV in os.environ:
        TIMEOUT = int(os.getenv(_CONFIG_ENDPOINT_TIMEOUT_ENV, str(TIMEOUT)))
except ValueError:
    log.error("Invalid value for %s. Using default value: %s", _CONFIG_ENDPOINT_TIMEOUT_ENV, TIMEOUT)


def _get_timeout():
    return TIMEOUT


def _do_request(url: str) -> Response:
    try:
        parsed_url = verify_url(url)
        url_path = parsed_url.path
        conn = get_connection(url, timeout=_get_timeout())
        conn.request("GET", url_path)
        response = conn.getresponse()
        result = Response.from_http_response(response)
    finally:
        conn.close()
    return result


def fetch_config_from_endpoint() -> dict:
    """
    Fetch the configuration from the configuration endpoint.
    """
    config_endpoint = os.getenv(_CONFIG_ENDPOINT_ENV, None)

    if config_endpoint is None:
        log.debug("Configuration endpoint not set. Skipping fetching configuration.")
        return {}

    try:
        # DEV: This can also work as a decorator,
        # but it's harder to mock the retries in the tests.
        res = fibonacci_backoff_with_jitter(
            attempts=_get_retries(),
            initial_wait=0.1,
            until=lambda resp: hasattr(resp, "status") and (200 <= resp.status < 300),
        )(_do_request)(config_endpoint)

        return res.get_json() or {}
    except Exception:
        log.error("Failed to fetch configuration from endpoint", exc_info=True)

    return {}
