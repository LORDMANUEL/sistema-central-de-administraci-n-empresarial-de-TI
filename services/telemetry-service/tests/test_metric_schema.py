import pytest

from app.metrics_schema import (
    MetricLabelsInvalid,
    MetricNotAllowed,
    MetricValueInvalid,
    validate_sample,
)


def test_cpu_percentage_is_accepted_and_normalized():
    sample = validate_sample("cpu.utilization_pct", 42.5)
    assert sample.metric == "cpu.utilization_pct"
    assert sample.value == 42.5
    assert sample.labels == {}


def test_cpu_percentage_above_100_is_rejected():
    with pytest.raises(MetricValueInvalid):
        validate_sample("cpu.utilization_pct", 100.1)


def test_boolean_is_not_accepted_as_numeric_metric():
    with pytest.raises(MetricValueInvalid):
        validate_sample("cpu.utilization_pct", True)


def test_unknown_metric_is_rejected():
    with pytest.raises(MetricNotAllowed):
        validate_sample("process.command_line", 1)


def test_disk_metric_requires_volume_label():
    with pytest.raises(MetricLabelsInvalid):
        validate_sample("disk.free_bytes", 1024, {})


def test_disk_metric_rejects_arbitrary_extra_label():
    with pytest.raises(MetricLabelsInvalid):
        validate_sample("disk.free_bytes", 1024, {"volume": "C:", "username": "alice"})


def test_disk_metric_accepts_bounded_volume_label():
    sample = validate_sample("disk.free_bytes", 1024, {"volume": "C:"})
    assert sample.labels == {"volume": "C:"}


def test_memory_total_must_be_positive():
    with pytest.raises(MetricValueInvalid):
        validate_sample("memory.total_bytes", 0)


def test_network_counter_cannot_be_negative():
    with pytest.raises(MetricValueInvalid):
        validate_sample("network.rx_bytes_total", -1)


def test_volume_label_length_is_bounded():
    with pytest.raises(MetricLabelsInvalid):
        validate_sample("disk.total_bytes", 2048, {"volume": "x" * 129})
