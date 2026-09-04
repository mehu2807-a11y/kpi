import re
import codecs

with codecs.open('app.py', 'r', 'utf-8') as f:
    code = f.read()

new_format_input = '''@app.route('/format_input', methods=['POST'])
def format_input():
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

        job_id = job_store.create_job()

        def _format_background(job_id, data, raw_text, backend, model, api_key, _t0):
            try:
                from dataclasses import asdict, fields
                from schemas import AnomalyEvent, CorrelationResult, RetrievedEvidence, StructuredDriver, EvidenceSource
                
                print(f"[/format_input] starting background job {job_id}: backend={backend!r} input_len={len(raw_text)} chars", flush=True)

                client = get_llm_client(backend, model, api_key)

                user_prompt = (
                    f"{FORMAT_SCHEMA_HINT}\\n\\nRAW INPUT TO CONVERT:\\n\\\"\\\"\\\"\\n{raw_text}\\n\\\"\\\"\\\"\\n\\n"
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
                job_store.update_job(job_id, 'done', result=result)

            except (TypeError, ValueError) as e:
                print(f"[/format_input] failed after {time.time() - _t0:.1f}s: {e}", flush=True)
                # We can't return 422 in a background job, so we just set error.
                # The frontend will just throw it. We can embed the raw output in the error if we want.
                job_store.update_job(job_id, 'error', error=f"The AI's formatted output was missing or had invalid fields: {e}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[/format_input] failed after {time.time() - _t0:.1f}s: {e}", flush=True)
                job_store.update_job(job_id, 'error', error=str(e))

        thread = threading.Thread(target=_format_background, args=(job_id, data, raw_text, backend, model, api_key, _t0), daemon=True)
        thread.start()
        
        job_store.cleanup_old_jobs()
        return jsonify({"job_id": job_id, "status": "pending"}), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/format_input/status/<job_id>', methods=['GET'])
def format_input_status(job_id):
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    if job['status'] == 'pending':
        return jsonify({"status": "pending"}), 200
    elif job['status'] == 'error':
        return jsonify({"status": "error", "error": job['error']}), 200
    elif job['status'] == 'done':
        return jsonify({"status": "done", "result": job['result']}), 200
'''

pattern = r"@app\.route\('/format_input', methods=\['POST'\]\)\ndef format_input\(\):.*?return jsonify\(\{\"error\": str\(e\)\}\), 500"
new_code = re.sub(pattern, new_format_input.strip(), code, flags=re.DOTALL)

if new_code == code:
    print("REPLACEMENT FAILED! Could not find target pattern in app.py")
else:
    with codecs.open('app.py', 'w', 'utf-8') as f:
        f.write(new_code)
    print("app.py patched for async format_input!")
