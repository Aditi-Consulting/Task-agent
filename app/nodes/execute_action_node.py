from app.k8s_orchestrator import build_k8s_graph
from app.tools.send_mail_tool import send_email
from app.utility.summary_tracker import capture_node_execution
from store.db import update_alert_status

# NEW helper to detect error semantics in result strings
def _contains_error(result: str) -> bool:
    if not isinstance(result, str):
        return False
    lowered = result.lower()
    return any(tok in lowered for tok in ["error", "not found", "404", "failed"])

def execute_action_node(state):
    """Execute the recommended action based on resolution type"""
    try:
        resolutions = state.get("resolutions", [])
        if not resolutions:
            result_msg = "No resolutions to execute"
            state = capture_node_execution(state, "execute_action", result=result_msg)
            return {**state, "executed": [result_msg]}

        resolution = resolutions[0]
        action_type = resolution.get("action_type", "")
        description = resolution.get("description", "")

        print(f"Executing action: {action_type}")
        print(f"Resolution description: {description}")

        alerts = state.get("alerts", [])
        original_ticket_text = None
        if alerts and isinstance(alerts, list) and alerts[0].get("ticket"):
            original_ticket_text = alerts[0].get("ticket")
            print(f"DEBUG: Using original alert ticket text for K8s processing: {original_ticket_text}")
        else:
            print("DEBUG: No original alert ticket available; falling back to resolution description")

        k8s_user_input = original_ticket_text or description

        k8s_keywords = [
            "k8s", "kubernetes", "deployment", "pod", "service",
            "restart", "scale", "fix", "port", "namespace"
        ]

        if any(keyword in action_type.lower() or keyword in k8s_user_input.lower() for keyword in k8s_keywords):
            print("Routing to K8s orchestrator...")
            k8s_app = build_k8s_graph()
            # Derive namespace from resolution or alert ticket if present
            derived_namespace = resolution.get("namespace") or (
                alerts[0].get("namespace") if alerts and alerts[0].get("namespace") else "default"
            )
            alert_id = alerts[0].get("id") if alerts else None
            k8s_input = {
                "user_input": k8s_user_input,
                "namespace": derived_namespace or "default",
                "alerts": alerts,           # Pass through alerts so finalization has context
                "summary_id": alert_id,     # Link execution summaries
                "workflow_type": "k8s"     # Hint for finalization logic
            }
            print(f"DEBUG: K8s orchestrator input: {k8s_input}")

            k8s_result_state = k8s_app.invoke(k8s_input)
            k8s_result = k8s_result_state.get("result") or k8s_result_state.get("error", "K8s action completed")

            # Copy execution summary from K8s orchestrator if available
            if "execution_summary" in k8s_result_state:
                state["execution_summary"] = state.get("execution_summary", []) + k8s_result_state["execution_summary"]

            # Determine if any node failed
            any_errors = any(node.get("status") == "error" for node in k8s_result_state.get("execution_summary", []))
            error_field = k8s_result_state.get("error") or (k8s_result if _contains_error(k8s_result) else None)

            if any_errors or error_field:
                # Capture as error
                state = capture_node_execution(state, "execute_action", error=error_field or "K8s workflow encountered errors")
                # Do NOT mark alert as resolved
                return {**state, "executed": [error_field or k8s_result]}

            # Capture successful execution
            state = capture_node_execution(state, "execute_action", result=f"K8s action executed: {k8s_result}")

            # Only mark resolved if no errors detected
            if alerts:
                alert_id = alerts[0].get("id")
                if alert_id:
                    update_alert_status(alert_id, "resolved")
                    print(f"Alert {alert_id} marked as resolved")

            return {**state, "executed": [k8s_result]}

        elif "email" in action_type.lower() or "notify" in action_type.lower():
            print("Sending email notification...")
            email_result = send_email({
                "subject": f"Alert Resolution: {action_type}",
                "body": description
            })
            state = capture_node_execution(state, "execute_action", result=f"Email sent: {email_result}")
            return {**state, "executed": [email_result]}
        else:
            result_msg = f"Executed: {action_type} - {description}"
            state = capture_node_execution(state, "execute_action", result=result_msg)
            return {**state, "executed": [result_msg]}
    except Exception as e:
        error_msg = f"Error executing action: {e}"
        state = capture_node_execution(state, "execute_action", error=str(e))
        return {**state, "executed": [error_msg]}
