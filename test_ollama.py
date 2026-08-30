#!/usr/bin/env python
"""Test script to run iterations with Ollama"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'task6'))

from run_iterations import run_iteration_suite

# Run 3 iterations of each test case with Ollama
print("Testing with Ollama (llama3:8b)...")
results = run_iteration_suite(
    num_iterations=3,
    use_ollama=True,
    ollama_model="llama3:8b"
)

print("\nResults:")
print(f"Easy case: {results['easy_case']['success_rate']*100:.1f}% success rate")
print(f"Hard case: {results['hard_case']['success_rate']*100:.1f}% success rate")
print(f"Average latency: {results['aggregated']['avg_latency_ms']:.2f} ms")
print(f"Average tokens: {results['aggregated']['avg_total_tokens']:.1f}")
print(f"Average cost: ${results['aggregated']['avg_cost_usd']:.6f}")