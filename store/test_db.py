import time
from store.db import *


def test_db_operations():
    print("Starting database operations test...")

    # Step 1: Ensure tables exist
    print("1. Creating tables...")
    ensure_tables()

    # Step 2: Insert test resolution
    print("2. Inserting test resolution...")
    test_resolution = {
        "issue_type": "pod_crash",
        "description": "Pod crash due to memory limit",
        "action_type": "restart_pod",
        "action_payload": {
            "namespace": "default",
            "pod_name": "test-pod",
            "container": "main"
        }
    }
    save_resolution(**test_resolution)

    # Step 3: Fetch and verify resolution
    print("3. Fetching resolution...")
    time.sleep(1)  # Small delay to ensure DB operation completed
    fetched = fetch_resolution("pod_crash")
    if fetched:
        print("✓ Resolution fetched successfully")
        print(f"  Action type: {fetched['action_type']}")
        print(f"  Payload: {fetched['action_payload']}")
    else:
        print("✗ Failed to fetch resolution")

    # Step 4: Test alert fetching
    print("\n4. Testing alert fetching...")
    alerts = fetch_alerts_from_db()
    print(f"  Found {len(alerts)} alerts")

    print("\nTest completed!")


if __name__ == "__main__":
    try:
        test_db_operations()
    except Exception as e:
        print(f"Error during test: {str(e)}")
