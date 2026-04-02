"""
Utility module for tracking and managing node execution summaries.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from store.db import (
    store_node_execution_summary,
    initialize_task_agent_execution,
    update_task_agent_execution,
    finalize_task_agent_execution,
    get_task_agent_execution_for_email
)


def capture_node_execution(state: Dict[str, Any], node_name: str, result: Any = None, error: str = None, status: str = None) -> Dict[str, Any]:
    """
    Capture execution summary for a node and store it in both state and database.
    Enhanced to include root cause analysis, evidence, verification_status and explicit status override.

    Args:
        state: Current workflow state
        node_name: Name of the executed node
        result: Result from node execution (optional)
        error: Error message if node failed (optional)
        status: Explicit status classification ('success','warning','error') if provided

    Returns:
        Updated state with execution summary
    """
    try:
        # Get current execution order
        current_step = state.get("current_step", 0)

        # Initialize execution_summary in state if not exists
        if "execution_summary" not in state:
            state["execution_summary"] = []

        # Derive status
        if error:
            derived_status = "error"
            result_summary = f"Error in {node_name}: {error}"
            error_message = error
        elif result:
            derived_status = status or "success"
            result_summary = _generate_result_summary(node_name, result)
            error_message = None
        else:
            derived_status = status or "warning"
            result_summary = f"{node_name} executed but no result available"
            error_message = None

        # Extract root cause and evidence if available
        root_cause = state.get("root_cause", "")
        evidence = state.get("evidence", "")
        verification_status = state.get("verification_status", "")

        # Create execution record for state with root cause data
        execution_record = {
            "node_name": node_name,
            "execution_order": current_step,
            "status": derived_status,
            "result_summary": result_summary,
            "error_message": error_message,
            "full_result": _serialize_result(result) if result else None
        }

        # Add root cause data if available
        if root_cause:
            execution_record["root_cause"] = root_cause
        if evidence:
            execution_record["evidence"] = evidence
        if verification_status:
            execution_record["verification_status"] = verification_status

        # Add to state execution summary
        state["execution_summary"].append(execution_record)

        # Store in database if alert_id is available
        alert_id = _get_alert_id_from_state(state)
        if alert_id:
            # Properly serialize the result for database storage
            serialized_result = _serialize_result(result) if result else None

            # Include root cause in the full_result for database storage
            if root_cause or evidence or verification_status:
                enhanced_result = {
                    "execution_result": serialized_result,
                    "root_cause": root_cause,
                    "evidence": evidence,
                    "verification_status": verification_status
                }
                serialized_result = enhanced_result

            # Pass expanded data to DB layer (modify DB function later to accept optional fields if needed)
            store_node_execution_summary(
                alert_id=alert_id,
                node_name=node_name,
                execution_order=current_step,
                status=derived_status,
                result_summary=result_summary,
                full_result=serialized_result,  # Enhanced with root cause data
                error_message=error_message
            )
            print(f"DEBUG: Stored execution summary for {node_name} (alert_id: {alert_id}) status={derived_status} root_cause={root_cause}")

        return state

    except Exception as e:
        print(f"ERROR: Failed to capture execution summary for {node_name}: {e}")
        return state


def _generate_result_summary(node_name: str, result: Any) -> str:
    """
    Generate a concise summary of the node execution result.

    Args:
        node_name: Name of the executed node
        result: Result from node execution

    Returns:
        Concise summary string
    """
    try:
        if isinstance(result, str):
            # For string results, take first 200 characters
            if len(result) > 200:
                return f"{node_name} completed: {result[:200]}..."
            else:
                return f"{node_name} completed: {result}"

        elif isinstance(result, dict):
            # For dict results, extract key information
            if "status" in result:
                return f"{node_name} completed with status: {result.get('status')}"
            elif "message" in result:
                return f"{node_name} completed: {result.get('message')}"
            else:
                return f"{node_name} completed successfully"

        elif isinstance(result, list):
            # For list results, show count
            return f"{node_name} completed: Found {len(result)} items"

        else:
            return f"{node_name} completed successfully"

    except Exception as e:
        return f"{node_name} completed with result parsing error: {str(e)}"


def _serialize_result(result: Any) -> Any:
    """
    Serialize result for database storage.

    Args:
        result: Result to serialize

    Returns:
        Serialized result safe for JSON storage
    """
    try:
        if isinstance(result, (str, int, float, bool, type(None))):
            return result
        elif isinstance(result, (dict, list)):
            return result
        else:
            return str(result)
    except Exception:
        return str(result)


def _get_alert_id_from_state(state: Dict[str, Any]) -> Optional[int]:
    """
    Extract alert_id from state.

    Args:
        state: Current workflow state

    Returns:
        Alert ID if available, None otherwise
    """
    try:
        # Try to get from alerts list
        alerts = state.get("alerts", [])
        if alerts and isinstance(alerts, list) and len(alerts) > 0:
            alert = alerts[0]
            if isinstance(alert, dict) and "id" in alert:
                return alert["id"]

        # Try to get from summary_id field
        summary_id = state.get("summary_id")
        if summary_id:
            return summary_id

        return None

    except Exception as e:
        print(f"ERROR: Could not extract alert_id from state: {e}")
        return None


def initialize_execution_tracking(state: Dict[str, Any], alert_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Initialize execution tracking for a workflow.

    Args:
        state: Current workflow state
        alert_id: Optional alert ID to link executions to

    Returns:
        Updated state with execution tracking initialized
    """
    # Extract alert_id from state if not provided
    if alert_id is None:
        alerts = state.get("alerts", [])
        if alerts and len(alerts) > 0:
            alert_id = alerts[0].get("id", 1)
        else:
            alert_id = 1

    # Initialize database record
    execution_id = initialize_task_agent_execution(alert_id)

    # Initialize in-memory tracking
    return {
        **state,
        "execution_summary": [],  # In-memory node executions
        "task_agent_execution_id": execution_id,
        "task_agent_alert_id": alert_id,
        "task_agent_start_time": datetime.now().isoformat()
    }


