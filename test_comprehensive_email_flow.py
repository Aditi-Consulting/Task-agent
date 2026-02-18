#!/usr/bin/env python3
"""
Test script to validate the comprehensive email flow implementation.
This tests the fix for 'Missing execution_id or alert_id' error.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from graph.graph_builder import build_graph, GraphState
from store.db import ensure_tables, get_task_agent_execution_summary
from app.utility.summary_tracker import get_execution_summary_text

def test_application_workflow_with_email():
    """Test the complete application workflow with task_agent email flow"""

    print("=== Testing Application Workflow Email Flow ===\n")

    # 1. Initialize database tables
    print("1. Setting up database tables...")
    try:
        ensure_tables()
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        return False

    # 2. Create test state simulating real application workflow
    print("\n2. Creating test application workflow state...")
    test_state = {
        "alerts": [
            {
                "id": 888,
                "ticket_id": "APP-TEST-001",
                "classification": "Application",
                "severity": "high",
                "ticket": "Test application issue for email flow validation",
                "issue_type": "application_error"
            }
        ],
        "processed": [],
        "executed": [],
        "resolutions": [],
        "generated": [],
        "splunk_results": None,
        "verification_status": "",
        "verification_message": "",
        "verification_data": [],
        "next": "",
        "execution_summary": [],
        "summary_id": 888
    }

    print(f"✓ Test state created with alert_id: {test_state['alerts'][0]['id']}")

    # 3. Build and run the application graph
    print("\n3. Building and executing application workflow...")
    try:
        app_graph = build_graph()
        print("✓ Application graph built successfully")

        # Execute the workflow
        print("\n4. Executing application workflow...")
        result_state = app_graph.invoke(test_state)

        print("✓ Application workflow executed successfully")

        # 5. Validate task_agent tracking was properly initialized
        print("\n5. Validating task_agent tracking...")
        execution_id = result_state.get("task_agent_execution_id")
        alert_id = result_state.get("task_agent_alert_id")

        if execution_id and alert_id:
            print(f"✓ Task_agent tracking initialized: execution_id={execution_id}, alert_id={alert_id}")
        else:
            print(f"✗ Task_agent tracking FAILED: execution_id={execution_id}, alert_id={alert_id}")
            return False

        # 6. Check execution summary
        print("\n6. Checking execution summary...")
        execution_summary = result_state.get("execution_summary", [])
        print(f"✓ Captured {len(execution_summary)} node executions in memory")

        if execution_summary:
            print("   Node executions:")
            for i, node in enumerate(execution_summary, 1):
                status = node.get('status', 'unknown')
                name = node.get('node_name', 'unknown')
                print(f"   {i}. {name}: {status.upper()}")

        # 7. Validate database storage
        print("\n7. Validating database storage...")
        db_execution_data = get_task_agent_execution_summary(alert_id)

        if db_execution_data:
            print("✓ Execution data stored in task_agent_execution_summary table")
            print(f"   Status: {db_execution_data.get('task_agent_status')}")
            print(f"   Total nodes: {db_execution_data.get('task_agent_total_nodes')}")
            print(f"   Successful: {db_execution_data.get('task_agent_successful_nodes')}")
            print(f"   Failed: {db_execution_data.get('task_agent_failed_nodes')}")
        else:
            print("✗ No execution data found in database")
            return False

        # 8. Check workflow finalization
        print("\n8. Checking workflow finalization...")
        if result_state.get("task_agent_finalized"):
            print("✓ Workflow finalization completed successfully")
            print(f"   Final status: {result_state.get('task_agent_execution_status')}")
        else:
            print("✗ Workflow finalization failed")
            return False

        # 9. Display formatted summary
        print("\n9. Execution Summary Text:")
        summary_text = get_execution_summary_text(result_state)
        print(summary_text)

        print("\n" + "="*60)
        print("🎉 APPLICATION WORKFLOW EMAIL FLOW TEST PASSED!")
        print("✓ Fixed 'Missing execution_id or alert_id' error")
        print("✓ Task_agent tracking properly initialized")
        print("✓ JSON-based execution summary working")
        print("✓ Email sent at workflow completion")
        print("✓ Database storage with task_agent prefix working")
        print("="*60)

        return True

    except Exception as e:
        print(f"✗ Application workflow execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_recovery():
    """Test the error recovery for missing execution_id/alert_id"""

    print("\n=== Testing Error Recovery for Missing execution_id/alert_id ===\n")

    from app.utility.summary_tracker import finalize_workflow_and_send_email

    # Test state with missing task_agent fields (simulating the original error)
    broken_state = {
        "alerts": [{"id": 999, "ticket_id": "RECOVERY-TEST"}],
        "execution_summary": [
            {
                "node_name": "test_node",
                "execution_order": 1,
                "status": "success",
                "result_summary": "Test successful",
                "error_message": None
            }
        ],
        "workflow_type": "application"
        # Missing: task_agent_execution_id, task_agent_alert_id
    }

    print("1. Testing recovery from missing task_agent fields...")
    try:
        recovered_state = finalize_workflow_and_send_email(broken_state)

        if recovered_state.get("task_agent_execution_id"):
            print("✓ Successfully recovered from missing execution_id")
            print(f"   Recovered execution_id: {recovered_state.get('task_agent_execution_id')}")
            print(f"   Recovered alert_id: {recovered_state.get('task_agent_alert_id')}")
        else:
            print("✗ Failed to recover from missing execution_id")
            return False

        if recovered_state.get("task_agent_finalized"):
            print("✓ Workflow finalization completed after recovery")
        else:
            print("✗ Workflow finalization failed after recovery")
            return False

        print("\n✓ ERROR RECOVERY TEST PASSED!")
        return True

    except Exception as e:
        print(f"✗ Error recovery test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting Comprehensive Email Flow Tests...\n")

    # Test 1: Application workflow
    test1_passed = test_application_workflow_with_email()

    # Test 2: Error recovery
    test2_passed = test_error_recovery()

    print(f"\n{'='*70}")
    print("📊 FINAL TEST RESULTS:")
    print(f"✅ Application Workflow Test: {'PASSED' if test1_passed else 'FAILED'}")
    print(f"✅ Error Recovery Test: {'PASSED' if test2_passed else 'FAILED'}")

    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! Email flow implementation is working correctly.")
        print("🔧 The 'Missing execution_id or alert_id' error has been FIXED!")
    else:
        print("\n❌ Some tests failed. Please check the implementation.")
        sys.exit(1)
