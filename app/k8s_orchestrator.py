from typing import TypedDict, cast
from langgraph.graph import StateGraph, END
import re
import json
from app.utility.llm import call_llm_for_json
from app.utility.summary_tracker import capture_node_execution, initialize_execution_tracking, \
    finalize_workflow_and_send_email, should_finalize_workflow
from app.nodes.send_email_node import run as send_email_run
# Import all your K8s tools with correct function names
from app.tools.k8s_fetch_deployments_tool import fetch_deployments
from app.tools.k8s_fetch_pods_tool import fetch_pods
from app.tools.k8s_fetch_services_tool import fetch_services
from app.tools.k8s_fetch_deployment_details_tool import get_deployment_details
from app.tools.k8s_fetch_service_details_tool import get_service_details
from app.tools.k8s_fetch_pod_logs_tool import fetch_pod_logs
from app.tools.k8s_fix_service_port_tool import fix_service_port
from app.tools.k8s_restart_deployment_tool import restart_deployment
from app.tools.k8s_restart_pod_tool import restart_pod
from app.tools.k8s_scale_deployment_tool import scale_deployment
from app.tools.k8s_pod_details_tool import get_pod_details
from app.tools.k8s_Pods_port_check_tool import port_check

# Helper to ensure all K8sState keys exist to satisfy TypedDict (avoid partial state warnings)
def ensure_k8s_state(state: dict) -> 'K8sState':
    return cast('K8sState', {
         **state,
         'user_input': state.get('user_input', ''),
         'namespace': state.get('namespace', 'default') or 'default',
         'service_name': state.get('service_name', ''),
         'deployment_name': state.get('deployment_name', ''),
         'pod_name': state.get('pod_name', ''),
         'old_port': state.get('old_port') if isinstance(state.get('old_port'), int) else (state.get('old_port') or 0),
         'new_port': state.get('new_port') if isinstance(state.get('new_port'), int) else (state.get('new_port') or 0),
         'expected_port': state.get('expected_port') if isinstance(state.get('expected_port'), int) else (state.get('expected_port') or 0),
         'scale_replicas': state.get('scale_replicas') if isinstance(state.get('scale_replicas'), int) else (state.get('scale_replicas') or 0),
         'result': state.get('result', ''),
         'error': state.get('error', ''),
         'mail_sent': state.get('mail_sent', False),
         'verification_status': state.get('verification_status', ''),
         'verification_message': state.get('verification_message', ''),
         'alerts': state.get('alerts', []),
         'resolution_steps': state.get('resolution_steps', []),
         'current_step': state.get('current_step', 0),
         'llm_analysis': state.get('llm_analysis', {}),
         'execution_summary': state.get('execution_summary', []),
         'summary_id': state.get('summary_id', 0)
    })


# NEW: Helper to detect error payloads consistently
def _is_error_payload(result) -> str | None:
    """Return standardized error message if result indicates failure (404/not found/etc.)."""
    try:
        if result is None:
            return "Empty result returned"
        if isinstance(result, list):  # handle pod details list error format
            if result and isinstance(result[0], dict) and result[0].get("error"):
                msg = result[0].get("message") or result[0].get("error")
                return f"{result[0].get('error')}: {msg}".strip()
        if isinstance(result, str):
            lowered = result.lower()
            if lowered.startswith("error") or "404" in lowered or "not found" in lowered:
                return result
            # Some backend error responses may embed JSON as string
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict) and parsed.get("error"):
                    return f"{parsed.get('error')}: {parsed.get('message', '')}".strip()
            except Exception:
                pass
        elif isinstance(result, dict):
            if result.get("error"):
                msg = result.get("message") or result.get("error")
                return f"{result.get('error')}: {msg}".strip()
        return None
    except Exception as e:
        return f"Error evaluating payload: {e}"


class K8sState(TypedDict):
    user_input: str
    namespace: str
    service_name: str
    deployment_name: str
    pod_name: str
    old_port: int
    new_port: int  # kept for backward compatibility (will mirror expected_port)
    expected_port: int  # explicit expected port extracted from alert
    scale_replicas: int
    result: str
    error: str
    mail_sent: bool
    verification_status: str
    verification_message: str
    alerts: list
    resolution_steps: list  # LLM-generated resolution steps
    current_step: int  # Track current step
    llm_analysis: dict  # Store LLM analysis results
    execution_summary: list  # Store node execution summaries
    summary_id: int  # Alert ID for linking to database summaries


