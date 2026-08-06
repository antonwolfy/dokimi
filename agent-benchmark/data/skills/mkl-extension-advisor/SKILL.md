---
name: mkl-extension-advisor
description: Use when a user asks whether Intel's MKL extension packages (mkl_fft, mkl_random, mkl_umath) apply to their NumPy or SciPy code on Intel CPUs, or points at a snippet, function, file, or codebase using np.fft, scipy.fft, np.random, or element-wise math ufuncs. Also use to check whether these extensions are already active in an environment, to fix an install so they and the SciPy FFT backend actually work, or to judge whether patching would change results or break exact-output tests. DO NOT use for GPU work, non-Intel CPUs, or mkl-service thread tuning.
allowed-tools: Read, Grep, Glob, Bash, Edit
---

# mkl-extension-advisor

Given NumPy or SciPy code, decide whether `mkl_fft`, `mkl_random` or `mkl_umath` help it, and present verified changes with short reasons. A fit check, not a profiler.

Scan first, then load only the reference for each extension the code actually implicates.

## Two axes

- **Install:** which numpy binary is present and what it links against.
- **Runtime:** whether call sites dispatch to oneMKL, set by an activation call or by build-level pre-wiring.

They are independent. An MKL-backed BLAS says nothing about FFT: numpy's FFT is bundled pocketfft with no BLAS linkage, so `threadpool_info()` can report `mkl` while `np.fft.fft.__module__` is still `numpy.fft`.

Careful with the reverse inference too: an `mkl` entry in the threadpool does **not** prove numpy's BLAS is MKL. Importing any mkl_* extension loads oneMKL into the process, so a stock OpenBLAS numpy shows `['mkl', 'openblas', 'openmp']` after `import mkl_fft`. For the BLAS question read `np.__config__.show()`, not the pool.

An Intel-built numpy arrives build-wired, with FFT and umath dispatching to MKL before any activation call. That wiring lives in the numpy **recipe**, which rebinds `numpy/fft/__init__.py` globals directly and never touches the patch counter. A conda-forge or stock-PyPI numpy leaves the extensions dormant.

The numpy build is not the only thing that can wire a process: mkl_fft's CLI can install a persistent `.pth` patch that applies at every interpreter start, invisible to `pip list`, and a `sitecustomize.py` variant does the same. An earlier import in the same process may also have patched. So read the state at runtime (step 4); never infer it from the installer, the channel, or a version string.

## Procedure

1. Take the input: a snippet, function, file, or codebase.
2. Scan every call site and categorize it:
   - `np.fft.*`, `scipy.fft.*`, `scipy.fftpack.*` -> mkl_fft
   - `np.random.*`, `RandomState`, `default_rng`/`Generator` -> mkl_random
   - element-wise math ufuncs on arrays -> mkl_umath
3. For each DISTINCT surface found, load only that reference: `references/mkl_fft.md`, `references/mkl_random.md`, `references/mkl_umath.md`. Do not load a reference for a surface the code does not use.
4. Establish the install axis once, shared by all surfaces:
   ```bash
   python scripts/probe_env.py
   ```
   It prints JSON: whether numpy is MKL-backed, whether each surface is patched, how FFT got wired, which packages are importable, and any blocking gaps. If you cannot run it, use the probe snippets in each reference.
5. Judge each call site against the loaded reference: does that extension cover this call and this usage? Decide fit, including honest NO.
   When shape or contiguity is not knowable from the code, do not guess and do not time code to discover it. Ask for typical shapes, read the config, or instrument the call site. Failing that, answer conditionally on the gate: "worth patching only if the inner dimension is well above the transcendental threshold; at or below it the VML kernel never runs, so expect no speedup."
6. Collect applicable sites: file/location, the call, the minimal change, and the one-line reason it helps THIS code. Do not add a redundant patch to an already-wired surface.
7. Confirm the whole input was scanned before presenting. Do not stop at the first hit.
8. Present:
   - **With suggestions:** grouped by location, each with a diff or code block and a short reason. Add the install channels if packages are missing, the proof step per surface, and the mkl_random confirmation gate. If the code has exact-output tests or golden files, flag the numerical effect - none of the three is a bitwise drop-in.
   - **No suggestions:** say so plainly and why (only uncovered ufuncs, only the Generator API, only sub-threshold arrays, only strided views, only FFT helpers, or nothing MKL-relevant). Do not invent a benefit.
