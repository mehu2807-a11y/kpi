"""
Run multiple iterations of the BusinessIntelligence.ai pipeline
for testing, validation, or performance measurement.
"""

import time
import statistics
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from mock_data import easy_case, hard_case
from llm_client import MockLLMClient
from synthesize import synthesize_enhanced

# Import enhancement modules - try to import them, but don't fail if not available
try:
    from ollama_llm import OllamaLLMClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    OllamaLLMClient = None

try:
    from grok_llm import GrokLLMClient
    GROK_AVAILABLE = True
except ImportError:
    GROK_AVAILABLE = False
    GrokLLMClient = None


def run_iteration_suite(
    num_iterations: int = 20,
    use_ollama: bool = False,
    use_grok: bool = False,
    ollama_model: str = "llama3:8b",
    grok_model: str = "grok-beta"
) -> Dict[str, Any]:
    """
    Run multiple iterations of both test cases and collect statistics.

    Returns:
        Dictionary with aggregated results and performance metrics
    """
    # Initialize LLM client based on choice
    if use_ollama:
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama not available. Make sure ollama_llm.py exists.")
        llm_client = OllamaLLMClient(model=ollama_model)
        print(f"Using Ollama model: {ollama_model}")
    elif use_grok:
        if not GROK_AVAILABLE:
            raise RuntimeError("Grok not available. Make sure grok_llm.py exists and GROK_API_KEY is set.")
        llm_client = GrokLLMClient(model=grok_model)
        print(f"Using Grok model: {grok_model}")
    else:
        # Use mock for fast testing
        # Use proper canned responses like in demo_enhanced.py
        EASY_LLM_RESPONSE = {
            "explanation": (
                "Region X revenue fell 7.5% for the week of July 4-10. The drop lines up closely "
                "with a 10% list-price increase on Product A that took effect July 4, which is also "
                "the strongest structured driver for this anomaly. A competitor promotion in "
                "overlapping markets is a much weaker, secondary signal."
            ),
            "hypotheses": [
                {
                    "cause": "10% price increase on Product A, effective July 4, reduced regional demand",
                    "citations": ["CorrelationResult.avg_price", "internal_00091", "news_00231"],
                    "actions": [
                        "Compare Region X's price elasticity for Product A against the assumption used when the increase was approved",
                        "Check whether the drop is concentrated in Product A or spread across the regional basket",
                    ],
                },
                {
                    "cause": "CompetitorCo's summer promotion pulled share in overlapping markets",
                    "citations": ["news_00255"],
                    "actions": [
                        "Confirm CompetitorCo's promotion end date before reversing any price change",
                    ],
                },
            ],
        }

        HARD_LLM_RESPONSE = {
            "explanation": (
                "Region Y signups fell 12% for the week of June 13-19. Two structural drivers are "
                "close in strength: a 3.2x spike in mobile app crash rate and a 40% cut to regional "
                "marketing spend, starting within a day of each other. Evidence supports each "
                "independently, and nothing in the data distinguishes which one dominates."
            ),
            "hypotheses": [
                {
                    "cause": "Mobile app crashes drove signup abandonment",
                    "citations": ["CorrelationResult.crash_rate", "reviews_00114"],
                    "actions": [
                        "Pull crash logs for the affected app version and confirm the release date lines up with June 14",
                        "Check signup funnel drop-off specifically at the crash-prone screen",
                    ],
                },
                {
                    "cause": "40% marketing spend cut in Region Y reduced top-of-funnel traffic",
                    "citations": ["CorrelationResult.marketing_spend_cut", "internal_00147"],
                    "actions": [
                        "Compare paid traffic volume in Region Y before and after June 13 against the signup drop timing",
                    ],
                },
            ],
        }

        # Store results from all iterations
    all_results = []
    latencies = []
    token_estimates = []
    cost_estimates = []

    test_cases = [
        ("EASY_CASE", easy_case),
        ("HARD_CASE", hard_case)
    ]

    print(f"\nRunning {num_iterations} iterations per test case...")
    print("=" * 60)

    for case_name, case_fn in test_cases:
        case_latencies = []
        case_results = []

        for i in range(num_iterations):
            start_time = time.perf_counter()

            try:
                anomaly, correlation, evidence = case_fn()
                # Use appropriate LLM client for each test case
                if use_ollama:
                    llm_client = OllamaLLMClient(model=ollama_model)
                elif use_grok:
                    llm_client = GrokLLMClient(model=grok_model)
                else:
                    # Use mock for fast testing - select response based on case
                    if case_name == "EASY_CASE":
                        EASY_LLM_RESPONSE = {
                            "explanation": (
                                "Region X revenue fell 7.5% for the week of July 4-10. The drop lines up closely "
                                "with a 10% list-price increase on Product A that took effect July 4, which is also "
                                "the strongest structured driver for this anomaly. A competitor promotion in "
                                "overlapping markets is a much weaker, secondary signal."
                            ),
                            "hypotheses": [
                                {
                                    "cause": "10% price increase on Product A, effective July 4, reduced regional demand",
                                    "citations": ["CorrelationResult.avg_price", "internal_00091", "news_00231"],
                                    "actions": [
                                        "Compare Region Xs price elasticity for Product A against the assumption used when the increase was approved",
                                        "Check whether the drop is concentrated in Product A or spread across the regional basket",
                                    ],
                                },
                                {
                                    "cause": "CompetitorCos summer promotion pulled share in overlapping markets",
                                    "citations": ["news_00255"],
                                    "actions": [
                                        "Confirm CompetitorCos promotion end date before reversing any price change",
                                    ],
                                },
                            ],
                        }
                        llm_client = MockLLMClient(EASY_LLM_RESPONSE)
                    else:  # HARD_CASE
                        HARD_LLM_RESPONSE = {
                            "explanation": (
                                "Region Y signups fell 12% for the week of June 13-19. Two structural drivers are "
                                "close in strength: a 3.2x spike in mobile app crash rate and a 40% cut to regional "
                                "marketing spend, starting within a day of each other. Evidence supports each "
                                "independently, and nothing in the data distinguishes which one dominates."
                            ),
                            "hypotheses": [
                                {
                                    "cause": "Mobile app crashes drove signup abandonment",
                                    "citations": ["CorrelationResult.crash_rate", "reviews_00114"],
                                    "actions": [
                                        "Pull crash logs for the affected app version and confirm the release date lines up with June 14",
                                        "Check signup funnel drop-off specifically at the crash-prone screen",
                                    ],
                                },
                                {
                                    "cause": "40% marketing spend cut in Region Y reduced top-of-funnel traffic",
                                    "citations": ["CorrelationResult.marketing_spend_cut", "internal_00147"],
                                    "actions": [
                                        "Compare paid traffic volume in Region Y before and after June 13 against the signup drop timing",
                                    ],
                                },
                            ]
                        }
                        llm_client = MockLLMClient(HARD_LLM_RESPONSE)

                result = synthesize_enhanced(anomaly, correlation, evidence, llm_client)

                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000

                # Collect metrics
                latencies.append(latency_ms)
                case_latencies.append(latency_ms)

                telemetry = result["telemetry"]
                token_estimates.append(telemetry.get("llm_total_tokens_estimate", 0))
                cost_estimates.append(telemetry.get("estimated_cost_usd", 0))

                # Store key results
                case_results.append({
                    "iteration": i + 1,
                    "case": case_name,
                    "confidence": result["original_story"].overall_confidence,
                    "escalate": result["original_story"].escalate_flag,
                    "latency_ms": latency_ms,
                    "num_actions": len(result["structured_actions"]),
                    "num_hypotheses": len(result["original_story"].hypotheses)
                })

                if (i + 1) % 5 == 0:  # Progress indicator
                    print(f"  {case_name}: Completed {i + 1}/{num_iterations} iterations")

            except Exception as e:
                print(f"  ERROR in {case_name} iteration {i + 1}: {e}")
                # Continue with next iteration

        all_results.extend(case_results)

        # Print case-specific stats
        if case_latencies:
            print(f"\n{case_name} Results:")
            print(f"  Avg Latency: {statistics.mean(case_latencies):.2f}ms")
            print(f"  Min Latency: {min(case_latencies):.2f}ms")
            print(f"  Max Latency: {max(case_latencies):.2f}ms")
            print(f"  Std Dev Latency: {statistics.stdev(case_latencies) if len(case_latencies) > 1 else 0:.2f}ms")

    # Overall statistics
    print("\n" + "=" * 60)
    print("OVERALL STATISTICS")
    print("=" * 60)
    print(f"Total Iterations: {len(all_results)}")
    print(f"Overall Avg Latency: {statistics.mean(latencies):.2f}ms")
    print(f"Overall Min Latency: {min(latencies):.2f}ms")
    print(f"Overall Max Latency: {max(latencies):.2f}ms")
    if len(latencies) > 1:
        print(f"Overall Std Dev Latency: {statistics.stdev(latencies):.2f}ms")

    print(f"\nLLM Usage Estimates:")
    print(f"Avg Tokens/Call: {statistics.mean(token_estimates) if token_estimates else 0:.0f}")
    print(f"Total Estimated Cost: ${sum(cost_estimates):.6f}")
    print(f"Avg Cost/Call: ${statistics.mean(cost_estimates) if cost_estimates else 0:.6f}")

    # Success rate
    success_count = len([r for r in all_results if "confidence" in r])
    print(f"\nSuccess Rate: {success_count}/{len(all_results)} ({success_count/len(all_results)*100:.1f}%)")

    return {
        "iterations": all_results,
        "latencies": latencies,
        "token_estimates": token_estimates,
        "cost_estimates": cost_estimates,
        "summary": {
            "total_iterations": len(all_results),
            "avg_latency_ms": statistics.mean(latencies),
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies),
            "std_latency_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "avg_tokens": statistics.mean(token_estimates) if token_estimates else 0,
            "total_cost_usd": sum(cost_estimates),
            "success_rate": success_count / len(all_results) if all_results else 0
        }
    }


