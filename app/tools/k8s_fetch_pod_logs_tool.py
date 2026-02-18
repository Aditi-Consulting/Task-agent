import os
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/pods"


def fetch_pod_logs(action_input):
    """
    Fetch logs for a specific Kubernetes pod.

    Supports:
      - Dict input: {'pod_name': 'nginx-deployment-xxx', 'namespace': 'default', 'tail_lines': 10}
      - String input: 'pod_name=nginx-deployment-xxx, namespace=default, tail_lines=10'

    Returns:
        str: Logs text or a descriptive error message.
    """

    namespace = "default"
    pod_name = ""
    tail_lines = 25

    # --- Handle dict input ---
    if isinstance(action_input, dict):
        pod_name = action_input.get("pod_name", "").strip()
        namespace = action_input.get("namespace", "default").strip()
        tail_lines = int(action_input.get("tail_lines", 25))

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
                elif key == "tail_lines":
                    try:
                        tail_lines = int(value)
                    except ValueError:
                        tail_lines = 25

    # --- Validate pod_name ---
    if not pod_name:
        return "Error: 'pod_name' is required to fetch logs."

    # --- Build URL ---
    url = f"{BASE_URL}/{namespace}/{pod_name}/logs"
    params = {"tailLines": tail_lines}

    try:
        response = requests.get(url, params=params, timeout=15)
        text = response.text.strip().lower()

        # --- Handle backend and API errors ---
        if response.status_code == 404 or "not found" in text:
            return f"Pod '{pod_name}' not found in namespace '{namespace}'. Please check the name."
        if response.status_code == 400 or "invalid" in text or "error" in text:
            return f"Bad request fetching logs for pod '{pod_name}' in namespace '{namespace}'. Details: {response.text}"
        if response.status_code >= 500:
            return f"Server error fetching logs for pod '{pod_name}': {response.text}"

        # --- Check for hidden 'not found' or 'error' inside 200 ---
        if "not found" in text or "does not exist" in text:
            return f"Pod '{pod_name}' does not exist in namespace '{namespace}'."
        if "failed" in text or "error" in text:
            return f"Failed to fetch logs for pod '{pod_name}': {response.text}"

        response.raise_for_status()
        # --- Success ---
        return f"Logs for pod '{pod_name}' in namespace '{namespace}' (last {tail_lines} lines):\n\n{response.text}"

    except requests.exceptions.RequestException as e:
        return f"Error fetching logs for pod '{pod_name}' in namespace '{namespace}': {e}"


# --- Register LangChain tool ---
get_pod_logs_tool = Tool(
    name="get_pod_logs",
    func=fetch_pod_logs,
    description=(
        "Fetch logs for a specific Kubernetes pod. Mandatory input: pod_name. "
        "Optional: namespace (defaults to 'default') and tail_lines (defaults to 25). "
        "Accepts dict or key=value comma-separated input, e.g. "
        "'pod_name=nginx-deployment-xxx, namespace=default, tail_lines=10'."
    )
)
