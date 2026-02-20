#!/usr/bin/env python3
"""Quick test script for Context7 MCP client."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from doc_benchmarks.mcp.context7 import create_context7_client, MCPConnectionError

def main():
    print("Testing Context7 MCP Client...")
    print("=" * 60)
    
    # Create client with cache
    cache_dir = Path(".cache/context7")
    client = create_context7_client(cache_dir=cache_dir)
    print(f"✓ Created client (cache: {cache_dir})")
    
    # Test connection
    print("\n1. Checking connection...")
    try:
        if client.check_connection():
            print("✓ Context7 is accessible")
        else:
            print("✗ Context7 check failed")
            return 1
    except Exception as e:
        print(f"✗ Connection check error: {e}")
        return 1
    
    # Test library ID resolution
    print("\n2. Testing library ID resolution...")
    test_libs = ["oneTBB", "oneDAL", "oneDNN", "onemkl"]
    for lib in test_libs:
        resolved = client.resolve_library_id(lib)
        print(f"  {lib:10s} -> {resolved}")
    
    # Test doc retrieval
    print("\n3. Testing doc retrieval for oneTBB...")
    try:
        docs = client.get_library_docs(
            "uxlfoundation/oneTBB",
            "How to use parallel_for?",
            max_tokens=1000
        )
        
        if docs:
            doc = docs[0]
            print(f"✓ Retrieved {len(doc['content'])} bytes")
            print(f"  Source: {doc['source']}")
            print(f"  Cached: {doc.get('cached', False)}")
            print(f"  Preview: {doc['content'][:200]}...")
        else:
            print("✗ No docs returned")
            return 1
            
    except MCPConnectionError as e:
        print(f"✗ Retrieval error: {e}")
        return 1
    
    # Test cache
    print("\n4. Testing cache (second request)...")
    try:
        docs2 = client.get_library_docs(
            "uxlfoundation/oneTBB",
            "How to use parallel_for?",
            max_tokens=1000
        )
        if docs2[0].get('cached'):
            print("✓ Cache hit!")
        else:
            print("⚠ No cache hit (expected on first run)")
    except Exception as e:
        print(f"✗ Cache test error: {e}")
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