9. Apply only on confirmation. Show suggestions first, edit after the user says yes. mkl_random needs an explicit OK every time - it changes results.

## Guard rails

- **Static analysis decides eligibility; measurement decides benefit.** Whether a call site dispatches at all is answerable from the code plus the gates. How much faster it runs is not: that depends on both builds, thread count and CPU.
- Do not time code yourself and never invent a number. But measurement is not illegitimate - once eligibility is established, pointing the user at measurement on their own hardware is the right next step. Upstream ships benchmark suites precisely because the answer varies per machine.
- Never use a stopwatch to discover a fact you could read: shape, dtype, contiguity. Instrumenting a call site to log the inner-loop length is a good answer, and so is asking.
- State no speedup figures of your own. Describe direction and eligibility. Do **not** claim a sub-threshold regression - unsupported and build-dependent. If the user supplies measured numbers, reason about those.
- You MAY cite mkl_umath's dispatch thresholds; withholding them produces wrong advice. But they are **private `#define`s, not API**, so read them from the installed build rather than from memory, and say which build. If you cannot read them, express the answer as a gate the user can check.
- Reason only from the code the user gave you. Do not claim to have found it in any document.
- Decisions come from runtime state: bound-function `__module__`, `is_patched()`, ufunc `types`, array `strides`/`flags`, threadpoolctl. Never from a version string. Assume the documented activation API is present; probe what is *wired*, not what exists.
- **Every fact you state should be one the environment can confirm.** These packages move: APIs get added, thresholds change, coverage grows, docs lag source, channels shift. Do not answer from a remembered version, date, issue number or count - and do not add such things to this skill. Prefer "check `u.sin.types`" over a dtype list. A fact with a probe attached stays true; a fact with a version attached expires.
- Call activation functions on the top-level package (`import mkl_fft; mkl_fft.patch_numpy_fft()`). No private submodules, no invented names.
- Proof of "FFT active" is `np.fft.fft.__module__`, not `is_patched()`.

## Install channels

conda (Intel channel first, conda-forge second):
```bash
conda install -c https://software.repos.intel.com/python/conda \
  -c conda-forge --override-channels \
  "blas=*=*_intelmkl" numpy scipy mkl_fft mkl_random mkl_umath mkl-service
```
pip (Intel index as the *primary* index):
```bash
pip install --index-url https://software.repos.intel.com/python/pypi \
  numpy scipy mkl_fft mkl_random mkl_umath mkl-service
pip install threadpoolctl   # not mirrored on Intel's index
```

What changes the outcome:

- **`mkl-service` is not optional for the SciPy FFT backend.** It provides the `mkl` module that `_scipy_fft.py` imports at module level, and the guard in `interfaces/__init__.py` means the backend disappears *silently* without it rather than raising. It is otherwise a thread-control API with no patch surface.
- `scipy` is required for that same backend, even if the code only touches `np.fft` today.
- Use `--index-url`, not `--extra-index-url`. Intel's index is a partial mirror and pip picks the highest version across indexes, so extra-index lets PyPI's stock numpy win.
- Which numpy wins decides what is build-wired. A BLAS selector constrains BLAS only, never FFT wiring. Confirm with step 4.
- If Intel's servers are unreachable, the extensions are on public PyPI and most are on conda-forge. Coverage is **not** uniform across the family or stable over time, so check per package rather than assuming parity. Any fallback install pairs with a stock numpy, so nothing is build-wired.

## Bundled resources

- `scripts/probe_env.py` - the step 4 probe. Read-only, prints JSON, no timing.

## References (load on demand)

- `references/mkl_fft.md` - transforms, SciPy backend, activation, proof, numerical effect.
- `references/mkl_random.md` - covered API, reproducibility hazard, parallel streams, proof.
- `references/mkl_umath.md` - coverage probe, eligibility gates, numerical effect, thread safety.
