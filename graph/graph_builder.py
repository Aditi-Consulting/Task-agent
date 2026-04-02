from langgraph.graph import StateGraph, END
from typing import TypedDict, Union

class GraphState(TypedDict):
    alerts: list
    processed: list
    executed: list
    resolutions: list
    generated: list
    next: str
    execution_summary: list  # Store node execution summaries
    summary_id: int        # Alert ID for linking to database summaries
    alert_id: int  # Alert ID from request body

    # Task agent tracking fields
    task_agent_execution_id: int
    task_agent_alert_id: int
    task_agent_start_time: str
    workflow_type: str  # 'k8s'

from app.nodes.read_from_db_node import read_from_db_node
from app.nodes.fetch_remediation_node import fetch_resolution_node
from app.nodes.generate_remediation_node import generate_remediation_node
from app.nodes.execute_action_node import execute_action_node
from app.nodes.send_email_node import send_email

# Task agent summary/finalization functions
from app.utility.summary_tracker import finalize_workflow_and_send_email, should_finalize_workflow


def k8s_workflow_finalization_node(state):
    """
    Finalization node for K8s workflow that ensures execution data is saved
    and sends the completion email.
    """
    from app.utility.summary_tracker import capture_node_execution

    print("🔄 Starting K8s workflow finalization...")

    # Build result message
    result_message = (
        "K8s workflow completed: Email sent with execution results"
    )

    # Track this node explicitly for UI display
    state = capture_node_execution(
        state,
        "finalize_workflow",
        result=result_message
    )

    # Set workflow type for proper tracking
    state["workflow_type"] = "k8s"

    # Call the enhanced finalization function that saves execution data and sends email
    final_state = finalize_workflow_and_send_email(state)

    print("✅ K8s workflow finalization completed")
    return final_state


def build_graph():
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("read_from_db", read_from_db_node)
    graph.add_node("fetch_resolution", fetch_resolution_node)
    graph.add_node("generate_resolution", generate_remediation_node)
    graph.add_node("execute_action", execute_action_node)
    graph.add_node("send_email", send_email)
    graph.add_node("finalize_workflow", k8s_workflow_finalization_node)

    graph.set_entry_point("read_from_db")

    # Define the flow with conditionals
    graph.add_edge("read_from_db", "fetch_resolution")
    graph.add_conditional_edges(
        "fetch_resolution",
        decide_resolution_path
    )

    # After generating resolutions, route back through decision logic
    graph.add_conditional_edges(
        "generate_resolution",
        decide_resolution_path  # Use same router to decide how to execute generated resolutions
    )

    # execute_action always goes to finalization
    graph.add_edge("execute_action", "finalize_workflow")

    # Finalization ends the workflow
    graph.add_edge("finalize_workflow", END)

    return graph


def decide_resolution_path(state: GraphState) -> str:
    """Decide the next node based on resolution type and availability"""
    resolutions = state.get("resolutions", [])
    processed_alerts = state.get("processed", [])
    alerts = state.get("alerts", [])

    # Check if we have any alerts that need resolution generation
    needs_generation = any(
        alert.get("resolution_source") == "needs_generation"
        for alert in processed_alerts
    )

    # PRIORITY 1: If no resolutions exist and we have alerts needing generation, generate them FIRST
    if not resolutions and needs_generation:
        print("No resolutions found, routing to generation")
        return "generate_resolution"

    # PRIORITY 2: If we have resolutions (either from DB or newly generated), proceed with execution
    if resolutions:
        resolution = resolutions[0]
        action_type = resolution.get("action_type", "").lower()

        print(f"Found {len(resolutions)} resolution(s), analyzing action type: {action_type}")

        # Route to specific workflows based on action type
        if any(k8s_word in action_type for k8s_word in ["k8s", "kubernetes", "deployment", "pod", "service"]):
            print("Routing to K8s execution")
            return "execute_action"
        elif "email" in action_type or "notify" in action_type:
            print("Routing to workflow finalization for email")
            return "finalize_workflow"
        else:
            print("Routing to default execution")
            return "execute_action"  # Default execution

    # Fallback: if no resolutions and no generation needed, finalize workflow
    print("No resolutions available and no generation needed, routing to finalization")
    return "finalize_workflow"
