"""
Test Clone Manager + Account Manager together.

Usage:
  cd ~/Hell/sentinel
  source venv/bin/activate
  python3 backend/modules/test_clone_account.py
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    print("")
    print("=" * 60)
    print("   📦 Clone Manager + 👤 Account Manager Test")
    print("=" * 60)

    # ── Setup ──
    from backend.modules.device_manager import DeviceManager
    from backend.modules.clone_manager import CloneManager
    from backend.modules.account_manager import AccountManager

    dm = DeviceManager()
    am = AccountManager()

    # Scan devices
    print("\n── STEP 1: Scan devices ──")
    devices = dm.scan()
    if not devices:
        print("   ❌ No devices found!")
        return

    first_serial = list(devices.keys())[0]
    device = devices[first_serial]
    print(f"   ✅ Using device: {first_serial} (DB ID: {device.db_id})")

    # ── Create Clone Manager ──
    print("\n── STEP 2: Create Clone Manager ──")
    cm = CloneManager(device.executor, device.db_id)
    clones = cm.load_clones_from_db()
    print(f"   ✅ Loaded {len(clones)} clones:")
    for c in clones:
        original = "⭐" if c["is_original"] else "  "
        account = f"→ account #{c['account_id']}" if c["account_id"] else "empty"
        print(f"      {original} [{c['clone_index']}] {c['package_name']} ({c['status']}) {account}")

    # ── Register Test Accounts ──
    print("\n── STEP 3: Register test accounts ──")

    # Find clone IDs from database
    from backend.database.connection import db_manager
    from backend.database.models import Clone

    session = db_manager.get_session()
    db_clones = session.query(Clone).filter_by(device_id=device.db_id).all()
    session.close()

    if not db_clones:
        print("   ❌ No clones found in database!")
        return

    # Register accounts for each clone
    test_accounts = [
        ("test_user_01", db_clones[0].id if len(db_clones) > 0 else None),
    ]

    # Add more if there are more clones
    if len(db_clones) > 1:
        test_accounts.append(("test_user_02", db_clones[1].id))
    if len(db_clones) > 2:
        test_accounts.append(("test_user_03", db_clones[2].id))

    registered_accounts = []
    for username, clone_id in test_accounts:
        account = am.register_account(
            username=username,
            clone_id=clone_id,
            device_id=device.db_id,
            email=f"{username}@test.com",
        )
        if account:
            registered_accounts.append(account)
            print(f"   ✅ @{username} registered (ID: {account.id}, State: {account.state.value})")

    # Link accounts to clones
    print("\n── STEP 4: Link accounts to clones ──")
    cm.load_clones_from_db()  # Refresh
    for c in cm.get_clone_list():
        account = f"→ account #{c['account_id']}" if c["account_id"] else "empty"
        print(f"      [{c['clone_index']}] {c['package_name']} {account}")

    # ── Test State Transitions ──
    print("\n── STEP 5: Test state transitions ──")
    if registered_accounts:
        acct = registered_accounts[0]
        print(f"   Account @{acct.username} (ID: {acct.id})")
        print(f"   Current state: {acct.state.value}")

        # Check auto transitions
        new_state = am.check_auto_transitions(acct.id)
        if new_state:
            print(f"   Auto-transitioned to: {new_state.value}")
        else:
            print(f"   No auto-transition needed")

        # Get current state
        current = am.get_account_state(acct.id)
        print(f"   State after check: {current.value}")

    # ── Test Rate Limits ──
    print("\n── STEP 6: Test rate limits ──")
    if registered_accounts:
        acct = registered_accounts[0]

        # Check if can like
        can_like, reason = am.can_perform_action(acct.id, "like")
        print(f"   Can like? {can_like} ({reason})")

        can_follow, reason = am.can_perform_action(acct.id, "follow")
        print(f"   Can follow? {can_follow} ({reason})")

        can_comment, reason = am.can_perform_action(acct.id, "comment")
        print(f"   Can comment? {can_comment} ({reason})")

        # Get remaining actions
        remaining = am.get_remaining_actions(acct.id)
        print(f"   Remaining today: {json.dumps(remaining)}")

    # ── Test Action Recording ──
    print("\n── STEP 7: Record some test actions ──")
    if registered_accounts:
        acct = registered_accounts[0]

        # Record some likes
        for i in range(3):
            action_id = am.record_action(
                account_id=acct.id,
                action_type="like",
                success=True,
                target_user=f"liked_user_{i}",
                target_hashtag="test",
            )
            print(f"   ✅ Like #{i+1} recorded (action log ID: {action_id})")

        # Record a follow
        action_id = am.record_action(
            account_id=acct.id,
            action_type="follow",
            success=True,
            target_user="followed_user_1",
            target_hashtag="travel",
        )
        print(f"   ✅ Follow recorded (action log ID: {action_id})")

        # Check updated counters
        remaining = am.get_remaining_actions(acct.id)
        print(f"   Remaining after actions: {json.dumps(remaining)}")

    # ── Test Account Summary ──
    print("\n── STEP 8: Account summary ──")
    if registered_accounts:
        acct = registered_accounts[0]
        summary = am.get_account_summary(acct.id)
        if summary:
            print(json.dumps(summary, indent=4, default=str))

    # ── Test Clone Cycling ──
    print("\n── STEP 9: Test clone cycling ──")
    print("   (Opening each clone, waiting 3 seconds, closing)")

    def test_callback(package_name: str, clone_id: int, account_id):
        print(f"      📱 Callback: {package_name} (clone #{clone_id}, account #{account_id})")
        print(f"      ⏳ Simulating work for 3 seconds...")
        time.sleep(3)
        print(f"      ✅ Work done on {package_name}")

    results = cm.cycle_all_clones(
        callback=test_callback,
        only_active=False,  # Include empty clones too for testing
        delay_between_clones_min=2,
        delay_between_clones_max=5,
    )

    print(f"\n   Cycle results:")
    print(f"      Total: {results['total']}")
    print(f"      Success: {results['success']}")
    print(f"      Failed: {results['failed']}")

    # ── Test Get All Accounts ──
    print("\n── STEP 10: All accounts ──")
    all_accounts = am.get_all_accounts()
    print(f"   Total accounts: {len(all_accounts)}")
    for a in all_accounts:
        print(f"      @{a['username']} | State: {a['state']} | "
              f"Likes today: {a['likes_today']} | "
              f"Risk: {a['risk_score']}")

    # ── Verify Database ──
    print("\n── STEP 11: Verify database ──")
    from backend.database.models import Account, ActionLog, FollowTracking, AccountStateHistory

    session = db_manager.get_session()
    try:
        account_count = session.query(Account).count()
        action_count = session.query(ActionLog).count()
        follow_count = session.query(FollowTracking).count()
        history_count = session.query(AccountStateHistory).count()

        print(f"   Accounts in DB: {account_count}")
        print(f"   Action logs: {action_count}")
        print(f"   Follow tracking: {follow_count}")
        print(f"   State history: {history_count}")

    finally:
        session.close()

    # Done
    print(f"\n{'=' * 60}")
    print("   🎉 Clone Manager + Account Manager Test Complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()