import os
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/deployments"

def get_deployment_details(namespace: str = "default", deployment_name: str = ""):
    """
    Fetch details for a specific Kubernetes deployment.

    Args:
        namespace (str): Namespace of the deployment. Defaults to "default" if not provided.
        deployment_name (str): Name of the deployment to fetch. Required.

    Returns:
        dict | str: Deployment details (namespace, name, replicas) or structured error payload.
    """
    print("Fetching deployments details...")
    print("Namespace:", namespace)
    print("Deployment name:", deployment_name)

    # Handle case where namespace might be passed as dict (error handling)
    if isinstance(namespace, dict):
        namespace = "default"

    # Sanitize namespace
    namespace = (namespace or "default").strip().strip('"').strip("'") or "default"

    # Validate required parameter
    if not deployment_name:
        return {"error": "MissingParameter", "message": "deployment_name is required to fetch deployment details"}

    url = f"{BASE_URL}/{namespace}/{deployment_name}"
    try:
        response = requests.get(url, timeout=10)
        # Success path
        if 200 <= response.status_code < 300:
            # Assume backend returns JSON; fall back to string if not
            try:
                return response.json()
            except Exception:
                return {"name": deployment_name, "namespace": namespace, "raw": response.text}
        # Error path: attempt to parse structured backend message
        try:
            payload = response.json()
            # Normalize expected fields
            backend_error = payload.get("error") or payload.get("status") or f"HTTP {response.status_code}"
            backend_message = payload.get("message") or payload.get("detail") or f"Deployment not found: {deployment_name} in namespace {namespace}" if response.status_code == 404 else (response.text[:200] if response.text else "Unknown error")
            return {"error": backend_error, "message": backend_message, "code": response.status_code}
        except Exception:
            # Fallback plain text
            generic_msg = f"Deployment lookup failed ({response.status_code}): {deployment_name} in {namespace}"
            return {"error": f"HTTP {response.status_code}", "message": generic_msg, "code": response.status_code}
    except requests.exceptions.RequestException as e:
        # Network / timeout / connection errors
        return {"error": "RequestException", "message": str(e)}


deployment_details_tool = Tool(
    name="get_deployment_details",
    func=get_deployment_details,
    description=(
        "Fetch details for a specific Kubernetes deployment. "
        "Requires deployment_name. Namespace is optional (defaults to 'default'). "
        "Returns details including name, namespace, and replica count or structured error {'error','message','code'}."
    )
)
