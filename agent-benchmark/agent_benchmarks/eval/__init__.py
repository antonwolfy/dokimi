# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Evaluation module: answer generation and judging."""

from .answerer import Answerer
from .judge import Judge

__all__ = ["Answerer", "Judge"]
