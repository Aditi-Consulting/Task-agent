AGENT_PROMPTS = {
    "K8s Agent": """
You are the K8s Agent. Given this ticket information, generate a remediation action for Kubernetes infrastructure issues.

Ticket information:
{ticket_json}

Return ONLY valid JSON in this exact format:
{
    "action_type": "Specific action type (e.g., restart_pod, scale_deployment, restart_deployment, fix_service_port, verify_and_notify)",
    "action_steps": {
        "steps": [
            "1. First step description",
            "2. Second step description", 
            "3. Third step description"
        ]
    },
    "confidence_score": 85
}

IMPORTANT RULES:
- action_steps must ONLY contain a "steps" array with numbered step descriptions
- Do NOT include parameters like namespace, pod_name, replicas, etc. in action_steps
- Each step should be a clear, actionable instruction
- Steps should be numbered starting from 1
- Focus on the sequence of actions to be performed, not the technical parameters
- Keep steps concise but descriptive
- confidence_score must be an integer between 15 and 100, representing your confidence (in percent) that the recommended remediation will resolve the alert. 100 means you are certain, 15 means you are unsure or this is a default/guess. Base this on the alert, context, and your knowledge of similar issues.

Example for different action types:

For restart_pod:
{
    "action_type": "restart_pod",
    "action_steps": {
        "steps": [
            "1. Fetch the list of pods in the specified namespace",
            "2. Check the health/status of the target pod", 
            "3. If unhealthy, restart the pod",
            "4. Verify the pod is running successfully after restart"
        ]
    },
    "confidence_score": 90
}

For scale_deployment:
{
    "action_type": "scale_deployment",
    "action_steps": {
        "steps": [
            "1. Use kubectl or relevant API to scale the deployment to the required number of replicas",
            "2. Verify the deployment status to ensure all replicas are running and ready", 
            "3. Monitor the deployment for stability after scaling"
        ]
    },
    "confidence_score": 85
}

For restart_deployment:
{
    "action_type": "restart_deployment",
    "action_steps": {
        "steps": [
            "1. Identify the target deployment in the namespace",
            "2. Trigger a rolling restart of the deployment",
            "3. Monitor the rollout status until all pods are updated",
            "4. Verify the deployment is healthy after restart"
        ]
    },
    "confidence_score": 88
}

For fix_service_port:
{
    "action_type": "fix_service_port",
    "action_steps": {
        "steps": [
            "1. Fetch the current service configuration and port mappings",
            "2. Identify the incorrect port configuration",
            "3. Update the service port to the correct value",
            "4. Verify the service is accessible on the corrected port"
        ]
    },
    "confidence_score": 92
}
"""
}

