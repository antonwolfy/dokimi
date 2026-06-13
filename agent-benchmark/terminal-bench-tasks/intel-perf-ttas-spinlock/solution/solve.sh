#!/usr/bin/env bash
set -euo pipefail

cat > /app/spin_fixed.cpp <<'CPP'
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

// Test-and-test-and-set (TTAS): spin on an ordinary relaxed read until the
// lock looks free, only then attempt the atomic exchange. The read-only spin
// keeps the line in shared state and avoids the write storm.
class TtasLock {
    std::atomic<int> flag{0};
public:
    void lock() {
        for (;;) {
            while (flag.load(std::memory_order_relaxed) == 1) {
                // ordinary read spin; no atomic write while the lock is held
            }
            if (flag.exchange(1, std::memory_order_acquire) == 0) return;
        }
    }
    void unlock() { flag.store(0, std::memory_order_release); }
};

int main(int argc, char** argv) {
    const unsigned threads = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 4u;
    const std::uint64_t iters = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 400000ULL;
    if (threads == 0 || iters == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }

    TtasLock lock;
    std::uint64_t counter = 0;
    std::vector<std::thread> pool;
    for (unsigned t = 0; t < threads; ++t) {
        pool.emplace_back([&] {
            for (std::uint64_t i = 0; i < iters; ++i) {
                lock.lock();
                ++counter;
                lock.unlock();
            }
        });
    }
    for (auto& th : pool) th.join();

    const std::uint64_t expected = static_cast<std::uint64_t>(threads) * iters;
    if (counter != expected) { std::cerr << "INVALID_RESULT counter=" << counter << "\n"; return 1; }
    std::cout << "VALID count=" << counter << "\n";
    return 0;
}
CPP

g++ -O3 -std=c++17 -pthread /app/spin_fixed.cpp -o /app/spin_fixed
