#!/usr/bin/env bash
set -euo pipefail

cat > /app/shared_counter_fixed.cpp <<'CPP'
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

static inline unsigned long long work_value(unsigned long long i, unsigned long long tid) {
    unsigned long long x = i * 11400714819323198485ull + tid * 0x9e3779b97f4a7c15ull;
    x ^= x >> 33;
    x *= 0xff51afd7ed558ccdull;
    x ^= x >> 33;
    return x & 0xffu;
}

int main(int argc, char** argv) {
    const int threads = argc > 1 ? std::atoi(argv[1]) : 4;
    const unsigned long long iterations = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 5000000ULL;
    if (threads < 1 || iterations < 1) return 2;
    std::vector<unsigned long long> local_counts(static_cast<std::size_t>(threads), 0);
    std::vector<unsigned long long> local_checksums(static_cast<std::size_t>(threads), 0);
    std::vector<std::thread> workers;
    for (int t = 0; t < threads; ++t) {
        workers.emplace_back([&, t] {
            unsigned long long count = 0;
            unsigned long long checksum = 0;
            for (unsigned long long i = 0; i < iterations; ++i) {
                checksum += work_value(i, static_cast<unsigned long long>(t));
                ++count;
            }
            local_counts[static_cast<std::size_t>(t)] = count;
            local_checksums[static_cast<std::size_t>(t)] = checksum;
        });
    }
    for (auto& worker : workers) worker.join();
    unsigned long long total = 0;
    unsigned long long checksum = 0;
    for (int t = 0; t < threads; ++t) {
        total += local_counts[static_cast<std::size_t>(t)];
        checksum += local_checksums[static_cast<std::size_t>(t)];
    }
    std::cout << "VALID total=" << total << " checksum=" << checksum << "\n";
    return total == static_cast<unsigned long long>(threads) * iterations ? 0 : 1;
}
CPP

g++ -O3 -std=c++17 -pthread /app/shared_counter_fixed.cpp -o /app/shared_counter_fixed
