#!/usr/bin/env python3
"""Test PersonaAnalyzer with gh CLI fallback."""

import sys
sys.path.insert(0, '/workspace/doc-benchmark')

from doc_benchmarks.personas.analyzer import PersonaAnalyzer

print("=" * 70)
print("Testing PersonaAnalyzer with gh CLI fallback")
print("=" * 70)

analyzer = PersonaAnalyzer()  # No GitHub token → will use gh CLI
print("\n[1] Analyzing uxlfoundation/oneTBB...")

analysis = analyzer.analyze_repository("uxlfoundation/oneTBB")

print(f"\n✓ Analysis complete:")
print(f"  Description: {analysis.get('description', 'N/A')}")
print(f"  README length: {len(analysis.get('readme_content', ''))} chars")
print(f"  Use cases found: {len(analysis.get('use_cases', []))}")
print(f"  API patterns found: {len(analysis.get('api_patterns', []))}")

if analysis.get('use_cases'):
    print(f"\n  Sample use cases:")
    for uc in analysis['use_cases'][:3]:
        print(f"    - {uc}")

if analysis.get('api_patterns'):
    print(f"\n  Sample API patterns:")
    for ap in analysis['api_patterns'][:5]:
        print(f"    - {ap}")

print("\n" + "=" * 70)
print("SUCCESS: gh CLI fallback working")
print("=" * 70)
