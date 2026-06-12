#include <atomic>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

struct CounterSlot {
    std::atomic<long long> value;
};

int main(int argc, char** argv) {
    const int threads = argc > 1 ? std::atoi(argv[1]) : 4;
    const long long iterations = argc > 2 ? std::atoll(argv[2]) : 8000000LL;
    if (threads < 1 || iterations < 1) return 2;

    std::vector<CounterSlot> slots(static_cast<std::size_t>(threads));
    for (auto& slot : slots) slot.value.store(0, std::memory_order_relaxed);

    std::vector<std::thread> workers;
    for (int t = 0; t < threads; ++t) {
        workers.emplace_back([&, t] {
            for (long long i = 0; i < iterations; ++i) {
                slots[static_cast<std::size_t>(t)].value.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    for (auto& worker : workers) worker.join();

    long long total = 0;
    for (const auto& slot : slots) total += slot.value.load(std::memory_order_relaxed);
    std::cout << "VALID total=" << total << "\n";
    return total == static_cast<long long>(threads) * iterations ? 0 : 1;
}
