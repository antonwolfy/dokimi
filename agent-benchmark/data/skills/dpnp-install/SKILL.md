---
name: dpnp-install
description: Installing and verifying dpnp on Intel CPUs and GPUs — conda vs pip, the SYCL runtime and GPU drivers underneath, and device-selection environment variables
---

# dpnp-install

Getting dpnp working is mostly about the runtime stack underneath, not the Python package. dpnp is a thin NumPy-compatible layer over dpctl and the Intel SYCL runtime, so "install dpnp" really means "make a SYCL device visible to Python." Building from source is out of scope — use conda or the pip wheels.

```bash
# Recommended: conda pulls dpnp + dpctl + the SYCL runtime together
conda create -n dpnp -c https://software.repos.intel.com/python/conda -c conda-forge --override-channels dpnp
conda activate dpnp
python -c "import dpnp; print(dpnp.__version__)"
```

## Requirements

- **OS / arch:** Linux or Windows on x86_64. dpnp is **not** available for macOS or ARM.
- **Python:** 3.10–3.14 (as of dpnp 0.20).
- **CPU:** any x86_64 CPU works via the bundled Intel OpenCL CPU runtime.
- **GPU:** an Intel GPU (Arc, Flex, Data Center GPU Max, or a recent integrated GPU) plus its OS driver — see Intel GPU drivers below.
- **WSL2:** supported — install dpnp inside a WSL2 Linux distro exactly as on native Linux. The CPU device works there directly; GPU use additionally needs an Intel GPU on the Windows host with a WSL-capable Intel graphics driver installed on **Windows** (it is then projected into WSL).

## Installing

If you don't have conda, install **Miniforge** (conda-forge by default). On Linux:

```bash
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash "Miniforge3-$(uname)-$(uname -m).sh"    # then open a new shell so conda is on PATH
```

For a Windows `.exe` or details, see the Miniforge docs: https://github.com/conda-forge/miniforge#install

Prefer **conda from Intel's repository** (`https://software.repos.intel.com/python/conda`, paired with conda-forge) — the command at the top. It resolves dpnp, dpctl, the SYCL runtime, and the CPU OpenCL runtime as one consistent set and makes the CPU device work automatically (see the ICD section). To add dpnp to an existing env, use `conda install` with the same channels:

```bash
conda install -c https://software.repos.intel.com/python/conda -c conda-forge --override-channels dpnp
```

Pass `--override-channels` so conda uses *only* those two channels and ignores `~/.condarc`. Without it, conda also searches the anaconda.org `defaults` channel, which can pull conflicting runtime/BLAS builds or hit the `defaults` Terms-of-Service prompt that now blocks installs. The older `-c intel` channel is deprecated (returns 403).

**pip wheels** also work and pull the runtime transitively — `dpnp` depends on `dpcpp-cpp-rt` (which brings `intel-opencl-rt`, i.e. `libintelocl.so`), plus `dpctl` and the `onemkl-sycl-*` wheels:

```bash
python -m venv .venv && source .venv/bin/activate
pip install dpnp
python -c "import dpnp; print(dpnp.__version__)"
```

`import dpnp` succeeding proves the package imports, not that a device is usable — on a fresh pip install the CPU device is frequently missing until the ICD is registered (next section).

Install into an isolated environment (never base conda or system Python), and never mix a conda `dpnp` and a pip `dpnp` in one env. (Neither installer provides the GPU driver — see Intel GPU drivers.)

## Getting the CPU device recognized (OpenCL ICD)

The CPU SYCL device runs through the Intel OpenCL CPU runtime, `libintelocl.so` (from `intel-opencl-rt`). The OpenCL loader finds it by reading `.icd` files from a vendors directory. Conda handles this automatically — its activation scripts set `OCL_ICD_VENDORS` to `$CONDA_PREFIX/etc/OpenCL/vendors` (with a correct-path `.icd`) and unset `OCL_ICD_FILENAMES`. A pip wheel instead drops its vendor ICD under the Python prefix with a broken placeholder path, and the system loader only scans `/etc/OpenCL/vendors`, so it finds no CPU device even though the runtime is installed. Symptom: an empty or GPU-only `dpctl` device list and a `SyclDeviceCreationError` when you ask for `"cpu"`.

ICD registration is OS-specific. On **Linux**, register the real absolute path of `libintelocl.so` as a system vendor ICD:

```bash
INTELOCL="$(find "$(python -c 'import sys; print(sys.prefix)')" -name libintelocl.so -print -quit)"
test -n "$INTELOCL" || echo "libintelocl.so not found — is intel-opencl-rt installed?"
sudo mkdir -p /etc/OpenCL/vendors
printf '%s\n' "$INTELOCL" | sudo tee /etc/OpenCL/vendors/intel-cpu.icd
python -c "import dpctl; print(dpctl.SyclDevice('cpu'))"   # should print a CPU device
```

Without root (locked-down container or CI runner), set `OCL_ICD_VENDORS` to a directory containing your `.icd` file, or to the `.icd` itself. (`OCL_ICD_FILENAMES` does *not* reliably surface the device through the SYCL runtime — prefer the `.icd`/`OCL_ICD_VENDORS` route.) The Intel wheels bake their own RPATHs, so transitive dependencies resolve once the loader finds the ICD.

**Windows** registers ICDs through the registry, not `/etc/OpenCL/vendors`, so the Linux fix doesn't apply. Normal user-mode conda activates the CPU runtime automatically; only when conda runs **elevated / as Administrator** (as CI runners do) must you register the ICD explicitly:

