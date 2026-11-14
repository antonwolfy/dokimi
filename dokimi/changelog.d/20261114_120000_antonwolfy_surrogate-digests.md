### Fixed

- **A remote source URL with a non-UTF-8 byte no longer stops `cache_path`** — the clone directory is hashed from the URL's file-system bytes, so a surrogate-escaped URL gets its own directory instead of a `UnicodeEncodeError`; the directory of every UTF-8 URL is unchanged.