def finalize_workflow_and_send_email(state):
    """
    Finalize the complete workflow execution and send summary email.
    Enhanced with error recovery for missing execution_id/alert_id and root cause tracking.
    """
    execution_id = state.get("task_agent_execution_id")
    alert_id = state.get("task_agent_alert_id")
    execution_summary = state.get("execution_summary", [])
    workflow_type = state.get("workflow_type", "k8s")

    print(f"DEBUG: Starting workflow finalization for {workflow_type} workflow...")
    print(f"DEBUG: execution_id={execution_id}, alert_id={alert_id}")

    # EARLY GUARD: Ensure at least one alert exists; inject synthetic if absent
    if (not state.get("alerts")) or not isinstance(state.get("alerts"), list) or len(state.get("alerts")) == 0:
        synthetic_id = alert_id or state.get("summary_id") or 1
        synthetic_alert = {
            "id": synthetic_id,
            "ticket": state.get("user_input", "Workflow issue detected"),
            "severity": state.get("llm_analysis", {}).get("severity", "medium"),
            "classification": state.get("llm_analysis", {}).get("issue_type", workflow_type),
            "source": state.get("alerts", [{}])[0].get("source", "unknown") if state.get("alerts") else "unknown",
            "status": "in_progress"
        }
        state["alerts"] = [synthetic_alert]
        print(f"DEBUG: Injected synthetic alert for finalization: {synthetic_alert}")
        # If we had no execution_id initialize tracking now
        if not execution_id:
            recovered_id = synthetic_alert.get("id", 1)
            execution_id = initialize_task_agent_execution(recovered_id)
            state["task_agent_execution_id"] = execution_id
            state["task_agent_alert_id"] = recovered_id
            print(f"DEBUG: Initialized execution tracking after synthetic alert injection: execution_id={execution_id}")

    # Extract root cause and verification details from state
    root_cause = state.get("root_cause", "No root cause identified")
    evidence = state.get("evidence", "")
    verification_status = state.get("verification_status", "unknown")
    verification_message = state.get("verification_message", "")
    llm_recommendation = state.get("llm_recommendation", "")

    print(f"DEBUG: Root cause to save: {root_cause}")
    print(f"DEBUG: Evidence: {evidence}")

    # ENHANCED ERROR RECOVERY FOR MISSING EXECUTION_ID/ALERT_ID
    if not execution_id:
        print("WARNING: Missing task_agent_execution_id - attempting recovery...")

        # Try to get alert_id and initialize if missing
        if not alert_id:
            alerts = state.get("alerts", [])
            if alerts and len(alerts) > 0:
                alert_id = alerts[0].get("id")
                if alert_id:
                    print(f"INFO: Recovered alert_id={alert_id} from alerts")
                    execution_id = initialize_task_agent_execution(alert_id)
                    state["task_agent_execution_id"] = execution_id
                    state["task_agent_alert_id"] = alert_id
                    print(f"SUCCESS: Initialized task_agent tracking - execution_id={execution_id}")
                else:
                    print("ERROR: Cannot recover - no alert ID in alerts[0]")
                    return {**state, "error": "Cannot finalize: No alert ID available"}
            else:
                print("ERROR: Cannot recover - no alerts in state AFTER synthetic injection attempt")
                return {**state, "error": "Cannot finalize: No alerts available"}
        else:
            print(f"INFO: Have alert_id={alert_id}, initializing execution tracking...")
            execution_id = initialize_task_agent_execution(alert_id)
            state["task_agent_execution_id"] = execution_id
            print(f"SUCCESS: Initialized execution_id={execution_id}")

    if not alert_id:
        print("FATAL: Missing task_agent_alert_id after recovery attempt")
        return {**state, "error": "Cannot finalize: Missing alert_id after recovery"}

    # Get additional context for K8s workflow
    llm_analysis = state.get("llm_analysis", {})
    additional_context = {
        "namespace": state.get("namespace", "default"),
        "service_name": state.get("service_name", ""),
        "deployment_name": state.get("deployment_name", ""),
        "root_cause": root_cause,
        "evidence": evidence,
        "verification_status": verification_status,
        "alert_count": len(state.get("alerts", [])),
        "resolutions_found": len(state.get("resolutions", [])),
        "resolutions_executed": len(state.get("executed", []))
    }

    if not llm_analysis:
        alerts = state.get("alerts", [])
        if alerts and len(alerts) > 0:
            alert = alerts[0]
            llm_analysis = {
                "issue_type": alert.get("classification", "k8s"),
                "severity": alert.get("severity", "medium"),
                "verification_status": verification_status,
                "root_cause": root_cause,
                "evidence": evidence,
                "llm_recommendation": llm_recommendation
            }

    # Extract confidence_score from state or use default
    confidence_score = state.get("confidence_score")
    if confidence_score is None:
        # Try to get from resolutions if available
        resolutions = state.get("resolutions", [])
        if resolutions and isinstance(resolutions, list):
            # Use the highest confidence_score among resolutions, or default to 15
            confidence_score = max((r.get("confidence_score", 15) for r in resolutions if isinstance(r, dict)), default=15)
        else:
            confidence_score = 15
    try:
        confidence_score = float(confidence_score)
    except Exception:
        confidence_score = 15.0
    confidence_score = max(15.0, min(confidence_score, 100.0))

    # Determine final status
    failed_nodes = [n for n in execution_summary if n.get("status") == "error"]
    final_status = "failed" if failed_nodes or state.get("error") else "completed"

    # Create complete result summary INCLUDING ROOT CAUSE
    full_result = {
        "task_agent_summary": {
            "total_steps": len(execution_summary),
            "completed_steps": len([n for n in execution_summary if n.get("status") == "success"]),
            "failed_steps": len(failed_nodes),
            "workflow_status": final_status,
            "workflow_type": workflow_type,
            "issue_type": llm_analysis.get("issue_type", "unknown"),
            "severity": llm_analysis.get("severity", "unknown"),
            "final_result": state.get("result", f"{workflow_type.title()} workflow completed"),
            "start_time": state.get("task_agent_start_time"),
            "end_time": datetime.now().isoformat(),
            # CRITICAL: Add root cause to summary
            "root_cause": root_cause,
            "evidence": evidence,
            "verification_status": verification_status,
            "llm_recommendation": llm_recommendation,
            "confidence_score": confidence_score
        },
        "execution_details": {
            "user_input": state.get("user_input", ""),
            "verification_status": verification_status,
            "verification_message": verification_message,
            "root_cause": root_cause,           # ADD ROOT CAUSE TO EXECUTION DETAILS
            "evidence": evidence,               # ADD EVIDENCE TO EXECUTION DETAILS
            **additional_context
        },
        # CRITICAL: Add LLM analysis with root cause
        "llm_analysis": llm_analysis
    }

    try:
        # Update database with complete execution summary
        update_task_agent_execution(
            execution_id,
            execution_summary,
            full_result,
            final_status,
            confidence_score
        )

        # Finalize execution (set end time)
        finalize_task_agent_execution(execution_id, final_status)

        print(f"SUCCESS: Finalized {workflow_type} execution {execution_id} with status {final_status}")

        # Send email with complete summary
        email_content = get_task_agent_execution_for_email(alert_id, workflow_type)

        # Import and call send_email function
        from app.nodes.send_email_node import run as send_email_run

        # Prepare email state
        email_state = {
            **state,
            "mail_sent": True,
            "email_content": email_content,
            "verification_status": "completed",
            "verification_message": f"{workflow_type.title()} workflow {final_status}: {len(execution_summary)} steps executed"
        }

        # Send the email
        final_state = send_email_run(email_state)

        print(f"SUCCESS: Sent {workflow_type} workflow completion email for alert {alert_id}")

        return {
            **final_state,
            "task_agent_finalized": True,
            "task_agent_execution_status": final_status
        }

    except Exception as e:
        print(f"ERROR: Failed to finalize {workflow_type} workflow: {e}")
        return {
            **state,
            "error": f"Failed to finalize workflow: {e}"
        }


