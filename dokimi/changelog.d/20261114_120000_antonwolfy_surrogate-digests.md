### Fixed

- **A remote source URL with a non-UTF-8 byte no longer stops `cache_path`** — the clone directory is hashed from the URL's file-system bytes, so a surrogate-escaped URL gets its own directory instead of a `UnicodeEncodeError`; the directory of every UTF-8 URL is unchanged.
- **A harness id with a non-UTF-8 byte and a Windows-reserved character no longer stops the suite runner** — `_safe_id` hashes the id's file-system bytes, so the directory name of an id that encodes as UTF-8 is unchanged.
- **A file name or case id with a non-UTF-8 byte no longer stops the reach and skill-reach tokens** — `token` in `repos/reach.py` and `repos/skill_reach.py` hashes the file-system bytes of its input; the token of a UTF-8 path or case id is unchanged.
- **A doc source with a non-UTF-8 byte no longer stops the URL cache key or the topics cache directory** — `URLClient._cache_key` and the question step of `EvaluationPipeline` hash the source's file-system bytes; both keys of a UTF-8 source are unchanged.
