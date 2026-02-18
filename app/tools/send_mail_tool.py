import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from langchain.tools import Tool

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST","smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER","aiopssp@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS","hxauuwvthcqgtshr")

# Default recipients - multiple emails
STATIC_TO_ADDRESSES = [
    "divyanshukollu@gmail.com","krishank@aditiconsulting.com"
]
STATIC_FROM_ADDRESS = EMAIL_USER


def send_email(action_input):
    """
    Send an email to multiple recipients.

    Input:
      1. Dict → {"subject": "Subject", "body": "Message body", "to": "email1@example.com,email2@example.com"}
      2. String → 'subject=Subject, body=Message body'

    The 'to' field is optional. If not provided, emails will be sent to default recipients.
    The 'to' field can be:
      - A comma-separated string: "email1@example.com,email2@example.com"
      - A list: ["email1@example.com", "email2@example.com"]
    """
    subject = body = ""
    to_addresses = None

    print('in send_mail')
    print(action_input)

    # Handle string that might be repr of dict
    if isinstance(action_input, str):
        # Try JSON parsing first
        try:
            import json
            if action_input.strip().startswith('{') and action_input.strip().endswith('}'):
                action_input = json.loads(action_input)
        except:
            try:
                # Try eval as fallback (safer than full eval)
                import ast
                action_input = ast.literal_eval(action_input)
            except:
                # Keep as string if parsing fails
                pass

    # Extract values based on type
    if isinstance(action_input, dict):
        # Case insensitive key lookup
        keys_lower = {k.lower(): k for k in action_input.keys()}
        subject = action_input.get(keys_lower.get('subject', 'subject'), '')
        body = action_input.get(keys_lower.get('body', 'body'), '')
        to_addresses = action_input.get(keys_lower.get('to', 'to'), None)
    elif isinstance(action_input, str):
        # Parse key=value format
        for pair in action_input.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                key = key.strip().lower()
                value = value.strip().strip("'\"")
                if key == "subject":
                    subject = value
                elif key == "body":
                    body = value
                elif key == "to":
                    to_addresses = value

    # Ensure values are strings
    subject = str(subject) if subject else ""
    body = str(body) if body else ""

    print(f"Extracted subject: '{subject}', type: {type(subject)}")
    print(f"Extracted body: '{body}', type: {type(body)}")
    print(f"Extracted to: '{to_addresses}'")

    if not subject or not body:
        print("Missing required fields after processing")
        return {"status": "error", "error": "Missing required fields: subject, body"}

    # Process recipients
    if to_addresses:
        if isinstance(to_addresses, str):
            # Split comma-separated string into list
            to_list = [email.strip() for email in to_addresses.split(",") if email.strip()]
        elif isinstance(to_addresses, list):
            to_list = to_addresses
        else:
            to_list = STATIC_TO_ADDRESSES
    else:
        # Use default recipients if none provided
        to_list = STATIC_TO_ADDRESSES

    print(f"Sending email to: {to_list}")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = STATIC_FROM_ADDRESS
    msg["To"] = ", ".join(to_list)  # Display all recipients in header

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(STATIC_FROM_ADDRESS, to_list, msg.as_string())
        return {"status": "success", "recipients": to_list}
    except Exception as e:
        return {"status": "error", "error": str(e)}


send_mail_tool = Tool(
    name="send_mail",
    func=send_email,
    description=(
        "Send an email to multiple recipients. Mandatory input: subject, body. Optional: to (comma-separated emails or list). "
        "Input can be a dict or a key=value string. "
        "Example: {'subject': 'Hello', 'body': 'Test message', 'to': 'email1@example.com,email2@example.com'}"
    )
)