"""Small completion hook for the existing MATLAB/Grasshopper workflow.

No GUI imports, app build, MATLAB Engine or extra runtime packages.
"""
from functools import wraps
import time

from habsim_notifications import notify_completion


def completed(success, elapsed=None, scope="run", wait=False):
    """Alert delivery must never change the calculation's outcome."""
    try:
        receipt = notify_completion(success=success, elapsed_seconds=elapsed, scope=scope)
        if wait:
            # The CLI can exit immediately afterwards; delivery uses daemon threads.
            receipt.wait(45)
        return receipt
    except Exception:
        return None


def notify_run(function):
    """Wrap a runner returning a MATLAB status code; alert once per call."""
    @wraps(function)
    def run(*args, **kwargs):
        started = time.monotonic()
        success = False
        cancelled = False
        try:
            result = function(*args, **kwargs)
            success = result == 0
            return result
        except (KeyboardInterrupt, SystemExit):
            cancelled = True
            raise
        finally:
            if not cancelled:
                completed(success, time.monotonic() - started, wait=True)
    return run


def notify_batch(state):
    """Called only on a batch terminal transition; deliberate Stop is silent.

    Whole-loop scope must be selected in settings. Per-run scope is handled
    by notify_run instead, so the two modes never produce duplicate alerts.
    """
    if state.get("status") in ("complete", "error"):
        started = state.get("started")
        elapsed = max(0, time.time() - started) if isinstance(started, (int, float)) else None
        return completed(state["status"] == "complete", elapsed, scope="loop")
    return None
