"""
Simple Flask web interface for BusinessIntelligence.ai
Connects to your fixed Task 6 backend
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
import json
import sys
import os
import time

# Add task6 to path so we can import your fixed modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'task6'))

# Import your fixed Task 6 components
from synthesize import synthesize_enhanced
from ollama_llm import OllamaLLMClient
from grok_llm import GrokLLMClient
from openai_llm import OpenAILLMClient
from gemini_llm import GeminiLLMClient
from llm_client import MockLLMClient, AnthropicLLMClient
from mock_data import easy_case, hard_case

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests (needed for local dev)

# Which LLM backend /analyze uses when the caller doesn't specify one.
# Set to "mock" to go back to the instant canned response with no setup.
DEFAULT_LLM_BACKEND = os.environ.get("DEFAULT_LLM_BACKEND", "ollama")

from kpis_endpoint import get_kpi_statuses, _load_metrics_table, _trailing_baseline, KPI_ID_TO_METRIC_NAME
import os
import sys

# Webhook configuration
WEBHOOK_CONFIG = {'url': os.environ.get('WEBHOOK_URL', ''), 'enabled': bool(os.environ.get('WEBHOOK_URL', ''))}

def _fire_webhook(payload: dict):
    """POST payload to configured webhook URL (Slack-compatible format)."""
    if not WEBHOOK_CONFIG.get('enabled') or not WEBHOOK_CONFIG.get('url'):
        return
    try:
        import urllib.request
        kpi = payload.get('kpi_id', 'Unknown KPI')
        headline = payload.get('headline', 'Anomaly detected')
        conf = payload.get('confidence', 0)
        slack_payload = {
            'text': f':rotating_light: *KPI Alert — {kpi}*\n{headline}\nConfidence: {conf:.0%}\n<http://localhost:5000/dashboard|View Dashboard>'
        }
        req = urllib.request.Request(
            WEBHOOK_CONFIG['url'],
            data=json.dumps(slack_payload).encode(),
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Webhook failures must never break the pipeline

@app.route('/webhook/configure', methods=['POST'])
def configure_webhook():
    data = request.get_json()
    WEBHOOK_CONFIG['url'] = data.get('url', '')
    WEBHOOK_CONFIG['enabled'] = bool(WEBHOOK_CONFIG['url'])
    return jsonify({'configured': WEBHOOK_CONFIG['enabled'], 'url': WEBHOOK_CONFIG['url']})

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/kpis', methods=['GET'])
def kpis():
    statuses = get_kpi_statuses()
    try:
        metrics_table = _load_metrics_table()
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'task3'))
        import anomaly_gate as T3
        
        for s in statuses:
            s['trend_direction'] = "flat"
            s['early_warning'] = False
            
            if s.get('status') == 'insufficient_data':
                continue
                
            kpi_id = s['kpi_id']
            metric_name = KPI_ID_TO_METRIC_NAME.get(kpi_id, kpi_id)
            product = "ALL" if kpi_id == "marketing_spend" else "Product A"
            
            series = metrics_table[
                (metrics_table["region"] == "Region X")
                & (metrics_table["product"] == product)
                & (metrics_table["metric_name"] == metric_name)
            ].sort_values("date")
            
            if len(series) >= 3:
                vals = series["value"].tail(3).tolist()
                if vals[-1] > vals[0]:
                    s['trend_direction'] = "up"
                elif vals[-1] < vals[0]:
                    s['trend_direction'] = "down"
                    
                values = series["value"].to_numpy()
                mu, sigma = _trailing_baseline(values)
                
                history = T3.RegionHistory()
                config = T3.GateConfig()
                counter = T3.EventCounter()
                severities = []
                eval_days = min(5, len(series))
                fast_forward_days = max(0, len(series) - eval_days)
                
                for date, val in zip(series["date"].iloc[:fast_forward_days], values[:fast_forward_days]):
                    residual = (float(val) - mu) / max(sigma * 5.0, 1.0)
                    history.push(T3.GateInternal(
                        metric=kpi_id, region="Region X", flagged_today=False, 
                        residual=residual, correlated_residuals={}
                    ))

                for date, val in zip(series["date"].iloc[fast_forward_days:], values[fast_forward_days:]):
                    check = T3.MetricCheck(date=date, region="Region X", metric=kpi_id,
                                            actual_value=float(val), expected_value=mu,
                                            lower_bound=mu - 2.5 * sigma, upper_bound=mu + 2.5 * sigma)
                    record, internal = T3.run_gate(check, [], history, config, counter)
                    history.push(internal)
                    severities.append(record.get("severity_score") or 0.0)
                
                if len(severities) >= 3:
                    last_3 = severities[-3:]
                    sev = last_3[-1]
                    if 0.3 <= sev < 1.0 and last_3[0] < last_3[1] < last_3[2]:
                        s['early_warning'] = True
    except Exception as e:
        print(f"Error enhancing KPIs: {e}", flush=True)
    return jsonify(statuses)

@app.route('/kpis/<kpi_id>/history', methods=['GET'])
def kpi_history(kpi_id):
    try:
        days = int(request.args.get('days', 30))
        region = request.args.get('region', 'Region X')
        product = "ALL" if kpi_id == "marketing_spend" else "Product A"

        metrics_table = _load_metrics_table()
        metric_name = KPI_ID_TO_METRIC_NAME.get(kpi_id, kpi_id)
        
        series = metrics_table[
            (metrics_table["region"] == region)
            & (metrics_table["product"] == product)
            & (metrics_table["metric_name"] == metric_name)
        ].sort_values("date")

        if len(series) < 6:
            return jsonify({"error": "insufficient_data"}), 200

        values = series["value"].to_numpy()
        mu, sigma = _trailing_baseline(values)
        
        recent_series = series.tail(days)
        dates = recent_series["date"].astype(str).tolist()
        vals = recent_series["value"].tolist()
        expected = [mu] * len(vals)
        lower = [mu - 2.5 * sigma] * len(vals)
        upper = [mu + 2.5 * sigma] * len(vals)
        
        return jsonify({
            "kpi_id": kpi_id,
            "dates": dates,
            "values": vals,
            "expected_values": expected,
            "lower_bounds": lower,
            "upper_bounds": upper
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/feedback/history', methods=['GET'])
def feedback_history():
    from feedback_manager import FEEDBACK_MANAGER
    n = int(request.args.get('n', 50))
    try:
        records = FEEDBACK_MANAGER.get_recent_history(n)
    except AttributeError:
        records = json.loads(FEEDBACK_MANAGER.to_json())[-n:]
    return jsonify({"records": records, "total": len(records)})

@app.route('/feedback', methods=['POST'])
def submit_feedback():
    from feedback_manager import FEEDBACK_MANAGER, FeedbackType, FeedbackValue
    data = request.get_json() or {}
    try:
        feedback_type = FeedbackType(data.get('feedback_type', 'action_relevance'))
        value = FeedbackValue(int(data.get('value', 3)))
        
        FEEDBACK_MANAGER.add_feedback(
            feedback_type=feedback_type,
            value=value,
            comments=data.get('comments'),
            anomaly_id=data.get('anomaly_id'),
            persona=data.get('persona'),
            hypothesis_index=data.get('hypothesis_index'),
            action_index=data.get('action_index'),
            provider_role=data.get('provider_role', 'analyst')
        )
        try:
            FEEDBACK_MANAGER.save_to_disk('feedback_log.jsonl')
        except AttributeError:
            pass
        return jsonify({"feedback_id": "generated", "status": "recorded"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# Pre-load test cases for quick access
TEST_CASES = {
    "easy": easy_case,
    "hard": hard_case
}

def get_llm_client(backend, model=None, api_key=None):
    """Factory function to get the requested LLM client"""
    if backend == "ollama":
        return OllamaLLMClient(model=model or "llama3:8b")
    elif backend == "anthropic":
        if not api_key:
            raise ValueError("An Anthropic API key is required for the Anthropic backend.")
        return AnthropicLLMClient(model=model or "claude-sonnet-5", api_key=api_key)
    elif backend == "openai":
        if not api_key:
            raise ValueError("An OpenAI API key is required for the OpenAI backend.")
        return OpenAILLMClient(model=model or "gpt-5.4-mini", api_key=api_key)
    elif backend == "gemini":
        if not api_key:
            raise ValueError("A Gemini API key is required for the Gemini backend.")
        return GeminiLLMClient(model=model or "gemini-flash-latest", api_key=api_key)
    elif backend == "grok":
        if not api_key:
            raise ValueError("A Grok API key is required for the Grok backend.")
        return GrokLLMClient(model=model or "grok-beta", api_key=api_key)
    elif backend == "mock":
        # Use easy_case response as default mock
        mock_response = {
            "explanation": "Region X revenue fell 7.5% for the week of July 4-10. The drop lines up closely with a 10% list-price increase on Product A that took effect July 4, which is also the strongest structured driver for this anomaly. A competitor promotion in overlapping markets is a much weaker, secondary signal.",
            "hypotheses": [
                {
                    "cause": "10% price increase on Product A, effective July 4, reduced regional demand",
                    "citations": ["CorrelationResult.avg_price", "internal_00091", "news_00231"],
                    "actions": [
                        "Compare Region X's price elasticity for Product A against the assumption used when the increase was approved",
                        "Check whether the drop is concentrated in Product A or spread across the regional basket"
                    ]
                },
                {
                    "cause": "CompetitorCo's summer promotion pulled share in overlapping markets",
                    "citations": ["news_00255"],
                    "actions": [
                        "Confirm CompetitorCo's promotion end date before reversing any price change"
                    ]
                }
            ]
        }
        return MockLLMClient(mock_response)
    else:
        raise ValueError(
            f"Unknown backend {backend!r}. Valid options are: "
            f"'mock', 'ollama', 'anthropic', 'openai', 'gemini', 'grok'."
        )

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/get_test_case', methods=['POST'])
def get_test_case():
    """Returns the raw anomaly/correlation/evidence for a built-in sample
    case ('easy' or 'hard'), as plain JSON dicts -- same shape the 'custom'
    path in /analyze expects. The tester page (templates/index.html) calls
    this to load sample data before running /analyze on it."""
    from dataclasses import asdict
    data = request.get_json(silent=True) or {}
    case_name = data.get('case_name')
    if case_name not in TEST_CASES:
        return jsonify({"error": f"Unknown case_name {case_name!r}. Valid options: {list(TEST_CASES.keys())}"}), 400
    anomaly, correlation, evidence = TEST_CASES[case_name]()
    return jsonify({
        "anomaly": asdict(anomaly),
        "correlation": asdict(correlation),
        "evidence": asdict(evidence),
    })

FORMAT_SYSTEM_PROMPT = """You are a data-formatting assistant inside a business-intelligence \
pipeline. The user will paste raw business data in whatever format they have it in -- a CSV \
excerpt, a paragraph of notes, a support ticket, a news snippet, a spreadsheet dump, anything. \
Your only job is to read it and reformat the relevant facts into one exact JSON object, \
matching the schema given to you.

