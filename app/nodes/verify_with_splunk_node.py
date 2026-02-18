from app.tools.splunk_tool import splunk_search_tool
from app.utility.llm import call_llm_for_json
from app.utility.summary_tracker import capture_node_execution
import json
from datetime import datetime

# Create a custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# NEW: helper to classify node execution status based on verification_status
_DEF_STATUS_MAP = {
    "verified": "success",
    "false_positive": "success",
    "failed": "error",
    "error": "error",
}

def _classify_execution_status(verification_status: str) -> str:
    if not verification_status:
        return "warning"
    vs = verification_status.lower()
    if vs in _DEF_STATUS_MAP:
        return _DEF_STATUS_MAP[vs]
    if vs.startswith("no_data") or vs in ("inconclusive", "unknown"):
        return "warning"
    return "success"

# Helper to try extract a root cause directly from raw Splunk event text if LLM missed it
def _extract_root_cause_from_raw(raw_items):
    try:
        for item in raw_items:
            if isinstance(item, dict):
                # search values
                for v in item.values():
                    if isinstance(v, str) and "Root Cause" in v:
                        return v
            elif isinstance(item, str) and "Root Cause" in item:
                return item
    except Exception:
        return None
    return None

def verify_with_splunk(state):
    """
    Verify the alert with Splunk data and determine next steps.
    Enhanced to handle empty results and use LLM for analysis.
    """
    try:
        print("Starting Splunk verification...")

        # CRITICAL: Preserve alert data to prevent "Cannot recover" error
        alerts = state.get("alerts", [])
        if alerts:
            alert_id = alerts[0].get("id")
            if alert_id:
                state["task_agent_alert_id"] = alert_id

        # Extract needed parameters from state
        query = state.get("generated", [{}])[0].get("query") if state.get("generated") else None
        ticket_id = alerts[0].get("ticket_id") if alerts else None

        if not query:
            # Fall back to searching by ticket_id if query isn't provided
            query = f'search index=main ticket_id={ticket_id}'
        else:
            # Ensure query has proper format
            if not query.lower().strip().startswith("search "):
                query = f"search {query}"

        # Prepare input for splunk tool
        splunk_input = json.dumps({
            "query": query,
            "earliest_time": "-24h",
            "latest_time": "now"
        })

        # Execute Splunk search
        splunk_results = splunk_search_tool(splunk_input)
        print(f"Splunk results: {splunk_results}")

        # Store results in the state
        state["splunk_results"] = splunk_results

        # Enhanced result analysis
        if isinstance(splunk_results, dict) and "error" in splunk_results:
            # Handle Splunk errors
            print(f"Splunk search error: {splunk_results['error']}")
            state["verification_status"] = "failed"
            state["verification_message"] = f"Splunk verification failed: {splunk_results['error']}"
            state["splunk_data_status"] = "error"
            # Add root cause for error scenario
            state["root_cause"] = f"Splunk search failed: {splunk_results['error']}"
            state["next"] = "finalize_workflow"

        elif isinstance(splunk_results, dict) and "results" in splunk_results:
            # Check if results are empty
            results_list = splunk_results.get("results", [])

            if not results_list or len(results_list) == 0:
                # Empty results - use LLM to determine significance AND root cause
                print("Splunk returned empty results - analyzing with LLM for significance and root cause...")
                state["splunk_data_status"] = "empty"
                state = verify_with_llm_for_empty_results(state, splunk_results)
            else:
                # Results found - use existing LLM verification AND add root cause analysis
                print(f"Splunk returned {len(results_list)} results - analyzing with LLM for verification and root cause...")
                state["splunk_data_status"] = "found"
                state = verify_with_llm(state, results_list)
                # If LLM root_cause still generic, attempt extraction from raw
                if state.get("root_cause", "").startswith("Unable to determine") or state.get("root_cause") in ("No root cause identified", ""):
                    extracted = _extract_root_cause_from_raw(state.get("verification_data", []))
                    if extracted:
                        state["root_cause"] = extracted

        else:
            # Unexpected response format
            print("Unexpected Splunk response format")
            state["verification_status"] = "inconclusive"
            state["verification_message"] = "Splunk returned unexpected response format"
            state["splunk_data_status"] = "unknown"
            # Add root cause for unexpected format
            state["root_cause"] = "Splunk returned unexpected response format - unable to analyze data"
            state["next"] = "finalize_workflow"

        # Populate llm_analysis early (may be overwritten/enhanced in finalization)
        alerts_meta = alerts[0] if alerts else {}
        state.setdefault("llm_analysis", {})
        state["llm_analysis"].update({
            "severity": alerts_meta.get("severity", state.get("llm_analysis", {}).get("severity", "medium")),
            "issue_type": alerts_meta.get("classification", state.get("llm_analysis", {}).get("issue_type", "Application")),
            "verification_status": state.get("verification_status"),
            "root_cause": state.get("root_cause", "No root cause identified"),
            "evidence": state.get("evidence", ""),
            "llm_recommendation": state.get("llm_recommendation", "")
        })
        exec_status = _classify_execution_status(state.get("verification_status"))
        result_msg = f"Splunk verification completed with status: {state['verification_status']} (data: {state.get('splunk_data_status', 'unknown')})"
        state = capture_node_execution(state, "verify_with_splunk", result=result_msg, status=exec_status)

        return state
    except Exception as e:
        state["verification_status"] = "error"
        state["verification_message"] = f"Error during Splunk verification: {str(e)}"
        state["splunk_data_status"] = "error"
        state["root_cause"] = f"Exception during Splunk verification: {str(e)}"
        state["next"] = "finalize_workflow"
        state = capture_node_execution(state, "verify_with_splunk", error=str(e), status="error")
        return state

