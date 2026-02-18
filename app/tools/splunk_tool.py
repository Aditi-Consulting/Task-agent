import os
import re
from langchain.tools import tool
import requests
import json

SPLUNK_HOST = os.environ.get("SPLUNK_HOST", "localhost")
base_url = f"http://{SPLUNK_HOST}:8082/api/splunk/search"

@tool("splunk_search_tool", return_direct=True)
def splunk_search_tool(input_str):
    """
    Query Splunk logs via the connector.
    Input must be a JSON string with keys: query, earliest_time, latest_time
    Example:
    '{"query": "search index=main", "earliest_time": "-6d", "latest_time": "now"}'
    """
    headers = {"Content-Type": "application/json"}
    print('in splunk tool')
    print(input_str)
    print(type(input_str))
    # Default values
    query = "search index=main"
    earliest_time = "-24h"
    latest_time = "now"

    # Try to parse JSON input
    try:
        # print("before trim",input_str)
        #input_str = input_str[re.search('{', input_str).start():re.search('}', input_str).start()+1]  # Trim leading text before '{'
        print("after trim",input_str)
        data = json.loads(input_str)
        query = data.get("query", query)
        print("earliest time", data.get("earliest_time"))
        print("before trim",query)
        # Add "search" prefix if not already present
        if query and not query.lower().strip().startswith("search "):
            query = "search " + query
        earliest_time = data.get("earliest_time", earliest_time)
        latest_time = data.get("latest_time", latest_time)
        print(query)
        print(earliest_time)
        print(latest_time)
    except Exception:
        # fallback: treat input_str as simple query
        query = input_str

    payload = {
        "query": query,
        "earliestTime": earliest_time,
        "latestTime": latest_time
    }

    try:
        response = requests.post(base_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(splunk_search_tool('{"query": "search index=main swap_usage_high node=grp-core-05", "earliest_time": "-1h", "latest_time": "now"}'))