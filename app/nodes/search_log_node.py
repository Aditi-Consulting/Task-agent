from app.tools.splunk_tool import splunk_search_tool

splunk_tool = splunk_search_tool

def search_log_node(state):
    """
    LangGraph node: invoke SplunkSearchTool and attach results to state.
    """
    query = state.get("query", "search index=main")
    earliest = state.get("earliestTime", "-4d")
    latest = state.get("latestTime", "now")

    result = splunk_tool.search(query, earliest, latest)
    state["splunk_results"] = result
    return state