def main():
    """Run the iteration suite."""
    print("BusinessIntelligence.ai - Iteration Test Suite")
    print("Choose testing mode:")
    print("1. Fast testing with Mock LLM (no setup needed)")
    print("2. Realistic testing with Ollama (requires Ollama installed)")
    print("3. Testing with Grok API (requires xAI API key)")

    choice = input("\nEnter choice (1, 2, or 3): ").strip()

    use_ollama = False
    use_grok = False

    if choice == "2":
        use_ollama = True
        print("\nMake sure Ollama is running: ollama serve")
        print("And you have pulled a model: ollama pull llama3:8b")
        input("Press Enter when ready...")
    elif choice == "3":
        use_grok = True
        print("\nMake sure you have set your GROK_API_KEY environment variable:")
        print("  export GROK_API_KEY='your_actual_key_here'")
        print("And that you have internet access to reach api.x.ai")
        input("Press Enter when ready...")
    else:
        use_ollama = False
        use_grok = False  # Default to mock

    num_iterations = 20
    try:
        custom = input(f"Number of iterations per test case? [{num_iterations}]: ").strip()
        if custom:
            num_iterations = int(custom)
    except ValueError:
        pass

    results = run_iteration_suite(
        num_iterations=num_iterations,
        use_ollama=use_ollama,
        use_grok=use_grok
    )

    # Save results to file for further analysis
    import json
    from datetime import datetime
    filename = f"iteration_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {filename}")


if __name__ == "__main__":
    main()
