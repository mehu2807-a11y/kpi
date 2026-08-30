#!/usr/bin/env python3
"""
Test script to demonstrate custom input functionality for BusinessIntelligence.ai
Shows how to provide real custom data/case studies and how timed data flows through the pipeline.
"""

import json
import requests
from datetime import datetime, timedelta

def test_custom_input_via_api():
    """Test sending custom data directly to the /analyze endpoint"""

    print("=" * 60)
    print("Testing Custom Data Input via API")
    print("=" * 60)

    # Example custom anomaly data (revenue spike scenario)
    custom_anomaly = {
        "anomaly_id": "rev-spike-2026-Q3-north",
        "metric_name": "revenue",
        "entity": "North Region",
        "direction": "increase",
        "magnitude_pct": 22.3,
        "baseline_value": 3200000,
        "observed_value": 3913600,
        "window_start": "2026-07-01",
        "window_end": "2026-07-31",
        "detected_at": "2026-08-01T08:00:00Z"
    }

    # Example correlation drivers (what caused the anomaly)
    custom_correlation = {
        "anomaly_id": "rev-spike-2026-Q3-north",
        "drivers": [
            {
                "driver_id": "price_increase_product_b",
                "label": "12% price increase on Product B effective July 1",
                "stat_type": "correlation",
                "value": 0.68,
                "rank": 1
            },
            {
                "driver_id": "marketing_campaign_summer",
                "label": "Summer marketing campaign launch June 15",
                "stat_type": "correlation",
                "value": 0.42,
                "rank": 2
            },
            {
                "driver_id": "inventory_improvement",
                "label": "Reduced stockouts from improved supply chain",
                "stat_type": "shap",
                "value": 0.51,
                "rank": 3
            }
        ]
    }

    # Example evidence sources (supporting documentation)
    custom_evidence = {
        "anomaly_id": "rev-spike-2026-Q3-north",
        "sources": [
            {
                "source_id": "pricing_00452",
                "title": "Pricing Strategy Review - June 2026",
                "snippet": "Approved 12% price increase on Product B to improve margin profile, effective July 1, 2026",
                "publisher": "Corporate Pricing Office",
                "date": "2026-06-28",
                "relevance_score": 0.91,
                "rank": 1
            },
            {
                "source_id": "marketing_00887",
                "title": "Summer Campaign Performance Report",
                "snippet": "Q3 summer campaign drove 18% increase in qualified leads in North Region markets",
                "publisher": "Marketing Analytics",
                "date": "2026-07-20",
                "relevance_score": 0.76,
                "rank": 2
            },
            {
                "source_id": "supply_00331",
                "title": "Logistics Performance - July 2026",
                "snippet": "On-time delivery improved to 96.5%, reducing stockout incidents by 34%",
                "publisher": "Supply Chain Operations",
                "date": "2026-07-25",
                "relevance_score": 0.63,
                "rank": 3
            }
        ]
    }

    # Prepare request payload
    payload = {
        "test_case": "custom",
        "backend": "mock",  # Using mock for instant testing
        "anomaly": custom_anomaly,
        "correlation": custom_correlation,
        "evidence": custom_evidence
    }

    print("Sending custom data to /analyze endpoint...")
    print(f"Anomaly: {custom_anomaly['metric_name']} {custom_anomaly['direction']} by {custom_anomaly['magnitude_pct']}%")
    print(f"Entity: {custom_anomaly['entity']}")
    print(f"Time window: {custom_anomaly['window_start']} to {custom_anomaly['window_end']}")
    print()

    try:
        response = requests.post(
            "http://localhost:5000/analyze",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            print("✅ Analysis successful!")
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
            print("See server logs for detailed error information")
            return False

    except Exception as e:
        print("Request failed - check server logs for details")
        return False

def explain_timed_data_flow():
    """Explain how timed data flows through the BusinessIntelligence.ai pipeline"""

    print("\n" + "=" * 60)
    print("How Timed Data Flows Through the Pipeline")
    print("=" * 60)

    explanation = """
The BusinessIntelligence.ai pipeline processes timed data features through 6 specialized tasks:

TASK 1: ANOMALY DETECTION
   • Input: Raw time-series metrics (revenue, units sold, price, etc.)
   • Processing: Statistical anomaly detection (Z-score, Isolation Forest, etc.)
   • Output: AnomalyEvent objects with timestamps, magnitude, direction
   • Timed Features Tracked:
     - Timestamp windows (window_start, window_end)
     - Trend analysis over time
     - Seasonal decomposition components
     - Rate of change metrics

TASK 2: CORRELATION ANALYSIS
   • Input: AnomalyEvents + correlated metric time-series
   • Processing: Correlation analysis (Pearson, Spearman), SHAP values, Granger causality
   • Output: CorrelationResult objects showing driver relationships
   • Timed Features Tracked:
     - Lead/lag relationships between metrics
     - Time-lagged correlations
     - Granger causality p-values over time windows
     - Rolling correlation coefficients

TASK 3: CAUSAL INFERENCE
   • Input: CorrelationResults + domain knowledge
   • Processing: Causal discovery algorithms, counterfactual analysis
   • Output: CausalRelationship objects with confidence scores
   • Timed Features Tracked:
     - Temporal precedence validation
     - Intervention analysis timing
     - Mediating variable timing

TASK 4: EVIDENCE RETRIEVAL
   • Input: CausalRelationships + time-bound queries
   • Processing: Semantic search over timestamped documents
   • Output: RetrievedEvidence objects with relevance scoring
   • Timed Features Tracked:
     - Document publication dates
     - Event timestamp alignment
     - Temporal relevance decay functions
     - Source recency weighting

TASK 5: SYNTHESIS & REASONING
   • Input: All previous task outputs
   • Processing: LLM-based reasoning with structured prompts
   • Output: StoryOutput with hypotheses and recommendations
   • Timed Features Tracked:
     - Temporal consistency checks
     - Timeline reconstruction validation
     - Chronological reasoning chains

TASK 6: ENHANCED ACTIONABLE OUTPUTS (YOUR FIXES)
   • Input: StoryOutput from Task 5
   • Processing: Enhancement layer adding:
     • Structured actions (driver → lever → action → impact)
     • Persona-specific narratives (executive/analyst/operations)
     • KPI semantic contracts
     • Comprehensive telemetry
     • Feedback mechanisms
   • Output: EnhancedStoryOutput with all Round 2 features
   • Timed Features Preserved:
     • All input timestamps carried through
     • Action implementation timelines
     • Monitoring schedule recommendations
     • KPI measurement frequencies

TASK 7: ORCHESTRATION & SCHEMA RECONCILIATION
   • Input: All task outputs
   • Processing: Pipeline coordination, schema validation
   • Output: Final integrated result

KEY POINT: The website interface (what you see at http://localhost:5000) ONLY DISPLAYS RESULTS.
It does NOT perform any analysis. All actual data processing happens in the backend Tasks 1-6,
which you've fixed and enhanced. The website is purely a presentation layer that calls your
enhanced Task 6 backend via the /analyze endpoint.
"""

    # Handle encoding issues on Windows by replacing problematic characters
    try:
        print(explanation)
    except UnicodeEncodeError:
        # Fallback: print line by line and handle encoding errors
        for line in explanation.split('\n'):
            try:
                print(line)
            except UnicodeEncodeError:
                # Replace non-encodable characters
                print(line.encode('cp1252', errors='replace').decode('cp1252'))

def show_how_to_provide_real_data():
    """Show users how to provide their own real data for testing"""

    print("\n" + "=" * 60)
    print("How to Provide Your Own Real Data/Case Studies")
    print("=" * 60)

    guidance = """
You have THREE options to provide real custom data to test the system:

OPTION A: MODIFY TEST CASES (Quickest for Development)
   • Edit: D:\KPI\project\task6\mock_data.py
   • Add your custom case as a function returning (anomaly, correlation, evidence) tuples
   • Example structure:
     def my_custom_case():
         anomaly = { ... }  # Your AnomalyEvent data
         correlation = { ... }  # Your CorrelationResult data
         evidence = { ... }  # Your RetrievedEvidence data
         return anomaly, correlation, evidence
   • Then reference it in app.py TEST_CASES dictionary

OPTION B: WEB INTERFACE CUSTOM INPUT TAB (What we just implemented)
   • Go to: http://localhost:5000
   • Select "Custom Input (Your Data)" from Test Case dropdown
   • Choose input method: "Paste JSON" or "Fill Form"
   • For JSON: Paste properly formatted anomaly/correlation/evidence objects
   • For Form: Fill in the fields and click "Build JSON from Form"
   • Click "Analyze Anomaly" to process with your selected LLM backend

OPTION C: DIRECT API INTEGRATION (For production/custom applications)
   • POST to: http://localhost:5000/analyze
   • JSON payload structure:
     {
       "test_case": "custom",
       "backend": "ollama|mock|grok",
       "model": "llama3:8b",  // optional, backend-specific
       "api_key": "your-key-here",  // required for Grok
       "anomaly": { ... },    // Your AnomalyEvent object
       "correlation": { ... }, // Your CorrelationResult object
       "evidence": { ... }    // Your RetrievedEvidence object
     }
   • See test_custom_input.py for working example

DATA FORMAT REQUIREMENTS:
-----------------------------
ANOMALY OBJECT:
   - anomaly_id: string (unique identifier)
   - metric_name: string (e.g., "revenue", "units_sold", "price")
   - entity: string (e.g., "North Region", "Product X", "Customer Segment A")
   - direction: "increase" or "decrease"
   - magnitude_pct: float (percentage change from baseline)
   - baseline_value: float (expected/normal value)
   - observed_value: float (actual observed value)
   - window_start: string (YYYY-MM-DD format)
   - window_end: string (YYYY-MM-DD format)
   - detected_at: string (ISO datetime format)

CORRELATION OBJECT:
   - anomaly_id: string (matches anomaly.anomaly_id)
   - drivers: array of driver objects, each with:
     - driver_id: string (unique identifier)
     - label: string (human-readable description)
     - stat_type: "correlation" or "shap"
     - value: float (correlation coefficient or SHAP value)
     - rank: integer (1=strongest driver)

EVIDENCE OBJECT:
   - anomaly_id: string (matches anomaly.anomaly_id)
   - sources: array of source objects, each with:
     - source_id: string (unique identifier)
     - title: string (document title)
     - snippet: string (relevant text excerpt)
     - publisher: string (source organization)
     - date: string (YYYY-MM-DD format)
     - relevance_score: float (0.0 to 1.0)
     - rank: integer (1=most relevant)

EXAMPLE USE CASES YOU CAN TEST:
------------------------------
1. REVENUE SPIKE ANALYSIS (like our test above)
   - Anomaly: +18% revenue in North Region
   - Drivers: Price increase, marketing campaign, inventory improvement
   - Evidence: Pricing documents, campaign reports, logistics data

2. COST OVER RUN INVESTIGATION
   - Anomaly: +22% manufacturing costs in Q3
   - Drivers: Raw material prices, overtime hours, supplier delays
   - Evidence: Commodity market data, labor reports, supply chain notices

3. CUSTOMER CHURN INVESTIGATION
   - Anomaly: +8% churn rate in Enterprise segment
   - Drivers: Product bugs, competitor offerings, pricing changes
   - Evidence: Support tickets, competitive analysis, contract renewals

4. WEBSITE TRAFFIC DROP ANALYSIS
   - Anomaly: -15% organic search traffic
   - Drivers: Algorithm update, content gaps, technical issues
   - Evidence: Google Search Console, SEO audits, site performance reports

NEXT STEPS FOR REAL DATA TESTING:
--------------------------------
1. Identify a business anomaly you want to investigate
2. Gather the timed metric data (anomaly)
3. Identify potential correlated drivers
4. Collect supporting evidence documents
5. Format as JSON objects per the structure above
6. Test via web interface (Option B) or API (Option C)
7. Review structured actions, persona narratives, and KPI recommendations
"""

    # Handle encoding issues on Windows by replacing problematic characters
    try:
        print(guidance)
    except UnicodeEncodeError:
        # Fallback: print line by line and handle encoding errors
        for line in guidance.split('\n'):
            try:
                print(line)
            except UnicodeEncodeError:
                # Replace non-encodable characters
                print(line.encode('cp1252', errors='replace').decode('cp1252'))

if __name__ == "__main__":
    # Explain the timed data flow first
    explain_timed_data_flow()

    # Show how to provide real data
    show_how_to_provide_real_data()

    # Test the custom input functionality
    print("\n" + "=" * 60)
    print("Running Custom Input Test")
    print("=" * 60)

    success = test_custom_input_via_api()

    if success:
        print("\nCUSTOM INPUT FUNCTIONALITY VERIFIED")
        print("You can now provide your own real data/case studies!")
    else:
        print("\nCUSTOM INPUT TEST FAILED")
        print("Please check that the web interface is running on localhost:5000")