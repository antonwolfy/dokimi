# Provenance notes for executable oneTBB tasks

The `onetbb-nstream`, `onetbb-stencil`, and `onetbb-transpose` tasks are inspired by the Parallel Research Kernels project:

- Repository: https://github.com/ParRes/Kernels
- Upstream kernels consulted: `Cxx11/nstream-tbb.cc`, `Cxx11/stencil-tbb.cc`, and `Cxx11/transpose-tbb.cc`
- Upstream license: BSD-style Intel Corporation license in `COPYING`

The task implementations in this repository are simplified, independently written exercises for terminal-bench-style validation. They do not copy the ParRes source files verbatim and should not be reported as official ParRes or STREAM benchmark results. The purpose here is functional verification of oneTBB usage by coding agents, not system benchmarking.
