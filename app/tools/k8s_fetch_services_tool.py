import os
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
import requests
import json

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/services"

class FetchServicesInput(BaseModel):
    namespace: str = Field(default="default", description="Kubernetes namespace to fetch services from")

def fetch_services(namespace: str = "default"):
    # Handle both plain string and JSON string input for namespace
    if namespace:
        try:
            data = json.loads(namespace)
            if isinstance(data, dict) and "namespace" in data:
                namespace = data["namespace"]
        except (json.JSONDecodeError, TypeError):
            pass

    if not namespace or namespace.lower() in ["none", "null", ""]:
        namespace = None

    url = BASE_URL
    params = {}
    if namespace:
        namespace = namespace.strip().strip('"').strip("'")
        params["namespace"] = namespace
    url = f"{BASE_URL}/{namespace}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        services = response.json()
        print(f"[DEBUG] URL called: {url}")
        print(f"[DEBUG] Response JSON: {services}")
        return services
    except requests.exceptions.RequestException as e:
        return f"Error fetching services from namespace '{namespace}': {e}"


fetch_services_tool = StructuredTool.from_function(
    func=fetch_services,
    name="fetch_services",
    description="Fetch Kubernetes services by namespace. Example: 'Fetch services from default namespace'",
    args_schema=FetchServicesInput,
)
if __name__ == "__main__":
    print(fetch_services("default"))
