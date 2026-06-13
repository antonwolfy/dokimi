#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>

// Worker pool that wakes ALL workers on every enqueued job (notify_all). With
// many workers, each enqueue wakes the whole pool; all but one immediately go
// back to sleep — a condition-variable thundering herd. Context switches and
// futex traffic scale with pool size even though only one worker has work.
class Pool {
    std::mutex m;
    std::condition_variable cv;
    std::queue<std::uint64_t> jobs;
    bool stop = false;
public:
    void submit(std::uint64_t job) {
        {
            std::lock_guard<std::mutex> g(m);
            jobs.push(job);
        }
        cv.notify_all();        // wake every worker for a single job
    }
    void shutdown() {
        {
            std::lock_guard<std::mutex> g(m);
            stop = true;
        }
        cv.notify_all();
    }
    bool take(std::uint64_t& out) {
        std::unique_lock<std::mutex> g(m);
        cv.wait(g, [&] { return stop || !jobs.empty(); });
        if (!jobs.empty()) { out = jobs.front(); jobs.pop(); return true; }
        return false;           // stop with empty queue
    }
};

int main(int argc, char** argv) {
    const unsigned workers = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 16u;
    const std::uint64_t njobs = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 200000ULL;
    if (workers == 0 || njobs == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }

    Pool pool;
    std::atomic<std::uint64_t> processed{0};
    std::atomic<std::uint64_t> checksum{0};
    std::vector<std::thread> pool_threads;
    for (unsigned w = 0; w < workers; ++w) {
        pool_threads.emplace_back([&] {
            std::uint64_t job;
            while (pool.take(job)) {
                processed.fetch_add(1, std::memory_order_relaxed);
                checksum.fetch_add(job, std::memory_order_relaxed);
            }
        });
    }
    for (std::uint64_t i = 1; i <= njobs; ++i) pool.submit(i);
    pool.shutdown();
    for (auto& th : pool_threads) th.join();

    const std::uint64_t expected_sum = njobs * (njobs + 1) / 2;
    if (processed.load() != njobs || checksum.load() != expected_sum) {
        std::cerr << "INVALID_RESULT processed=" << processed.load()
                  << " checksum=" << checksum.load() << "\n";
        return 1;
    }
    std::cout << "VALID processed=" << processed.load() << " checksum=" << checksum.load() << "\n";
    return 0;
}
