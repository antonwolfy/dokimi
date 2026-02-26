# Documentation Quality Report

**Total Questions:** 27

## Overall Statistics

| Metric | WITH Docs | WITHOUT Docs | Delta |
|--------|-----------|--------------|-------|
| Average | 85.3 | 82.6 | **+2.7** |
| Min | 68 | 38 | -18.0 |
| Max | 93 | 90 | +48.0 |

- **Improvements:** 10 questions (docs helped)
- **Degradations:** 5 questions (docs hurt)

---

## Top 10: Best WITH Docs Performance

| Question ID | Score | Question Text |
|-------------|-------|---------------|
| tbb-int-01 | 93.0 | How do I integrate oneTBB with CMake? Show a complete CMakeLists.txt example.... |
| tbb-gs-03 | 87.0 | What are the basic building blocks of oneTBB? Explain the core concepts.... |
| tbb-mig-03 | 87.0 | What APIs were deprecated in oneTBB? What are the recommended replacements?... |
| tbb-gs-02 | 86.0 | How do I parallelize a simple for-loop using oneTBB? Show a complete hello-world... |
| tbb-int-02 | 86.0 | How do I use oneTBB with conan package manager? Show the conanfile and integrati... |
| tbb-int-03 | 86.0 | How do I use oneTBB together with OpenMP in the same application? Are there conf... |
| tbb-int-04 | 86.0 | How do I integrate oneTBB with vcpkg? Show installation and CMake usage.... |
| tbb-int-05 | 86.0 | Can I use oneTBB with std::execution parallel algorithms? How do they interopera... |
| tbb-perf-01 | 86.0 | How do I optimize parallel_for grainsize for my workload? What's the impact on p... |
| tbb-perf-02 | 86.0 | How do I use task_arena to control thread counts and affinity for specific code ... |

---

## Bottom 10: Worst WITH Docs Performance

| Question ID | Score | Question Text |
|-------------|-------|---------------|
| tbb-int-06 | 68.0 | How do I use oneTBB from a Python application? Show the Python bindings setup an... |
| tbb-gs-01 | 81.0 | How do I install oneTBB on Ubuntu and verify the installation?... |
| tbb-api-02 | 83.0 | What are the differences between concurrent_vector, concurrent_queue, and concur... |
| tbb-mig-01 | 85.0 | I'm migrating from legacy TBB (2020) to oneTBB. What are the breaking changes?... |
| tbb-gs-02 | 86.0 | How do I parallelize a simple for-loop using oneTBB? Show a complete hello-world... |
| tbb-int-02 | 86.0 | How do I use oneTBB with conan package manager? Show the conanfile and integrati... |
| tbb-int-03 | 86.0 | How do I use oneTBB together with OpenMP in the same application? Are there conf... |
| tbb-int-04 | 86.0 | How do I integrate oneTBB with vcpkg? Show installation and CMake usage.... |
| tbb-int-05 | 86.0 | Can I use oneTBB with std::execution parallel algorithms? How do they interopera... |
| tbb-perf-01 | 86.0 | How do I optimize parallel_for grainsize for my workload? What's the impact on p... |

---

## Top 10: Biggest Improvements (docs helped most)

| Question ID | Delta | WITH | WITHOUT | Question Text |
|-------------|-------|------|---------|---------------|
| tbb-perf-04 | **+48.0** | 86.0 | 38.0 | What's the difference between auto_partitioner, simple_partitioner, and affinity... |
| tbb-int-05 | **+13.0** | 86.0 | 73.0 | Can I use oneTBB with std::execution parallel algorithms? How do they interopera... |
| tbb-api-03 | **+13.0** | 86.0 | 73.0 | How do I implement parallel reduction (sum, min, max) using parallel_reduce? Sho... |
| tbb-int-02 | **+9.0** | 86.0 | 77.0 | How do I use oneTBB with conan package manager? Show the conanfile and integrati... |
| tbb-int-01 | **+7.0** | 93.0 | 86.0 | How do I integrate oneTBB with CMake? Show a complete CMakeLists.txt example.... |
| tbb-mig-02 | **+7.0** | 86.0 | 79.0 | How do I replace std::thread and std::mutex with oneTBB equivalents? Why would I... |
| tbb-api-01 | **+5.0** | 86.0 | 81.0 | How do I build a flow graph pipeline using oneTBB? Show a multi-stage producer-c... |
| tbb-gs-03 | **+4.0** | 87.0 | 83.0 | What are the basic building blocks of oneTBB? Explain the core concepts.... |
| tbb-mig-03 | **+2.0** | 87.0 | 85.0 | What APIs were deprecated in oneTBB? What are the recommended replacements?... |
| tbb-trouble-02 | **+1.0** | 86.0 | 85.0 | I'm seeing worse performance with parallel_for than serial code. What are common... |

---

## Bottom 10: Biggest Degradations (docs hurt most)

| Question ID | Delta | WITH | WITHOUT | Question Text |
|-------------|-------|------|---------|---------------|
| tbb-int-06 | **-18.0** | 68.0 | 86.0 | How do I use oneTBB from a Python application? Show the Python bindings setup an... |
| tbb-api-02 | **-7.0** | 83.0 | 90.0 | What are the differences between concurrent_vector, concurrent_queue, and concur... |
| tbb-gs-01 | **-5.0** | 81.0 | 86.0 | How do I install oneTBB on Ubuntu and verify the installation?... |
| tbb-mig-01 | **-4.0** | 85.0 | 89.0 | I'm migrating from legacy TBB (2020) to oneTBB. What are the breaking changes?... |
| tbb-perf-01 | **-2.0** | 86.0 | 88.0 | How do I optimize parallel_for grainsize for my workload? What's the impact on p... |
| tbb-gs-02 | **0.0** | 86.0 | 86.0 | How do I parallelize a simple for-loop using oneTBB? Show a complete hello-world... |
| tbb-int-03 | **0.0** | 86.0 | 86.0 | How do I use oneTBB together with OpenMP in the same application? Are there conf... |
| tbb-int-04 | **0.0** | 86.0 | 86.0 | How do I integrate oneTBB with vcpkg? Show installation and CMake usage.... |
| tbb-perf-02 | **0.0** | 86.0 | 86.0 | How do I use task_arena to control thread counts and affinity for specific code ... |
| tbb-perf-03 | **0.0** | 86.0 | 86.0 | How do I implement NUMA-aware parallel algorithms with oneTBB for multi-socket s... |

---

## Performance by Topic/Persona

| Topic | Count | WITH Avg | WITHOUT Avg | Delta |
|-------|-------|----------|-------------|-------|
| unknown | 27 | 85.3 | 82.6 | **+2.7** |

---

## Recommendations

✅ **Overall:** Documentation is significantly helping. Continue:
- Maintaining doc quality
- Expanding coverage for low-performing topics
