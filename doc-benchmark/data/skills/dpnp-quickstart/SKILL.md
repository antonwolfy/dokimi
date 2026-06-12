---
name: dpnp-quickstart
description: NumPy-compatible array operations optimized for Intel hardware
---
# dpnp quickstart

Use this skill when working with Intel-optimized Python array operations, or when migrating NumPy code to run on Intel CPUs and GPUs.

## Installation

```bash
# Conda (officially recommended)
conda install -c intel dpnp

# Alternative: pip (may have native dependency issues)
pip install dpnp

# verify installation
python -c "import dpnp; print(dpnp.__version__)"
```

## Basic usage

```python
# Drop-in NumPy replacement
import dpnp as np

# Create arrays
x = np.array([1, 2, 3, 4])
y = np.arange(1000000)

# Operations work like NumPy
result = np.sum(y)
dot_product = np.dot(x, x)
```

## When to use dpnp vs NumPy

Use dpnp for:
- Large arrays (>10,000 elements)
- Math-heavy operations (linear algebra, FFT, reductions)
- Intel CPU/GPU acceleration

Stick with NumPy for:
- Small arrays (<1,000 elements)
- I/O operations
- APIs not yet implemented in dpnp

## Common operations

```python
import dpnp as np

# Array creation
a = np.zeros((100, 100))
b = np.ones(1000)
c = np.linspace(0, 10, 100)

# Math operations
sum_val = np.sum(a)
mean_val = np.mean(b)
std_val = np.std(c)

# Linear algebra
mat = np.random.randn(100, 100)
result = np.dot(mat, mat.T)
```

## Pitfalls

- **First run is slow**: JIT compilation happens on first execution. Time the second run.
- **Not all NumPy APIs available**: Check compatibility with `dir(dpnp)` or documentation.
- **Data transfer cost**: Converting between dpnp and NumPy arrays has overhead. Avoid in tight loops.
- **Small arrays slower**: dpnp has dispatch overhead. Use NumPy for small arrays (<1,000 elements).

## Compatibility and fallback pattern

```python
import dpnp
import numpy as np

def safe_unique(x):
    try:
        return dpnp.unique(x)
    except (NotImplementedError, TypeError):
        host_x = dpnp.asnumpy(x) if isinstance(x, dpnp.ndarray) else x
        return np.unique(host_x)
```

Use `dpnp.asnumpy()` when a downstream library needs a NumPy array. Keep
conversions at API boundaries; repeated device-to-host copies inside tight loops
can erase acceleration gains.

Pandas, scikit-learn, and many NumPy-based libraries usually expect NumPy arrays.
Use dpnp for numeric hot paths, then convert once with `asnumpy()` before calling
host-oriented libraries.

## Device control

```python
import dpctl
import dpnp as np

print(dpctl.select_default_device())

with dpctl.device_context("cpu"):
    x = np.arange(100_000)
    print(x.sycl_device)
```

Use `dpctl` to inspect or constrain CPU/GPU selection when code must run across
workstations, containers, and cloud VMs with different SYCL devices.

## Profiling and validation

- Warm up once before timing to avoid measuring first-run compilation.
- Compare against NumPy with `numpy.testing.assert_allclose()` for critical math.
- Profile end-to-end pipelines, including conversions and host-library calls.
