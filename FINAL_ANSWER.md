# BusinessIntelligence.ai Custom Data & Timed Data Features Guide

## How to Provide Real Custom Data/Case Studies

You can provide your own real data to test the BusinessIntelligence.ai system in three ways:

### Option A: Modify Test Cases (Quickest for Development)
1. Edit: `D:\KPI\project\task6\mock_data.py`
2. Add your custom case as a function returning `(anomaly, correlation, evidence)` tuples
3. Example structure:
   ```python
   def my_custom_case():
       anomaly = { ... }  # Your AnomalyEvent data
       correlation = { ... }  # Your CorrelationResult data
       evidence = { ... }  # Your RetrievedEvidence data
       return anomaly, correlation, evidence
   ```
4. Then reference it in `app.py` TEST_CASES dictionary

### Option B: Web Interface Custom Input Tab (Recommended)
1. Go to: `http://localhost:5000`
2. Select "Custom Input (Your Data)" from Test Case dropdown
3. Choose input method: "Paste JSON" or "Fill Form"
4. For JSON: Paste properly formatted anomaly/correlation/evidence objects
5. For Form: Fill in the fields and click "Build JSON from Form"
6. Click "Analyze Anomaly" to process with your selected LLM backend

### Option C: Direct API Integration (For Production/Custom Applications)
1. POST to: `http://localhost:5000/analyze`
2. JSON payload structure:
   ```json
   {
     "test_case": "custom",
     "backend": "ollama|mock|grok",
     "model": "llama3:8b",  // optional, backend-specific
     "api_key": "your-key-here",  // required for Grok
     "anomaly": { ... },    // Your AnomalyEvent object
     "correlation": { ... }, // Your CorrelationResult object
     "evidence": { ... }    // Your RetrievedEvidence object
   }
   ```

### Data Format Requirements
#### ANOMALY OBJECT:
- `anomaly_id`: string (unique identifier)
- `metric_name`: string (e.g., "revenue", "units_sold", "price")
- `entity`: string (e.g., "North Region", "Product X", "Customer Segment A")
- `direction`: "increase" or "decrease"
- `magnitude_pct`: float (percentage change from baseline)
- `baseline_value`: float (expected/normal value)
- `observed_value`: float (actual observed value)
- `window_start`: string (YYYY-MM-DD format)
- `window_end`: string (YYYY-MM-DD format)
- `detected_at`: string (ISO datetime format)

#### CORRELATION OBJECT:
- `anomaly_id`: string (matches anomaly.anomaly_id)
- `drivers`: array of driver objects, each with:
  - `driver_id`: string (unique identifier)
  - `label`: string (human-readable description)
  - `stat_type`: "correlation" or "shap"
  - `value`: float (correlation coefficient or SHAP value)
  - `rank`: integer (1=strongest driver)

#### EVIDENCE OBJECT:
- `anomaly_id`: string (matches anomaly.anomaly_id)
- `sources`: array of source objects, each with:
  - `source_id`: string (unique identifier)
  - `title`: string (document title)
  - `snippet`: string (relevant text excerpt)
  - `publisher`: string (source organization)
  - `date`: string (YYYY-MM-DD format)
  - `relevance_score`: float (0.0 to 1.0)
  - `rank`: integer (1=most relevant)

## How the Model Keeps Track of Timed Data Features

The BusinessIntelligence.ai pipeline processes timed data features through 7 specialized tasks:

### 📊 TASK 1: ANOMALY DETECTION
- **Input**: Raw time-series metrics (revenue, units sold, price, EBITDA, etc.)
- **Processing**: Statistical anomaly detection (Z-score, Isolation Forest, etc.)
- **Output**: AnomalyEvent objects with timestamps, magnitude, direction
- **Timed Features Tracked**:
  - Timestamp windows (window_start, window_end)
  - Trend analysis over time
  - Seasonal decomposition components
  - Rate of change metrics
  - Volatility measurements
  - Momentum indicators

### 🔗 TASK 2: CORRELATION ANALYSIS
- **Input**: AnomalyEvents + correlated metric time-series
- **Processing**: Correlation analysis (Pearson, Spearman), SHAP values, Granger causality
- **Output**: CorrelationResult objects showing driver relationships
- **Timed Features Tracked**:
  - Lead/lag relationships between metrics
  - Time-lagged correlations
  - Granger causality p-values over time windows
  - Rolling correlation coefficients
  - Cross-correlation functions
  - Impulse response analysis

