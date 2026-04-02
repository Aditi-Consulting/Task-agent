from app.k8s_orchestrator import build_k8s_graph
from graph.graph_builder import build_graph

def handle_k8s_request(user_input: str):
    """Handle direct K8s requests"""
    try:
        print(f"🔄 Processing K8s request: {user_input}")
        app = build_k8s_graph()
        initial_state = {"user_input": user_input}
        result = app.invoke(initial_state)
        return result.get("result") or result.get("error", "K8s operation completed")
    except Exception as e:
        return f"Error processing K8s request: {e}"

def handle_alert_workflow():
    """Handle the main K8s alert processing workflow"""
    try:
        print("🚀 Starting K8s alert processing workflow...")
        app = build_graph().compile()
        initial_state = {
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
            "workflow_type": "k8s"
        }

        print("📊 Processing through nodes: read_from_db → fetch_resolution → decision → execute...")
        result = app.invoke(initial_state)

        # Print workflow summary
        print("\n📋 Workflow Summary:")
        print(f"  - Alerts processed: {len(result.get('alerts', []))}")
        print(f"  - Resolutions found: {len(result.get('resolutions', []))}")
        print(f"  - Actions executed: {len(result.get('executed', []))}")
        print(f"  - Root cause: {result.get('root_cause', 'Not identified')}")
        print(f"  - Verification status: {result.get('verification_status', 'Not verified')}")

        return result
    except Exception as e:
        return f"Error processing K8s alert workflow: {e}"

def main():
    """Main application entry point"""
    print("=== K8s Task Agent ===")
    print("📋 Available Options:")
    print("1. 🔧 K8s Operations (Direct)")
    print("2. 🚨 K8s Alert Processing Workflow (Full Pipeline)")
    print("3. 💬 Interactive K8s Mode")
    print("4. 📊 Test K8s Examples")

    while True:
        choice = input("\nSelect option (1-4, or 'exit'): ").strip()

        if choice.lower() in ['exit', 'quit', 'q']:
            print("👋 Goodbye!")
            break

        elif choice == '1':
            # Direct K8s operations
            print("\n🔧 K8s Direct Mode")
            print("Examples:")
            print("  - 'Get deployments in default namespace'")
            print("  - 'Fix service nginx-service port from 8085 to 8080'")
            print("  - 'Restart deployment myapp in production namespace'")

            user_input = input("\nEnter K8s command: ").strip()
            if user_input:
                result = handle_k8s_request(user_input)
                print(f"✅ Result: {result}")

        elif choice == '2':
            # Full K8s alert workflow
            print("\n🚨 Full K8s Alert Processing Workflow")
            print("Flow: read_alert_from_db → fetch_resolution → decide_next_node → execute")
            result = handle_alert_workflow()
            print(f"\n🏁 Final Result: {result}")

        elif choice == '3':
            # Interactive K8s mode
            print("\n💬 Interactive K8s Mode")
            print("Type K8s commands (type 'back' to return to main menu)")
            while True:
                k8s_input = input("K8s> ").strip()
                if k8s_input.lower() == 'back':
                    break
                if k8s_input:
                    result = handle_k8s_request(k8s_input)
                    print(f"Result: {result}")

        elif choice == '4':
            # Test K8s examples
            print("\n📊 Testing K8s Examples...")
            test_examples = [
                "Get deployments in default namespace",
                "Fetch pods in kube-system namespace",
                "List services in default namespace"
            ]

            for example in test_examples:
                print(f"\n🧪 Testing: {example}")
                result = handle_k8s_request(example)
                print(f"  Result: {result}")

        else:
            print("❌ Invalid option. Please select 1-4 or 'exit'")

if __name__ == "__main__":
    main()