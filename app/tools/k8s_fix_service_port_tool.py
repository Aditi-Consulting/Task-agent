import os
import requests
import json
from langchain.tools import Tool

HOST_NAME = os.environ.get("K8S_HOST_NAME", "localhost")
BASE_URL = f"http://{HOST_NAME}:8081/api/k8s/services"


def fix_service_port(action_input):
    """
    Fix a Kubernetes service port by updating the service configuration.

    Args:
        action_input (dict): Dictionary containing namespace, service_name, old_port, new_port

    Returns:
        str: Result message of the port fix operation
    """
    try:
        print("Action Input:", action_input)
        namespace = action_input.get("namespace", "default")
        service_name = action_input.get("service_name")
        old_port = action_input.get("old_port")
        new_port = action_input.get("new_port")

        if not service_name:
            return "Error: Service name is required"
        if not new_port:
            return "Error: New port is required"

        print(f"Fixing service port: {service_name} in {namespace} from {old_port} to {new_port}")

        # Build URL with path parameters and query parameters
        url = f"{BASE_URL}/{namespace}/{service_name}/fix-port"
        params = {
            "newPort": new_port
        }

        # Add oldPort parameter if available
        if old_port is not None:
            params["oldPort"] = old_port

        print(f"Making request to: {url} with params: {params}")

        # Make API call with GET or POST (depending on your API design)
        response = requests.post(url, params=params)

        if response.status_code == 200:
            result = response.text
            return f"Successfully updated service {service_name} port to {new_port}. Details: {result}"
        else:
            return f"Failed to update service port. Status: {response.status_code}, Error: {response.text}"

    except requests.exceptions.RequestException as e:
        return f"API request failed: {str(e)}"
    except Exception as e:
        return f"Error fixing service port: {str(e)}"


# Register tool
fix_service_port_tool = Tool(
    name="fix_service_port",
    func=fix_service_port,
    description=(
        "Fix a Kubernetes service port. Input should be a dictionary with: "
        "namespace, service_name, old_port (optional), new_port (required). "
        "Example: {'namespace': 'default', 'service_name': 'my-app', 'new_port': 8083}"
    )
)
