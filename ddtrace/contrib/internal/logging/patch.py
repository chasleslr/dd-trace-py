import logging

from wrapt import wrap_function_wrapper as _w

import ddtrace
from ddtrace import config
from ddtrace.contrib.internal.trace_utils import unwrap as _u
from ddtrace.internal.utils import get_argument_value

from .constants import RECORD_ATTR_ENV
from .constants import RECORD_ATTR_SERVICE
from .constants import RECORD_ATTR_SPAN_ID
from .constants import RECORD_ATTR_TRACE_ID
from .constants import RECORD_ATTR_VALUE_EMPTY
from .constants import RECORD_ATTR_VALUE_ZERO
from .constants import RECORD_ATTR_VERSION


_LOG_SPAN_KEY = "__datadog_log_span"

config._add(
    "logging",
    dict(
        tracer=None,
    ),
)  # by default, override here for custom tracer


def get_version():
    # type: () -> str
    return getattr(logging, "__version__", "")


class DDLogRecord:
    trace_id: int
    span_id: int
    service: str
    version: str
    env: str
    __slots__ = ("trace_id", "span_id", "service", "version", "env")

    def __init__(self, trace_id: int, span_id: int, service: str, version: str, env: str):
        self.trace_id = trace_id
        self.span_id = span_id
        self.service = service
        self.version = version
        self.env = env


def _get_tracer(tracer=None):
    if not tracer:
        # With the addition of a custom ddtrace logger in _logger.py, logs that happen on startup
        # don't have access to `ddtrace.tracer`. Checking that this exists prevents an error
        # if log injection is enabled.
        if not getattr(ddtrace, "tracer", False):
            return None

        tracer = ddtrace.tracer

    # We might be calling this during library initialization, in which case `ddtrace.tracer` might
    # be the `tracer` module and not the global tracer instance.
    if not getattr(tracer, "enabled", False):
        return None

    return tracer


def _w_makeRecord(func, instance, args, kwargs):
    # Get the LogRecord instance for this log
    record = func(*args, **kwargs)

    setattr(record, RECORD_ATTR_VERSION, config.version or RECORD_ATTR_VALUE_EMPTY)
    setattr(record, RECORD_ATTR_ENV, config.env or RECORD_ATTR_VALUE_EMPTY)
    setattr(record, RECORD_ATTR_SERVICE, config.service or RECORD_ATTR_VALUE_EMPTY)

    tracer = _get_tracer(tracer=config.logging.tracer)
    trace_details = {}
    span = None

    # logs from internal logger may explicitly pass the current span to
    # avoid deadlocks in getting the current span while already in locked code.
    span_from_log = getattr(record, _LOG_SPAN_KEY, None)
    if isinstance(span_from_log, ddtrace.trace.Span):
        span = span_from_log

    if tracer:
        trace_details = tracer.get_log_correlation_context(active=span)

    setattr(record, RECORD_ATTR_TRACE_ID, trace_details.get("trace_id", "0"))
    setattr(record, RECORD_ATTR_SPAN_ID, trace_details.get("span_id", "0"))

    return record


def _w_StrFormatStyle_format(func, instance, args, kwargs):
    # The format string "dd.service={dd.service}" expects
    # the record to have a "dd" property which is an object that
    # has a "service" property
    # PercentStyle, and StringTemplateStyle both look for
    # a "dd.service" property on the record
    record = get_argument_value(args, kwargs, 0, "record")

    record.dd = DDLogRecord(
        trace_id=getattr(record, RECORD_ATTR_TRACE_ID, RECORD_ATTR_VALUE_ZERO),
        span_id=getattr(record, RECORD_ATTR_SPAN_ID, RECORD_ATTR_VALUE_ZERO),
        service=getattr(record, RECORD_ATTR_SERVICE, RECORD_ATTR_VALUE_EMPTY),
        version=getattr(record, RECORD_ATTR_VERSION, RECORD_ATTR_VALUE_EMPTY),
        env=getattr(record, RECORD_ATTR_ENV, RECORD_ATTR_VALUE_EMPTY),
    )

    try:
        return func(*args, **kwargs)
    finally:
        # We need to remove this extra attribute so it does not pollute other formatters
        # For example: if we format with StrFormatStyle and then  a JSON logger
        # then the JSON logger will have `dd.{service,version,env,trace_id,span_id}` as
        # well as the `record.dd` `DDLogRecord` instance
        del record.dd


def patch():
    """
    Patch ``logging`` module in the Python Standard Library for injection of
    tracer information by wrapping the base factory method ``Logger.makeRecord``
    """
    if getattr(logging, "_datadog_patch", False):
        return
    logging._datadog_patch = True

    _w(logging.Logger, "makeRecord", _w_makeRecord)
    if hasattr(logging, "StrFormatStyle"):
        if hasattr(logging.StrFormatStyle, "_format"):
            _w(logging.StrFormatStyle, "_format", _w_StrFormatStyle_format)
        else:
            _w(logging.StrFormatStyle, "format", _w_StrFormatStyle_format)


def unpatch():
    if getattr(logging, "_datadog_patch", False):
        logging._datadog_patch = False

        _u(logging.Logger, "makeRecord")
        if hasattr(logging, "StrFormatStyle"):
            if hasattr(logging.StrFormatStyle, "_format"):
                _u(logging.StrFormatStyle, "_format")
            else:
                _u(logging.StrFormatStyle, "format")