def verify_with_llm_for_empty_results(state, splunk_results):
    """Use LLM to analyze empty Splunk results, determine significance, and identify root cause."""
    try:
        # Format the context for the LLM
        alerts = state.get("alerts", [])
        alert_data = alerts[0] if alerts else {}

        # Use the custom encoder to handle datetime objects
        alert_context = json.dumps(alert_data, indent=2, cls=DateTimeEncoder)

        # Enhanced prompt for empty results analysis INCLUDING root cause
        prompt = f"""
        You are analyzing an alert where Splunk search returned NO DATA/EMPTY RESULTS.

        ALERT INFORMATION:
        {alert_context}

        SPLUNK SEARCH DETAILS:
        - Query executed successfully but returned no results
        - Search timeframe: last 24 hours
        - Search ID: {splunk_results.get('sid', 'unknown')}

        ANALYSIS TASK:
        1. Determine if the absence of Splunk data is significant for this alert
        2. IDENTIFY THE ROOT CAUSE of why there's no data
        3. Provide actionable recommendations

        Consider:
        - Is this alert type expected to have corresponding log data?
        - Could empty results indicate the issue has been resolved?
        - Could empty results indicate a more serious problem (e.g., logging failure)?
        - What is the most likely root cause for the absence of data?
        - Should we proceed with remediation despite no confirming data?

        Respond in JSON format with the following structure:
        {{
            "status": "NO_DATA_CONCERNING" or "NO_DATA_NORMAL" or "PROCEED_WITH_CAUTION",
            "explanation": "Brief explanation of why empty results are significant or not",
            "root_cause": "Most likely root cause for the absence of Splunk data",
            "recommendation": "Should we proceed to remediation or treat as resolved?"
        }}
        """

        # Use the call_llm_for_json function
        response = call_llm_for_json(prompt, model="gpt-4o-mini", temperature=0.0)
        print(f"LLM empty results analysis: {response}")

        # Check for errors in LLM response
        if "__error__" in response:
            state["verification_status"] = "error"
            state["verification_message"] = f"Error from LLM: {response.get('raw_text', 'Unknown error')}"
            state["root_cause"] = "LLM analysis failed for empty Splunk results"
            state["next"] = "finalize_workflow"
            return state

        # Extract verification result
        status = response.get("status", "PROCEED_WITH_CAUTION")
        explanation = response.get("explanation", "No explanation provided")
        root_cause = response.get("root_cause", "Unknown - no data found in Splunk logs")
        recommendation = response.get("recommendation", "Proceed with caution")

        # Set verification status based on LLM analysis (preserve existing UI logic)
        if status == "NO_DATA_CONCERNING":
            state["verification_status"] = "no_data_concerning"
            state["verification_message"] = f"Empty Splunk results are concerning: {explanation}"
        elif status == "NO_DATA_NORMAL":
            state["verification_status"] = "no_data_normal"
            state["verification_message"] = f"Empty Splunk results are normal: {explanation}"
        else:  # PROCEED_WITH_CAUTION or any other response
            state["verification_status"] = "no_data_cautious"
            state["verification_message"] = f"Empty Splunk results require caution: {explanation}"

        # ADD ROOT CAUSE (new field - won't break UI)
        state["root_cause"] = root_cause
        state["llm_recommendation"] = recommendation
        state["verification_data"] = {
            "empty_results": True,
            "sid": splunk_results.get('sid'),
            "root_cause_analysis": root_cause  # Additional metadata
        }
        state["next"] = "finalize_workflow"

        return state

    except Exception as e:
        print(f"Exception during LLM empty results analysis: {str(e)}")
        state["verification_status"] = "error"
        state["verification_message"] = f"Error during LLM analysis of empty results: {str(e)}"
        state["root_cause"] = f"Exception during empty results analysis: {str(e)}"
        state["next"] = "finalize_workflow"
        return state

