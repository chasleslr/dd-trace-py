from typing import Optional

from ddtrace.internal.ci_visibility.telemetry.constants import ERROR_TYPES
from ddtrace.internal.ci_visibility.telemetry.constants import GIT_TELEMETRY
from ddtrace.internal.ci_visibility.telemetry.constants import GIT_TELEMETRY_COMMANDS
from ddtrace.internal.logger import get_logger
from ddtrace.internal.telemetry import telemetry_writer
from ddtrace.internal.telemetry.constants import TELEMETRY_NAMESPACE


log = get_logger(__name__)


def record_git_command(command: GIT_TELEMETRY_COMMANDS, duration: float, exit_code: Optional[int]) -> None:
    log.debug("Recording git command telemetry: %s, %s, %s", command, duration, exit_code)
    tags = (("command", command),)
    telemetry_writer.add_count_metric(TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.COMMAND_COUNT, 1, tags)
    telemetry_writer.add_distribution_metric(TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.COMMAND_MS, duration, tags)
    if exit_code is not None and exit_code != 0:
        error_tags = (("command", command), ("exit_code", str(exit_code)))
        telemetry_writer.add_count_metric(TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.COMMAND_ERRORS, 1, error_tags)


def record_search_commits(duration: float, error: Optional[ERROR_TYPES] = None) -> None:
    log.debug("Recording search commits telemetry: %s, %s", duration, error)
    telemetry_writer.add_count_metric(TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.SEARCH_COMMITS_COUNT, 1)
    telemetry_writer.add_distribution_metric(
        TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.SEARCH_COMMITS_MS, duration
    )
    if error is not None:
        error_tags = (("error_type", str(error)),)
        telemetry_writer.add_count_metric(
            TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.SEARCH_COMMITS_ERRORS, 1, error_tags
        )


def record_objects_pack_request(duration: float, error: Optional[ERROR_TYPES] = None) -> None:
    log.debug("Recording objects pack request telmetry: %s, %s", duration, error)
    telemetry_writer.add_count_metric(TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.OBJECTS_PACK_COUNT, 1)
    telemetry_writer.add_distribution_metric(TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.OBJECTS_PACK_MS, duration)
    if error is not None:
        error_tags = (("error", error),)
        telemetry_writer.add_count_metric(
            TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.OBJECTS_PACK_ERRORS, 1, error_tags
        )


def record_objects_pack_data(num_files: int, num_bytes: int) -> None:
    log.debug("Recording objects pack data telemetry: %s, %s", num_files, num_bytes)
    telemetry_writer.add_distribution_metric(
        TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.OBJECTS_PACK_BYTES, num_bytes
    )
    telemetry_writer.add_distribution_metric(
        TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.OBJECTS_PACK_FILES, num_files
    )


def record_settings_response(
    coverage_enabled: Optional[bool] = False,
    skipping_enabled: Optional[bool] = False,
    require_git: Optional[bool] = False,
    itr_enabled: Optional[bool] = False,
    flaky_test_retries_enabled: Optional[bool] = False,
    known_tests_enabled: Optional[bool] = False,
    early_flake_detection_enabled: Optional[bool] = False,
    test_management_enabled: Optional[bool] = False,
) -> None:
    log.debug(
        "Recording settings telemetry:"
        " coverage_enabled=%s"
        ", skipping_enabled=%s"
        ", require_git=%s"
        ", itr_enabled=%s"
        ", flaky_test_retries_enabled=%s"
        ", known_tests_enabled=%s"
        ", early_flake_detection_enabled=%s"
        ", test_management_enabled=%s",
        coverage_enabled,
        skipping_enabled,
        require_git,
        itr_enabled,
        flaky_test_retries_enabled,
        known_tests_enabled,
        early_flake_detection_enabled,
        test_management_enabled,
    )
    # Telemetry "booleans" are true if they exist, otherwise false
    response_tags = []
    if coverage_enabled:
        response_tags.append(("coverage_enabled", "true"))
    if skipping_enabled:
        response_tags.append(("itrskip_enabled", "true"))
    if require_git:
        response_tags.append(("require_git", "true"))
    if itr_enabled:
        response_tags.append(("itr_enabled", "true"))
    if flaky_test_retries_enabled:
        response_tags.append(("flaky_test_retries_enabled", "true"))
    if known_tests_enabled:
        response_tags.append(("known_tests_enabled", "true"))
    if early_flake_detection_enabled:
        response_tags.append(("early_flake_detection_enabled", "true"))
    if test_management_enabled:
        response_tags.append(("test_management_enabled", "true"))

    if response_tags:
        telemetry_writer.add_count_metric(
            TELEMETRY_NAMESPACE.CIVISIBILITY, GIT_TELEMETRY.SETTINGS_RESPONSE, 1, tuple(response_tags)
        )
