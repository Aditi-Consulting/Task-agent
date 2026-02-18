import os
import requests
import json
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/deployments"

def restart_deployment(action_input):
    """
    Restart a Kubernetes deployment.
    Accepts flexible input formats:
      1. {'namespace': 'default', 'deployment_name': 'nginx-deployment'}
      2. '{"namespace": "default", "deployment_name": "nginx-deployment"}'
      3. 'namespace=default, deployment_name=nginx-deployment'
    """

    namespace = "default"
    deployment_name = ""

    try:
        data = None

        # Case 1: Already a dict
        if isinstance(action_input, dict):
            data = action_input

        # Case 2: JSON string
        elif isinstance(action_input, str) and action_input.strip().startswith("{"):
            data = json.loads(action_input)

        # Case 3: key=value format
        elif isinstance(action_input, str):
            data = {}
            for pair in action_input.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    data[k.strip()] = v.strip().strip("'\"")

        if not data:
            return "Error: Could not parse action input."

        namespace = data.get("namespace", "default").strip() or "default"
        deployment_name = data.get("deployment_name", "").strip()

    except Exception as e:
        return f"Error parsing action input: {e}"

    if not deployment_name:
        return "Error: 'deployment_name' is required to restart a deployment."

    url = f"{BASE_URL}/{namespace}/{deployment_name}/restart"

    try:
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        return f"Deployment '{deployment_name}' restarted successfully in namespace '{namespace}'."
    except requests.exceptions.RequestException as e:
        return f"Error restarting deployment '{deployment_name}' in namespace '{namespace}': {e}"

# Register as LangChain Tool
restart_deployment_tool = Tool(
    name="restart_deployment",
    func=restart_deployment,
    description=(
        "Restart a specific Kubernetes deployment by name and namespace. "
        "Input example: 'namespace=default, deployment_name=nginx-deployment' "
        "or JSON format. Use this to restart a deployment instead of individual pods."
    )
)