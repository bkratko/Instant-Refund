from __future__ import annotations
from app.db import db_cursor

def run():
    with db_cursor() as (_, cur):
        # Add acquirer_id
        cur.execute("""
            ALTER TABLE refunds
            ADD COLUMN IF NOT EXISTS acquirer_id TEXT NULL;
        """)
        # Add flow_position with allowed values
        cur.execute("""
            ALTER TABLE refunds
            ADD COLUMN IF NOT EXISTS flow_position TEXT NOT NULL DEFAULT 'post_auth';
        """)
        # Add acquirer index
        cur.execute("""
            CREATE INDEX IF NOT EXISTS refunds_acquirer_idx ON refunds (acquirer_id);
        """)
        print("Migration complete: acquirer_id + flow_position added to refunds")

if __name__ == "__main__":
    run()
