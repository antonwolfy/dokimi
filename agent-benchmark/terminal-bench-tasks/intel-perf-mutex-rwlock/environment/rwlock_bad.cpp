#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <numeric>
#include <thread>
#include <vector>

// Read-mostly shared table guarded by a plain mutex. Readers dominate but are
// serialized against each other even though they only read, which caps read
// throughput at high core counts. Writers are rare.
class Table {
    mutable std::mutex m;
    std::vector<std::uint64_t> data;
public:
    explicit Table(std::size_t n) : data(n, 1) {}

    std::uint64_t get(std::size_t i) const {
        std::lock_guard<std::mutex> g(m);     // exclusive lock for a pure read
        return data[i % data.size()];
    }
    void bump(std::size_t i) {
        std::lock_guard<std::mutex> g(m);
        data[i % data.size()] += 1;
    }
    std::uint64_t checksum() const {
        std::lock_guard<std::mutex> g(m);
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
                if ((i & 0x3ff) == 0) table.bump(i + t);   // ~0.1% writers
                else local += table.get(i + t);            // readers dominate
            }
            read_acc[t] = local;
        });
    }
    for (auto& th : pool) th.join();

    // Final array checksum depends only on the number of writes (reads do not
    // mutate), so it is deterministic across read interleavings and across the
    // mutex vs rwlock builds. Each thread issues ceil(ops/1024) bumps.
    const std::uint64_t bumps_per_thread = (ops + 1023) / 1024;
    const std::uint64_t expected = slots + static_cast<std::uint64_t>(threads) * bumps_per_thread;
    const std::uint64_t got = table.checksum();
    if (got != expected) { std::cerr << "INVALID_RESULT checksum=" << got << " expected=" << expected << "\n"; return 1; }

    // keep read_acc observable so the reader loop is not optimized away
    std::uint64_t read_total = 0;
    for (auto r : read_acc) read_total += r;
    std::cout << "VALID checksum=" << got << " reads=" << read_total << "\n";
    return 0;
}