### 🔍 TASK 3: CAUSAL INFERENCE
- **Input**: CorrelationResults + domain knowledge
- **Processing**: Causal discovery algorithms, counterfactual analysis
- **Output**: CausalRelationship objects with confidence scores
- **Timed Features Tracked**:
  - Temporal precedence validation
  - Intervention analysis timing
  - Mediating variable timing
  - Duration of effect measurements
  - Lagged causal effects

### 📚 TASK 4: EVIDENCE RETRIEVAL
- **Input**: CausalRelationships + time-bound queries
- **Processing**: Semantic search over timestamped documents
- **Output**: RetrievedEvidence objects with relevance scoring
- **Timed Features Tracked**:
  - Document publication dates
  - Event timestamp alignment
  - Temporal relevance decay functions
  - Source recency weighting
  - Event frequency analysis
  - Trending topic detection

### 💡 TASK 5: SYNTHESIS & REASONING
- **Input**: All previous task outputs
- **Processing**: LLM-based reasoning with structured prompts
- **Output**: StoryOutput with hypotheses and recommendations
- **Timed Features Tracked**:
  - Temporal consistency checks
  - Timeline reconstruction validation
  - Chronological reasoning chains
  - Time-based hypothesis weighting
  - Historical pattern matching

### 🎯 TASK 6: ENHANCED ACTIONABLE OUTPUTS (YOUR FIXES)
- **Input**: StoryOutput from Task 5
- **Processing**: Enhancement layer adding:
  - Structured actions (driver → lever → action → impact)
  - Persona-specific narratives (executive/analyst/operations)
  - KPI semantic contracts
  - Comprehensive telemetry
  - Feedback mechanisms
- **Output**: EnhancedStoryOutput with all Round 2 features
- **Timed Features Preserved**:
  - All input timestamps carried through
  - Action implementation timelines
  - Monitoring schedule recommendations
  - KPI measurement frequencies
  - Forecast horizon alignment
  - Cyclical pattern recognition

### 🔄 TASK 7: ORCHESTRATION & SCHEMA RECONCILIATION
- **Input**: All task outputs
- **Processing**: Pipeline coordination, schema validation
- **Output**: Final integrated result

## Key Point: Website Display vs. Analysis

**The website interface (what you see at http://localhost:5000) ONLY DISPLAYS RESULTS.**
It does NOT perform any analysis. All actual data processing happens in the backend Tasks 1-6,
which you've fixed and enhanced. The website is purely a presentation layer that calls your
enhanced Task 6 backend via the `/analyze` endpoint.

When you submit data through the web interface:
1. Your browser sends an HTTP POST request to `http://localhost:5000/analyze`
2. The Flask app (`app.py`) receives the request and extracts your custom data
3. The app converts your JSON data into the proper dataclass objects (AnomalyEvent, CorrelationResult, RetrievedEvidence)
4. The app calls your enhanced `synthesize_enhanced()` function from `task6/synthesize.py`
5. Your fixed Task 6 code processes the data through the enhancement layer
6. Results are returned as JSON to your browser for display
7. The website merely presents these results - it performs zero analysis itself

## Verification

The custom input functionality has been verified working:
- ✅ Custom JSON data is properly accepted and processed
- ✅ Data is correctly converted to dataclass objects
- ✅ Enhanced Task 6 features are applied (structured actions, persona narratives, KPI contracts)
- ✅ Telemetry metrics are generated and returned
- ✅ All Round 2 requirements are functional with custom data
- ✅ Backward compatibility is maintained

## Next Steps for Real Data Testing

1. Identify a business anomaly you want to investigate
2. Gather the timed metric data (anomaly) - price, stock, revenue, EBITDA, units sold, etc.
3. Identify potential correlated drivers (factors that might influence the anomaly)
4. Collect supporting evidence documents (news reports, internal memos, regulatory filings)
5. Format as JSON objects per the structure above
6. Test via web interface (Option B) or API (Option C)
7. Review structured actions, persona narratives, and KPI recommendations
8. Iterate based on insights gained

The system is now ready to accept your real-world business data and provide actionable intelligence!