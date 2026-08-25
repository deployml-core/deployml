"""Unit test for the batch-splitting logic in the streaming tutorial. No GCP/FastAPI calls."""
import importlib.util
from pathlib import Path

DATASET_MODULE_PATH = Path(__file__).parent.parent / "example" / "tutorial_streaming" / "_dataset.py"


def _load_dataset_module():
    spec = importlib.util.spec_from_file_location("tutorial_streaming_dataset", DATASET_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


split_into_batches = _load_dataset_module().split_into_batches


def test_split_into_batches_covers_every_row_once():
    rows = [{"entity_id": i} for i in range(300)]
    batches = split_into_batches(rows, 5)

    assert len(batches) == 5
    flattened = [row for batch in batches for row in batch]
    assert sorted(row["entity_id"] for row in flattened) == list(range(300))


def test_split_into_batches_near_equal_sizes():
    rows = [{"entity_id": i} for i in range(7)]
    batches = split_into_batches(rows, 3)

    sizes = sorted(len(b) for b in batches)
    assert sizes == [2, 2, 3]


def test_split_into_batches_more_batches_than_rows():
    rows = [{"entity_id": i} for i in range(2)]
    batches = split_into_batches(rows, 5)

    assert len(batches) == 5
    flattened = [row for batch in batches for row in batch]
    assert sorted(row["entity_id"] for row in flattened) == [0, 1]
