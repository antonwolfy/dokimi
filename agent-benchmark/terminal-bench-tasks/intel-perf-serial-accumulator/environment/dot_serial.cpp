#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>

static inline double a_value(std::size_t i) {
    return static_cast<double>((i * 17u + 13u) % 1024u) * 0.001 + 1.0;
}

static inline double b_value(std::size_t i) {
    return static_cast<double>((i * 29u + 7u) % 2048u) * 0.0005 - 0.25;
}

int main(int argc, char** argv) {
    const std::size_t n = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 24000000ULL;
    if (n == 0) {
        std::cerr << "INVALID_ARGUMENTS\n";
        return 2;
    }

    double sum = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        sum += a_value(i) * b_value(i);
    }

    if (!std::isfinite(sum)) {
        std::cerr << "INVALID_RESULT\n";
        return 1;
    }
    std::cout << std::setprecision(17) << "VALID dot=" << sum << "\n";
    return 0;
}
