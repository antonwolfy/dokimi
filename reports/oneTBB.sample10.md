# Documentation Quality Report

**Total Questions:** 10

## Overall Statistics

| Metric | WITH Docs | WITHOUT Docs | Delta |
|--------|-----------|--------------|-------|
| Average | 87.8 | 87.4 | **+0.4** |
| Min | 86 | 86 | -4.0 |
| Max | 91 | 90 | +5.0 |

- **Improvements:** 4 questions (docs helped)
- **Degradations:** 4 questions (docs hurt)

---

## Top 10: Best WITH Docs Performance

| Question ID | Score | Question Text |
|-------------|-------|---------------|
| q_005 | 91.0 | How can I optimize the task scheduling granularity in tbb::flow to improve perfo... |
| q_008 | 91.0 | What are the best practices for using oneTBB's scalable_allocator to improve mem... |
| q_009 | 91.0 | How can I effectively use oneTBB's parallel constructs along with std::endl for ... |
| q_002 | 87.0 | What are the best practices for managing thread affinity with std::this_thread i... |
| q_006 | 87.0 | What best practices should I follow when designing a tbb::flow graph to ensure l... |
| q_007 | 87.0 | How can I optimize my task parallelism strategy in oneTBB to minimize overhead w... |
| q_003 | 86.0 | How can I effectively use std::move in oneTBB to optimize the performance of my ... |
| q_004 | 86.0 | In oneTBB, what best practices should I follow for managing memory allocation an... |
| q_011 | 86.0 | How can I effectively configure tbb::parallel_do_feeder to maximize data paralle... |
| q_012 | 86.0 | What are the recommended best practices for integrating tbb::parallel_do_feeder ... |

---

## Bottom 10: Worst WITH Docs Performance

| Question ID | Score | Question Text |
|-------------|-------|---------------|
| q_003 | 86.0 | How can I effectively use std::move in oneTBB to optimize the performance of my ... |
| q_004 | 86.0 | In oneTBB, what best practices should I follow for managing memory allocation an... |
| q_011 | 86.0 | How can I effectively configure tbb::parallel_do_feeder to maximize data paralle... |
| q_012 | 86.0 | What are the recommended best practices for integrating tbb::parallel_do_feeder ... |
| q_002 | 87.0 | What are the best practices for managing thread affinity with std::this_thread i... |
| q_006 | 87.0 | What best practices should I follow when designing a tbb::flow graph to ensure l... |
| q_007 | 87.0 | How can I optimize my task parallelism strategy in oneTBB to minimize overhead w... |
| q_005 | 91.0 | How can I optimize the task scheduling granularity in tbb::flow to improve perfo... |
| q_008 | 91.0 | What are the best practices for using oneTBB's scalable_allocator to improve mem... |
| q_009 | 91.0 | How can I effectively use oneTBB's parallel constructs along with std::endl for ... |

---

## Top 10: Biggest Improvements (docs helped most)

| Question ID | Delta | WITH | WITHOUT | Question Text |
|-------------|-------|------|---------|---------------|
| q_008 | **+5.0** | 91.0 | 86.0 | What are the best practices for using oneTBB's scalable_allocator to improve mem... |
| q_005 | **+4.0** | 91.0 | 87.0 | How can I optimize the task scheduling granularity in tbb::flow to improve perfo... |
| q_009 | **+4.0** | 91.0 | 87.0 | How can I effectively use oneTBB's parallel constructs along with std::endl for ... |
| q_002 | **+1.0** | 87.0 | 86.0 | What are the best practices for managing thread affinity with std::this_thread i... |
| q_007 | **+0.0** | 87.0 | 87.0 | How can I optimize my task parallelism strategy in oneTBB to minimize overhead w... |
| q_012 | **+0.0** | 86.0 | 86.0 | What are the recommended best practices for integrating tbb::parallel_do_feeder ... |
| q_003 | **+-1.0** | 86.0 | 87.0 | How can I effectively use std::move in oneTBB to optimize the performance of my ... |
| q_006 | **+-1.0** | 87.0 | 88.0 | What best practices should I follow when designing a tbb::flow graph to ensure l... |
| q_004 | **+-4.0** | 86.0 | 90.0 | In oneTBB, what best practices should I follow for managing memory allocation an... |
| q_011 | **+-4.0** | 86.0 | 90.0 | How can I effectively configure tbb::parallel_do_feeder to maximize data paralle... |

---

## Bottom 10: Biggest Degradations (docs hurt most)

| Question ID | Delta | WITH | WITHOUT | Question Text |
|-------------|-------|------|---------|---------------|
| q_004 | **-4.0** | 86.0 | 90.0 | In oneTBB, what best practices should I follow for managing memory allocation an... |
| q_011 | **-4.0** | 86.0 | 90.0 | How can I effectively configure tbb::parallel_do_feeder to maximize data paralle... |
| q_003 | **-1.0** | 86.0 | 87.0 | How can I effectively use std::move in oneTBB to optimize the performance of my ... |
| q_006 | **-1.0** | 87.0 | 88.0 | What best practices should I follow when designing a tbb::flow graph to ensure l... |
| q_007 | **0.0** | 87.0 | 87.0 | How can I optimize my task parallelism strategy in oneTBB to minimize overhead w... |
| q_012 | **0.0** | 86.0 | 86.0 | What are the recommended best practices for integrating tbb::parallel_do_feeder ... |
| q_002 | **1.0** | 87.0 | 86.0 | What are the best practices for managing thread affinity with std::this_thread i... |
| q_005 | **4.0** | 91.0 | 87.0 | How can I optimize the task scheduling granularity in tbb::flow to improve perfo... |
| q_009 | **4.0** | 91.0 | 87.0 | How can I effectively use oneTBB's parallel constructs along with std::endl for ... |
| q_008 | **5.0** | 91.0 | 86.0 | What are the best practices for using oneTBB's scalable_allocator to improve mem... |

---

## Performance by Topic/Persona

| Topic | Count | WITH Avg | WITHOUT Avg | Delta |
|-------|-------|----------|-------------|-------|
| unknown | 10 | 87.8 | 87.4 | **+0.4** |

---

## Recommendations

⚪ **Overall:** Documentation has minimal impact. Consider:
- Improving doc discoverability
- Adding more practical examples
