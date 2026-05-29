---
name: onetbb-quickstart
description: How to start parallelizing C++ loops and reductions with Intel oneTBB, including headers, CMake wiring, and the most common pitfalls.
---
# oneTBB quickstart

Use this skill when a question is about getting started with Intel oneAPI
Threading Building Blocks (oneTBB): parallel loops, reductions, ranges, or
build setup.

## Headers and namespace

```cpp
#include <oneapi/tbb.h>            // umbrella header
using namespace oneapi::tbb;       // or qualify each call
```

## Parallel loop

```cpp
oneapi::tbb::parallel_for(
    oneapi::tbb::blocked_range<size_t>(0, n),
    [&](const oneapi::tbb::blocked_range<size_t>& r) {
        for (size_t i = r.begin(); i != r.end(); ++i)
            out[i] = f(in[i]);
    });
```

## Parallel reduction

```cpp
double sum = oneapi::tbb::parallel_reduce(
    oneapi::tbb::blocked_range<size_t>(0, n), 0.0,
    [&](const auto& r, double acc) {
        for (size_t i = r.begin(); i != r.end(); ++i) acc += a[i];
        return acc;
    },
    std::plus<double>());
```

## CMake

```cmake
find_package(TBB REQUIRED)
target_link_libraries(my_app PRIVATE TBB::tbb)
```

## Pitfalls

- Don't assume the lambda runs once — `parallel_for` splits the range across
  tasks, so the body may run on many threads concurrently. Avoid shared mutable
  state without `concurrent_*` containers or reduction.
- Prefer `parallel_reduce` over a `parallel_for` writing to a shared accumulator.
- Grain size is usually best left to the auto-partitioner; tune only if profiling says so.
