import json
import time
from app.utility.prompts import AGENT_PROMPTS
from app.utility.config import OPENAI_MODEL_AGENT
from store.db import save_resolution
from app.utility.llm import call_llm_for_json
from app.utility.summary_tracker import capture_node_execution


def generate_remediation_node(state):
    try:
        # Get alerts that need resolution generation
        processed_alerts = state.get("processed", [])
        alerts_needing_generation = []

        # Identify which alerts need resolution generation
        for processed_alert in processed_alerts:
            if processed_alert.get("resolution_source") == "needs_generation":
                alerts_needing_generation.append(processed_alert["alert"])

        # If no alerts need generation, skip this node
        if not alerts_needing_generation:
            result_msg = "No alerts need resolution generation, skipping"
            state = capture_node_execution(state, "generate_resolution", result=result_msg)
            return state

        generated = []
        updated_processed = []

        # Process each alert that needs generation
        for alert in alerts_needing_generation:
            ticket_data = {
                "issue_type": alert.get("issue_type", "unknown"),
                "ticket": alert.get("ticket", ""),
                "severity": alert.get("severity", "medium")
            }

            print(f"Generating resolution for {ticket_data['issue_type']}")

            # Compose the prompt for the LLM
            prompt = AGENT_PROMPTS["Application Agent"].replace("{", "{{").replace("}", "}}")
            prompt = prompt.replace("{{ticket_json}}", "{ticket_json}")
            formatted_prompt = prompt.format(ticket_json=json.dumps(ticket_data, indent=2))

            # Call the LLM and parse the response
            resolution_obj = call_llm_for_json(formatted_prompt, model=OPENAI_MODEL_AGENT)
            confidence_score = resolution_obj.get("confidence_score", 15)
            try:
                confidence_score = int(confidence_score)
            except Exception:
                confidence_score = 15
            confidence_score = max(15, min(confidence_score, 100))
            resolution_obj["confidence_score"] = confidence_score

            # Optional second-pass evaluation for confidence (more context-aware)
            try:
                tool_context = (
                    "Tooling Context: The platform provides automated tools for common K8s remediations including "
                    "restart_pod, restart_deployment, scale_deployment, fix_service_port, fetch_* details and verification. "
                    "If the resolution's action_type maps to any of these deterministic tools and the input parameters are available, "
                    "it is more likely to succeed. Please factor this into your confidence estimate."
                )
                eval_prompt = (
                    "You are a reliability evaluator. Given the alert and the generated remediation resolution, "
                    "estimate a refined confidence (integer 15-100) that the resolution will address the alert effectively.\n\n"
                    f"{tool_context}\n\n"
                    "Return ONLY valid JSON with keys: confidence_score, reasoning. If refinement is not needed, reuse current score.\n"
                    f"Alert JSON: {alert}\nGenerated Resolution JSON: {resolution_obj}\n"
                )
                eval_result = call_llm_for_json(eval_prompt)
                refined = eval_result.get("confidence_score")
                if refined is not None:
                    try:
                        refined = int(refined)
                        refined = max(15, min(refined, 100))
                        confidence_score = refined
                    except Exception:
                        pass
                    resolution_obj["confidence_reasoning"] = eval_result.get("reasoning", "")
            except Exception:
                pass

            resolution = {
                "issue_type": ticket_data["issue_type"],
                "description": ticket_data["ticket"],
                "action_type": "error" if "__error__" in resolution_obj else resolution_obj.get("action_type", "unknown"),
                "action_steps": {
                    "error": resolution_obj.get("raw_text")} if "__error__" in resolution_obj else resolution_obj.get(
                    "action_steps", {}),
                "confidence_score": confidence_score,
                "confidence_reasoning": resolution_obj.get("confidence_reasoning", "")
            }

            # Save to database for future use and capture the returned resolution ID
            resolution_id = save_resolution(
                resolution["issue_type"],
                resolution["description"],
                resolution["action_type"],
                resolution["action_steps"]
            )

            # Store the ID so UI can fetch latest data using this ID
            resolution["id"] = resolution_id
            generated.append(resolution)

            # Add to processed alerts with generated resolution
            updated_processed.append({
                "alert": alert,
                "resolution": resolution,
                "resolution_source": "generated"
            })

            print(f"Generated and saved resolution for {ticket_data['issue_type']}")
            time.sleep(0.3)

        # Update state with generated resolutions
        # Merge existing processed alerts (that had DB resolutions) with newly generated ones
        existing_processed = [p for p in processed_alerts if p.get("resolution_source") == "database"]
        all_processed = existing_processed + updated_processed

        # Combine all resolutions (existing + generated)
        existing_resolutions = state.get("resolutions", [])
        all_resolutions = existing_resolutions + generated

        state["processed"] = all_processed
        state["generated"] = generated
        state["resolutions"] = all_resolutions  # This ensures execute_action has all resolutions

        # Capture execution summary - pass dict to show simple "completed successfully" in resultSummary
        # while fullResult contains detailed info with Resolution ID for UI
        resolution_id_text = f" | Resolution ID: {generated[0].get('id')}" if generated and generated[0].get('id') else ""
        detailed_msg = f"Generated {len(generated)} new resolutions, total resolutions available: {len(all_resolutions)}{resolution_id_text}"

        full_result_data = {
            "summary": detailed_msg,
            "generated_count": len(generated),
            "resolution_id": generated[0].get('id') if generated and generated[0].get('id') else None
        }

        state = capture_node_execution(state, "generate_resolution", result=full_result_data)

        return state
    except Exception as e:
        state = capture_node_execution(state, "generate_resolution", error=str(e))
        return state
