import mysql.connector
import json
from datetime import datetime
from app.utility.config import DB_HOST, DB_USER, DB_PASS, DB_NAME

def get_db_conn():
    # Step 1: Connect without selecting DB
    root_conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        autocommit=True
    )

    cursor = root_conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    cursor.close()
    root_conn.close()

    # Step 2: Connect again but now use the DB
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=False
    )
def ensure_tables():
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
    conn.database = DB_NAME

    # Create alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticket_id VARCHAR(128) UNIQUE,
        created_by VARCHAR(128),
        severity VARCHAR(64),
        ticket TEXT,
        inserted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        classification VARCHAR(64),
        confidence FLOAT,
        reasoning TEXT,
        agent_name VARCHAR(64),
        remediation_summary TEXT,
        remediation_json JSON NULL,
        status VARCHAR(32) DEFAULT 'new',
        processed_at DATETIME NULL
    ) ENGINE=InnoDB;
    """)

    # Create resolution_steps table with only original fields
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS resolutions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        issue_type VARCHAR(128),
        description TEXT,
        action_type VARCHAR(64),
        action_payload JSON
    ) ENGINE=InnoDB;
    """)

    # Create alert_execution_summary table for tracking node executions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alert_execution_summary (
        id INT AUTO_INCREMENT PRIMARY KEY,
        alert_id INT NOT NULL,
        node_name VARCHAR(128) NOT NULL,
        execution_order INT NOT NULL,
        status ENUM('success', 'error', 'warning') NOT NULL,
        result_summary TEXT,
        execution_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        full_result JSON,
        error_message TEXT,
        INDEX idx_alert_id (alert_id),
        INDEX idx_execution_order (execution_order)
    ) ENGINE=InnoDB;
    """)

    # Create new task_agent_execution_summary table with JSON structure
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_agent_execution_summary (
        id INT AUTO_INCREMENT PRIMARY KEY,
        task_agent_alert_id INT NOT NULL,
        task_agent_execution_nodes JSON NOT NULL,
        task_agent_full_result JSON NOT NULL,
        task_agent_start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        task_agent_end_time DATETIME,
        task_agent_status ENUM('in_progress', 'completed', 'failed') NOT NULL DEFAULT 'in_progress',
        task_agent_total_nodes INT DEFAULT 0,
        task_agent_successful_nodes INT DEFAULT 0,
        task_agent_failed_nodes INT DEFAULT 0,
        INDEX idx_task_agent_alert_id (task_agent_alert_id)
    ) ENGINE=InnoDB;
    """)

    conn.commit()
    cursor.close()
    conn.close()

