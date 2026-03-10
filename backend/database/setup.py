"""
Database setup script.
Run this once to create all tables.

Usage:
  cd ~/sentinel
  source venv/bin/activate
  python -m backend.database.setup
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database.connection import db_manager
from backend.database.models import Base


def setup_database():
    """Create all tables and verify"""

    print("=" * 50)
    print("  Sentinel — Database Setup")
    print("=" * 50)
    print()

    # Test connection
    print("1. Testing database connection...")
    if not db_manager.test_connection():
        print("\n❌ Cannot connect to database.")
        print("   Make sure PostgreSQL is running:")
        print("   brew services start postgresql")
        print("   And database exists:")
        print("   createdb sentinel")
        sys.exit(1)

    # Create tables
    print("\n2. Creating all tables...")
    db_manager.create_all_tables()

    # Verify tables
    print("\n3. Verifying tables...")
    from sqlalchemy import inspect
    inspector = inspect(db_manager.engine)
    tables = inspector.get_table_names()

    expected_tables = [
        "devices",
        "clones",
        "accounts",
        "account_state_history",
        "task_templates",
        "task_executions",
        "action_logs",
        "account_metrics_history",
        "clone_account_history",
        "follow_tracking",
        "schedules",
        "error_logs",
    ]

    print(f"\n   Found {len(tables)} tables:")
    all_found = True
    for table in expected_tables:
        if table in tables:
            print(f"   ✅ {table}")
        else:
            print(f"   ❌ {table} — MISSING!")
            all_found = False

    # Check for extra tables
    extra = set(tables) - set(expected_tables)
    if extra:
        print(f"\n   Extra tables found: {extra}")

    if all_found:
        print(f"\n{'=' * 50}")
        print("  ✅ ALL {len(expected_tables)} TABLES CREATED SUCCESSFULLY!")
        print(f"{'=' * 50}")
    else:
        print(f"\n{'=' * 50}")
        print("  ⚠️  Some tables are missing. Check errors above.")
        print(f"{'=' * 50}")

    # Print table details
    print("\n4. Table details:")
    for table in expected_tables:
        if table in tables:
            columns = inspector.get_columns(table)
            print(f"\n   📋 {table} ({len(columns)} columns)")
            for col in columns:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                print(f"      • {col['name']}: {col['type']} {nullable}")


def reset_database():
    """Drop and recreate all tables (DEVELOPMENT ONLY)"""
    print("⚠️  WARNING: This will DELETE all data!")
    confirm = input("Type 'RESET' to confirm: ")
    if confirm == "RESET":
        db_manager.drop_all_tables()
        db_manager.create_all_tables()
        print("✅ Database reset complete")
    else:
        print("❌ Reset cancelled")


def insert_default_data():
    """Insert default schedules and task templates"""

    session = db_manager.get_session()

    try:
        from backend.database.models import Schedule, TaskTemplate

        # Default schedule
        existing = session.query(Schedule).first()
        if not existing:
            default_schedule = Schedule(
                name="Default Schedule",
                description="Standard automation schedule",
                active_hours_start="08:00",
                active_hours_end="22:00",
                active_days=[1, 2, 3, 4, 5, 6, 7],
                sessions_per_day=4,
                session_min_minutes=15,
                session_max_minutes=45,
                break_min_minutes=60,
                break_max_minutes=240,
                timezone="UTC",
            )
            session.add(default_schedule)
            print("   ✅ Default schedule created")

        # Default task templates
        existing_templates = session.query(TaskTemplate).count()
        if existing_templates == 0:
            templates = [
                TaskTemplate(
                    name="Warmup — Day 1-2",
                    description="Light browsing and minimal engagement for new accounts",
                    task_type="warmup",
                    applicable_states=["warmup"],
                    config={
                        "max_likes": 10,
                        "max_follows": 2,
                        "max_comments": 0,
                        "max_stories": 5,
                        "browse_feed_scrolls": 10,
                        "delay_min": 60,
                        "delay_max": 180,
                        "session_duration_min": 10,
                        "session_duration_max": 20,
                    },
                    priority=1,
                ),
                TaskTemplate(
                    name="Growing — Day 3-7",
                    description="Moderate engagement to build activity history",
                    task_type="growing",
                    applicable_states=["growing"],
                    config={
                        "max_likes": 40,
                        "max_follows": 15,
                        "max_comments": 5,
                        "max_stories": 15,
                        "browse_feed_scrolls": 20,
                        "delay_min": 30,
                        "delay_max": 120,
                        "session_duration_min": 15,
                        "session_duration_max": 35,
                    },
                    priority=2,
                ),
                TaskTemplate(
                    name="Cooldown — Reduced Activity",
                    description="Minimal activity after rate limit or suspicious behavior",
                    task_type="cooldown",
                    applicable_states=["cooldown"],
                    config={
                        "max_likes": 0,
                        "max_follows": 0,
                        "max_comments": 0,
                        "max_stories": 3,
                        "browse_feed_scrolls": 5,
                        "delay_min": 120,
                        "delay_max": 300,
                        "session_duration_min": 5,
                        "session_duration_max": 10,
                    },
                    priority=10,
                ),
            ]
            session.add_all(templates)
            print(f"   ✅ {len(templates)} default task templates created")

        session.commit()
        print("   ✅ Default data inserted")

    except Exception as e:
        session.rollback()
        print(f"   ❌ Error inserting default data: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        reset_database()
    else:
        setup_database()
        print("\n5. Inserting default data...")
        insert_default_data()
        print("\n🎉 Database is ready to use!")