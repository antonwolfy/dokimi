### Fixed

- **`skill shorten` and `skill novelty analyze` refuse a `--cache-dir` they cannot store into, before any paid call** — a `--cache-dir` naming a regular file (or whose parent is one, or an unwritable directory) ended both commands in a `FileExistsError` traceback on the first retention adjudication. They now exit 2 with `--cache-dir <path> is not a directory` (or names the unwritable directory). A directory that exists, and one that does not exist yet, are taken as before.
