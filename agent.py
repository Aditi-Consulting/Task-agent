import re
import json
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate

# Import tools
from app.tools.k8s_fetch_services_tool import fetch_services_tool
from app.tools.k8s_fetch_pods_tool import fetch_pods_tool
from app.tools.k8s_scale_deployment_tool import scale_deployment_tool
from app.tools.k8s_restart_pod_tool import restart_pod_tool
from app.tools.k8s_fetch_deployments_tool import fetch_deployments_tool
from app.tools.k8s_fix_service_port_tool import fix_service_port_tool
from app.tools.k8s_restart_deployment_tool import restart_deployment_tool
from app.tools.k8s_fetch_pod_logs_tool import get_pod_logs_tool
from app.tools.k8s_Pods_port_check_tool import port_check_tool
from app.tools.splunk_tool import splunk_search_tool
from app.tools.send_mail_tool import send_mail_tool

load_dotenv()

# Create LLM
llm = ChatOpenAI(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini", temperature=0)

# Register all tools
tools = [
    splunk_search_tool,
    send_mail_tool,
    fetch_services_tool,
    fetch_pods_tool,
    scale_deployment_tool,
    restart_pod_tool,
    restart_deployment_tool,
    port_check_tool,
    fetch_deployments_tool,
    get_pod_logs_tool,
    fix_service_port_tool
]

# Define the prompt template correctly
prompt_template_str = """You are an AI assistant helping with Kubernetes and infrastructure issues.
You have access to the following tools:

{tools}

You are also provided with resolution steps that describe how to fix known issues.
Refer to these steps when deciding actions.

Resolution Steps (follow these step by step exactly as numbered):
{resolution_steps}

Use the following format:

Input: {input}
Subject: {subject}
Query: {query}
Thought: I need to think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Input: {input}
Subject: {subject}
Query: {query}
{agent_scratchpad}
"""

prompt = PromptTemplate(
    template=prompt_template_str,
    input_variables=["tools", "resolution_steps", "input", "subject", "query", "tool_names", "agent_scratchpad"]
)

# Create agent
agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True
)

def process_alert(alert_json):
    try:
        if isinstance(alert_json, str):
            alert_json = json.loads(alert_json)

        subject = alert_json.get("subject", "N/A")
        query = alert_json.get("query", "N/A")
        alert_data = alert_json.get("alert", {})
        resolution = alert_json.get("resolution", {})
        action_required = alert_json.get("action_required", "")

        # Build input text
        input_text = (
            f"Alert ID: {alert_data.get('id')} - {alert_data.get('ticket')}. "
            f"Issue type: {alert_data.get('issue_type')}. "
            f"Severity: {alert_data.get('severity')}. "
            f"Reasoning: {alert_data.get('reasoning')}. "
            f"Action required: {action_required}."
        )

        # Extract resolution steps
        resolution_steps_str = ""
        action_steps = resolution.get("action_steps", {})
        if isinstance(action_steps, dict) and "steps" in action_steps:
            steps_data = action_steps.get("steps", [])
            if isinstance(steps_data, list):
                resolution_steps_str = "\n".join(steps_data)
            else:
                resolution_steps_str = str(steps_data)
        elif isinstance(action_steps, list):
            steps = []
            for step_item in action_steps:
                if isinstance(step_item, dict) and "step" in step_item:
                    steps.append(step_item["step"])
            resolution_steps_str = "\n".join([f"{i + 1}. {step}" for i, step in enumerate(steps)])

        # Pass variables directly to agent_executor
        result = agent_executor.invoke({
            "input": input_text,
            "subject": subject,
            "query": query,
            "resolution_steps": resolution_steps_str,
            "tools": ", ".join([t.name for t in tools]),
            "tool_names": ", ".join([t.name for t in tools]),
            "agent_scratchpad": ""
        })

        return json.dumps({
            "status": "resolved",
            "message": result.get("output", "Task completed successfully")
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "status": "failed",
            "message": f"Error processing alert: {str(e)}"
        })


if __name__ == "__main__":
    # Example alert
    alert_json = {"subject": "High Severity Alert: Abnormal Incident Handling Activity Detected by Splunk", "query": "index=main ticket_id=32a6a83b", "alert": {"id": 17, "agent_name": "Application Agent", "classification": "Application", "confidence": 0.85, "created_by": "Splunk Monitoring", "inserted_at": "2025-10-14T11:38:11.620342", "issue_type": "workflow_issue", "processed_at": "2025-10-14T14:20:04", "reasoning": "The alert references Splunk detecting abnormal incident handling activity and high-severity logs related to system or workflow issues during root cause analysis. This suggests problems within application-level processes or monitoring workflows rather than hardware or database-specific issues. The focus on incident handling and logs aligns more with application monitoring.", "severity": "High", "status": "failed", "ticket": "Alert: Splunk detected abnormal incident handling activity \u2014 high-severity logs indicate potential system or workflow issue during root cause analysis.", "ticket_id": "32a6a83b"}, "resolution": {"id": 9, "issue_type": "workflow_issue", "description": "Alert: Splunk detected abnormal incident handling activity \u2014 high-severity logs indicate potential system or workflow issue during root cause analysis.", "action_type": "Verify_and_notify", "action_steps": {"steps": ["1. Check Splunk to verify if the abnormal incident handling activity persists. 2. Review related logs and confirm whether the issue is genuine or a false trigger. 3. Once verified, summarize the findings. 4. Send a confirmation email to the DevOps team with the verification details and resolution outcome."]}}, "action_required": "Verify_and_notify", "action_parameters": {}, "instruction": "Please respond in JSON: {\"status\": \"<resolved|failed>\", \"message\": \"<your answer>\"}"}  # Use your full alert dict here
    response = process_alert(alert_json)
    print(response)
