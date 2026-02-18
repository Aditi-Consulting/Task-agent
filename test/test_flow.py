import asyncio
from graph.graph_builder import build_graph
from store.db import ensure_tables, fetch_resolution
from app.nodes.generate_remediation_node import generate_remediation_node
from app.nodes.execute_action_node import execute_action_node

async def test_complete_flow():
    print("Starting complete flow test...")

    # Step 1: Ensure DB tables exist
    print("\n1. Setting up database...")
    ensure_tables()

    # Step 2: Build the graph with actual nodes
    print("\n2. Building graph...")
    graph = build_graph()

    app = graph.compile()  # Assuming compile should be async

    # If compile() is not async, remove the await and just use:
    # app = graph.compile()

    # Step 3: Prepare test input state
    print("\n3. Preparing test state...")
    initial_state = {
        "alerts": [{
            "id": 1,
            "issue_type": "pod_crash",
            "ticket": "Pod myapp-pod-123 in namespace default is crashing with OOMKilled",
            "severity": "high",
            "status": "new"
        }],
        "processed": [],
        "executed": [],
        "resolutions": [],
        "generated": [],
        "splunk_results": None
    }

    # Step 4: Execute the graph
    print("\n4. Executing graph flow...")
    print("----------------------------")
    try:
        # Convert invoke to async if it's not already
        if asyncio.iscoroutinefunction(app.invoke):
            result = await app.invoke(initial_state)
        else:
            result = app.invoke(initial_state)

        # Rest of the verification code remains the same
        print("\n5. Verifying results...")

        saved_resolution = fetch_resolution("pod_crash")
        if saved_resolution:
            print("✓ Resolution saved in database")
            print(f"  Action type: {saved_resolution['action_type']}")
        else:
            print("✗ No resolution found in database")

        if result["processed"]:
            print("✓ Alert processed")
            print(f"  Processed alerts: {len(result['processed'])}")

        if result["executed"]:
            print("✓ Action executed")
            for exec_result in result["executed"]:
                print(f"  Status: {exec_result['status']}")

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        raise e

if __name__ == "__main__":
    print("Starting full flow test...")
    asyncio.run(test_complete_flow())