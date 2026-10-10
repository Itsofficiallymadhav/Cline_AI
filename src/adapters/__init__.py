from src.adapters.base import RecordAdapter
from src.adapters.sample import SampleAdapter


def get_adapter() -> RecordAdapter:
    """Swap in a live read-only adapter here later; the demo must never depend on it."""
    return SampleAdapter()
