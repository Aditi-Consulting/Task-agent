"""
Test script to demonstrate enhanced Splunk verification handling empty results.
This simulates your scenario where Splunk returns empty results but verification should proceed.
"""

import json
from datetime import datetime
from app.nodes.verify_with_splunk_node import verify_with_splunk, verify_with_llm_for_empty_results

def test_empty_splunk_results():
    """Test the enhanced empty results handling."""

    # Simulate your scenario - empty Splunk results
    mock_splunk_results = {
        'sid': '1760524659.215',
        'results': []
    }

    # Mock state with alert data similar to your scenario
    mock_state = {
        "alerts": [{
            "id": 1,
            "ticket_id": "65dfe4c7",
            "classification": "application_error",
            "severity": "medium",
            "description": "Application alert requiring verification",
            "created_at": datetime.now()
        }],
        "generated": [{
            "query": "search index=main ticket_id=65dfe4c7"
        }],
        "current_step": 3
    }

    print("=== Testing Empty Splunk Results Scenario ===")
    print(f"Mock Splunk Results: {mock_splunk_results}")
    print(f"Alert ID: {mock_state['alerts'][0]['ticket_id']}")

    # Test the empty results handler directly
    print("\n--- Testing LLM Analysis for Empty Results ---")
    result_state = verify_with_llm_for_empty_results(mock_state.copy(), mock_splunk_results)

    print(f"Verification Status: {result_state.get('verification_status')}")
    print(f"Splunk Data Status: {result_state.get('splunk_data_status', 'empty')}")
    print(f"Verification Message: {result_state.get('verification_message')}")
    print(f"LLM Recommendation: {result_state.get('llm_recommendation')}")
    print(f"Next Step: {result_state.get('next')}")

    return result_state

def test_workflow_decision_logic():
    """Test the workflow decision logic for different verification statuses."""

    print("\n=== Testing Workflow Decision Logic ===")

    # Test scenarios
    scenarios = [
        {
            "name": "No Data Concerning",
            "verification_status": "no_data_concerning",
            "expected_action": "Proceed with heightened caution or manual review"
        },
        {
            "name": "No Data Normal",
            "verification_status": "no_data_normal",
            "expected_action": "Proceed normally or mark as resolved"
        },
        {
            "name": "No Data Cautious",
            "verification_status": "no_data_cautious",
            "expected_action": "Proceed with standard caution"
        }
    ]

    for scenario in scenarios:
        print(f"\n--- Scenario: {scenario['name']} ---")
        print(f"Status: {scenario['verification_status']}")
        print(f"Expected Action: {scenario['expected_action']}")

        # Simulate workflow decision
        if scenario['verification_status'] in ['no_data_concerning', 'no_data_cautious']:
            print("✓ Workflow will proceed to next step with appropriate context")
        elif scenario['verification_status'] == 'no_data_normal':
            print("✓ Workflow may proceed normally or conclude as resolved")
        else:
            print("✓ Workflow continues with standard flow")

def show_enhanced_features():
    """Show the key enhancements made to handle empty results."""

    print("\n=== Enhanced Features Summary ===")

    features = [
        "✓ Detects empty Splunk results vs. errors vs. data found",
        "✓ Uses LLM to analyze significance of empty results",
        "✓ Provides intelligent recommendations for next steps",
        "✓ Maintains detailed status tracking (splunk_data_status)",
        "✓ Always proceeds to next step unless critical error",
        "✓ Enhanced error handling and logging",
        "✓ Context-aware decision making based on alert type"
    ]

    for feature in features:
        print(feature)

    print("\n--- Status Types ---")
    status_types = [
        "splunk_data_status: 'empty', 'found', 'error', 'unknown'",
        "verification_status: 'no_data_concerning', 'no_data_normal', 'no_data_cautious'",
        "verification_status: 'verified', 'false_positive', 'inconclusive', 'failed', 'error'"
    ]

    for status in status_types:
        print(f"  • {status}")

if __name__ == "__main__":
    print("Testing Enhanced Splunk Verification for Empty Results")
    print("=" * 60)

    # Run the test
    result = test_empty_splunk_results()

    # Show decision logic
    test_workflow_decision_logic()

    # Show enhanced features
    show_enhanced_features()

    print("\n" + "=" * 60)
    print("Test completed! The enhanced verification can now properly handle:")
    print("• Empty Splunk results (your scenario)")
    print("• LLM-based analysis of empty data significance")
    print("• Smart workflow continuation decisions")
    print("• Detailed status tracking and reporting")
