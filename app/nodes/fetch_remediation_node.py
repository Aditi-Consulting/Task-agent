from store.db import fetch_resolution
from app.utility.summary_tracker import capture_node_execution

def fetch_resolution_node(state):
    try:
        alerts = state.get("alerts", [])
        processed_alerts = []
        resolutions = []

        for alert in alerts:
            issue_type = alert.get("issue_type")
            resolution = fetch_resolution(issue_type=issue_type) if issue_type else None

            if resolution:
                resolutions.append(resolution)
                processed_alerts.append({
                    "alert": alert,
                    "resolution": resolution,
                    "resolution_source": "database"
                })
                print(f"✅ Found existing resolution for {issue_type} in database")
                print(f"DEBUG [fetch_resolution] resolution keys: {list(resolution.keys())}")
                print(f"DEBUG [fetch_resolution] resolution action_type: '{resolution.get('action_type')}'")
                print(f"DEBUG [fetch_resolution] resolution description (first 100): '{str(resolution.get('description', ''))[:100]}'")
            else:
                # Mark alert as needs_generation and add to processed list
                processed_alerts.append({
                    "alert": alert,
                    "resolution": None,
                    "resolution_source": "needs_generation"
                })
                print(f"⚠️ No resolution found for {issue_type}, will need to generate")

        # Always update state with processed alerts (even if resolution not found)
        state["processed"] = processed_alerts
        state["resolutions"] = resolutions

        found_count = len(resolutions)
        needs_generation_count = len(alerts) - found_count

        # Build summary message
        summary_msg = (
            f"Alert processing summary:\n"
            f"Total alerts received: {len(alerts)}\n"
            f"Existing resolutions found in DB: {found_count}\n"
            f"Alerts requiring new resolution generation: {needs_generation_count}"
        )

        # Extract resolution steps for UI display when found in DB
        resolution_steps_list = []
        if resolutions:
            for res in resolutions:
                action_steps = res.get("action_steps", {})
                steps = []

                # Handle different action_steps formats
                if isinstance(action_steps, dict) and "steps" in action_steps:
                    steps_data = action_steps.get("steps", [])
                    if isinstance(steps_data, list):
                        steps = steps_data
                    elif isinstance(steps_data, str):
                        # Split string with numbered steps
                        steps = [s.strip() for s in steps_data.split('\n') if s.strip()]
                    else:
                        steps = [str(steps_data)]
                elif isinstance(action_steps, list):
                    steps = action_steps

                resolution_steps_list.append({
                    "issue_type": res.get("issue_type"),
                    "action_type": res.get("action_type"),
                    "resolution_id": res.get("id"),
                    "steps": steps
                })

        # Create structured result for UI
        full_result = {
            "summary": summary_msg,
            "resolution_steps": resolution_steps_list if resolution_steps_list else None,
            "resolutions_found": found_count,
            "needs_generation": needs_generation_count
        }

        state = capture_node_execution(state, "fetch_resolution", result=full_result)
        return state
    except Exception as e:
        state = capture_node_execution(state, "fetch_resolution", error=str(e))
        return state
