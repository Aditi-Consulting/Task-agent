import os
import requests
import json
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/deployments/scale"

def scale_deployment(action_input):
    """
    Scale a Kubernetes deployment using JSON body.
    Accepts agent input in any of these formats:
      1. dict: {'namespace': 'default', 'deployment_name': 'nginx-deployment', 'replicas': 3}
      2. JSON string: '{"namespace": "default", "deployment_name": "nginx-deployment", "replicas": 3}'
      3. key=value string: 'namespace=default, deployment_name=nginx-deployment, replicas=3'
    """

    namespace = "default"
    deployment_name = ""
    replicas = None

    try:
        data = None

        # Case 1: dict
        if isinstance(action_input, dict):
            data = action_input

        # Case 2: JSON string
        elif isinstance(action_input, str) and action_input.strip().startswith("{"):
            data = json.loads(action_input)

        # Case 3: key=value string
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
        replicas = int(data.get("replicas")) if "replicas" in data else None

    except Exception as e:
        return f"Error parsing action input: {e}"

    # Validation
    if not deployment_name:
        return "Error: 'deployment_name' is required to scale deployment."
    if replicas is None or replicas < 0:
        return "Error: 'replicas' must be a non-negative integer."

    # Prepare JSON payload for POST
    payload = {
        "namespace": namespace,
        "name": deployment_name,
        "replicas": replicas
    }

    try:
        response = requests.post(BASE_URL, json=payload, timeout=10)
        response.raise_for_status()
        return f"Deployment '{deployment_name}' in namespace '{namespace}' scaled to {replicas} replicas successfully."
    except requests.exceptions.RequestException as e:
        return f"Error scaling deployment '{deployment_name}' in namespace '{namespace}': {e}"

# Register tool
scale_deployment_tool = Tool(
    name="scale_deployment",
    func=scale_deployment,
    description=(
        "Scale a Kubernetes deployment to a desired number of replicas. "
        "Input examples: "
        "'namespace=default, deployment_name=nginx-deployment, replicas=3' "
        "or JSON/dict format. Sends JSON body to backend API."
    )
)
