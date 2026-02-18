from app.utility.llm import call_llm_for_json

def generate_parameters_node(state):
    alerts = state.get("alerts", [])
    resolutions = state.get("resolutions", [])
    processed = []
    generated = []

    for idx, alert in enumerate(alerts):
        resolution = resolutions[idx] if idx < len(resolutions) else {}
        prompt = (
            f"You are a monitoring assistant. Based on this alert: '{alert}', "
            "generate a Splunk search query that only uses `index=main` and the `ticket_id` from the alert. "
            "Use `earliest_time` in relative format (like `-1d` or `-15m`) and set `latest_time` to `now`. "
            "Do not add any other filters or transformations. Ensure the query is ready to be used directly in Splunk.\n\n"
            "Also provide a short, clear email subject.\n\n"
            "Respond strictly in valid JSON only, with the following format:\n"
            "{\n"
            "  \"query\": \"<splunk_query>\",\n"
            "  \"subject\": \"<email_subject>\",\n"
            "  \"earliest_time\": \"<relative_time>\",\n"
            "  \"latest_time\": \"now\"\n"
            "}\n\n"
            "Do not include any explanation, commentary, or extra text outside the JSON object. "
            "Do not escape quotes inside the query; it should be directly usable in Splunk."
        )

        params = call_llm_for_json(prompt)
        subject = params.get("subject", "")
        query = params.get("query", "")

        generated.append(params)
        processed.append({
            "alert": alert,
            "resolution": resolution
        })

    state["processed"] = processed
    state["generated"] = generated
    # Set top-level keys for execution node
    if generated and alerts:
        state["subject"] = generated[0].get("subject", "")
        state["query"] = generated[0].get("query", "")
        state["input"] = alerts[0]
    else:
        state["subject"] = ""
        state["query"] = ""
        state["input"] = {}

    return state