def get_execution_summary_text(state):
    """
    Get formatted text summary of execution for display/logging.

    Args:
        state: Current workflow state

    Returns:
        Formatted string with execution summary
    """
    execution_summary = state.get("execution_summary", [])

    if not execution_summary:
        return "No execution summary available."

    lines = []
    lines.append("=== In-Memory Execution Summary ===")

    for node in execution_summary:
        status_symbol = "✓" if node.get('status') == 'success' else "✗"
        lines.append(f"{node.get('execution_order')}. {status_symbol} {node.get('node_name')}")
        lines.append(f"   Status: {node.get('status', 'unknown').upper()}")
        lines.append(f"   Result: {node.get('result_summary', 'No summary')}")
        if node.get('error_message'):
            lines.append(f"   Error: {node.get('error_message')}")
        lines.append("")

    return "\n".join(lines)


def should_finalize_workflow(state):
    """
    Determine if the workflow should be finalized and email sent.

    Args:
        state: Current workflow state

    Returns:
        Boolean indicating if workflow should be finalized
    """
    # Check if we've reached the end of resolution steps
    resolution_steps = state.get("resolution_steps", [])
    current_step = state.get("current_step", 0)

    # Finalize if all steps are completed
    if current_step >= len(resolution_steps):
        return True

    # Finalize if mail_sent flag is set (from conditional_mail node)
    if state.get("mail_sent"):
        return True

    # Finalize if there's a critical error
    if state.get("error") and "critical" in state.get("error", "").lower():
        return True

    return False