```powershell
& "$env:CONDA_PREFIX\Scripts\set-intel-ocl-icd-registry.ps1"   # unset-intel-ocl-icd-registry.ps1 removes it
```

The Windows CPU driver finds its TBB DLLs via `$env:CONDA_PREFIX\Library\bin\cl.cfg`; if the device is missing under a given launcher, check that file.

## Intel GPU drivers

Running on an Intel GPU (Arc, Flex, Data Center GPU Max, or an integrated iGPU) needs the OS GPU driver, in two layers — and **neither pip nor conda installs either**. The conda package `intel-gpu-ocl-icd-system` only *registers* a pointer to a system driver; it is not the driver.

- **Kernel-mode driver** — `i915` (or the newer `Xe` on recent kernels), built into the kernel; keep firmware current via `linux-firmware`.
- **User-mode compute runtime** — what SYCL dispatches to: `intel-opencl-icd` (OpenCL GPU driver, `libigdrcl.so`) and `intel-level-zero-gpu` (Level Zero driver, `libze_intel_gpu.so`) plus the `level-zero` loader. Level Zero is the preferred backend (lower overhead than OpenCL).

On Linux these come from Intel's graphics repository — follow Intel's GPU driver install guide (https://dgpu-docs.intel.com/driver/installation.html) rather than pinning package names, which change across releases. On Windows, the single Intel Graphics driver bundles both runtimes — install it via the Intel Driver & Support Assistant (https://www.intel.com/content/www/us/en/support/detect.html). Confirm the GPU is visible to SYCL before running dpnp (see Verification). If it never shows up, fix the kernel driver or compute runtime, not dpnp.

## Selecting the device with environment variables

dpnp picks a default device at import time from whatever SYCL exposes, so the environment you launch Python in determines where arrays land. The useful variables:

- **`ONEAPI_DEVICE_SELECTOR`** — the modern device selector (replaces the deprecated `SYCL_DEVICE_FILTER`). Values are `backend:device_type`, e.g. `level_zero:gpu`, `opencl:cpu`, or `*:gpu`. Set it before Python starts to constrain what dpnp sees.
- **`OCL_ICD_VENDORS`** — directory the OpenCL loader scans for `.icd` files; used for the rootless CPU-ICD fix above and in containers.
- **`SYCL_CACHE_PERSISTENT=1`** — persist the JIT kernel cache across runs, so first-run compilation cost is paid once rather than every process start.
- **`SYCL_UR_TRACE=1`** — verbose runtime tracing; useful when debugging why a device is not discovered (replaces the deprecated `SYCL_PI_TRACE`).

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu python -c "import dpnp; print(dpnp.arange(4).sycl_device.filter_string)"
ONEAPI_DEVICE_SELECTOR=opencl:cpu  python -c "import dpnp; print(dpnp.arange(4).sycl_device.filter_string)"
```

## Verification

A correct numerical result does not prove dpnp ran where you wanted — a CPU-only install returns exactly the numbers a GPU would. Confirm the device explicitly. List what SYCL sees, then check where an array actually lives:

```bash
python - <<'EOF'
import dpctl, dpnp

print("SYCL platforms/devices:")
dpctl.lsplatform()                      # dpctl's device lister

for d in dpctl.get_devices():
    print(" ", d.filter_string, "-", d.name)

a = dpnp.arange(1_000_000)
print("array ran on:", a.sycl_device.filter_string)   # e.g. level_zero:gpu:0 or opencl:cpu:0
EOF
```

For a no-code check, `python -m dpctl -f` prints the same platform/device list with filter strings straight from the command line (`-s` for a short summary). And if you have the oneAPI DPC++ runtime, `sycl-ls` reports the device list independently of dpctl — handy for separating "SYCL can't see the device" from "dpnp/dpctl can't see the device". If the device isn't the one you expected, see Troubleshooting.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'dpnp'`** — you're on the wrong interpreter. Check the active one with `which python`, then confirm dpnp is present there via `conda list dpnp` or `pip show dpnp`. A mismatch means the install landed in a different environment.
- **No CPU device / `SyclDeviceCreationError` for `"cpu"` after a pip install** — the OpenCL CPU ICD is not registered; apply the fix in "Getting the CPU device recognized (OpenCL ICD)".
- **Expected a GPU but only `opencl:cpu:0` shows up** — the Intel GPU driver/compute runtime is missing (pip and conda do not install it). See Intel GPU drivers, then re-check with `python -m dpctl -f`.
- **Slower than NumPy on small arrays** — expected: dpnp has per-call dispatch and first-run JIT overhead. Use it for large, math-heavy work, time the second run, and set `SYCL_CACHE_PERSISTENT=1`.

## Best practices

- Install into an isolated env, preferring conda; never mix a conda `dpnp` and a pip `dpnp` in one environment.
- Confirm the device with `dpctl.lsplatform()` / `array.sycl_device.filter_string` before benchmarking — correct output alone does not prove GPU execution.

## See also

- `data/skills/dpnp-quickstart` — basic NumPy-compatible usage once dpnp is installed.
- `data/skills/dpnp-memory` — device inspection, USM memory, and monitoring tools (`xpu-smi`, `clinfo`, `ze_info`).
- `data/skills/dpnp-io` — reading and writing dpnp arrays (NumPy round-trips, HDF5, Zarr, CSV).
- dpnp documentation: https://intelpython.github.io/dpnp/
- dpctl documentation: https://intelpython.github.io/dpctl/
