# Umbrella Makefile for the "Software Packaging for Agents" repository.
#
# This repo has two areas:
#   software-packaging-for-agents/  framing & architecture (docs today)
#   agent-benchmark/                  the measurement engine (runnable project)
#
# Most runnable targets delegate into agent-benchmark/. Run `make help` for the
# current target list.

BENCH_DIR := agent-benchmark

.PHONY: help test benchmark-run benchmark-compare validate-benchmark-spec

help:
	@echo "Software Packaging for Agents — top-level targets:"
	@echo "  make test                    Run the agent-benchmark test suite"
	@echo "  make benchmark-run           Run the static agent-quality benchmark"
	@echo "  make benchmark-compare       Compare benchmark snapshots"
	@echo "  make validate-benchmark-spec Validate the benchmark spec schema"
	@echo ""
	@echo "All runnable targets currently delegate into $(BENCH_DIR)/."
	@echo "See $(BENCH_DIR)/Makefile for the full benchmark target list."

# Run the benchmark test suite from its own directory.
test:
	$(MAKE) -C $(BENCH_DIR) test 2>/dev/null || (cd $(BENCH_DIR) && python -m pytest -q)

# Delegate benchmark targets into the benchmark project's own Makefile.
benchmark-run benchmark-compare validate-benchmark-spec:
	$(MAKE) -C $(BENCH_DIR) $@
