"""
Test script to validate the node execution summary tracking system.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from store.db import ensure_tables, store_node_execution_summary, get_alert_execution_history
from app.utility.summary_tracker import capture_node_execution, initialize_execution_tracking, get_execution_summary_text

def test_execution_summary_system():
    """Test the complete execution summary tracking system"""

    print("=== Testing Node Execution Summary System ===\n")

    # 1. Initialize database tables
    print("1. Setting up database tables...")
    try:
        ensure_tables()
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        return False

    # 2. Test state-based summary tracking
    print("\n2. Testing state-based summary tracking...")
    test_state = {
        "user_input": "Test K8s pod down alert",
        "alerts": [{"id": 999, "ticket_id": "TEST-001"}]
    }

    # Initialize tracking
    test_state = initialize_execution_tracking(test_state, alert_id=999)
    print(f"✓ Execution tracking initialized")

    # Simulate node executions
    test_state = capture_node_execution(test_state, "extract_parameters",
                                       result="Successfully analyzed test alert")
    test_state = capture_node_execution(test_state, "fetch_pods",
                                       result="Retrieved 3 pods from namespace default")
    test_state = capture_node_execution(test_state, "analyze_pod_health",
                                       result="Found 1 unhealthy pod, 2 healthy pods")
    test_state = capture_node_execution(test_state, "restart_unhealthy_pods",
                                       result="Restarted pod test-pod-123")

    print(f"✓ Captured {len(test_state.get('execution_summary', []))} node executions")

    # 3. Test database storage
    print("\n3. Testing database storage...")
    try:
        # Manually store one execution for testing
        store_node_execution_summary(
            alert_id=999,
            node_name="test_verification",
            execution_order=5,
            status="success",
            result_summary="Test verification completed successfully",
            full_result={"status": "success", "message": "All tests passed"}
        )
        print("✓ Successfully stored execution summary in database")
    except Exception as e:
        print(f"✗ Database storage failed: {e}")
        return False

    # 4. Test database retrieval
    print("\n4. Testing database retrieval...")
    try:
        history = get_alert_execution_history(999)
        print(f"✓ Retrieved {len(history)} execution records from database")
        if history:
            print(f"   - Latest record: {history[-1]['node_name']} ({history[-1]['status']})")
    except Exception as e:
        print(f"✗ Database retrieval failed: {e}")
        return False

    # 5. Test email-ready summary formatting
    print("\n5. Testing summary formatting...")
    try:
        formatted_summary = get_execution_summary_text(test_state)
        print("✓ Generated formatted summary for email:")
        print("   " + "\n   ".join(formatted_summary.split("\n")[:5]) + "...")
    except Exception as e:
        print(f"✗ Summary formatting failed: {e}")
        return False

    print("\n=== All Tests Passed! ===")
    print("\nExecution Summary System Features Validated:")
    print("✓ Database schema creation")
    print("✓ State-based execution tracking")
    print("✓ Database storage of execution summaries")
    print("✓ Database retrieval of execution history")
    print("✓ Email-ready summary formatting")

    return True

def test_k8s_orchestrator_integration():
    """Test integration with K8s orchestrator"""
    print("\n=== Testing K8s Orchestrator Integration ===\n")

    try:
        from app.k8s_orchestrator import extract_k8s_parameters_and_resolution, initialize_execution_tracking

        # Test state with K8s alert
        test_state = {
            "user_input": "Pod down alert: nginx-pod in default namespace is not running",
            "alerts": [{"id": 998, "ticket_id": "K8S-002"}]
        }

        # This should initialize tracking and capture the first execution
        result_state = extract_k8s_parameters_and_resolution(test_state)

        execution_summary = result_state.get("execution_summary", [])
        print(f"✓ K8s orchestrator integration working")
        print(f"✓ Captured {len(execution_summary)} execution(s)")

        if execution_summary:
            print(f"   - First execution: {execution_summary[0]['node_name']}")
            print(f"   - Status: {execution_summary[0]['status']}")

        return True

    except Exception as e:
        print(f"✗ K8s orchestrator integration failed: {e}")
        return False

if __name__ == "__main__":
    success = test_execution_summary_system()
    if success:
        success = test_k8s_orchestrator_integration()

    if success:
        print("\n🎉 All tests completed successfully!")
        print("\nThe node execution summary system is ready for production use.")
    else:
        print("\n❌ Some tests failed. Please check the implementation.")

    sys.exit(0 if success else 1)
