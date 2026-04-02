from app.k8s_orchestrator import build_k8s_graph
from app.tools.send_mail_tool import send_email
from app.utility.summary_tracker import capture_node_execution
from store.db import update_alert_status


def _contains_error(result: str) -> bool:
    """Detect error semantics in result strings."""
    if not isinstance(result, str):
        return False
    lowered = result.lower()
    return any(tok in lowered for tok in ["error", "not found", "404", "failed"])


def _is_k8s_source(alerts: list) -> bool:
    """Check if the alert source is Kubernetes."""
    if alerts and len(alerts) > 0:
        source = (alerts[0].get("source") or "").strip().lower()
        result = source in ("kubernetes", "k8s", "k8s_monitor")
        print(f"DEBUG [ExecuteAction._is_k8s_source] raw='{alerts[0].get('source')}', normalized='{source}', result={result}")
        return result
    print(f"DEBUG [ExecuteAction._is_k8s_source] No alerts, returning False")
    return False


def execute_action_node(state):
    """
    Execute the recommended action based on resolution type.

    Routing logic:
      1. If alert source is NOT Kubernetes, skip K8s orchestrator entirely.
      2. If source IS Kubernetes, run K8s orchestrator.
      3. Fallback: email/notify actions or generic execution.
    """
    try:
        resolutions = state.get("resolutions", [])
        alerts = state.get("alerts", [])

        # ─── FULL DEBUG DUMP ON ENTRY ───
        print(f"[ExecuteAction] ========== ENTRY ==========")
        print(f"[ExecuteAction] alerts count: {len(alerts)}")
        print(f"[ExecuteAction] resolutions count: {len(resolutions)}")
        if alerts:
            a0 = alerts[0]
            print(f"[ExecuteAction] Alert[0] keys: {list(a0.keys())}")
            print(f"[ExecuteAction] Alert[0] id: {a0.get('id')}")
            print(f"[ExecuteAction] Alert[0] source (raw): '{a0.get('source')}'")
            print(f"[ExecuteAction] Alert[0] 'source' in keys: {'source' in a0}")
            print(f"[ExecuteAction] Alert[0] classification: '{a0.get('classification')}'")
            print(f"[ExecuteAction] Alert[0] created_by: '{a0.get('created_by')}'")
            print(f"[ExecuteAction] Alert[0] ticket_id: '{a0.get('ticket_id')}'")
            print(f"[ExecuteAction] Alert[0] ticket (first 120): '{str(a0.get('ticket', ''))[:120]}'")
        else:
            print(f"[ExecuteAction] WARNING: No alerts in state!")

        if not resolutions:
            result_msg = "No resolutions to execute"
            state = capture_node_execution(state, "execute_action", result=result_msg)
            return {**state, "executed": [result_msg]}

        resolution = resolutions[0]
        action_type = resolution.get("action_type", "")
        description = resolution.get("description", "")
        alerts = state.get("alerts", [])

        print(f"[ExecuteAction] action_type='{action_type}', description='{description[:80]}...'")

        # ─── GUARD: Only invoke K8s orchestrator when source is explicitly Kubernetes ───
        if _is_k8s_source(alerts):
            return _execute_k8s_action(state, resolution, alerts)

        # ─── Non-K8s path: email / notify / generic ───
        if "email" in action_type.lower() or "notify" in action_type.lower():
            print("[ExecuteAction] Sending email notification...")
            email_result = send_email({
                "subject": f"Alert Resolution: {action_type}",
                "body": description
            })
            state = capture_node_execution(state, "execute_action", result=f"Email sent: {email_result}")
            return {**state, "executed": [email_result]}

        # Generic execution — log the resolution, do not invoke K8s
        source = alerts[0].get("source", "unknown") if alerts else "unknown"
        result_msg = f"Executed resolution (source={source}): {action_type} — {description}"
        print(f"[ExecuteAction] {result_msg}")
        state = capture_node_execution(state, "execute_action", result=result_msg)
        return {**state, "executed": [result_msg]}

    except Exception as e:
        error_msg = f"Error executing action: {e}"
        print(f"[ExecuteAction] {error_msg}")
        state = capture_node_execution(state, "execute_action", error=str(e))
        return {**state, "executed": [error_msg]}


def _execute_k8s_action(state, resolution, alerts):
    """
    Run the K8s orchestrator sub-graph for Kubernetes-sourced alerts.
    Isolated into a separate function for clarity and testability.
    """
    original_ticket_text = None
    if alerts and isinstance(alerts, list) and alerts[0].get("ticket"):
        original_ticket_text = alerts[0].get("ticket")

    k8s_user_input = original_ticket_text or resolution.get("description", "")
    print(f"[ExecuteAction] Routing to K8s orchestrator: '{k8s_user_input[:100]}...'")

    k8s_app = build_k8s_graph()

    derived_namespace = resolution.get("namespace") or (
        alerts[0].get("namespace") if alerts and alerts[0].get("namespace") else "default"
    )
    alert_id = alerts[0].get("id") if alerts else None

    k8s_input = {
        "user_input": k8s_user_input,
        "namespace": derived_namespace or "default",
        "alerts": alerts,
        "summary_id": alert_id,
        "workflow_type": "k8s"
    }

    k8s_result_state = k8s_app.invoke(k8s_input)
    k8s_result = k8s_result_state.get("result") or k8s_result_state.get("error", "K8s action completed")

    # Merge execution summaries from K8s sub-graph
    if "execution_summary" in k8s_result_state:
        state["execution_summary"] = state.get("execution_summary", []) + k8s_result_state["execution_summary"]

    # Determine success vs failure
    any_errors = any(
        node.get("status") == "error"
        for node in k8s_result_state.get("execution_summary", [])
    )
    error_field = k8s_result_state.get("error") or (k8s_result if _contains_error(k8s_result) else None)

    if any_errors or error_field:
        state = capture_node_execution(
            state, "execute_action",
            error=error_field or "K8s workflow encountered errors"
        )
        return {**state, "executed": [error_field or k8s_result]}

    # Success path
    state = capture_node_execution(
        state, "execute_action",
        result=f"K8s action executed: {k8s_result}"
    )

    if alerts:
        alert_id = alerts[0].get("id")
        if alert_id:
            update_alert_status(alert_id, "resolved")
            print(f"[ExecuteAction] Alert {alert_id} marked as resolved")

    return {**state, "executed": [k8s_result]}
