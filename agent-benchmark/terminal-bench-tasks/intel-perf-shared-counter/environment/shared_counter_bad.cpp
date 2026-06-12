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

    std::atomic<unsigned long long> global_packets{0};
    std::vector<unsigned long long> checksums(static_cast<std::size_t>(threads), 0);
    std::vector<std::thread> workers;
    for (int t = 0; t < threads; ++t) {
        workers.emplace_back([&, t] {
            unsigned long long local_checksum = 0;
            for (unsigned long long i = 0; i < iterations; ++i) {
                local_checksum += work_value(i, static_cast<unsigned long long>(t));
                global_packets.fetch_add(1, std::memory_order_relaxed);
            }
            checksums[static_cast<std::size_t>(t)] = local_checksum;
        });
    }
    for (auto& worker : workers) worker.join();
    unsigned long long checksum = 0;
    for (auto value : checksums) checksum += value;
    const unsigned long long total = global_packets.load(std::memory_order_relaxed);
    std::cout << "VALID total=" << total << " checksum=" << checksum << "\n";
    return total == static_cast<unsigned long long>(threads) * iterations ? 0 : 1;
}
