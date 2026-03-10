"""
Test warmup task — ONE FULL SESSION (5-12 minutes).

Usage:
  cd ~/Hell/sentinel
  source venv/bin/activate
  python3 backend/modules/test_warmup.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    print("")
    print("=" * 60)
    print("   🌅 Warmup Task Test — ONE FULL SESSION")
    print("   Watch the emulator!")
    print("=" * 60)
    print("")
    print("   This runs one session (5-12 minutes)")
    print("   You'll see reels, home feed, explore browsing")
    print("")

    from backend.modules.device_manager import DeviceManager
    from backend.modules.screen_reader import ScreenReader
    from backend.modules.warmup_task import WarmupTask
    from backend.modules.account_manager import AccountManager

    dm = DeviceManager()
    am = AccountManager()

    print("1. Setting up...")
    devices = dm.scan()
    if not devices:
        print("   ❌ No devices found!")
        return

    serial = list(devices.keys())[0]
    device = devices[serial]
    executor = device.executor
    print(f"   ✅ Device: {serial} ({executor.mode.value})")

    print("\n2. Connecting screen reader...")
    reader = ScreenReader(serial)
    reader.connect()
    print("   ✅ Connected")

    print("\n3. Setting up account...")
    account = am.register_account(
        username="warmup_test_user",
        device_id=device.db_id,
    )
    if account:
        print(f"   ✅ @{account.username} (ID: {account.id}, State: {account.state.value})")

    print("\n4. Creating warmup task...")
    warmup = WarmupTask(
        executor=executor,
        reader=reader,
        account_manager=am,
        account_id=account.id,
        instagram_package="com.instagram.android",
    )

    # ONE SESSION: 5-12 minutes (no gaps, single session)
    warmup.total_day_minutes_min = 5
    warmup.total_day_minutes_max = 12
    warmup.session_minutes_min = 5
    warmup.session_minutes_max = 12
    warmup.gap_minutes_min = 0
    warmup.gap_minutes_max = 0

    print("\n5. 🚀 Starting warmup session (watch emulator!)...")
    print("─" * 60)
    summary = warmup.run()
    print("─" * 60)

    print(f"\n6. Results:")
    print(f"   Status:          {summary.get('status')}")
    print(f"   Sessions:        {summary.get('sessions')}")
    print(f"   Active time:     {summary.get('total_active_minutes')} min")
    print(f"   Reels seen:      {summary.get('reels_seen')}")
    print(f"   Reels liked:     {summary.get('reels_liked')}")
    print(f"   Home posts seen: {summary.get('home_posts_seen')}")
    print(f"   Home posts liked:{summary.get('home_posts_liked')}")
    print(f"   Explore seen:    {summary.get('explore_posts_seen')}")
    print(f"   Followed:        {summary.get('followed')}")

    acct_summary = am.get_account_summary(account.id)
    if acct_summary:
        print(f"\n7. Account state:")
        print(f"   Likes today:  {acct_summary['today']['likes']}")
        print(f"   Follows today:{acct_summary['today']['follows']}")
        print(f"   Total likes:  {acct_summary['totals']['likes']}")
        print(f"   Risk score:   {acct_summary['safety']['risk_score']}")

    print(f"\n{'=' * 60}")
    print("   🎉 Warmup session complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()