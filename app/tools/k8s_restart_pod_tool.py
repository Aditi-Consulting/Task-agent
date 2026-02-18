import os
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/pods"

def restart_pod(action_input):
    """
    Restart a Kubernetes pod.

    Supports input as:
      1. Dict → {'pod_name': 'nginx-deployment-xxx', 'namespace': 'default'}
      2. String → 'pod_name=nginx-deployment-xxx, namespace=default'
    """
    print("Restarting pod", action_input)
    namespace = "default"
    pod_name = ""

    # --- Handle dict input ---
    if isinstance(action_input, dict):
        pod_name = action_input.get("pod_name", "").strip()
        namespace = action_input.get("namespace", "default").strip()

    # --- Handle string input ---
    elif isinstance(action_input, str):
        if "=" not in action_input:  # simple pod name provided
            pod_name = action_input.strip()
            namespace = "default"
        else:  # key=value string
            for pair in action_input.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip().strip("'\"")
                    if key == "pod_name":
                        pod_name = value
                    elif key == "namespace":
                        namespace = value or "default"

    # --- Validate pod_name ---
    if not pod_name:
        return "Error: 'pod_name' is required to restart a pod."

    # --- API call ---
    url = f"{BASE_URL}/{namespace}/{pod_name}/restart"
    try:
        response = requests.post(url, timeout=10)

        # --- Handle non-existing pod ---
        if response.status_code == 404:
            return f"Pod '{pod_name}' not found in namespace '{namespace}'. Cannot restart non-existing pod."

        # --- Handle other errors ---
        if response.status_code == 400:
            return f"Bad request while restarting pod '{pod_name}'. Details: {response.text}"
        if response.status_code >= 500:
            return f"Server error while restarting pod '{pod_name}': {response.text}"

        response.raise_for_status()
        return f"Pod '{pod_name}' in namespace '{namespace}' has been restarted successfully."

    except requests.exceptions.RequestException as e:
        return f"Error restarting pod '{pod_name}' in namespace '{namespace}': {e}"


# --- Register LangChain tool ---
restart_pod_tool = Tool(
    name="restart_pod",
    func=restart_pod,
    description=(
        "If request come to restart a Kubernetes pod, use this tool. and restart pod doesn't matter pod is heathy and running. "
        "Restart a Kubernetes pod. Mandatory input: pod_name. "
        "Optional: namespace (defaults to 'default'). "
        "Accepts both dict or key=value string format."
    )
)