def verify_with_llm(state, splunk_results):
    """Use LLM to analyze Splunk results, determine if issue is real, and identify root cause."""
    try:
        # Extract relevant data from Splunk results for analysis
        raw_data = []
        for result in splunk_results:
            if "_raw" in result:
                try:
                    # Try to parse as JSON
                    parsed = json.loads(result["_raw"])
                    raw_data.append(parsed)
                except:
                    # If not JSON, use as is
                    raw_data.append(result["_raw"])

        # Format the context for the LLM - using custom encoder for datetime objects
        alerts = state.get("alerts", [])
        alert_data = alerts[0] if alerts else {}

        # Use the custom encoder to handle datetime objects
        alert_context = json.dumps(alert_data, indent=2, cls=DateTimeEncoder)
        results_context = json.dumps(raw_data, indent=2)

        # Enhanced prompt for LLM INCLUDING root cause identification
        prompt = f"""
        You are verifying if an alert requires action based on Splunk data AND identifying the root cause.

        ALERT INFORMATION:
        {alert_context}

        SPLUNK RESULTS:
        {results_context}

        ANALYSIS TASK:
        1. Determine if this is a real issue that needs attention
        2. IDENTIFY THE ROOT CAUSE based on the Splunk data
        3. Provide clear explanation and evidence

        Based on the Splunk data, analyze:
        - Is this a legitimate issue requiring action?
        - What is the root cause of the problem?
        - What evidence from the logs supports your conclusion?

        Respond in JSON format with the following structure:
        {{
            "status": "VERIFIED" or "FALSE_POSITIVE" or "INSUFFICIENT_DATA",
            "explanation": "Brief explanation of your determination",
            "root_cause": "Identified root cause based on Splunk data analysis",
            "evidence": "Key evidence from logs that supports your conclusion"
        }}
        """

        # Use the call_llm_for_json function
        response = call_llm_for_json(prompt, model="gpt-4o-mini", temperature=0.0)
        print(f"LLM verification response: {response}")

        # Check for errors in LLM response
        if "__error__" in response:
            state["verification_status"] = "error"
            state["verification_message"] = f"Error from LLM: {response.get('raw_text', 'Unknown error')}"
            state["root_cause"] = "LLM analysis failed for Splunk results"
            state["next"] = "finalize_workflow"
            return state

        # Extract verification result
        status = response.get("status", "INSUFFICIENT_DATA")
        explanation = response.get("explanation", "No explanation provided")
        root_cause = response.get("root_cause", "Unable to determine root cause from available data")
        evidence = response.get("evidence", "No evidence provided")

        # Set verification status based on LLM analysis (preserve existing UI logic)
        if status == "VERIFIED":
            state["verification_status"] = "verified"
            state["verification_message"] = explanation
            state["verification_data"] = raw_data
        elif status == "FALSE_POSITIVE":
            state["verification_status"] = "false_positive"
            state["verification_message"] = explanation
            state["verification_data"] = raw_data
        else:  # INSUFFICIENT_DATA or any other response
            state["verification_status"] = "inconclusive"
            state["verification_message"] = explanation
            state["verification_data"] = raw_data

        # ADD ROOT CAUSE (new field - won't break UI)
        state["root_cause"] = root_cause
        state["evidence"] = evidence
        state["next"] = "finalize_workflow"

        return state

    except Exception as e:
        print(f"Exception during LLM verification: {str(e)}")
        state["verification_status"] = "error"
        state["verification_message"] = f"Error during LLM verification: {str(e)}"
        state["root_cause"] = f"Exception during Splunk results analysis: {str(e)}"
        state["next"] = "finalize_workflow"
        return state

def run(state):
    """Entry point for the node."""
    return verify_with_splunk(state)