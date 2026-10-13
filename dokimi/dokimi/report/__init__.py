# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Report generation module."""

from .generator import ReportGenerator
from .model_compare import (
    check_run_consistency,
    extract_scores,
    generate_combined_report,
    generate_section_report,
    load_run,
)

__all__ = [
    "ReportGenerator",
    "check_run_consistency",
    "extract_scores",
    "generate_combined_report",
    "generate_section_report",
    "load_run",
]
