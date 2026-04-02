from app.utility.llm import call_llm_for_json
from app.tools.send_mail_tool import send_mail_tool
from app.utility.summary_tracker import get_execution_summary_text
import json

from store.db import update_alert_status


def prepare_email_content(state):
    """
    Prepare email content based on verification results and execution summary.
    Uses LLM to generate appropriate email content based on verification status.
    """
    # Extract verification data from state
    # print("State in email node:", state)
    verification_status = state.get("verification_status", "unknown")
    verification_message = state.get("verification_message", "No details available")

    # Access alert data from the correct location
    alerts = state.get("alerts", [])
    alert_data = alerts[0] if alerts else {}

    ticket_id = alert_data.get("ticket_id", "unknown")
    source = alert_data.get("source", "unknown")
    severity = alert_data.get("severity", "unknown")
    issue_type = alert_data.get("issue_type", "unknown")
    ticket = alert_data.get("ticket", "No description")

    # Get execution summary
    execution_summary = get_execution_summary_text(state)

    # Format verification data for LLM
    verification_data = state.get("verification_data", [])

    # Handle different verification_data formats (dict or list)
    if isinstance(verification_data, dict):
        # If it's a dict (like empty results scenario), convert to JSON directly
        data_summary = json.dumps(verification_data, indent=2)
    elif isinstance(verification_data, list):
        # If it's a list, take first 3 items for brevity
        data_summary = json.dumps(verification_data[:3], indent=2)
    else:
        # Fallback for other types
        data_summary = str(verification_data)

    # Create prompt for LLM
    prompt = f"""
    Create an email notification based on alert verification results and workflow execution:

    ALERT DETAILS:
    - Ticket ID: {ticket_id}
    - Source: {source}
    - Severity: {severity}
    - Issue Type: {issue_type}
    - Description: {ticket}

    VERIFICATION RESULTS:
    - Status: {verification_status}
    - Details: {verification_message}

    WORKFLOW EXECUTION SUMMARY:
    {execution_summary}

    VERIFICATION DATA SAMPLE:
    {data_summary}

    Generate an appropriate email with:
    1. A subject line reflecting the alert and verification status
    2. A clear opening statement about the alert status
    3. A summary of verification findings
    4. A detailed workflow execution summary showing what actions were taken
    5. Recommended next steps based on verification status
    6. A professional closing

    Return in JSON format:
    {{
        "subject": "Email subject line",
        "body": "Full email body with proper formatting including execution details"
    }}
    """

    # Call LLM to generate email content
    email_content = call_llm_for_json(prompt, model="gpt-4o-mini", temperature=0.1)

    if "__error__" in email_content:
        # Fallback if LLM fails
        subject = f"Alert Notification: {severity} Issue {ticket_id} [{source}] - {verification_status}"
        body = f"""
        Alert Notification: {ticket_id}
        Source: {source}

        Status: {verification_status}
        Details: {verification_message}

        Original Alert: {ticket}

        {execution_summary}
        """
        return {"subject": subject, "body": body}

    return email_content


def send_email(state):
    """Process state and send appropriate email based on verification results"""
    try:
        print("Preparing to send email notification...")

        # Get recipient from state or use None to let send_mail_tool use default multiple recipients
        recipient = state.get("action_parameters", {}).get("recipient", None)

        # Generate email content
        email_content = prepare_email_content(state)
        subject = email_content.get("subject", "Alert Notification")
        body = email_content.get("body", "Please review the attached alert.")

        # Prepare email payload
        email_payload = {
            "subject": subject,
            "body": body
        }

        # Only add 'to' field if recipient is explicitly specified in state
        if recipient:
            email_payload["to"] = recipient

        # Send email using the email tool
        result = send_mail_tool(json.dumps(email_payload))
        print(f"Email sending result: {result}")

        # Update state with email status
        email_status = "sent" if result.get("status") == "success" else "failed"
        state["email_status"] = email_status
        state["email_details"] = result

        # Check verification status and email status to update alert
        verification_status = state.get("verification_status", "unknown")
        alerts = state.get("alerts", [])

        if alerts and verification_status in ["verified","completed"] and email_status == "sent":
            alert_id = alerts[0].get("id")
            if alert_id:
                # Update alert status to resolved in the database
                update_alert_status(alert_id, "resolved")
                print(f"Alert {alert_id} marked as resolved in database")
                state["alert_update_status"] = "resolved"

        return state

    except Exception as e:
        print(f"Error sending email: {str(e)}")
        state["email_status"] = "error"
        state["email_details"] = {"error": str(e)}
        return state
def run(state):
    """Entry point for the node."""
    return send_email(state)