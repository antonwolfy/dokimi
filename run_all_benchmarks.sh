#!/bin/bash
set -euo pipefail

# Run from repo root (portable)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
else
  echo "❌ No virtualenv found (.venv/ or venv/). Create one and install requirements.txt" >&2
  exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "=========================================="
echo "Starting all benchmarks..."
echo "=========================================="

# Create result directories
mkdir -p results/onedal results/onetbb_full

# 1. oneDAL Baseline
echo ""
echo "1/4: Running oneDAL baseline..."
$PYTHON_BIN -u benchmark.py scan \
    -q questions/onedal.json \
    --source baseline \
    --scorer-model deepseek-chat \
    2>&1 | tee results/onedal/baseline_run.log

# Copy latest results
LATEST_DIR=$(ls -td results/run_* 2>/dev/null | head -1 || true)
if [ -z "$LATEST_DIR" ]; then
  echo "❌ No results/run_* found after scan" >&2
  exit 3
fi
rm -rf results/onedal/baseline
cp -r "$LATEST_DIR" results/onedal/baseline
echo "✓ oneDAL baseline complete: results/onedal/baseline"

# 2. oneDAL Context7
echo ""
echo "2/4: Running oneDAL context7..."
$PYTHON_BIN -u benchmark.py scan \
    -q questions/onedal.json \
    --source context7:oneapi-src/onedal \
    --scorer-model deepseek-chat \
    2>&1 | tee results/onedal/context7_run.log

LATEST_DIR=$(ls -td results/run_* 2>/dev/null | head -1 || true)
if [ -z "$LATEST_DIR" ]; then
  echo "❌ No results/run_* found after scan" >&2
  exit 3
fi
rm -rf results/onedal/context7
cp -r "$LATEST_DIR" results/onedal/context7
echo "✓ oneDAL context7 complete: results/onedal/context7"

# 3. oneTBB Baseline (full 27 questions)
echo ""
echo "3/4: Running oneTBB baseline (full)..."
$PYTHON_BIN -u benchmark.py scan \
    -q questions/onetbb.json \
    --source baseline \
    --scorer-model deepseek-chat \
    2>&1 | tee results/onetbb_full/baseline_run.log

LATEST_DIR=$(ls -td results/run_* 2>/dev/null | head -1 || true)
if [ -z "$LATEST_DIR" ]; then
  echo "❌ No results/run_* found after scan" >&2
  exit 3
fi
rm -rf results/onetbb_full/baseline
cp -r "$LATEST_DIR" results/onetbb_full/baseline
echo "✓ oneTBB baseline complete: results/onetbb_full/baseline"

# 4. oneTBB Context7 (full 27 questions)
echo ""
echo "4/4: Running oneTBB context7 (full)..."
$PYTHON_BIN -u benchmark.py scan \
    -q questions/onetbb.json \
    --source context7:uxlfoundation/onetbb \
    --scorer-model deepseek-chat \
    2>&1 | tee results/onetbb_full/context7_run.log

LATEST_DIR=$(ls -td results/run_* 2>/dev/null | head -1 || true)
if [ -z "$LATEST_DIR" ]; then
  echo "❌ No results/run_* found after scan" >&2
  exit 3
fi
rm -rf results/onetbb_full/context7
cp -r "$LATEST_DIR" results/onetbb_full/context7
echo "✓ oneTBB context7 complete: results/onetbb_full/context7"

echo ""
echo "=========================================="
echo "All benchmarks complete!"
echo "=========================================="
echo ""
echo "Results:"
echo "  oneDAL:  results/onedal/{baseline,context7}"
echo "  oneTBB:  results/onetbb_full/{baseline,context7}"
echo ""
echo "Reports:"
echo "  results/onedal/baseline/report.md"
echo "  results/onedal/context7/report.md"
echo "  results/onetbb_full/baseline/report.md"
echo "  results/onetbb_full/context7/report.md"
