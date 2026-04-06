from flask import Flask, jsonify, request
# from endpoints.cors import setup_cors
from graph.graph_builder import build_graph
from store.db import get_db_conn, fetch_alerts_from_db
import json
import threading
import time
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("application-task-agent")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))

app = Flask(__name__)

# setup_cors(app)


@app.route('/trigger-agent', methods=['POST'])
def handle_alert_workflow():
    """Handle the main K8s alert processing workflow"""
    try:
        print("🚀 Starting K8s alert processing workflow...")

        # Extract alertId from request body
        request_data = request.get_json() or {}
        alert_id = request_data.get('alertId')

        workflow_app = build_graph().compile()
        initial_state = _build_initial_state(alert_id)

        print("📊 Processing through nodes: read_from_db → fetch_resolution → decision → execute...")
        result = workflow_app.invoke(initial_state)

        # Print workflow summary
        print("\n📋 Workflow Summary:")
        print(f"  - Alerts processed: {len(result.get('alerts', []))}")
        print(f"  - Resolutions found: {len(result.get('resolutions', []))}")
        print(f"  - Actions executed: {len(result.get('executed', []))}")

        return result
    except Exception as e:
        return f"Error processing K8s alert workflow: {e}"

@app.route('/get-resolution/<int:resolution_id>', methods=['GET'])
def get_resolution_by_id(resolution_id):
    """
    Fetch a specific resolution by ID (for UI to display latest steps).
    """
    try:
        conn = get_db_conn()
        cursor = conn.cursor(dictionary=True)
        sql = """
        SELECT id, issue_type, description, action_type, action_steps
        FROM resolutions
        WHERE id = %s
        """
        cursor.execute(sql, (resolution_id,))
        resolution = cursor.fetchone()
        cursor.close()
        conn.close()

        if resolution:
            if isinstance(resolution['action_steps'], str):
                try:
                    resolution['action_steps'] = json.loads(resolution['action_steps'])
                except Exception:
                    pass
            return jsonify({"success": True, "resolution": resolution}), 200
        else:
            return jsonify({"success": False, "error": f"Resolution {resolution_id} not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"Error fetching resolution: {str(e)}"}), 500

def _build_initial_state(alert_id):
    return {
        "alerts": [],
        "processed": [],
        "executed": [],
        "resolutions": [],
        "generated": [],
        "verification_status": "",
        "verification_message": "",
        "next": "",
        "execution_summary": [],
        "summary_id": None,
        "root_cause": "",
        "evidence": "",
        "llm_recommendation": "",
        "workflow_type": "k8s",
        "alert_id": alert_id,
    }


def poll_and_process():
    """Background poller that picks up Kubernetes alerts with status IN_PROGRESS/FAILED."""
    while True:
        try:
            alerts = fetch_alerts_from_db(limit=10)
            if alerts:
                logger.info("Poller found %d Kubernetes alert(s) to process", len(alerts))
                for alert in alerts:
                    try:
                        workflow_app = build_graph().compile()
                        workflow_app.invoke(_build_initial_state(alert["id"]))
                        logger.info("Processed alert id=%s", alert["id"])
                    except Exception as e:
                        logger.error("Failed to process alert id=%s: %s", alert["id"], e)
        except Exception as e:
            logger.error("Poller error: %s", e)

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    poller = threading.Thread(target=poll_and_process, daemon=True)
    poller.start()
    logger.info("Poller started — checking every %ds for Kubernetes alerts", POLL_INTERVAL)
    app.run(host='0.0.0.0', port=5001)