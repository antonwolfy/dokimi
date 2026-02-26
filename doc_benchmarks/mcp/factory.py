"""Factory for creating documentation source clients from CLI flag values."""

from pathlib import Path
from typing import Optional

from . import MCPClient


def create_doc_source_client(
    doc_source: str,
    cache_dir: Optional[Path] = None,
) -> MCPClient:
    """
    Create an MCP client from a ``--doc-source`` string.

    Supported formats
    -----------------
    ``context7``
        Use the Context7 cloud API (default).  Requires internet access.

    ``local:<path>``
        Load documentation from a local directory or file.
        ``<path>`` may be absolute or relative to the current working directory.
        Supports ``.md``, ``.rst``, ``.txt``, ``.html`` and ``.htm`` files.

    ``url:<url>``
        Fetch documentation from an arbitrary URL, split into paragraphs,
        and return the most query-relevant chunks.

    Parameters
    ----------
    doc_source:
        Source descriptor string (see formats above).
    cache_dir:
        Optional cache directory.  Used by Context7Client and URLClient.
        Defaults to ``.cache/<source-type>``.

    Returns
    -------
    MCPClient
        A fully-configured client ready to call ``get_library_docs()``.

    Raises
    ------
    ValueError
        If *doc_source* is not recognised.

    Examples
    --------
    >>> client = create_doc_source_client("context7")
    >>> client = create_doc_source_client("local:/docs/onetbb")
    >>> client = create_doc_source_client("url:https://spec.example.com/api.html")
    """
    if doc_source == "context7":
        from .context7 import Context7Client
        _cache = cache_dir or Path(".cache/context7")
        return Context7Client(cache_dir=_cache)

    if doc_source.startswith("local:"):
        from .local_markdown import LocalMarkdownClient
        path_str = doc_source[len("local:"):]
        if not path_str:
            raise ValueError("'local:' source requires a path, e.g. 'local:/path/to/docs'")
        return LocalMarkdownClient(Path(path_str))

    if doc_source.startswith("url:"):
        from .url_client import URLClient
        url = doc_source[len("url:"):]
        if not url:
            raise ValueError("'url:' source requires a URL, e.g. 'url:https://example.com/docs'")
        _cache = cache_dir or Path(".cache/url")
        return URLClient(url=url, cache_dir=_cache)

    raise ValueError(
        f"Unknown --doc-source format: '{doc_source}'. "
        "Valid formats: 'context7', 'local:<path>', 'url:<url>'"
    )
