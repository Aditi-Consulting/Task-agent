import os
import requests
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/services"

def get_service_details(namespace: str = "default", service_name: str = ""):
    print(f"Getting service details for {namespace}/{service_name}")
    namespace = (namespace or "default").strip().strip('"').strip("'") or "default"
    if not service_name:
        return {"error": "MissingParameter", "message": "service_name is required"}

    url = f"{BASE_URL}/{namespace}/{service_name}"
    print("Debug URL:", url)
    try:
        response = requests.get(url, timeout=10)
        if 200 <= response.status_code < 300:
            try:
                return response.json()
            except Exception:
                return {"name": service_name, "namespace": namespace, "raw": response.text}
        # Non-success status codes
        try:
            payload = response.json()
            backend_error = payload.get("error") or payload.get("status") or f"HTTP {response.status_code}"
            backend_message = payload.get("message") or payload.get("detail") or (
                f"Service not found: {service_name} in namespace {namespace}" if response.status_code == 404 else (response.text[:200] if response.text else "Unknown error")
            )
            return {"error": backend_error, "message": backend_message, "code": response.status_code}
        except Exception:
            generic_msg = f"Service lookup failed ({response.status_code}): {service_name} in {namespace}"
            return {"error": f"HTTP {response.status_code}", "message": generic_msg, "code": response.status_code}
    except requests.exceptions.RequestException as e:
        return {"error": "RequestException", "message": str(e)}

service_details_tool = Tool(
    name="get_service_details",
    func=get_service_details,
    description=(
        "Use this tool to fetch detailed information for a specific Kubernetes service.\n"
        "Required: service_name (e.g., 'nginx-service')\n"
        "Optional: namespace (defaults to 'default')\n"
        "Returns service details JSON or structured error {'error','message','code'}."
    )
)
