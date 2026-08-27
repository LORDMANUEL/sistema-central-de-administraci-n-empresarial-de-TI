from dataclasses import dataclass
from math import isfinite
from typing import Mapping


class MetricNotAllowed(ValueError):
    pass


class MetricValueInvalid(ValueError):
    pass


class MetricLabelsInvalid(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NormalizedSample:
    metric: str
    value: int | float
    labels: dict[str, str]


_DISK_METRICS = {"disk.free_bytes", "disk.total_bytes"}
_INTEGER_NONNEGATIVE = {
    "memory.used_bytes",
    "disk.free_bytes",
    "network.rx_bytes_total",
    "network.tx_bytes_total",
}
_INTEGER_POSITIVE = {"memory.total_bytes", "disk.total_bytes"}
_ALLOWED_METRICS = {"cpu.utilization_pct"} | _INTEGER_NONNEGATIVE | _INTEGER_POSITIVE


def _normalize_labels(metric: str, labels: Mapping[str, str] | None) -> dict[str, str]:
    normalized = dict(labels or {})
    if len(normalized) > 4:
        raise MetricLabelsInvalid("at most four labels are allowed")

    for key, value in normalized.items():
        if not isinstance(key, str) or not 1 <= len(key) <= 32:
            raise MetricLabelsInvalid("label keys must contain 1..32 characters")
        if not isinstance(value, str) or not 1 <= len(value) <= 128:
            raise MetricLabelsInvalid("label values must contain 1..128 characters")

    expected = {"volume"} if metric in _DISK_METRICS else set()
    if set(normalized) != expected:
        raise MetricLabelsInvalid("labels do not match the metric schema")
    return normalized


def _require_integer(value: object, *, positive: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetricValueInvalid("metric requires an integer value")
    if positive and value <= 0:
        raise MetricValueInvalid("metric value must be positive")
    if not positive and value < 0:
        raise MetricValueInvalid("metric value must be non-negative")
    return value


def validate_sample(
    metric: str,
    value: int | float,
    labels: Mapping[str, str] | None = None,
) -> NormalizedSample:
    if metric not in _ALLOWED_METRICS:
        raise MetricNotAllowed(f"unsupported metric: {metric}")

    normalized_labels = _normalize_labels(metric, labels)

    if metric == "cpu.utilization_pct":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MetricValueInvalid("cpu utilization must be numeric")
        normalized_value = float(value)
        if not isfinite(normalized_value) or not 0.0 <= normalized_value <= 100.0:
            raise MetricValueInvalid("cpu utilization must be between 0 and 100")
        return NormalizedSample(metric=metric, value=normalized_value, labels=normalized_labels)

    if metric in _INTEGER_POSITIVE:
        normalized_integer = _require_integer(value, positive=True)
    else:
        normalized_integer = _require_integer(value, positive=False)

    return NormalizedSample(metric=metric, value=normalized_integer, labels=normalized_labels)