def extract_k8s_parameters_and_resolution(state: K8sState) -> K8sState:
    """Extract parameters and resolution steps from user input using actual LLM analysis (robust port logic)."""
    user_input = state.get("user_input", "")
    print(f"DEBUG: Analyzing user input with LLM: {user_input}")
    # Initialize execution tracking
    state = initialize_execution_tracking(state)

    # Use actual LLM to analyze the input and extract resolution steps
    llm_analysis = analyze_k8s_issue_with_llm(user_input)

    if "__error__" in llm_analysis:
        print(f"WARNING: LLM analysis failed: {llm_analysis['__error__']}")
        # Capture error and fallback to regex-based extraction
        state = capture_node_execution(state, "extract_parameters", error=llm_analysis['__error__'])
        return extract_k8s_parameters_fallback(state)

    # Extract parameters from LLM analysis
    namespace = llm_analysis.get("namespace", "default") or "default"
    service_name = llm_analysis.get("service_name", "") or ""
    deployment_name = llm_analysis.get("deployment_name", service_name) or service_name
    pod_name = llm_analysis.get("pod_name", "") or ""
    llm_new_port = llm_analysis.get("new_port")
    llm_old_port = llm_analysis.get("old_port")
    scale_replicas = llm_analysis.get("scale_replicas")

    # Always prefer explicit expected port from alert text
    lowered = user_input.lower()
    regex_expected_port = None
    matched_pattern = None
    expected_port_patterns = [
        r"expected port[^\d]*(\d+)",
        r"expected port is[^\d]*(\d+)",
        r"expected port:\s*(\d+)",
        r"\(expected (\d+)\)",
        r"\(expected port[^\d]*(\d+)\)",
        r"expected\s+(\d+)",
        r"port\s*should\s*be\s*(\d+)"
    ]
    for pat in expected_port_patterns:
        m = re.search(pat, lowered)
        if m:
            try:
                regex_expected_port = int(m.group(1))
                matched_pattern = pat
                break
            except ValueError:
                continue

    expected_port_source = "regex" if regex_expected_port is not None else (
        "llm" if llm_new_port is not None else "none")
    expected_port = regex_expected_port if regex_expected_port is not None else llm_new_port

    # Improve service name extraction if missing
    if not service_name:
        svc_patterns = [
            r"service\s+([a-z0-9-]+)",
            r"The\s+([a-z0-9-]+)\s+is\s+exposing",
            r"Service\s+([a-z0-9-]+)\s+in\s+namespace"
        ]
        for sp in svc_patterns:
            sm = re.search(sp, user_input)
            if sm:
                service_name = sm.group(1)
                deployment_name = service_name
                print(f"DEBUG: Service name extracted via pattern '{sp}' -> {service_name}")
                break

    # Log extraction decisions
    print(
        f"DEBUG: Port extraction -> source={expected_port_source}, pattern={matched_pattern}, regex_expected_port={regex_expected_port}, llm_new_port={llm_new_port}, final expected_port={expected_port}"
    )

    # Override resolution steps for port issues to enforce deterministic sequence
    resolution_steps = llm_analysis.get("resolution_steps", [])
    if expected_port and service_name and re.search(r"port|expos", lowered):
        resolution_steps = ["get_service_details", "fix_service_port", "verify_resolution"]
        print("DEBUG: Overriding resolution_steps for port issue ->", resolution_steps)
    # For scaling issues ensure deployment detail + scale + verify
    if llm_analysis.get("issue_type") == "scaling_needed" and deployment_name:
        resolution_steps = ["get_deployment_details", "scale_deployment", "verify_resolution", "conditional_mail"]
        print("DEBUG: Overriding resolution_steps for scaling issue ->", resolution_steps)
    # NEW: Pod down with explicit pod name -> use get_pod_details first, then analyze/optional restart, verify, mail
    pod_name_in_text = None
    m_pod = re.search(r"pod\s+([a-z0-9-]+)", lowered)
    if m_pod:
        pod_name_in_text = m_pod.group(1)
        if llm_analysis.get("issue_type") == "pod_down":
            # Focused remediation path; attempt direct pod details early
            pod_name = pod_name_in_text  # overwrite extracted
            resolution_steps = ["get_pod_details", "verify_resolution", "conditional_mail"]
            print("DEBUG: Overriding resolution_steps for pod_down with explicit pod ->", resolution_steps)

    summary = (
        f"Analyzed K8s issue: {llm_analysis.get('issue_type', 'unknown')} severity="
        f"{llm_analysis.get('severity', 'unknown')} steps={resolution_steps} expected_port={expected_port} source={expected_port_source}"
    )
    state = capture_node_execution(state, "extract_parameters", result=summary)

    return ensure_k8s_state({
        **state,
        "namespace": namespace,
        "service_name": service_name,
        "deployment_name": deployment_name,
        "pod_name": pod_name,
        "old_port": llm_old_port if isinstance(llm_old_port, int) else None,
        "expected_port": expected_port if isinstance(expected_port, int) else None,
        "new_port": expected_port if isinstance(expected_port, int) else None,
        "scale_replicas": scale_replicas if isinstance(scale_replicas, int) else None,
        "resolution_steps": resolution_steps,
        "current_step": 0,
        "llm_analysis": llm_analysis
    })