def fetch_alerts_from_db(limit=1, alert_id=None):
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)

    if alert_id:
        query = """
            SELECT * FROM alerts
            WHERE id = %s
            AND classification IN ('Application','Infrastructure','Database')
            AND UPPER(status) IN ('FAILED','IN_PROGRESS')
        """
        cursor.execute(query, (alert_id,))
    else:
        query = """
            SELECT * FROM alerts
            WHERE classification IN ('Application','Infrastructure','Database')
            AND UPPER(status) IN ('FAILED','IN_PROGRESS')
            LIMIT %s
        """
        cursor.execute(query, (limit,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


# ----------------- Save Resolution -----------------
def save_resolution(issue_type, description, action_type, action_steps):
    conn = get_db_conn()
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = 'active'

    sql = """
    INSERT INTO resolutions
        (issue_type, description, action_type, action_steps, created_at, updated_at, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    cursor.execute(sql, (
        issue_type,
        description,
        action_type,
        json.dumps(action_steps),
        now,
        now,
        status
    ))

    resolution_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    return resolution_id


def fetch_resolution(issue_type):
    """
    Fetch a resolution from the resolution_steps table based on the issue type.
    Returns None if no resolution is found.
    """
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT 
        id,
        issue_type,
        description,
        action_type,
        action_steps
    FROM resolutions 
    WHERE issue_type = %s
    LIMIT 1
    """

    cursor.execute(sql, (issue_type,))
    resolution = cursor.fetchone()

    if resolution and resolution['action_steps']:
        # Parse JSON string to dict if it's a string
        if isinstance(resolution['action_steps'], str):
            resolution['action_steps'] = json.loads(resolution['action_steps'])

    cursor.close()
    conn.close()

    return resolution

def update_alert_status(alert_id, status):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alerts 
        SET status = %s, 
            processed_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    """, (status, alert_id))
    conn.commit()
    cursor.close()
    conn.close()


# ----------------- Task Agent Execution Summary Functions -----------------

# def initialize_task_agent_execution(alert_id):
#     """
#     Initialize a new task agent execution record in the database.
#
#     Args:
#         alert_id: ID of the alert being processed
#
#     Returns:
#         The ID of the created execution record
#     """
#     conn = get_db_conn()
#     cursor = conn.cursor()
#
#     sql = """
#     INSERT INTO task_agent_execution_summary
#     (task_agent_alert_id, task_agent_execution_nodes, task_agent_full_result, task_agent_status)
#     VALUES (%s, %s, %s, %s)
#     """
#
#     initial_nodes = json.dumps([])
#     initial_result = json.dumps({
#         "task_agent_summary": {
#             "total_steps": 0,
#             "completed_steps": 0,
#             "workflow_status": "in_progress",
#             "issue_type": "unknown",
#             "severity": "unknown"
#         }
#     })
#
#     cursor.execute(sql, (alert_id, initial_nodes, initial_result, "in_progress"))
#     execution_id = cursor.lastrowid
#
#     conn.commit()
#     cursor.close()
#     conn.close()
#
#     return execution_id


def initialize_task_agent_execution(alert_id):
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)
    # Check if a summary already exists for this alert
    cursor.execute(
        "SELECT id FROM task_agent_execution_summary WHERE task_agent_alert_id = %s AND task_agent_status IN ('in_progress', 'completed')",
        (alert_id,)
    )
    existing = cursor.fetchone()
    if existing:
        cursor.close()
        conn.close()
        return existing['id']  # Return existing execution id, do not insert duplicate

    # If not exists, insert new row
    cursor = conn.cursor()
    sql = """
    INSERT INTO task_agent_execution_summary (task_agent_alert_id, task_agent_execution_nodes, task_agent_full_result, task_agent_status)
    VALUES (%s, %s, %s, %s)
    """
    cursor.execute(sql, (alert_id, '[]', '{"task_agent_summary":{}}', 'in_progress'))
    execution_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return execution_id


def store_node_execution_summary(alert_id, node_name, execution_order, status, result_summary, full_result=None, error_message=None):
    """
    Store execution summary for a node in the task_agent_execution_summary table.
    Updated to use the new task_agent prefixed table structure.
    Now supports embedding root_cause and verification_status in node record if present.
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, task_agent_execution_nodes, task_agent_full_result 
        FROM task_agent_execution_summary 
        WHERE task_agent_alert_id = %s 
        ORDER BY id DESC LIMIT 1
    """, (alert_id,))
    existing_record = cursor.fetchone()
    def _normalize_full_result(fr):
        if fr is None:
            return None
        if isinstance(fr, (dict, list)):
            return fr
        if isinstance(fr, str):
            return {"result": fr}
        return {"result": str(fr)}
    enriched_full_result = _normalize_full_result(full_result)
    root_cause = None
    verification_status = None
    evidence = None
    if isinstance(enriched_full_result, dict):
        root_cause = enriched_full_result.get("root_cause") or enriched_full_result.get("execution_result", {}).get("root_cause")
        verification_status = enriched_full_result.get("verification_status") or enriched_full_result.get("execution_result", {}).get("verification_status")
        evidence = enriched_full_result.get("evidence") or enriched_full_result.get("execution_result", {}).get("evidence")
    node_data = {
        "node_name": node_name,
        "execution_order": execution_order,
        "status": status,
        "result_summary": result_summary,
        "execution_time": datetime.now().isoformat(),
        "error_message": error_message
    }
    if enriched_full_result is not None:
        node_data["full_result"] = enriched_full_result
    if root_cause:
        node_data["root_cause"] = root_cause
    if verification_status:
        node_data["verification_status"] = verification_status
    if evidence:
        node_data["evidence"] = evidence
    if existing_record:
        execution_id, existing_nodes_json, existing_result_json = existing_record
        existing_nodes = json.loads(existing_nodes_json) if existing_nodes_json else []
        existing_nodes.append(node_data)
        total_nodes = len(existing_nodes)
        successful_nodes = len([n for n in existing_nodes if n.get("status") == "success"])
        failed_nodes = len([n for n in existing_nodes if n.get("status") == "error"])
        cursor.execute("""
            UPDATE task_agent_execution_summary 
            SET task_agent_execution_nodes = %s,
                task_agent_total_nodes = %s,
                task_agent_successful_nodes = %s,
                task_agent_failed_nodes = %s
            WHERE id = %s
        """, (json.dumps(existing_nodes), total_nodes, successful_nodes, failed_nodes, execution_id))
    else:
        execution_id = initialize_task_agent_execution(alert_id)
        successful = 1 if status == "success" else 0
        failed = 1 if status == "error" else 0
        cursor.execute("""
            UPDATE task_agent_execution_summary 
            SET task_agent_execution_nodes = %s,
                task_agent_total_nodes = 1,
                task_agent_successful_nodes = %s,
                task_agent_failed_nodes = %s
            WHERE id = %s
        """, (json.dumps([node_data]), successful, failed, execution_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_alert_execution_history(alert_id):
    """
    Retrieve execution history for a specific alert from task_agent_execution_summary table.
    Updated to use the new task_agent prefixed table structure.

    Args:
        alert_id: ID of the alert

    Returns:
        List of execution summary records ordered by execution_order
    """
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT 
        id,
        task_agent_execution_nodes,
        task_agent_start_time,
        task_agent_end_time,
        task_agent_status
    FROM task_agent_execution_summary 
    WHERE task_agent_alert_id = %s 
    ORDER BY id DESC LIMIT 1
    """

    cursor.execute(sql, (alert_id,))
    record = cursor.fetchone()

    if not record:
        cursor.close()
        conn.close()
        return []

    # Parse the execution nodes JSON
    nodes_data = []
    if record['task_agent_execution_nodes']:
        try:
            nodes_data = json.loads(record['task_agent_execution_nodes'])
        except json.JSONDecodeError:
            pass

    cursor.close()
    conn.close()

    # Convert to the expected format for backward compatibility
    formatted_records = []
    for i, node in enumerate(nodes_data):
        formatted_record = {
            'id': f"{record['id']}-{i}",
            'node_name': node.get('node_name', 'unknown'),
            'execution_order': node.get('execution_order', i + 1),
            'status': node.get('status', 'unknown'),
            'result_summary': node.get('result_summary', ''),
            'execution_time': node.get('execution_time', record['task_agent_start_time']),
            'full_result': node.get('full_result'),
            'error_message': node.get('error_message')
        }
        formatted_records.append(formatted_record)

    return formatted_records


def get_execution_summary_for_email(alert_id):
    """
    Get a formatted execution summary suitable for email notifications.
    Updated to use the new task_agent_execution_summary table.

    Args:
        alert_id: ID of the alert

    Returns:
        Formatted string with execution summary
    """
    history = get_alert_execution_history(alert_id)

    if not history:
        return "No execution history available."

    summary_lines = ["Task Agent Execution Summary:"]
    summary_lines.append("=" * 50)

    for record in history:
        status_symbol = "✓" if record['status'] == 'success' else "✗" if record['status'] == 'error' else "⚠"
        summary_lines.append(f"{record['execution_order']}. {status_symbol} {record['node_name']}")
        summary_lines.append(f"   Status: {record['status'].upper()}")
        summary_lines.append(f"   Result: {record['result_summary']}")
        if record['error_message']:
            summary_lines.append(f"   Error: {record['error_message']}")
        summary_lines.append(f"   Time: {record['execution_time']}")
        summary_lines.append("")

    return "\n".join(summary_lines)


def update_task_agent_execution(execution_id, nodes_data, full_result_data, status="in_progress", confidence_score=None):
    """
    Update task agent execution with new node data and results.
    Adds fallback to propagate latest root_cause from nodes if missing in summary.
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    # Backfill root_cause if missing in full_result_data['task_agent_summary']
    try:
        summary_rc = full_result_data.get("task_agent_summary", {}).get("root_cause")
        if not summary_rc:
            for n in reversed(nodes_data):
                rc = n.get("root_cause")
                if rc:
                    full_result_data.setdefault("task_agent_summary", {})["root_cause"] = rc
                    break
    except Exception:
        pass
    total_nodes = len(nodes_data)
    successful_nodes = len([n for n in nodes_data if n.get("status") == "success"])
    failed_nodes = len([n for n in nodes_data if n.get("status") == "error"])
    cursor.execute("""
    UPDATE task_agent_execution_summary 
    SET task_agent_execution_nodes = %s,
        task_agent_full_result = %s,
        task_agent_status = %s,
        confidence_score = %s,
        task_agent_total_nodes = %s,
        task_agent_successful_nodes = %s,
        task_agent_failed_nodes = %s
    WHERE id = %s
    """, (
        json.dumps(nodes_data),
        json.dumps(full_result_data),
        status,
        confidence_score,  # <-- use the correct variable here
        total_nodes,
        successful_nodes,
        failed_nodes,
        execution_id
    ))
    conn.commit()
    cursor.close()
    conn.close()


def finalize_task_agent_execution(execution_id, final_status="completed"):
    """
    Finalize task agent execution by setting end time and final status.

    Args:
        execution_id: ID of the execution record
        final_status: Final status ('completed' or 'failed')
    """
    conn = get_db_conn()
    cursor = conn.cursor()

    sql = """
    UPDATE task_agent_execution_summary 
    SET task_agent_end_time = CURRENT_TIMESTAMP,
        task_agent_status = %s
    WHERE id = %s
    """

    cursor.execute(sql, (final_status, execution_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_task_agent_execution_summary(alert_id):
    """
    Get the complete task agent execution summary for an alert.

    Args:
        alert_id: ID of the alert

    Returns:
        Dictionary with complete execution data or None if not found
    """
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT * FROM task_agent_execution_summary 
    WHERE task_agent_alert_id = %s 
    ORDER BY id DESC LIMIT 1
    """

    cursor.execute(sql, (alert_id,))
    result = cursor.fetchone()

    if result:
        # Parse JSON fields
        if result['task_agent_execution_nodes']:
            result['task_agent_execution_nodes'] = json.loads(result['task_agent_execution_nodes'])
        if result['task_agent_full_result']:
            result['task_agent_full_result'] = json.loads(result['task_agent_full_result'])

    cursor.close()
    conn.close()
    return result


def get_task_agent_execution_for_email(alert_id, workflow_type="application"):
    """
    Get formatted task agent execution summary for email notifications.
    Enhanced with workflow-specific formatting.

    Args:
        alert_id: ID of the alert
        workflow_type: Type of workflow ('k8s', 'application', 'infrastructure')

    Returns:
        Formatted string with complete execution summary
    """
    execution_data = get_task_agent_execution_summary(alert_id)

    if not execution_data:
        return "No task agent execution history available."

    nodes = execution_data.get('task_agent_execution_nodes', [])
    full_result = execution_data.get('task_agent_full_result', {})
    summary = full_result.get('task_agent_summary', {})

    # Workflow-specific headers and formatting
    if workflow_type == "k8s":
        header = "=== Task Agent - Kubernetes Workflow Summary ==="
        workflow_icon = "🚀"
    elif workflow_type == "application":
        header = "=== Task Agent - Application Workflow Summary ==="
        workflow_icon = "📱"
    elif workflow_type == "infrastructure":
        header = "=== Task Agent - Infrastructure Workflow Summary ==="
        workflow_icon = "🏗️"
    else:
        header = "=== Task Agent - Workflow Summary ==="
        workflow_icon = "⚙️"

    summary_lines = [header]
    summary_lines.append("=" * len(header))
    summary_lines.append("")

    # Workflow overview
    summary_lines.append(f"{workflow_icon} Workflow Type: {workflow_type.title()}")
    summary_lines.append(f"📊 Total Steps: {summary.get('total_steps', len(nodes))}")
    summary_lines.append(f"✅ Completed Steps: {summary.get('completed_steps', len([n for n in nodes if n.get('status') == 'success']))}")
    summary_lines.append(f"🎯 Final Status: {summary.get('workflow_status', 'unknown').upper()}")
    summary_lines.append("")

    # Execution details
    summary_lines.append("📋 Execution Details:")
    summary_lines.append("-" * 30)

    for i, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            continue
        status = node.get('status', 'unknown')
        status_symbol = "✅" if status == 'success' else "❌" if status == 'error' else "⚠️"
        summary_lines.append(f"{i}. {status_symbol} {node.get('node_name', 'Unknown Node')}")
        summary_lines.append(f"   Status: {status.upper()}")
        summary_lines.append(f"   Result: {node.get('result_summary', 'No summary available')}")
        if node.get('error_message'):
            summary_lines.append(f"   ❗ Error: {node.get('error_message')}")
        execution_time = node.get('execution_time', '')
        if execution_time:
            summary_lines.append(f"   🕒 Time: {execution_time}")
        summary_lines.append("")

    # Summary footer
    summary_lines.append("-" * 50)
    summary_lines.append(f"Workflow completed at: {execution_data.get('task_agent_end_time', 'In Progress')}")
    summary_lines.append(f"Total execution time: {execution_data.get('task_agent_start_time', '')} to {execution_data.get('task_agent_end_time', 'In Progress')}")

    return "\n".join(summary_lines)
