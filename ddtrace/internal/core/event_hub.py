import dataclasses
import enum
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from ddtrace.settings._config import config


_listeners: Dict[str, Dict[Any, Callable[..., Any]]] = {}
_all_listeners: List[Callable[[str, Tuple[Any, ...]], None]] = []


class ResultType(enum.Enum):
    RESULT_OK = 0
    RESULT_EXCEPTION = 1
    RESULT_UNDEFINED = -1


@dataclasses.dataclass
class EventResult:
    response_type: ResultType = ResultType.RESULT_UNDEFINED
    value: Any = None
    exception: Optional[Exception] = None

    def __bool__(self):
        "EventResult can easily be checked as a valid result"
        return self.response_type == ResultType.RESULT_OK


_MissingEvent = EventResult()


class EventResultDict(Dict[str, EventResult]):
    def __missing__(self, key: str) -> EventResult:
        return _MissingEvent

    def __getattr__(self, name: str) -> EventResult:
        return dict.__getitem__(self, name)


_MissingEventDict = EventResultDict()


def has_listeners(event_id: str) -> bool:
    """Check if there are hooks registered for the provided event_id"""
    global _listeners
    return bool(_listeners.get(event_id))


def on(event_id: str, callback: Callable[..., Any], name: Any = None) -> None:
    """Register a listener for the provided event_id"""
    global _listeners
    if name is None:
        name = id(callback)
    if event_id not in _listeners:
        _listeners[event_id] = {}
    _listeners[event_id][name] = callback


def on_all(callback: Callable[..., Any]) -> None:
    """Register a listener for all events emitted"""
    global _all_listeners
    if callback not in _all_listeners:
        _all_listeners.insert(0, callback)


def reset(event_id: Optional[str] = None, callback: Optional[Callable[..., Any]] = None) -> None:
    """Remove all registered listeners. If an event_id is provided, only clear those
    event listeners. If a callback is provided, then only the listeners for that callback are removed.
    """
    global _listeners
    global _all_listeners

    if callback:
        if not event_id:
            _all_listeners = [cb for cb in _all_listeners if cb != callback]
        elif event_id in _listeners:
            _listeners[event_id] = {name: cb for name, cb in _listeners[event_id].items() if cb != callback}
    else:
        if not event_id:
            _listeners.clear()
            _all_listeners.clear()
        elif event_id in _listeners:
            del _listeners[event_id]


def dispatch(event_id: str, args: Tuple[Any, ...] = ()) -> None:
    """Call all hooks for the provided event_id with the provided args"""
    global _all_listeners
    global _listeners

    for hook in _all_listeners:
        try:
            hook(event_id, args)
        except Exception:
            if config._raise:
                raise

    if event_id not in _listeners:
        return

    for local_hook in _listeners[event_id].values():
        try:
            local_hook(*args)
        except Exception:
            if config._raise:
                raise


def dispatch_with_results(event_id: str, args: Tuple[Any, ...] = ()) -> EventResultDict:
    """Call all hooks for the provided event_id with the provided args
    returning the results and exceptions from the called hooks
    """
    global _listeners
    global _all_listeners

    for hook in _all_listeners:
        try:
            hook(event_id, args)
        except Exception:
            if config._raise:
                raise

    if event_id not in _listeners:
        return _MissingEventDict

    results = EventResultDict()
    for name, hook in _listeners[event_id].items():
        try:
            results[name] = EventResult(ResultType.RESULT_OK, hook(*args))
        except Exception as e:
            if config._raise:
                raise
            results[name] = EventResult(ResultType.RESULT_EXCEPTION, None, e)

    return results
