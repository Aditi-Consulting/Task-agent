import json
from app.utility.llm import call_llm_for_json
from app.utility.prompts import LOG_SUMMARY_PROMPT

def summarize_logs_node(state):
    """
    LangGraph node: Summarize Splunk logs via LLM.
    """
    results = state.get("splunk_results", {}).get("results", [])
    summaries = []

    for event in results:
        raw_log = event.get("_raw", "{}")
        try:
            log_data = json.loads(raw_log)
        except Exception:
            log_data = {"message": raw_log}  # fallback

        prompt = LOG_SUMMARY_PROMPT.format(log=json.dumps(log_data, indent=2))
        summary_json = call_llm_for_json(prompt)
        summaries.append(summary_json)

    state["summaries"] = summaries
    return state
