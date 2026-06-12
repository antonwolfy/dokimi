#!/usr/bin/env bash
set -euo pipefail

cat > /app/dpl_reduce.cpp <<'CPP'
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <functional>
#include <oneapi/dpl/execution>
#include <oneapi/dpl/numeric>

int main(int argc, char **argv) {
    std::size_t n = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 4000000;
    if (n == 0) {
        std::cerr << "INVALID_ARGUMENTS\n";
        return 2;
    }
    std::vector<long long> v(n);
    for (std::size_t i = 0; i < n; ++i)
        v[i] = (long long)((i * 17 + 13) % 1009) - 504;

    long long sig = oneapi::dpl::transform_reduce(
        oneapi::dpl::execution::par_unseq,
        v.begin(), v.end(), 0LL, std::plus<long long>(),
        [](long long x) { return x * x; });

    std::cout << "VALID dpl sig=" << sig << "\n";
    return 0;
}
CPP

g++ -O3 -std=c++17 /app/dpl_reduce.cpp -ltbb -pthread -o /app/dpl_reduce