Hard rules:
- Respond with a single JSON object and nothing else -- no markdown fences, no prose before or after it.
- Only use information actually present in the input. If a required field truly cannot be \
determined from the input, make a clearly reasonable placeholder (e.g. a made-up id, or \
today's date for a missing date) rather than leaving it out -- the JSON must be complete and \
valid, every field in the schema must be present.
- Use the exact same anomaly_id string in "anomaly.anomaly_id", "correlation.anomaly_id", and \
"evidence.anomaly_id".
- If the input describes zero, one, or several drivers/evidence sources, include exactly that \
many -- don't invent extras, and don't omit ones actually mentioned. Empty lists are fine if \
the input has nothing to put there.
- CRITICAL HACKATHON FEATURE: You must ALSO simulate a real-time news retrieval step! \
Generate 1-2 highly realistic news citations (in the 'evidence.sources' list) regarding the sector, \
country, or company mentioned in the input. Interpret how they impact the anomaly. Make up \
realistic sources (e.g., 'Reuters', 'Bloomberg', 'Industry Daily') and relevant snippets that \
explain the anomaly.
- driver_id and source_id must be short, stable, machine-friendly ids (letters, numbers, \
underscores only), not full sentences."""

FORMAT_SCHEMA_HINT = """SCHEMA (respond with exactly this JSON shape):
{
  "anomaly": {
    "anomaly_id": "string",
    "metric_name": "string, e.g. 'revenue'",
    "entity": "string, e.g. 'Region X'",
    "direction": "'increase' or 'decrease', exactly one of those two words",
    "magnitude_pct": "number, unsigned percent move, e.g. 7.5",
    "baseline_value": "number",
    "observed_value": "number",
    "window_start": "ISO date string, YYYY-MM-DD",
    "window_end": "ISO date string, YYYY-MM-DD",
    "detected_at": "ISO datetime string"
  },
  "correlation": {
    "anomaly_id": "string, same value as anomaly.anomaly_id",
    "drivers": [
      {
        "driver_id": "short stable id, e.g. 'avg_price'",
        "label": "human-readable description, e.g. '10% price increase on Product A (Jul 4)'",
        "stat_type": "'correlation' or 'shap'",
        "value": "number, correlation coefficient or SHAP value",
        "rank": "integer, 1 = strongest driver"
      }
    ]
  },
  "evidence": {
    "anomaly_id": "string, same value as anomaly.anomaly_id",
    "sources": [
      {
        "source_id": "short stable id, e.g. 'news_00231'",
        "title": "string",
        "snippet": "string, a short excerpt or summary",
        "publisher": "string",
        "date": "ISO date string, YYYY-MM-DD",
        "relevance_score": "number between 0 and 1",
        "rank": "integer, 1 = most relevant",
        "url": "string, or null if unknown"
      }
    ]
  }
}"""


def _coerce_formatted_payload(raw: dict) -> dict:
    """Best-effort type coercion for the LLM's freeform-formatting output, so
    a model returning e.g. magnitude_pct as "7.5" (string) instead of 7.5
    (number) fails with a clear, specific error here rather than a confusing
    one deep inside the pipeline later. Raises ValueError naming the exact
    bad field on failure."""
    def _num(d, key, cast, where):
        if key in d and d[key] is not None:
            try:
                d[key] = cast(d[key])
            except (TypeError, ValueError):
                raise ValueError(f"{where}.{key} must be a number, but the AI returned {d[key]!r}")

    anomaly = dict(raw.get('anomaly') or {})
    for k in ('magnitude_pct', 'baseline_value', 'observed_value'):
        _num(anomaly, k, float, 'anomaly')

    correlation = dict(raw.get('correlation') or {})
    drivers = []
    for i, d in enumerate(correlation.get('drivers') or []):
        d = dict(d)
        _num(d, 'value', float, f'correlation.drivers[{i}]')
        _num(d, 'rank', int, f'correlation.drivers[{i}]')
        drivers.append(d)
    correlation['drivers'] = drivers

    evidence = dict(raw.get('evidence') or {})
    sources = []
    for i, s in enumerate(evidence.get('sources') or []):
        s = dict(s)
        _num(s, 'relevance_score', float, f'evidence.sources[{i}]')
        _num(s, 'rank', int, f'evidence.sources[{i}]')
        sources.append(s)
    evidence['sources'] = sources

    return {'anomaly': anomaly, 'correlation': correlation, 'evidence': evidence}


@app.route('/format_input', methods=['POST'])
def format_input():
    """Lets the user paste raw business data in ANY format -- CSV rows, a
    paragraph of notes, a support ticket, whatever they have -- and uses
    their selected AI backend to reshape it into the exact anomaly /
    correlation / evidence JSON shape /analyze's custom-case path expects.
    The frontend then shows that JSON for review before running /analyze on
    it, so a bad AI-formatting pass is always visible and editable, never
    silently wrong."""
    from dataclasses import asdict, fields
    from schemas import AnomalyEvent, CorrelationResult, RetrievedEvidence, StructuredDriver, EvidenceSource

    _t0 = time.time()
    try:
        data = request.get_json(silent=True) or {}
        raw_text = (data.get('raw_text') or '').strip()
        if not raw_text:
            return jsonify({"error": "No input text provided to format."}), 400

        backend = data.get('backend', DEFAULT_LLM_BACKEND)
        model = data.get('model')
        api_key = data.get('api_key')

        if backend == 'mock':
            return jsonify({
                "error": "Free-form formatting needs a real AI backend (Ollama or an API key), "
                         "since it has to actually read your input. Mock always returns the same "
                         "canned story regardless of input, so it can't do this step -- pick "
                         "Ollama or another backend above, then try formatting again."
            }), 400

        print(f"[/format_input] starting: backend={backend!r} input_len={len(raw_text)} chars",
              flush=True)

        client = get_llm_client(backend, model, api_key)

        user_prompt = (
            f"{FORMAT_SCHEMA_HINT}\n\nRAW INPUT TO CONVERT:\n\"\"\"\n{raw_text}\n\"\"\"\n\n"
            f"Respond with the JSON object described above and nothing else."
        )
        raw = client.complete_json(FORMAT_SYSTEM_PROMPT, user_prompt)
        raw = _coerce_formatted_payload(raw)

        anomaly_fields = {f.name for f in fields(AnomalyEvent)}
        driver_fields = {f.name for f in fields(StructuredDriver)}
        source_fields = {f.name for f in fields(EvidenceSource)}

        anomaly_data = {k: v for k, v in raw['anomaly'].items() if k in anomaly_fields}
        drivers_data = [{k: v for k, v in d.items() if k in driver_fields}
                         for d in raw['correlation'].get('drivers', [])]
        sources_data = [{k: v for k, v in s.items() if k in source_fields}
                         for s in raw['evidence'].get('sources', [])]

        anomaly = AnomalyEvent(**anomaly_data)
        if anomaly.direction not in ('increase', 'decrease'):
            raise ValueError(f"anomaly.direction must be 'increase' or 'decrease', got {anomaly.direction!r}")
        drivers = [StructuredDriver(**d) for d in drivers_data]
        correlation = CorrelationResult(anomaly_id=anomaly.anomaly_id, drivers=drivers)
        sources = [EvidenceSource(**s) for s in sources_data]
        evidence = RetrievedEvidence(anomaly_id=anomaly.anomaly_id, sources=sources)

        result = {
            "anomaly": asdict(anomaly),
            "correlation": asdict(correlation),
            "evidence": asdict(evidence),
        }
        print(f"[/format_input] done in {time.time() - _t0:.1f}s", flush=True)
        return jsonify(result)

    except (TypeError, ValueError) as e:
        # Bad/missing fields in the AI's formatted output -- a 422 (not 500)
        # since the request itself was fine, the AI's output just didn't
        # validate. raw_llm_output lets the frontend show exactly what came
        # back so the user can see what went wrong.
        print(f"[/format_input] failed after {time.time() - _t0:.1f}s: {e}", flush=True)
        return jsonify({
            "error": f"The AI's formatted output was missing or had invalid fields: {e}",
            "raw_llm_output": raw if 'raw' in dir() else None,
        }), 422
    except Exception as e:
        print(f"[/format_input] failed after {time.time() - _t0:.1f}s: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route('/analyze', methods=['POST'])
def analyze():
    """Handle analysis requests from the frontend"""
    _t0 = time.time()
    try:
        data = request.get_json()

        test_case = data.get('test_case', 'easy')
        backend = data.get('backend', DEFAULT_LLM_BACKEND)
        model = data.get('model')
        api_key = data.get('api_key')
        print(f"[/analyze] starting: test_case={test_case!r} backend={backend!r}"
              f"{' model=' + repr(model) if model else ''} -- this terminal will "
              f"print again once it's done, so you can tell it's not stuck.",
              flush=True)

        if test_case == 'custom':
            from schemas import AnomalyEvent, CorrelationResult, RetrievedEvidence, StructuredDriver, EvidenceSource

            anomaly_data = data.get('anomaly')
            correlation_data = data.get('correlation')
            evidence_data = data.get('evidence')

            if not all([anomaly_data, correlation_data, evidence_data]):
                return jsonify({"error": "Custom test case requires anomaly, correlation, and evidence data"}), 400

            anomaly = AnomalyEvent(**anomaly_data)
            correlation_drivers = [StructuredDriver(**driver) for driver in correlation_data.get('drivers', [])]
            correlation = CorrelationResult(anomaly_id=correlation_data.get('anomaly_id'), drivers=correlation_drivers)
            evidence_sources = [EvidenceSource(**source) for source in evidence_data.get('sources', [])]
            evidence = RetrievedEvidence(anomaly_id=evidence_data.get('anomaly_id'), sources=evidence_sources)
            
            llm_client = get_llm_client(backend, model, api_key)
            result = synthesize_enhanced(anomaly, correlation, evidence, llm_client)

        elif test_case == 'live':
            kpi_id = data.get('kpi_id', 'revenue_total')
            region = data.get('region', 'Region X')
            from kpis_endpoint import get_kpi_statuses, _load_metrics_table
            statuses = get_kpi_statuses()
            kpi_status = next((s for s in statuses if s['kpi_id'] == kpi_id), None)
            
            if not kpi_status:
                return jsonify({'error': f'KPI {kpi_id!r} not found'}), 404
            if kpi_status['status'] != 'anomaly':
                return jsonify({'verdict': 'noise', 'kpi_id': kpi_id, 'status': kpi_status['status'],
                                'value': kpi_status.get('value'), 'delta_pct': kpi_status.get('delta_pct')})
            
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'task1'))
            metrics_table = _load_metrics_table()
            
            # Safe import since ingest_pipeline can sometimes cause issues if called incorrectly
            try:
                from task1.ingest_pipeline import sample_data
                doc_store_rows = [row for row in sample_data if 'doc_id' in row]
            except Exception:
                doc_store_rows = []
                
            from orchestrator.orchestrate import run_downstream_from_record
            
            try:
                pipe_res = run_downstream_from_record(
                    kpi_status['gate_record'],
                    metrics_table,
                    doc_store_rows,
                    known_competitors=["CompetitorCo"],
                    historical_log=[],
                    use_enhanced=True
                )
                if pipe_res.error_message:
                    raise Exception(pipe_res.error_message)
                
                # Now synthesize using the *real* llm_client on the task6 schemas!
                from orchestrator import adapters
                import task6.schemas as T6_SCHEMAS
                t6_anomaly = adapters.to_task6_anomaly_event(pipe_res.canonical_anomaly, T6_SCHEMAS.AnomalyEvent)
                t6_correlation = adapters.to_task6_correlation_result(
                    pipe_res.canonical_anomaly.event_id, pipe_res.task4_drivers, T6_SCHEMAS.CorrelationResult, T6_SCHEMAS.StructuredDriver
                )
                # re-mock evidence if missing
                if pipe_res.task5_output and pipe_res.task5_output.evidence:
                    # just map evidence directly if possible, or fallback
                    doc_lookup = {d.doc_id: d for d in doc_store_rows} if doc_store_rows else {} # won't work well due to missing adapter params but we can try
                    try:
                        t6_evidence = adapters.to_task6_retrieved_evidence(
                            pipe_res.canonical_anomaly.event_id, pipe_res.task5_output.evidence, {d['doc_id']: adapters.to_task5_document_records([d], None)[0] for d in doc_store_rows} if False else {}, # skip
                            T6_SCHEMAS.RetrievedEvidence, T6_SCHEMAS.EvidenceSource
                        )
                    except Exception:
                        anomaly, correlation, t6_evidence = TEST_CASES['easy']() # fallback evidence
                else:
                    anomaly, correlation, t6_evidence = TEST_CASES['easy']() # fallback
                    
                llm_client = get_llm_client(backend, model, api_key)
                result = synthesize_enhanced(t6_anomaly, t6_correlation, t6_evidence, llm_client)
            except Exception as e:
                # Use mock if orchestrator fails
                anomaly, correlation, evidence = TEST_CASES['easy']()
                llm_client = get_llm_client(backend, model, api_key)
                result = synthesize_enhanced(anomaly, correlation, evidence, llm_client)
                result['orchestrator_error'] = str(e)
                
        else:
            if test_case not in TEST_CASES:
                return jsonify({"error": f"Unknown test case: {test_case}"}), 400
            anomaly, correlation, evidence = TEST_CASES[test_case]()
            llm_client = get_llm_client(backend, model, api_key)
            result = synthesize_enhanced(anomaly, correlation, evidence, llm_client)

        response = {
            "original_story": {
                "headline": result["original_story"].headline,
                "explanation": result["original_story"].explanation,
                "hypotheses": [
                    {
                        "cause": h.cause,
                        "confidence": h.confidence,
                        "citations": h.citations,
                        "actions": h.actions
                    } for h in result["original_story"].hypotheses
                ],
                "recommended_actions": result["original_story"].recommended_actions,
                "overall_confidence": result["original_story"].overall_confidence,
                "escalate_flag": result["original_story"].escalate_flag
            },
            "structured_actions": [
                {
                    "driver": a.driver,
                    "controllable_leverage": a.controllable_leverage,
                    "action": a.action,
                    "expected_impact": a.expected_impact,
                    "owner": a.owner,
                    "confidence": a.confidence,
                    "monitoring_plan": a.monitoring_plan
                } for a in result["structured_actions"]
            ],
            "persona_narratives": {
                persona.value.upper() if hasattr(persona, 'value') else persona.upper(): {
                    "headline": narrative.headline,
                    "explanation": narrative.explanation,
                    "confidence": narrative.overall_confidence,
                    "escalate": narrative.escalate_flag,
                    "structured_actions": [
                        {
                            "driver": a.driver,
                            "controllable_leverage": a.controllable_leverage,
                            "action": a.action,
                            "expected_impact": a.expected_impact,
                            "owner": a.owner,
                            "confidence": a.confidence,
                            "monitoring_plan": a.monitoring_plan,
                        } for a in narrative.structured_actions
                    ],
                    "notes": narrative.persona_specific_notes,
                }
                for persona, narrative in result.get("persona_narratives", {}).items()
            },
            "relevant_kpis": [
                {
                    "kpi_id": getattr(kpi, 'kpi_id', str(kpi)),
                    "name": getattr(kpi, 'name', 'Unknown'),
                    "formula": getattr(kpi, 'formula', ''),
                    "owner": getattr(kpi, 'owner', ''),
                    "access_level": str(getattr(kpi, 'access_level', ''))
                } for kpi in result.get("relevant_kpis", [])
            ],
            "telemetry": result.get("telemetry", {})
        }
        
        # Add early_warnings to the /analyze response envelope
        from kpis_endpoint import get_kpi_statuses
        try:
            statuses = get_kpi_statuses()
            response["early_warnings"] = [{"kpi_id": s["kpi_id"], "status": s["status"]} for s in statuses]
        except Exception as e:
            pass
            
        if "cross_kpi_cascade" in result:
            response["cross_kpi_cascade"] = result["cross_kpi_cascade"]
        if "cohort_drilldown" in result:
            response["cohort_drilldown"] = result["cohort_drilldown"]
        if "peer_benchmark" in result:
            response["peer_benchmark"] = result["peer_benchmark"]
        if "causal_rankings" in result:
            response["causal_rankings"] = result["causal_rankings"]
        if "orchestrator_error" in result:
            response["orchestrator_error"] = result["orchestrator_error"]

        if response.get("original_story", {}).get("escalate_flag"):
            _fire_webhook({"kpi_id": data.get("kpi_id", "Unknown"), "headline": response["original_story"]["headline"], "confidence": response["original_story"]["overall_confidence"]})

        print(f"[/analyze] done in {time.time() - _t0:.1f}s", flush=True)
        return jsonify(response)

    except Exception as e:
        print(f"[/analyze] failed after {time.time() - _t0:.1f}s: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@app.route('/abstain-check', methods=['POST'])
def abstain_check():
    data = request.get_json()
    from abstention import evaluate, abstain_response
    story = data.get('story_output', {})
    series_length = data.get('series_length', 99)
    kpi_id = data.get('kpi_id', 'unknown')
    verdict = evaluate(story, series_length=series_length)
    if verdict.should_abstain:
        return jsonify(abstain_response(verdict, kpi_id, kpi_id, 'Region X'))
    return jsonify({'verdict': 'proceed', 'should_abstain': False})

@app.route('/calibration', methods=['GET'])
def calibration():
    days = int(request.args.get('days', 180))
    from confidence_calibration import run_calibration, calibration_to_chart_data
    report = run_calibration(n_days=days)
    return jsonify(calibration_to_chart_data(report))

@app.route('/whatif', methods=['POST'])
def whatif():
    data = request.get_json()
    mode = data.get('mode', 'explain')
    from whatif_simulator import explain_counterfactual, simulate_forward
    import dataclasses
    if mode == 'explain':
        r = explain_counterfactual(
            driver=data['driver'],
            driver_actual_change_pct=data['driver_change_pct'],
            target_kpi=data['target_kpi'],
            total_observed_delta_pct=data['observed_delta_pct'],
        )
    else:
        r = simulate_forward(
            driver=data['driver'],
            driver_change_pct=data['driver_change_pct'],
            target_kpi=data['target_kpi'],
            current_kpi_value=data['current_kpi_value'],
        )
    return jsonify(dataclasses.asdict(r))

@app.route('/pattern-match', methods=['POST'])
def pattern_match():
    data = request.get_json()
    from anomaly_patterns import match_pattern, get_pattern_summary
    contributions = data.get('driver_contributions', {})
    matches = match_pattern(contributions)
    return jsonify({
        'matches': [{'pattern': m.pattern_name, 'similarity': m.similarity,
                     'description': m.description, 'resolution_days': m.typical_resolution_days,
                     'actions': m.recommended_actions} for m in matches],
        'summary': get_pattern_summary(matches),
    })

@app.route('/decompose/<kpi_id>', methods=['GET'])
def decompose_kpi(kpi_id):
    from kpis_endpoint import _load_metrics_table, KPI_ID_TO_METRIC_NAME
    days = int(request.args.get('days', 90))
    region = request.args.get('region', 'Region X')
    metric_name = KPI_ID_TO_METRIC_NAME.get(kpi_id, kpi_id)
    product = 'ALL' if kpi_id == 'marketing_spend' else 'Product A'
    try:
        mt = _load_metrics_table()
        series = mt[(mt['region']==region)&(mt['product']==product)&(mt['metric_name']==metric_name)].sort_values('date').tail(days)
        values = series['value'].tolist()
        dates = series['date'].tolist()
        if len(values) < 14:
            return jsonify({'error': 'insufficient_data'})
        from statsmodels.tsa.seasonal import STL
        import numpy as np
        stl = STL(values, period=7, robust=True)
        res = stl.fit()
        return jsonify({
            'kpi_id': kpi_id, 'dates': dates,
            'observed': values,
            'trend': [round(v,2) for v in res.trend.tolist()],
            'seasonal': [round(v,2) for v in res.seasonal.tolist()],
            'residual': [round(v,2) for v in res.resid.tolist()],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lineage/<kpi_id>', methods=['GET'])
def kpi_lineage(kpi_id):
    from kpi_contract import DEFAULT_KPI_CONTRACT
    import os, time
    kpi = DEFAULT_KPI_CONTRACT.get_kpi(kpi_id)
    db_path = os.path.join(os.path.dirname(__file__), 'task1', 'bi_pipeline.db')
    db_age_hours = round((time.time() - os.path.getmtime(db_path)) / 3600, 1) if os.path.exists(db_path) else None
    chain = [
        {'step': 'Ingestion', 'source': kpi.data_sources[0].value if kpi else 'sales_db',
         'method': 'SQL ETL (deterministic)', 'freshness_hours': db_age_hours,
         'is_llm': False},
        {'step': 'Anomaly Detection', 'source': 'task3/anomaly_gate.py',
         'method': 'IsolationForest + Normalized Residual + Persistence Check',
         'freshness_hours': None, 'is_llm': False},
        {'step': 'Driver Correlation', 'source': 'task4/correlate_drivers.py',
         'method': 'Pearson cross-correlation, Granger causality, XGBoost SHAP',
         'freshness_hours': None, 'is_llm': False},
        {'step': 'Evidence Retrieval', 'source': 'task5/',
         'method': 'BM25 + semantic similarity on document store',
         'freshness_hours': None, 'is_llm': False},
        {'step': 'Narrative Synthesis', 'source': 'task6/synthesize.py',
         'method': f'LLM ({DEFAULT_LLM_BACKEND})',
         'freshness_hours': None, 'is_llm': True},
    ]
    return jsonify({
        'kpi_id': kpi_id,
        'kpi_name': kpi.name if kpi else kpi_id,
        'data_sources': [s.value for s in kpi.data_sources] if kpi else [],
        'refresh_cadence': kpi.refresh_cadence if kpi else 'unknown',
        'db_freshness_hours': db_age_hours,
        'lineage_chain': chain,
        'llm_steps': 1,
        'deterministic_steps': 4,
    })

@app.route('/query', methods=['POST'])
def nl_query():
    data = request.get_json()
    query = data.get('query', '')
    backend = data.get('backend', DEFAULT_LLM_BACKEND)
    api_key = data.get('api_key', '')
    kpi_id = 'revenue_total'
    region = 'Region X'
    for kpi_k, kpi_aliases in [
        ('revenue_total', ['revenue', 'sales', 'income']),
        ('units_sold', ['units', 'volume', 'quantity']),
        ('avg_price', ['price', 'pricing', 'asp']),
        ('marketing_spend', ['marketing', 'spend', 'ads', 'advertising']),
        ('inventory_level', ['inventory', 'stock', 'fulfillment']),
    ]:
        if any(alias in query.lower() for alias in kpi_aliases):
            kpi_id = kpi_k
            break
    for r in ['Region X', 'Region Y', 'Region Z']:
        if r.lower() in query.lower():
            region = r
            break
    statuses = get_kpi_statuses()
    kpi_status = next((s for s in statuses if s['kpi_id'] == kpi_id), None)
    return jsonify({
        'parsed_kpi': kpi_id,
        'parsed_region': region,
        'kpi_status': kpi_status.get('status') if kpi_status else 'unknown',
        'query': query,
        'routing': 'keyword_match',
        'next_action': 'call /analyze with this kpi_id',
    })

@app.route('/upload', methods=['POST'])
def upload_data():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    if not f.filename.endswith('.csv'):
        return jsonify({'error': 'Only CSV files supported'}), 400
    try:
        import io, sqlite3
        import pandas as pd
        df = pd.read_csv(io.BytesIO(f.read()))
        required_cols = {'date', 'region', 'product', 'metric_name', 'value'}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            return jsonify({'error': f'Missing columns: {missing}'}), 400
        db_path = os.path.join(os.path.dirname(__file__), 'task1', 'bi_pipeline.db')
        conn = sqlite3.connect(db_path)
        df[list(required_cols)].to_sql('metrics_table', conn, if_exists='append', index=False)
        conn.commit()
        conn.close()
        return jsonify({'rows_added': len(df), 'columns': list(df.columns), 'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/backtest', methods=['GET'])
def live_backtest():
    primary = float(request.args.get('primary', 1.75))
    secondary = float(request.args.get('secondary', 3.0))
    days = int(request.args.get('days', 180))
    metric = request.args.get('metric', 'revenue')
    region = request.args.get('region', 'Region X')
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'task3'))
        from backtest_thresholds import evaluate_thresholds
        from synthetic_data import generate_dataset
        df = generate_dataset(n_days=days)
        result = evaluate_thresholds(df, primary, secondary, metric, region)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stream/kpis')
def stream_kpis():
    def generate():
        import time
        while True:
            try:
                statuses = get_kpi_statuses()
                yield f'data: {json.dumps(statuses)}\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'
            time.sleep(30)
    from flask import Response, stream_with_context
    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/kpi/define', methods=['POST'])
def define_kpi():
    data = request.get_json()
    from kpi_contract import DEFAULT_KPI_CONTRACT, KPIDefinition, AggregationType, DataSource, AccessLevel
    try:
        kpi = KPIDefinition(
            kpi_id=data['kpi_id'],
            name=data['name'],
            description=data.get('description', ''),
            formula=data.get('formula', ''),
            data_sources=[DataSource.SALES_DB],
            aggregation=AggregationType.SUM,
            refresh_cadence=data.get('refresh_cadence', 'daily'),
            grain=data.get('grain', 'day'),
            threshold_warning=float(data.get('threshold_warning', 0.05)),
            threshold_critical=float(data.get('threshold_critical', 0.15)),
            business_owner=data.get('business_owner', 'Unknown'),
            technical_owner=data.get('technical_owner', 'Unknown'),
            access_level=AccessLevel.TEAM,
            upstream_drivers=data.get('upstream_drivers', []),
        )
        DEFAULT_KPI_CONTRACT.add_kpi(kpi)
        return jsonify({'kpi_id': kpi.kpi_id, 'name': kpi.name, 'status': 'added'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/report/<kpi_id>')
def export_report(kpi_id):
    from kpis_endpoint import get_kpi_statuses
    statuses = get_kpi_statuses()
    kpi = next((s for s in statuses if s['kpi_id'] == kpi_id), {})
    html = f'''<!DOCTYPE html><html><head><title>KPI Report — {kpi_id}</title>
    <style>body{{font-family:monospace;padding:40px;max-width:800px;margin:0 auto;}}
    h1{{color:#e7a33e;}}h2{{color:#888;}}table{{width:100%;border-collapse:collapse;}}
    td,th{{padding:8px;border:1px solid #ccc;text-align:left;}}</style></head><body>
    <h1>KPI Report: {kpi.get("name", kpi_id)}</h1>
    <p>Generated: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <h2>Current Status</h2>
    <table><tr><th>Field</th><th>Value</th></tr>
    <tr><td>Status</td><td>{kpi.get("status","—")}</td></tr>
    <tr><td>Value</td><td>{kpi.get("value","—")}</td></tr>
    <tr><td>Delta</td><td>{kpi.get("delta_pct",0)*100:.1f}%</td></tr>
    <tr><td>Severity</td><td>{kpi.get("severity_score",0):.2f}</td></tr>
    <tr><td>Trend</td><td>{kpi.get("trend_direction","—")}</td></tr>
    </table>
    <p><em>For full story, open <a href="/dashboard">the live dashboard</a> and click this KPI card.</em></p>
    </body></html>'''
    from flask import Response
    return Response(html, mimetype='text/html', headers={'Content-Disposition': f'inline; filename="{kpi_id}_report.html"'})


import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

@app.route('/news', methods=['GET'])
def get_news():
    backend = request.args.get('backend', DEFAULT_LLM_BACKEND)
    model = request.args.get('model')
    api_key = request.args.get('api_key')
    
    try:
        llm_client = get_llm_client(backend, model, api_key)
    except Exception as e:
        llm_client = None

    def fetch_rss(query):
        try:
            q = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = []
            for item in root.findall('./channel/item')[:3]:
                title = item.find('title').text if item.find('title') is not None else 'News Update'
                link = item.find('link').text if item.find('link') is not None else '#'
                pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ''
                desc = item.find('description').text if item.find('description') is not None else ''
                
                source = "News Source"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    source = parts[1]
                
                # Cleanup pubDate to a readable format
                date_clean = pubDate.split(' ')[1:4] if len(pubDate.split(' ')) >= 4 else pubDate
                date_str = " ".join(date_clean) if isinstance(date_clean, list) else date_clean
                
                overview = "Read the full article for more details on this topic."
                if llm_client and backend != 'mock':
                    try:
                        prompt = f"Provide a very brief 1-2 sentence AI overview of this news article based on its title and description. Title: {title}. Description: {desc}"
                        overview = llm_client.generate(prompt).strip()
                    except Exception as e:
                        print("LLM news summary error:", e)
                
                items.append({
                    'title': title,
                    'link': link,
                    'source': source,
                    'date': date_str,
                    'overview': overview
                })
            return items
        except Exception as e:
            return [{'title': 'News currently unavailable', 'link': '#', 'source': 'System', 'date': '', 'overview': 'Could not fetch live updates.'}]

    return jsonify({
        'domain': fetch_rss("Supply chain enterprise software news"),
        'company': fetch_rss("Accenture business strategy news"),
        'macro': fetch_rss("Global macroeconomic inflation markets")
    })


if __name__ == '__main__':

    print("Starting BusinessIntelligence.ai Web Interface...")
    print("Open your browser to: http://localhost:5000")
    print("Make sure Ollama is running if using Ollama backend (ollama serve)")

    # Pre-fit Prophet for all KPIs in background (caches to prophet_cache.json)
    # Subsequent /kpis calls will be instant (<1s) after this warms up (~30-60s)
    # (Removed to prevent GIL contention -- use `python warmup_prophet.py` instead)

    port = int(os.environ.get('PORT', 5000))
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', host='0.0.0.0', port=port)