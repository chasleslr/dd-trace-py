import os
from typing import Any
from typing import Callable
from typing import List
from typing import Tuple

from ddtrace.debugging._encoding import BufferedEncoder
from ddtrace.debugging._metrics import metrics
from ddtrace.debugging._signal.log import LogSignal
from ddtrace.debugging._signal.model import Signal
from ddtrace.debugging._signal.model import SignalState
from ddtrace.internal._encoding import BufferFull
from ddtrace.internal.compat import ExcInfoType
from ddtrace.internal.logger import get_logger


CaptorType = Callable[[List[Tuple[str, Any]], List[Tuple[str, Any]], ExcInfoType, int], Any]

log = get_logger(__name__)
meter = metrics.get_meter("signal.collector")


class SignalCollector(object):
    """Debugger signal collector.

    This is used to collect and encode signals emitted by probes as soon as
    requested. The ``push`` method is intended to be called after a line-level
    signal is fully emitted, and information is available and ready to be
    encoded, or the signal status indicate it should be skipped.
    """

    def __init__(self, encoder: BufferedEncoder) -> None:
        self._encoder = encoder

    def _enqueue(self, log_signal: LogSignal) -> None:
        try:
            log.debug(
                "[%s][P: %s] SignalCollector. _encoder (%s) _enqueue signal", os.getpid(), os.getppid(), self._encoder
            )
            self._encoder.put(log_signal)
        except BufferFull:
            log.debug("Encoder buffer full")
            meter.increment("encoder.buffer.full")

    def push(self, signal: Signal) -> None:
        if signal.state is SignalState.SKIP_COND:
            meter.increment("skip", tags={"cause": "cond", "probe_id": signal.probe.probe_id})
        elif signal.state in {SignalState.SKIP_COND_ERROR, SignalState.COND_ERROR}:
            meter.increment("skip", tags={"cause": "cond_error", "probe_id": signal.probe.probe_id})
        elif signal.state is SignalState.SKIP_RATE:
            meter.increment("skip", tags={"cause": "rate", "probe_id": signal.probe.probe_id})
        elif signal.state is SignalState.SKIP_BUDGET:
            meter.increment("skip", tags={"cause": "budget", "probe_id": signal.probe.probe_id})
        elif signal.state is SignalState.DONE:
            meter.increment("signal", tags={"probe_id": signal.probe.probe_id})

        if (
            isinstance(signal, LogSignal)
            and signal.state in {SignalState.DONE, SignalState.COND_ERROR}
            and signal.has_message()
        ):
            log.debug("Enqueueing signal %s", signal)
            # This signal emits a log message
            self._enqueue(signal)
        else:
            log.debug(
                "Skipping signal %s (has message: %s)", signal, isinstance(signal, LogSignal) and signal.has_message()
            )
