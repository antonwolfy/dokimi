/* Serial reference: transform-reduce (sum of squares) over deterministic data. */
#include <cstdint>
#include <cstdlib>
#include <iostream>

int main(int argc, char **argv) {
    std::size_t n = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 4000000;
    if (n == 0) {
        std::cerr << "INVALID_ARGUMENTS\n";
        return 2;
    }
    long long sig = 0;
    for (std::size_t i = 0; i < n; ++i) {
        long long v = (long long)((i * 17 + 13) % 1009) - 504;
        sig += v * v;
    }
    std::cout << "VALID dpl sig=" << sig << "\n";
    return 0;
}