def analyze_k8s_issue_with_llm(user_input: str) -> dict:
    """Use actual LLM to analyze the K8s issue and determine resolution steps"""

    prompt = f"""
    Analyze this Kubernetes issue and provide a structured resolution plan in JSON format:

    Issue Description: {user_input}

    Extract parameters from the issue description above and create a step-by-step resolution plan. 

    IMPORTANT: Extract actual values from the issue description. Do NOT return placeholder text like "extracted namespace" - return the ACTUAL namespace name mentioned in the issue, or use "default" if none is mentioned.

    Provide a JSON response with these exact fields:

    {{
        "issue_type": "one of: pod_down, port_misconfiguration, scaling_needed, deployment_restart, service_issue, general",
        "severity": "one of: low, medium, high, critical",
        "namespace": "the actual namespace name from the issue, or 'default' if not specified",
        "service_name": "the actual service name from the issue, or null if not mentioned",
        "deployment_name": "the actual deployment name from the issue, or null if not mentioned",
        "pod_name": "the actual pod name from the issue, or null if not mentioned",
        "new_port": integer or null,
        "old_port": integer or null,
        "scale_replicas": integer or null,
        "resolution_steps": [
            "ordered list of action names"
        ]
    }}

    Available actions for resolution_steps:
    - "fetch_pods": Get pod status
    - "fetch_deployments": Get deployment status  
    - "fetch_services": Get service status
    - "get_pod_details": Get detailed pod information
    - "get_deployment_details": Get detailed deployment information
    - "get_service_details": Get detailed service information
    - "fetch_pod_logs": Get pod logs
    - "port_check": Check pod ports
    - "analyze_pod_health": Analyze fetched pods for health issues
    - "restart_unhealthy_pods": Restart pods that are not running
    - "fix_service_port": Fix service port configuration
    - "restart_deployment": Restart a deployment
    - "restart_pod": Restart a specific pod
    - "scale_deployment": Scale deployment replicas
    - "verify_resolution": Verify that issues are resolved
    - "conditional_mail": Send notification email if needed

    Guidelines:
    - For pod down alerts: start with "fetch_pods", then "analyze_pod_health", then "restart_unhealthy_pods", then "verify_resolution", then "conditional_mail"
    - For port issues: start with "get_service_details", then "fix_service_port", then "verify_resolution"
    - For scaling: start with "get_deployment_details", then "scale_deployment", then "verify_resolution"
    - Always end critical issues with "conditional_mail"

    Return ONLY valid JSON, no additional text.
    """

    try:
        result = call_llm_for_json(prompt, model="gpt-4o-mini", temperature=0.0, max_tokens=1000)
        print(f"DEBUG: LLM analysis result: {result}")
        return result
    except Exception as e:
        print(f"ERROR: LLM analysis failed: {e}")
        return {"__error__": f"LLM analysis failed: {e}"}


def extract_k8s_parameters_fallback(state: K8sState) -> K8sState:
    """Fallback parameter extraction using regex when LLM fails"""
    user_input = state.get("user_input", "")

    # Use original regex-based extraction
    namespace_match = re.search(r"namespace[=:\s]+([a-zA-Z0-9-]+)", user_input)
    namespace = namespace_match.group(1) if namespace_match else "default"

    service_match = re.search(r"The ([a-zA-Z0-9-]+) is exposing", user_input)
    if not service_match:
        service_match = re.search(r"(service|app)[=:\s]+([a-zA-Z0-9-]+)", user_input)
        service_name = service_match.group(2) if service_match else ""
    else:
        service_name = service_match.group(1)

    deployment_name = service_name
    pod_name = ""

    expected_port_match = re.search(r"Expected port is (\d+)", user_input)
    new_port = int(expected_port_match.group(1)) if expected_port_match else None
    old_port = None

    # Determine resolution steps based on issue type
    resolution_steps = []
    if re.search(r"pod.*down", user_input.lower()):
        resolution_steps = ["fetch_pods", "analyze_pod_health", "restart_unhealthy_pods", "conditional_mail"]
    elif re.search(r"(port|exposing)", user_input.lower()) and new_port:
        resolution_steps = ["get_service_details", "fix_service_port", "verify_resolution"]
    else:
        resolution_steps = ["fetch_deployments", "fetch_services", "fetch_pods"]

    return ensure_k8s_state({
        **state,
        "namespace": namespace,
        "service_name": service_name,
        "deployment_name": deployment_name,
        "pod_name": pod_name,
        "old_port": old_port if isinstance(old_port, int) else None,
        "new_port": new_port if isinstance(new_port, int) else None,
        "expected_port": new_port if isinstance(new_port, int) else None,
        "scale_replicas": None,
        "resolution_steps": resolution_steps,
        "current_step": 0,
        "llm_analysis": {"fallback": True}
    })


def llm_decision_router(state: K8sState) -> str:
    """LLM-powered router that decides next action based on resolution steps"""

    resolution_steps = state.get("resolution_steps", [])
    current_step = state.get("current_step", 0)

    print(f"DEBUG: LLM Router - Step {current_step} of {len(resolution_steps)}")

    # Check if workflow should be finalized first
    if should_finalize_workflow(state):
        print("DEBUG: Workflow should be finalized, routing to finalize_workflow")
        return "finalize_workflow"

    # NEW: If an error has been recorded, finalize early
    if state.get("error"):
        print(f"DEBUG: Error detected in state -> {state.get('error')}. Routing to finalize_workflow.")
        return "finalize_workflow"

    if state.get("mail_sent"):
        return "finalize_workflow"

    if current_step >= len(resolution_steps):
        print("DEBUG: All resolution steps completed, routing to finalize_workflow")
        return "finalize_workflow"

    current_action = resolution_steps[current_step]
    print(f"DEBUG: LLM Router - Executing step: {current_action}")

    # Map resolution step names to actual node names
    action_mapping = {
        "fetch_pods": "fetch_pods",
        "analyze_pod_health": "analyze_pod_health",
        "restart_unhealthy_pods": "restart_unhealthy_pods",
        "verify_resolution": "verify_resolution",
        "conditional_mail": "conditional_mail",
        "get_service_details": "get_service_details",
        "fix_service_port": "fix_service_port",
        "fetch_deployments": "fetch_deployments",
        "fetch_services": "fetch_services",
        "get_deployment_details": "get_deployment_details",
        "get_pod_details": "get_pod_details",
        "fetch_pod_logs": "fetch_pod_logs",
        "port_check": "port_check",
        "restart_deployment": "restart_deployment",
        "restart_pod": "restart_pod",
        "scale_deployment": "scale_deployment"
    }

    mapped_action = action_mapping.get(current_action, current_action)
    return mapped_action


