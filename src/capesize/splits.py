"""Walk-forward splits with a purge for overlapping h-day targets (docs/02, section 3.6)."""
from collections.abc import Iterator

import numpy as np
import pandas as pd


def walk_forward_splits(dates, first_test, h: int, refit: str = "M",
                        min_train: int = 250) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window splits on a sorted trading-day grid; returns positional indices.

    One test block per refit period (pandas period code: "M" month, "W" week) from first_test on.
    Purge: the target of row i uses S_{i+h}, so a training row needs i + h < first test row; the last
    h rows before each test block are dropped from training. Folds with < min_train rows are skipped.
    """
    d = pd.DatetimeIndex(pd.to_datetime(dates))
    if not d.is_monotonic_increasing:
        raise ValueError("dates must be sorted ascending")
    first = int(d.searchsorted(pd.Timestamp(first_test)))
    if first >= len(d):
        return
    period = d.to_period(refit)
    starts = [first] + [i for i in range(first + 1, len(d)) if period[i] != period[i - 1]]
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(d)
        train_end = s - h
        if train_end < min_train:
            continue
        yield np.arange(0, train_end), np.arange(s, e)
