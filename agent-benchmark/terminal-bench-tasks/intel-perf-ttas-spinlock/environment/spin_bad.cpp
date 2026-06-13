#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

// Test-and-set (TAS) spinlock: every waiter hammers the line with an atomic
// exchange, so the cache line bounces between cores under contention.
class TasLock {
    std::atomic<int> flag{0};
public:
    void lock() {
        while (flag.exchange(1, std::memory_order_acquire) == 1) {
            // spin by repeatedly attempting the atomic exchange (writes the line)
        }
    }
    void unlock() { flag.store(0, std::memory_order_release); }
};

int main(int argc, char** argv) {
    const unsigned threads = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 4u;
    const std::uint64_t iters = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 400000ULL;
    if (threads == 0 || iters == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }

    TasLock lock;
    std::uint64_t counter = 0;
    std::vector<std::thread> pool;
    for (unsigned t = 0; t < threads; ++t) {
        pool.emplace_back([&] {
            for (std::uint64_t i = 0; i < iters; ++i) {
                lock.lock();
                ++counter;            // critical section
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
