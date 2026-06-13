#!/usr/bin/env bash
set -euo pipefail

cat > /app/rwlock_fixed.cpp <<'CPP'
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <numeric>
#include <shared_mutex>
#include <thread>
#include <vector>

// Read-mostly table using a reader-writer lock: many readers share the lock
// concurrently (shared_lock), writers take it exclusively (unique_lock). Same
// data and same final checksum as the mutex version.
class Table {
    mutable std::shared_mutex m;
    std::vector<std::uint64_t> data;
public:
    explicit Table(std::size_t n) : data(n, 1) {}

    std::uint64_t get(std::size_t i) const {
        std::shared_lock<std::shared_mutex> g(m);   // concurrent readers
        return data[i % data.size()];
    }
    void bump(std::size_t i) {
        std::unique_lock<std::shared_mutex> g(m);   // exclusive writer
        data[i % data.size()] += 1;
    }
    std::uint64_t checksum() const {
        std::shared_lock<std::shared_mutex> g(m);
        return std::accumulate(data.begin(), data.end(), std::uint64_t{0});
    }
};

int main(int argc, char** argv) {
    const unsigned threads = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 8u;
    const std::uint64_t ops = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 400000ULL;
    if (threads == 0 || ops == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }

    const std::size_t slots = 4096;
    Table table(slots);
    std::vector<std::uint64_t> read_acc(threads, 0);
    std::vector<std::thread> pool;
    for (unsigned t = 0; t < threads; ++t) {
        pool.emplace_back([&, t] {
            std::uint64_t local = 0;
            for (std::uint64_t i = 0; i < ops; ++i) {
                if ((i & 0x3ff) == 0) table.bump(i + t);
                else local += table.get(i + t);
            }
            read_acc[t] = local;
        });
    }
    for (auto& th : pool) th.join();

    const std::uint64_t bumps_per_thread = (ops + 1023) / 1024;
    const std::uint64_t expected = slots + static_cast<std::uint64_t>(threads) * bumps_per_thread;
    const std::uint64_t got = table.checksum();
    if (got != expected) { std::cerr << "INVALID_RESULT checksum=" << got << " expected=" << expected << "\n"; return 1; }

    std::uint64_t read_total = 0;
    for (auto r : read_acc) read_total += r;
    std::cout << "VALID checksum=" << got << " reads=" << read_total << "\n";
    return 0;
}
CPP

g++ -O3 -std=c++17 -pthread /app/rwlock_fixed.cpp -o /app/rwlock_fixed
