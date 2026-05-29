# Provenance notes for executable tasks

## oneTBB (ParRes-inspired)

The `onetbb-nstream`, `onetbb-stencil`, and `onetbb-transpose` tasks are inspired by the Parallel Research Kernels project:

- Repository: https://github.com/ParRes/Kernels
- Upstream kernels consulted: `Cxx11/nstream-tbb.cc`, `Cxx11/stencil-tbb.cc`, and `Cxx11/transpose-tbb.cc`
- Upstream license: BSD-style Intel Corporation license in `COPYING`

The task implementations in this repository are simplified, independently written exercises for terminal-bench-style validation. They do not copy the ParRes source files verbatim and should not be reported as official ParRes or STREAM benchmark results. The purpose here is functional verification of oneTBB usage by coding agents, not system benchmarking.

## oneMKL, oneDPL, IPP, sklearnex

The `onemkl-*`, `onedpl-*`, `ipp-*`, and `sklearnex-*` tasks are original
exercises written for this repository. Their environments pull dependencies at
**build** time only; the verifier runs offline:

- oneMKL and IPP are installed from the Intel oneAPI apt repository
  (`https://apt.repos.intel.com/oneapi`).
- oneDPL is header-only and is fetched from the upstream repository
  ([uxlfoundation/oneDPL](https://github.com/uxlfoundation/oneDPL)) at a pinned
  release tag; it uses the oneTBB backend (`libtbb-dev`).
- sklearnex is installed from PyPI (`scikit-learn-intelex`) alongside
  `scikit-learn`.

The `sklearnex-classification` task is a generic, self-contained tabular
classification workflow in the spirit of common Kaggle starter notebooks
(synthetic `make_classification` data, a train/test split, and a KNN
classifier). It is not derived from or copied out of any specific Kaggle
notebook or dataset.