def analyze_pod_health_node(state: K8sState) -> K8sState:
    """Analyze pod health based on fetch_pods result"""
    try:
        result = state.get("result", "")

        # Parse pods data
        if isinstance(result, str):
            try:
                pods_data = json.loads(result)
            except json.JSONDecodeError:
                pods_data = []
        else:
            pods_data = result

        unhealthy_pods = []
        healthy_pods = []

        if isinstance(pods_data, list):
            for pod in pods_data:
                if isinstance(pod, dict):
                    phase = pod.get('phase', '').lower()
                    name = pod.get('name', '')
                    if name:
                        if phase != 'running':
                            unhealthy_pods.append(name)
                        else:
                            healthy_pods.append(name)

        analysis_result = {
            "unhealthy_pods": unhealthy_pods,
            "healthy_pods": healthy_pods,
            "total_pods": len(unhealthy_pods) + len(healthy_pods),
            "analysis": f"Found {len(unhealthy_pods)} unhealthy pods and {len(healthy_pods)} healthy pods"
        }

        print(f"DEBUG: Pod health analysis: {analysis_result}")

        # Capture execution summary
        state = capture_node_execution(state, "analyze_pod_health", result=analysis_result)

        return ensure_k8s_state({
            **state,
            "result": json.dumps(analysis_result),
            "current_step": state.get("current_step", 0) + 1
        })
    except Exception as e:
        state = capture_node_execution(state, "analyze_pod_health", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error analyzing pod health: {e}"})


def restart_unhealthy_pods_node(state: K8sState) -> K8sState:
    """Restart unhealthy pods identified in analysis"""
    try:
        result = state.get("result", "")
        analysis_data = json.loads(result) if isinstance(result, str) else result

        unhealthy_pods = analysis_data.get("unhealthy_pods", [])

        if not unhealthy_pods:
            # Check if pod name was specified in original input
            user_input = state.get("user_input", "")
            pod_name_match = re.search(r"pod_name[\"']:\s*[\"']([^\"']+)[\"']", user_input)

            if pod_name_match:
                specified_pod = pod_name_match.group(1)
                if specified_pod == "affected-pod" or specified_pod not in analysis_data.get("healthy_pods", []):
                    result_msg = f"No actual unhealthy pods found. Specified pod '{specified_pod}' appears to be a placeholder."
                    state = capture_node_execution(state, "restart_unhealthy_pods", result=result_msg)
                    return ensure_k8s_state({
                        **state,
                        "result": result_msg,
                        "mail_sent": True,
                        "verification_status": "investigation_required",
                        "verification_message": f"Pod down alert received but no unhealthy pods found. Alert mentioned placeholder pod: {specified_pod}",
                        "current_step": state.get("current_step", 0) + 1
                    })

            result_msg = "No unhealthy pods found to restart"
            state = capture_node_execution(state, "restart_unhealthy_pods", result=result_msg)
            return ensure_k8s_state({
                **state,
                "result": result_msg,
                "current_step": state.get("current_step", 0) + 1
            })

        # Restart the first unhealthy pod
        pod_to_restart = unhealthy_pods[0]
        namespace = state.get("namespace", "default")

        action_input = {
            "namespace": namespace,
            "pod_name": pod_to_restart
        }

        restart_result = restart_pod(action_input)
        result_msg = f"Restarted unhealthy pod: {pod_to_restart}. Result: {restart_result}"

        # Capture execution summary
        state = capture_node_execution(state, "restart_unhealthy_pods", result=result_msg)

        return ensure_k8s_state({
            **state,
            "result": result_msg,
            "pod_name": pod_to_restart,
            "current_step": state.get("current_step", 0) + 1
        })
    except Exception as e:
        state = capture_node_execution(state, "restart_unhealthy_pods", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error restarting unhealthy pods: {e}"})


def verify_resolution_node(state: K8sState) -> K8sState:
    """Verify that the resolution was successful"""
    try:
        # Re-fetch relevant resources to verify resolution
        namespace = state.get("namespace", "default")

        # Verify based on issue type from LLM analysis
        llm_analysis = state.get("llm_analysis", {})
        issue_type = llm_analysis.get("issue_type", "general")

        if issue_type == "pod_down":
            # Use pod-specific details if pod name available
            pod_name = state.get("pod_name")
            if pod_name:
                verification_result = get_pod_details([{"name": pod_name, "namespace": namespace}])
                verification_message = f"Pod verification completed. Details: {verification_result}" if not _is_error_payload(verification_result) else f"Pod verification failed: {_is_error_payload(verification_result)}"
            else:
                verification_result = fetch_pods(namespace)
                verification_message = f"Pod verification completed. Current pod status: {verification_result}"
        elif issue_type == "port_misconfiguration":
            service_name = state.get("service_name", "")
            if service_name:
                verification_result = get_service_details(namespace, service_name)
                verification_message = f"Port verification completed. Service details: {verification_result}"
            else:
                verification_result = "No service name available for verification"
                verification_message = verification_result
        else:
            # For scaling/general deployment issues verify deployment exists and replica count
            deployment_name = state.get("deployment_name", "")
            if deployment_name:
                deployment_details = get_deployment_details(namespace, deployment_name)
                err = _is_error_payload(deployment_details)
                if err:
                    verification_result = deployment_details
                    verification_message = f"Verification failed: {err}"
                else:
                    verification_result = deployment_details
                    verification_message = f"General verification completed. Deployment details: {deployment_details}"
            else:
                verification_result = fetch_deployments(namespace)
                verification_message = f"General verification completed. Deployment status: {verification_result}"

        # Detect error
        err_payload = _is_error_payload(verification_result)
        if err_payload:
            state = capture_node_execution(state, "verify_resolution", error=err_payload)
            return ensure_k8s_state({
                **state,
                "error": err_payload,
                "verification_status": "failed",
                "verification_message": err_payload,
                "current_step": len(state.get("resolution_steps", []))  # force finalize
            })
        # Capture execution summary success
        state = capture_node_execution(state, "verify_resolution", result=verification_message)

        return ensure_k8s_state({
            **state,
            "result": verification_message,
            "verification_status": "completed",
            "verification_message": verification_message,
            "current_step": state.get("current_step", 0) + 1
        })
    except Exception as e:
        state = capture_node_execution(state, "verify_resolution", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error during verification: {e}"})


def conditional_mail_node(state: K8sState) -> K8sState:
    """Decide whether to send mail based on LLM analysis and current state"""
    try:
        llm_analysis = state.get("llm_analysis", {})
        severity = llm_analysis.get("severity", "low")
        issue_type = llm_analysis.get("issue_type", "general")

        # Determine if mail should be sent based on LLM analysis
        should_send_mail = False
        mail_reason = ""

        if severity in ["high", "critical"]:
            should_send_mail = True
            mail_reason = f"High/Critical severity {issue_type} issue"
        elif "placeholder" in state.get("result", "").lower() or "affected-pod" in state.get("result", "").lower():
            should_send_mail = True
            mail_reason = "Alert received but no actual issues found - investigation required"
        elif state.get("error"):
            should_send_mail = True
            mail_reason = f"Error occurred during resolution: {state.get('error')}"

        if should_send_mail:
            # Capture execution summary
            state = capture_node_execution(state, "conditional_mail", result=f"Mail sending triggered: {mail_reason}")
            return ensure_k8s_state({
                **state,
                "mail_sent": True,
                "verification_status": "investigation_required",
                "verification_message": mail_reason,
                "current_step": state.get("current_step", 0) + 1
            })
        else:
            result_msg = f"Resolution completed successfully. Mail not required. Reason: {issue_type} resolved without issues."
            state = capture_node_execution(state, "conditional_mail", result=result_msg)
            return ensure_k8s_state({
                **state,
                "result": result_msg,
                "current_step": state.get("current_step", 0) + 1
            })
    except Exception as e:
        state = capture_node_execution(state, "conditional_mail", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error in conditional mail: {e}"})


# Enhanced versions of existing nodes with step tracking
def fetch_pods_node_enhanced(state: K8sState) -> K8sState:
    """Enhanced fetch_pods with step tracking"""
    try:
        namespace = state.get("namespace", "default")
        result = fetch_pods(namespace)
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "fetch_pods", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})

        # Capture execution summary
        state = capture_node_execution(state, "fetch_pods", result=f"Fetched pods from namespace {namespace}")

        return ensure_k8s_state({
            **state,
            "result": str(result),
            "current_step": state.get("current_step", 0) + 1
        })
    except Exception as e:
        state = capture_node_execution(state, "fetch_pods", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching pods: {e}"})


def fix_service_port_node_enhanced(state: K8sState) -> K8sState:
    """Fix service port using expected_port; avoid false 'already running' and old->old updates."""
    try:
        namespace = state.get("namespace", "default")
        service_name = state.get("service_name", "")
        expected_port = state.get("expected_port") or state.get("new_port")
        provided_old_port = state.get("old_port")

        if not service_name or expected_port is None:
            error_msg = "Service name and expected port required."
            state = capture_node_execution(state, "fix_service_port", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        service_details = get_service_details(namespace, service_name)
        # NEW: Treat missing service (404) as error early
        svc_err = _is_error_payload(service_details)
        if svc_err:
            state = capture_node_execution(state, "fix_service_port", error=svc_err)
            return ensure_k8s_state({**state, "error": svc_err, "current_step": len(state.get("resolution_steps", []))})

        running_port = None
        parsed = None
        if isinstance(service_details, dict):
            parsed = service_details
        elif isinstance(service_details, str):
            try:
                parsed = json.loads(service_details)
            except Exception:
                parsed = {}
        else:
            parsed = {}

        # Attempt structured port extraction
        if isinstance(parsed, dict):
            ports_candidates = parsed.get("ports") or parsed.get("spec", {}).get("ports")
            if isinstance(ports_candidates, list) and ports_candidates:
                first = ports_candidates[0]
                if isinstance(first, dict):
                    running_port = first.get("port") or first.get("targetPort") or first.get("nodePort")
                elif isinstance(first, int):
                    running_port = first
        # Regex fallback if still None and raw string available
        if running_port is None and isinstance(service_details, str):
            m = re.search(r"\bport\b[^0-9]*(\d+)", service_details.lower())
            if m:
                running_port = int(m.group(1))

        if running_port is None:
            running_port = provided_old_port

        print(
            f"DEBUG: Service={service_name} running_port={running_port} expected_port={expected_port} provided_old_port={provided_old_port}")

        if running_port is not None and expected_port == running_port:
            msg = f"Service {service_name} already running on expected port {expected_port}. No change needed."
            state = capture_node_execution(state, "fix_service_port", result=msg)
            return ensure_k8s_state({
                **state,
                "result": msg,
                "old_port": running_port,
                "new_port": expected_port,
                "current_step": state.get("current_step", 0) + 1
            })

        effective_old_port = running_port if running_port is not None else provided_old_port
        if effective_old_port is None:
            # If still unknown, abort with clear message
            error_msg = "Unable to determine current running port; aborting port fix to prevent incorrect update."
            state = capture_node_execution(state, "fix_service_port", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg, "current_step": state.get("current_step", 0) + 1})

        action_input = {
            "namespace": namespace,
            "service_name": service_name,
            "old_port": effective_old_port,
            "new_port": expected_port
        }
        tool_result = fix_service_port(action_input)

        msg = f"Changed service {service_name} port from {effective_old_port} to {expected_port}"
        state = capture_node_execution(state, "fix_service_port", result=msg)

        return ensure_k8s_state({
            **state,
            "result": f"{msg}. Tool: {tool_result}",
            "old_port": effective_old_port,
            "new_port": expected_port,
            "expected_port": expected_port,
            "current_step": state.get("current_step", 0) + 1
        })
    except Exception as e:
        state = capture_node_execution(state, "fix_service_port", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fixing service port: {e}", "current_step": state.get("current_step", 0) + 1})


def build_k8s_graph():
    """Build the LLM-powered K8s workflow graph"""
    workflow = StateGraph(K8sState)

    # Add parameter extraction and LLM analysis node
    workflow.add_node("extract_parameters", extract_k8s_parameters_and_resolution)

    # Add LLM-guided action nodes
    workflow.add_node("fetch_pods", fetch_pods_node_enhanced)
    workflow.add_node("analyze_pod_health", analyze_pod_health_node)
    workflow.add_node("restart_unhealthy_pods", restart_unhealthy_pods_node)
    workflow.add_node("verify_resolution", verify_resolution_node)
    workflow.add_node("conditional_mail", conditional_mail_node)
    workflow.add_node("fix_service_port", fix_service_port_node_enhanced)

    # Add all K8s operation nodes
    workflow.add_node("fetch_deployments", fetch_deployments_node)
    workflow.add_node("fetch_services", fetch_services_node)
    workflow.add_node("get_deployment_details", get_deployment_details_node)
    workflow.add_node("get_service_details", get_service_details_node)
    workflow.add_node("get_pod_details", get_pod_details_node)
    workflow.add_node("fetch_pod_logs", fetch_pod_logs_node)
    workflow.add_node("port_check", port_check_node)
    workflow.add_node("restart_deployment", restart_deployment_node)
    workflow.add_node("restart_pod", restart_pod_node)
    workflow.add_node("scale_deployment", scale_deployment_node)
    workflow.add_node("send_mail", send_mail_node)
    workflow.add_node("finalize_workflow", workflow_finalization_node)

    # Set entry point
    workflow.set_entry_point("extract_parameters")

    # Add conditional edges with LLM decision making
    workflow.add_conditional_edges(
        "extract_parameters",
        llm_decision_router,
        {
            "fetch_pods": "fetch_pods",
            "analyze_pod_health": "analyze_pod_health",
            "restart_unhealthy_pods": "restart_unhealthy_pods",
            "verify_resolution": "verify_resolution",
            "conditional_mail": "conditional_mail",
            "fix_service_port": "fix_service_port",
            "fetch_deployments": "fetch_deployments",
            "fetch_services": "fetch_services",
            "get_deployment_details": "get_deployment_details",
            "get_service_details": "get_service_details",
            "get_pod_details": "get_pod_details",
            "fetch_pod_logs": "fetch_pod_logs",
            "port_check": "port_check",
            "restart_deployment": "restart_deployment",
            "restart_pod": "restart_pod",
            "scale_deployment": "scale_deployment",
            "finalize_workflow": "finalize_workflow"
        }
    )

    # Add conditional edges from each node back to router for next step
    for node_name in ["fetch_pods", "analyze_pod_health", "restart_unhealthy_pods",
                      "verify_resolution", "conditional_mail", "fix_service_port",
                      "fetch_deployments", "fetch_services", "get_deployment_details",
                      "get_service_details", "get_pod_details", "fetch_pod_logs",
                      "port_check", "restart_deployment", "restart_pod", "scale_deployment"]:
        workflow.add_conditional_edges(
            node_name,
            llm_decision_router,
            {
                "fetch_pods": "fetch_pods",
                "analyze_pod_health": "analyze_pod_health",
                "restart_unhealthy_pods": "restart_unhealthy_pods",
                "verify_resolution": "verify_resolution",
                "conditional_mail": "conditional_mail",
                "fix_service_port": "fix_service_port",
                "fetch_deployments": "fetch_deployments",
                "fetch_services": "fetch_services",
                "get_deployment_details": "get_deployment_details",
                "get_service_details": "get_service_details",
                "get_pod_details": "get_pod_details",
                "fetch_pod_logs": "fetch_pod_logs",
                "port_check": "port_check",
                "restart_deployment": "restart_deployment",
                "restart_pod": "restart_pod",
                "scale_deployment": "scale_deployment",
                "finalize_workflow": "finalize_workflow"
            }
        )

    # Finalize workflow ends the process
    workflow.add_edge("finalize_workflow", END)

    return workflow.compile()


# Keep existing node functions for compatibility
def extract_k8s_parameters(state: K8sState) -> K8sState:
    """Legacy function - redirects to LLM-powered version"""
    return extract_k8s_parameters_and_resolution(state)


def k8s_action_router(state: K8sState) -> str:
    """Legacy function - redirects to LLM-powered router"""
    return llm_decision_router(state)


# Keep all existing node implementations for backward compatibility
def fetch_deployments_node(state: K8sState) -> K8sState:
    try:
        namespace = state.get("namespace", "default")
        result = fetch_deployments(namespace)
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "fetch_deployments", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "fetch_deployments",
                                       result=f"Fetched deployments from namespace {namespace}")
        return ensure_k8s_state({**state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "fetch_deployments", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching deployments: {e}"})


def fetch_pods_node(state: K8sState) -> K8sState:
    """Legacy fetch_pods_node - kept for compatibility"""
    return fetch_pods_node_enhanced(state)


def fetch_services_node(state: K8sState) -> K8sState:
    try:
        namespace = state.get("namespace", "default")
        result = fetch_services(namespace)
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "fetch_services", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "fetch_services", result=f"Fetched services from namespace {namespace}")
        return ensure_k8s_state({**state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "fetch_services", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching services: {e}"})


def get_deployment_details_node(state: K8sState) -> K8sState:
    """Node wrapper for get_deployment_details tool"""
    try:
        namespace = state.get("namespace", "default")
        deployment_name = state.get("deployment_name", "")
        if not deployment_name:
            error_msg = "Deployment name required for details"
            state = capture_node_execution(state, "get_deployment_details", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        result = get_deployment_details(namespace, deployment_name)
        err_payload = _is_error_payload(result)
        if err_payload:
            # If structured dict returned include it in full_result
            structured = result if isinstance(result, dict) else {"raw": result}
            state = capture_node_execution(state, "get_deployment_details", result=structured, error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "get_deployment_details",
                                       result=f"Retrieved details for deployment {deployment_name}")
        return ensure_k8s_state({**state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "get_deployment_details", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching deployment details: {e}"})


def get_service_details_node(state: K8sState) -> K8sState:
    try:
        namespace = state.get("namespace", "default")
        service_name = state.get("service_name", "")
        if not service_name:
            error_msg = "Service name required for details"
            state = capture_node_execution(state, "get_service_details", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        result = get_service_details(namespace, service_name)
        err_payload = _is_error_payload(result)
        if err_payload:
            structured = result if isinstance(result, dict) else {"raw": result}
            updated_state = capture_node_execution(state, "get_service_details", result=structured, error=err_payload)
            return ensure_k8s_state({**updated_state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})

        # Attempt to extract current running port and update old_port in state
        running_port = None
        parsed = result if isinstance(result, dict) else None
        if parsed is None and isinstance(result, str):
            try:
                parsed = json.loads(result)
            except Exception:
                parsed = None
        if isinstance(parsed, dict):
            ports_candidates = parsed.get("ports") or parsed.get("spec", {}).get("ports")
            if isinstance(ports_candidates, list) and ports_candidates:
                first = ports_candidates[0]
                if isinstance(first, dict):
                    running_port = first.get("port") or first.get("targetPort") or first.get("nodePort")
                elif isinstance(first, int):
                    running_port = first
        if running_port is None and isinstance(result, str):
            m = re.search(r"\bport\b[^0-9]*(\d+)", result.lower())
            if m:
                running_port = int(m.group(1))
        if running_port:
            state["old_port"] = running_port

        updated_state = capture_node_execution(state, "get_service_details", result=f"Retrieved details for service {service_name}")
        return ensure_k8s_state({**updated_state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "get_service_details", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching service details: {e}"})


def fetch_pod_logs_node(state: K8sState) -> K8sState:
    """Node wrapper for fetch_pod_logs tool"""
    try:
        namespace = state.get("namespace", "default")
        pod_name = state.get("pod_name", "")
        if not pod_name:
            error_msg = "Pod name required for logs"
            state = capture_node_execution(state, "fetch_pod_logs", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        # Tool expects a single action_input (dict or string); provide dict
        result = fetch_pod_logs({"namespace": namespace, "pod_name": pod_name})
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "fetch_pod_logs", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "fetch_pod_logs", result=f"Retrieved logs for pod {pod_name}")
        return ensure_k8s_state({**state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "fetch_pod_logs", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching pod logs: {e}"})


def get_pod_details_node(state: K8sState) -> K8sState:
    """Node wrapper for get_pod_details tool with early failure if pod missing"""
    try:
        namespace = state.get("namespace", "default")
        pod_name = state.get("pod_name", "")
        # Attempt extraction if missing but user_input contains pod pattern
        if not pod_name:
            ui = state.get("user_input", "").lower()
            m = re.search(r"pod\s+([a-z0-9-]+)", ui)
            if m:
                pod_name = m.group(1)
                state["pod_name"] = pod_name
        if not pod_name:
            error_msg = "Pod name required for details"
            state = capture_node_execution(state, "get_pod_details", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        result = get_pod_details([{"name": pod_name, "namespace": namespace}])
        err_payload = _is_error_payload(result)
        if err_payload:
            # Early finalize on missing pod
            structured = result if isinstance(result, (dict, list)) else {"raw": result}
            state = capture_node_execution(state, "get_pod_details", result=structured, error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "get_pod_details", result=f"Retrieved details for pod {pod_name}")
        return ensure_k8s_state({**state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "get_pod_details", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error fetching pod details: {e}"})


def port_check_node(state: K8sState) -> K8sState:
    """Node wrapper for port_check tool"""
    try:
        namespace = state.get("namespace", "default")
        pod_name = state.get("pod_name", "")
        if not pod_name:
            error_msg = "Pod name required for port check"
            state = capture_node_execution(state, "port_check", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        # Port check requires a port; attempt to derive expected_port/new_port or default 80
        derived_port = state.get('expected_port') or state.get('new_port') or 80
        result = port_check({"namespace": namespace, "pod_name": pod_name, "port": derived_port})
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "port_check", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "port_check", result=f"Checked ports for pod {pod_name}")
        return ensure_k8s_state({**state, "result": str(result), "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "port_check", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error checking pod ports: {e}"})


def fix_service_port_node(state: K8sState) -> K8sState:
    """Legacy fix_service_port_node - redirects to enhanced version"""
    return fix_service_port_node_enhanced(state)


def restart_deployment_node(state: K8sState) -> K8sState:
    """Node wrapper for restart_deployment tool"""
    try:
        namespace = state.get("namespace", "default")
        deployment_name = state.get("deployment_name", "")
        if not deployment_name:
            error_msg = "Deployment name required for restart"
            state = capture_node_execution(state, "restart_deployment", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        action_input = {
            "namespace": namespace,
            "deployment_name": deployment_name
        }
        result = restart_deployment(action_input)
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "restart_deployment", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "restart_deployment", result=f"Restarted deployment {deployment_name}")
        return ensure_k8s_state({**state, "result": result, "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "restart_deployment", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error restarting deployment: {e}"})


def restart_pod_node(state: K8sState) -> K8sState:
    """Node wrapper for restart_pod tool"""
    try:
        namespace = state.get("namespace", "default")
        pod_name = state.get("pod_name", "")
        if not pod_name:
            error_msg = "Pod name required for restart"
            state = capture_node_execution(state, "restart_pod", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        action_input = {
            "namespace": namespace,
            "pod_name": pod_name
        }
        result = restart_pod(action_input)
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "restart_pod", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "restart_pod", result=f"Restarted pod {pod_name}")
        return ensure_k8s_state({**state, "result": result, "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "restart_pod", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error restarting pod: {e}"})


def scale_deployment_node(state: K8sState) -> K8sState:
    """Node wrapper for scale_deployment tool"""
    try:
        namespace = state.get("namespace", "default")
        deployment_name = state.get("deployment_name", "")
        scale_replicas = state.get("scale_replicas", 1)

        if not deployment_name:
            error_msg = "Deployment name required for scaling"
            state = capture_node_execution(state, "scale_deployment", error=error_msg)
            return ensure_k8s_state({**state, "error": error_msg})

        action_input = {
            "namespace": namespace,
            "deployment_name": deployment_name,
            "replicas": scale_replicas
        }
        result = scale_deployment(action_input)
        err_payload = _is_error_payload(result)
        if err_payload:
            state = capture_node_execution(state, "scale_deployment", error=err_payload)
            return ensure_k8s_state({**state, "error": err_payload, "current_step": len(state.get("resolution_steps", []))})
        state = capture_node_execution(state, "scale_deployment",
                                       result=f"Scaled deployment {deployment_name} to {scale_replicas} replicas")
        return ensure_k8s_state({**state, "result": result, "current_step": state.get("current_step", 0) + 1})
    except Exception as e:
        state = capture_node_execution(state, "scale_deployment", error=str(e))
        return ensure_k8s_state({**state, "error": f"Error scaling deployment: {e}"})


def send_mail_node(state: K8sState) -> K8sState:
    """Wrapper for the existing send_email_node"""
    try:
        # Ensure alerts field exists for send_email_node
        if "alerts" not in state:
            # Create alert data from LLM analysis
            llm_analysis = state.get("llm_analysis", {})
            state["alerts"] = [{
                "ticket_id": f"k8s-{llm_analysis.get('issue_type', 'alert')}",
                "severity": llm_analysis.get('severity', 'medium'),
                "issue_type": llm_analysis.get('issue_type', 'general'),
                "ticket": state.get("user_input", "K8s alert received"),
                "id": 1
            }]

        # Set verification fields for send_email_node
        if not state.get("verification_status"):
            state["verification_status"] = "investigation_required"
        if not state.get("verification_message"):
            state["verification_message"] = "K8s alert needs investigation"

        print(f"DEBUG: Calling send_email_node with mail_sent=True")

        # Call your existing send_email_node
        result_state = send_email_run(state)

        # Reset mail_sent flag
        result_state["mail_sent"] = False

        print(f"DEBUG: Email node result: {result_state.get('email_status', 'unknown')}")

        return result_state
    except Exception as e:
        print(f"DEBUG: Error in send_mail_node: {e}")
        return ensure_k8s_state({**state, "error": f"Error sending mail: {e}"})


def workflow_finalization_node(state: K8sState) -> K8sState:
    """
    Finalize the complete workflow and send summary email.
    This node is called when all resolution steps are completed.
    """
    try:
        print("DEBUG: Starting workflow finalization...")
        # Ensure at least one alert exists so finalize logic doesn't fail
        if not state.get("alerts") or not isinstance(state.get("alerts"), list) or len(state.get("alerts")) == 0:
            synthetic_id = state.get("summary_id") or 1
            synthetic_alert = {
                "id": synthetic_id,
                "ticket": state.get("user_input", "K8s issue detected"),
                "severity": state.get("llm_analysis", {}).get("severity", "medium"),
                "classification": state.get("llm_analysis", {}).get("issue_type", "k8s"),
                "status": "in_progress",
                "namespace": state.get("namespace", "default")
            }
            state["alerts"] = [synthetic_alert]
            print(f"DEBUG: Injected synthetic alert for finalization: {synthetic_alert}")
        # Finalize workflow and send email
        final_state = finalize_workflow_and_send_email(state)
        print("DEBUG: Workflow finalization completed")
        return final_state
    except Exception as e:
        print(f"ERROR: Failed to finalize workflow: {e}")
        failed_state = {**state, "error": f"Failed to finalize workflow: {e}"}
        return ensure_k8s_state(failed_state)
