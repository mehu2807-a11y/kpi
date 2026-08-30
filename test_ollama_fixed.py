#!/usr/bin/env python
"""Test script to run iterations with Ollama"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'task6'))

from run_iterations import run_iteration_suite

# Run 2 iterations of each test case with Ollama
print("Testing with Ollama (llama3:8b)...")
results = run_iteration_suite(
    num_iterations=2,
    use_ollama=True,
    ollama_model="llama3:8b"
)

print("\nResults from returned dictionary:")
summary = results['summary']
print(f"Total iterations: {summary['total_iterations']}")
print(f"Success rate: {summary['success_rate']*100:.1f}%")
print(f"Average latency: {summary['avg_latency_ms']:.2f} ms")
print(f"Min latency: {summary['min_latency_ms']:.2f} ms")
print(f"Max latency: {summary['max_latency_ms']:.2f} ms")
print(f"Average tokens: {summary['avg_tokens']:.1f}")
print(f"Total cost: ${summary['total_cost_usd']:.6f}")
print(f"Average cost per call: ${summary['total_cost_usd']/summary['total_iterations']:.6f}")