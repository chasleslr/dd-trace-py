from typing import Text

from ddtrace.appsec._common_module_patches import try_unwrap
from ddtrace.internal.logger import get_logger
from ddtrace.settings.asm import config as asm_config

from ..._constants import IAST
from .._patch import set_and_check_module_is_patched
from .._patch import set_module_unpatched
from .._patch import try_wrap_function_wrapper


log = get_logger(__name__)


_DEFAULT_ATTR = "_datadog_json_tainting_patch"


def get_version() -> Text:
    return ""


def unpatch_iast():
    set_module_unpatched("json", default_attr=_DEFAULT_ATTR)
    try_unwrap("json", "loads")
    if asm_config._iast_lazy_taint:
        try_unwrap("json.encoder", "JSONEncoder.default")
        try_unwrap("simplejson.encoder", "JSONEncoder.default")


def patch():
    """Wrap functions which interact with file system."""
    if not set_and_check_module_is_patched("json", default_attr=_DEFAULT_ATTR):
        return
    try_wrap_function_wrapper("json", "loads", wrapped_loads)
    if asm_config._iast_lazy_taint:
        try_wrap_function_wrapper("json.encoder", "JSONEncoder.default", patched_json_encoder_default)
        try_wrap_function_wrapper("simplejson.encoder", "JSONEncoder.default", patched_json_encoder_default)


def wrapped_loads(wrapped, instance, args, kwargs):
    from .._taint_utils import taint_structure

    obj = wrapped(*args, **kwargs)
    if asm_config._iast_enabled and asm_config.is_iast_request_enabled:
        from .._taint_tracking._taint_objects import taint_pyobject
        from .._taint_tracking._taint_objects_base import get_tainted_ranges

        ranges = get_tainted_ranges(args[0])

        if ranges and obj:
            try:
                # take the first source as main source
                source = ranges[0].source
                if isinstance(obj, dict):
                    obj = taint_structure(obj, source.origin, source.origin)
                elif isinstance(obj, list):
                    obj = taint_structure(obj, source.origin, source.origin)
                elif isinstance(obj, IAST.TEXT_TYPES):
                    obj = taint_pyobject(obj, source.name, source.value, source.origin)
            except Exception:
                log.debug("Unexpected exception while reporting vulnerability", exc_info=True)
                raise
    return obj


def patched_json_encoder_default(original_func, instance, args, kwargs):
    from .._taint_utils import LazyTaintDict
    from .._taint_utils import LazyTaintList

    if isinstance(args[0], (LazyTaintList, LazyTaintDict)):
        return args[0]._obj

    return original_func(*args, **kwargs)
