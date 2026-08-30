#!/usr/bin/env python3
"""
Simple test to verify custom input functionality works
"""

import json
import requests

def test_custom_input():
    """Test sending custom data to the /analyze endpoint"""

    # Load the test payload we know works
    with open('test_payload.json', 'r') as f:
        payload = json.load(f)

    print("Sending custom data to /analyze endpoint...")
    print(f"Anomaly: {payload['anomaly']['metric_name']} {payload['anomaly']['direction']} by {payload['anomaly']['magnitude_pct']}%")
    print(f"Entity: {payload['anomaly']['entity']}")
    print(f"Time window: {payload['anomaly']['window_start']} to {payload['anomaly']['window_end']}")
    print()

    try:
        response = requests.post(
            "http://localhost:5000/analyze",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            print("Analysis successful!")
            print()
            print("Results Summary:")
            print(f"- Headline: {result['original_story']['headline']}")
            print(f"- Confidence: {result['original_story']['overall_confidence']:.1%}")
            print(f"- Structured Actions: {len(result['structured_actions'])} generated")
            print(f"- Persona Narratives: {len(result['persona_narratives'])} perspectives")
            print(f"- Relevant KPIs: {len(result['relevant_kpis'])} identified")
            print()

            # Show telemetry
            telemetry = result.get('telemetry', {})
            if telemetry:
                print("Telemetry:")
                print(f"- Processing Latency: {telemetry.get('processing_latency_ms', 0):.2f} ms")
                print(f"- LLM Calls: {telemetry.get('llm_calls', 0)}")
                print(f"- Estimated Tokens: {telemetry.get('llm_total_tokens_estimate', 0)}")
                print(f"- Estimated Cost: ${telemetry.get('estimated_cost_usd', 0):.6f}")

            return True
        else:
            print(f"Error: {response.status_code}")
            return False

    except Exception as e:
        print(f"Request failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Testing Custom Data Input")
    print("=" * 50)

    success = test_custom_input()

    print()
    if success:
        print("CUSTOM INPUT FUNCTIONALITY VERIFIED")
        print("You can now provide your own real data/case studies!")
    else:
        print("CUSTOM INPUT TEST FAILED")