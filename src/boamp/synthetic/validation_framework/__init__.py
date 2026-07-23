"""Minimum-suite validation framework for BOAMP synthetic benchmarks."""

from boamp.synthetic.validation_framework.loaders import BenchmarkData, benchmark_output_dir, load_benchmark_data
from boamp.synthetic.validation_framework.models import GateResult, MetricResult, Status
from boamp.synthetic.validation_framework.runner import run_validation, write_validation_outputs

__all__ = [
    "BenchmarkData",
    "GateResult",
    "MetricResult",
    "Status",
    "benchmark_output_dir",
    "load_benchmark_data",
    "run_validation",
    "write_validation_outputs",
]
