import os
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/pods"

def get_pod_details(pods: list = None):
    """
    Fetch detailed info for each pod in the provided list.

    Args:
        pods (list): List of pod objects. Each object should have:
                     - 'name' (str): pod name (required)
                     - 'namespace' (str, optional): namespace of the pod. Defaults to 'default'

    Returns:
        list | str: List of pod details or structured error payloads per pod.
    """
    if not pods:
        return "No pods provided. Please provide pod names and namespaces."

    details_list = []
    for pod in pods:
        pod_name = pod.get("name")
        namespace = pod.get("namespace", "default")  # fallback to default if not provided
        if not pod_name:
            details_list.append({"error": "MissingParameter", "message": f"Missing pod name in {pod}"})
            continue

        # sanitize namespace
        namespace = namespace.strip().strip('"').strip("'") or "default"

        url = f"{BASE_URL}/{namespace}/{pod_name}"
        try:
            response = requests.get(url, timeout=10)
            if 200 <= response.status_code < 300:
                try:
                    details_list.append(response.json())
                except Exception:
                    details_list.append({"name": pod_name, "namespace": namespace, "raw": response.text})
            else:
                # Attempt structured error
                try:
                    payload = response.json()
                    backend_error = payload.get("error") or payload.get("status") or f"HTTP {response.status_code}"
                    backend_message = payload.get("message") or payload.get("detail") or (
                        f"Pod not found: {pod_name} in namespace {namespace}" if response.status_code == 404 else (response.text[:200] if response.text else "Unknown error")
                    )
                    details_list.append({"pod": pod_name, "namespace": namespace, "error": backend_error, "message": backend_message, "code": response.status_code})
                except Exception:
                    details_list.append({"pod": pod_name, "namespace": namespace, "error": f"HTTP {response.status_code}", "message": f"Pod lookup failed ({response.status_code}): {pod_name} in {namespace}", "code": response.status_code})
        except requests.exceptions.RequestException as e:
            details_list.append({"pod": pod_name, "namespace": namespace, "error": "RequestException", "message": str(e)})

    return details_list

get_pod_details_tool = Tool(
    name="get_pod_details",
    func=get_pod_details,
    description=(
        "Fetch detailed info for a list of pods. "
        "Input must be a list of objects with 'name' and optional 'namespace'. "
        "If 'namespace' is missing, it defaults to 'default'. "
        "Example: [{'name': 'nginx-pod', 'namespace': 'default'}]. "
        "Returns per-pod JSON data or structured error {'error','message','code'}."
    ),
)
