import os
import json
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/deployments"


def fetch_deployments(namespace="default"):
    """
    Fetch Kubernetes deployments in a specific namespace.
    Handles plain string, dict, and JSON string input for namespace.
    """
    print("Fetching deployments...", namespace)

    # Handle dict input directly (when LangChain passes {'namespace': 'default'})
    if isinstance(namespace, dict):
        namespace = namespace.get("namespace", "default")
    elif isinstance(namespace, str):
        # Try to parse as JSON string
        try:
            data = json.loads(namespace)
            if isinstance(data, dict) and "namespace" in data:
                namespace = data["namespace"]
        except (json.JSONDecodeError, TypeError):
            pass

    # Clean up and ensure we have a valid namespace
    namespace = str(namespace).strip().strip('"').strip("'") or "default"

    url = f"{BASE_URL}/{namespace}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return f"Error fetching deployments for namespace '{namespace}': {e}"


fetch_deployments_tool = Tool(
    name="fetch_deployments",
    func=fetch_deployments,
    description=(
        "Fetch all Kubernetes deployments in a namespace. "
        "If namespace is not provided, it defaults to 'default'. "
        "Returns a list of deployments with name, replica count, and labels."
    )
)
