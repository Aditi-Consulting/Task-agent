import os
import requests
import json
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/pods"

def fetch_pods(namespace=None):
    # Handle dict input directly (when LangChain passes {'namespace': 'default'})
    if isinstance(namespace, dict):
        namespace = namespace.get("namespace")
    elif isinstance(namespace, str) and namespace:
        # Try to parse as JSON string
        try:
            data = json.loads(namespace)
            if isinstance(data, dict) and "namespace" in data:
                namespace = data["namespace"]
        except (json.JSONDecodeError, TypeError):
            pass

    if not namespace or str(namespace).lower() in ["none", "null", ""]:
        namespace = None

    url = BASE_URL
    params = {}
    if namespace:
        namespace = str(namespace).strip().strip('"').strip("'")
        params["namespace"] = namespace

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except requests.exceptions.RequestException as e:
        return f"Error fetching pods: {e}"

def fetch_pods_agent_input(namespace: str):
    return fetch_pods(namespace)

fetch_pods_tool = Tool(
    name="fetch_pods",
    func=fetch_pods_agent_input,
    description=(
        "Fetch all pods from the Kubernetes cluster. "
        "Provide a namespace to filter (optional). "
        "If no namespace is provided, returns pods from all namespaces."
    )
)

if __name__ == "__main__":
    print(fetch_pods_agent_input(""))
    print(fetch_pods_agent_input("default"))
