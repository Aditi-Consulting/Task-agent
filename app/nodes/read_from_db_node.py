from store.db import fetch_alerts_from_db, fetch_resolution
from app.utility.summary_tracker import capture_node_execution, initialize_execution_tracking

def read_from_db_node(state):
    """
    Read alerts from database and initialize task_agent tracking.
    This is the CRITICAL FIX for 'Missing execution_id or alert_id' error.
    """
    print("DEBUG: Starting read_from_db_node with task_agent initialization...")

    try:
        # Get alert_id from state if provided
        alert_id = state.get("alert_id")

        # Fetch alerts
        alerts = fetch_alerts_from_db(alert_id=alert_id)
        state["alerts"] = alerts

        print(f"DEBUG: Fetched {len(alerts)} alerts from database")

        # ─── CRITICAL DEBUG: Log alert keys and source value ───
        if alerts and len(alerts) > 0:
            alert0 = alerts[0]
            print(f"DEBUG [read_from_db] Alert[0] keys: {list(alert0.keys())}")
            print(f"DEBUG [read_from_db] Alert[0] id: {alert0.get('id')}")
            print(f"DEBUG [read_from_db] Alert[0] source: '{alert0.get('source', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] ticket_id: '{alert0.get('ticket_id', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] classification: '{alert0.get('classification', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] issue_type: '{alert0.get('issue_type', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] created_by: '{alert0.get('created_by', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] status: '{alert0.get('status', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] severity: '{alert0.get('severity', 'KEY_NOT_FOUND')}'")
            print(f"DEBUG [read_from_db] Alert[0] ticket (first 150): '{str(alert0.get('ticket', ''))[:150]}'")
            # Check if 'source' key truly exists vs missing
            print(f"DEBUG [read_from_db] 'source' IN alert0.keys(): {'source' in alert0}")
        else:
            print(f"DEBUG [read_from_db] WARNING: No alerts returned for alert_id={alert_id}")

        # Check if resolution exists in DB for this alert
        db_resolution_id = None
        if alerts and len(alerts) > 0:
            issue_type = alerts[0].get("issue_type")
            if issue_type:
                resolution = fetch_resolution(issue_type)
                if resolution and resolution.get("id"):
                    db_resolution_id = resolution["id"]
                    state["db_resolution_id"] = db_resolution_id
                    print(f"DEBUG: Found DB resolution id: {db_resolution_id} for issue_type: {issue_type}")

        # CRITICAL: Initialize task_agent tracking if not already done
        if "task_agent_execution_id" not in state or not state.get("task_agent_execution_id"):
            print("DEBUG: Initializing task_agent execution tracking...")

            # Extract alert_id for initialization
            alert_id = None
            if alerts and len(alerts) > 0 and "id" in alerts[0]:
                alert_id = alerts[0]["id"]
                state["summary_id"] = alert_id  # Keep legacy field for compatibility

            # Initialize task_agent tracking
            state = initialize_execution_tracking(state, alert_id)
            print(f"DEBUG: Task_agent tracking initialized with execution_id: {state.get('task_agent_execution_id')}, alert_id: {state.get('task_agent_alert_id')}")
        else:
            print("DEBUG: Task_agent tracking already initialized")

        # Set workflow type
        state["workflow_type"] = "k8s"

        # Capture execution summary with resolution ID if found
        base_msg = f"Retrieved {len(alerts)} alerts from database and initialized task_agent tracking"
        if db_resolution_id:
            result_msg = f"{base_msg} | Found resolution in DB (ID: {db_resolution_id})"
        else:
            result_msg = base_msg

        state = capture_node_execution(state, "read_from_db", result=result_msg)

        print("DEBUG: read_from_db_node completed successfully")
        return state

    except Exception as e:
        print(f"ERROR: read_from_db_node failed: {e}")
        # Still try to capture the error even if initialization failed
        try:
            state = capture_node_execution(state, "read_from_db", error=str(e))
        except Exception as capture_error:
            print(f"ERROR: Could not capture execution error: {capture_error}")
        return state
