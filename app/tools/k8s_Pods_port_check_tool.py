import os
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/pods"

def port_check(action_input):
    """
    Check if a specific port is accessible on a Kubernetes pod.

    Supports:
      - Dict input: {'pod_name': 'nginx-deployment-xxx', 'namespace': 'default', 'port': 80, 'timeout': 2000}
      - String input: 'pod_name=nginx-deployment-xxx, namespace=default, port=80, timeout=2000'

    Returns:
        dict: {"status": True/False, "message": str}
    """

    namespace = "default"
    pod_name = ""
    port = None
    timeout = 2000

    # --- Handle dict input ---
    if isinstance(action_input, dict):
        pod_name = action_input.get("pod_name", "").strip()
        namespace = action_input.get("namespace", "default").strip()
        port = action_input.get("port")
        timeout = int(action_input.get("timeout", 2000))

    # --- Handle string input ---
    elif isinstance(action_input, str):
        for pair in action_input.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                key = key.strip().lower()
                value = value.strip().strip("'\"")
                if key == "pod_name":
                    pod_name = value
                elif key == "namespace":
                    namespace = value or "default"
                elif key == "port":
                    try:
                        port = int(value)
                    except ValueError:
                        return {"status": False, "message": f"Invalid port value: {value}"}
                elif key == "timeout":
                    try:
                        timeout = int(value)
                    except ValueError:
                        timeout = 2000

    # --- Validate required inputs ---
    if not pod_name:
        return {"status": False, "message": "Error: 'pod_name' is required for port check."}
    if port is None:
        return {"status": False, "message": "Error: 'port' is required for port check."}

    # sanitize namespace
    namespace = namespace.strip().strip('"').strip("'") or "default"

    url = f"{BASE_URL}/{namespace}/{pod_name}/port-check"
    params = {"port": port, "timeout": timeout}

    try:
        response = requests.get(url, params=params, timeout=10)

        # --- Handle errors from backend ---
        if response.status_code == 404:
            return {"status": False, "message": f"Pod '{pod_name}' not found in namespace '{namespace}'."}
        if response.status_code >= 400 and response.status_code < 500:
            return {"status": False, "message": f"Bad request for pod '{pod_name}': {response.text}"}
        if response.status_code >= 500:
            return {"status": False, "message": f"Server error checking port for pod '{pod_name}': {response.text}"}

        result = response.json()  # expected True/False
        message = f"Port {port} on pod '{pod_name}' in namespace '{namespace}' is {'open' if result else 'closed'}."
        return {"status": result, "message": message}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Error performing port check on pod '{pod_name}' in namespace '{namespace}': {e}"}


# --- Register LangChain tool ---
port_check_tool = Tool(
    name="port_check",
    func=port_check,
    description=(
        "Check if a specific port is accessible on a Kubernetes pod. "
        "Mandatory inputs: pod_name and port. "
        "Namespace is optional (defaults to 'default'), timeout is optional (default 2000ms). "
        "Accepts dict or key=value comma-separated input. Returns status and descriptive message."
    )
)
