# Example execution (`example_pass_rate`)

The static benchmark can execute fenced code blocks found in documentation to
measure whether examples actually run. Executing arbitrary code from docs is
dangerous, so execution is governed by an explicit **execution policy** in the
spec.

## Backends

Configure under `metrics.example_pass_rate.execution` in your spec:

```yaml
metrics:
  example_pass_rate:
    enabled: true
    weight: 0.20
    execution:
      backend: none        # none | subprocess | docker
      allow_host: false    # required true for the subprocess backend
      timeout: 5           # seconds per example
      docker_image: python:3.11-slim
      mem_mb: 512
      cpus: 1.0
```

| Backend | Isolation | Use when |
| --- | --- | --- |
| `none` (default) | Nothing runs; examples reported as `skipped` | Untrusted corpora, or you only want extraction |
| `subprocess` | Resource-limited host subprocess (CPU/mem/pids caps, minimal env, temp cwd). **No network isolation.** Requires `allow_host: true`. | Trusted, self-owned documentation |
| `docker` | Container with `--network none`, read-only mounts, CPU/memory/pid limits, per-example timeout | Untrusted documentation |

### Why `none` is the default

Previously, fenced `python`/`bash`/`sh` blocks were executed directly on the
host with only a timeout. That is unsafe for any documentation you do not own.
The default is now `none`; you must explicitly opt into execution.

`example_pass_rate` is computed over **executed** examples only. A document with no
examples — or whose examples were all skipped — scores `1.0` (nothing failed).
Each example records a `status` of `passed` / `failed` / `skipped` / `error`.

## Overriding the backend

Set `DOC_BENCH_EXAMPLE_BACKEND` to force a backend regardless of the spec — for
example, to neutralize execution in a shared CI runner:

```bash
DOC_BENCH_EXAMPLE_BACKEND=none agent-benchmark run --spec benchmarks/spec.v1.yaml
```

## Security notes

- The `subprocess` backend strips the parent environment (no API keys leak into
  examples) and applies POSIX resource limits, but it **cannot** isolate the
  network. Only use it on documentation you trust.
- For anything else, use `docker`, which adds `--network none` and a read-only
  filesystem. See also [SECURITY.md](../SECURITY.md).
