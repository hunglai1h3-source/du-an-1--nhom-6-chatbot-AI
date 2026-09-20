# -*- coding: utf-8 -*-
"""
Phase 9: Personal Health Intelligence - Database Schema & Migrations.

Defines schemas and indexes for:
- health_episodes: First-class health episode entity tracking condition over time
- health_episode_events: Event timeline within each health episode
- personal_baselines: Individual-specific baseline patterns with maturity levels
- personal_fact_states: Canonical personal facts with provenance and confidence
- adaptive_severity_logs: Audit logs for adaptive severity evaluations
"""

import logging

logger = logging.getLogger(__name__)


def is_sqlite_connection(connection) -> bool:
    """Detect whether connection is an SQLite connection or wrapped PostgreSQL."""
    raw = getattr(connection, "_connection", connection)
    module_name = type(raw).__module__
    return "sqlite" in module_name.lower()


def init_personal_intelligence_schema(connection) -> None:
    """
    Initialize all Phase 9 tables and indexes idempotently.
    Compatible with both PostgreSQL and SQLite.
    """
    is_sqlite = is_sqlite_connection(connection)

    id_col = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
    timestamp_type = "TIMESTAMP" if is_sqlite else "TIMESTAMPTZ"
    now_default = "DEFAULT CURRENT_TIMESTAMP"

    # 1. health_episodes
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS health_episodes (
            id {id_col},
            episode_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            profile_type TEXT NOT NULL DEFAULT 'self',
            profile_ref TEXT NOT NULL DEFAULT 'self',
            chief_complaint TEXT NOT NULL,
            normalized_problem TEXT,
            body_location TEXT,
            onset_at {timestamp_type},
            first_reported_at {timestamp_type} NOT NULL {now_default},
            last_updated_at {timestamp_type} NOT NULL {now_default},
            status TEXT NOT NULL DEFAULT 'OPEN',
            severity_current INTEGER DEFAULT 1,
            severity_peak INTEGER DEFAULT 1,
            pain_scale INTEGER,
            fever INTEGER DEFAULT 0,
            associated_symptoms_json TEXT,
            red_flags_json TEXT,
            medications_taken_json TEXT,
            actions_taken_json TEXT,
            outcome TEXT,
            topic TEXT,
            conversation_ids_json TEXT,
            source_message_ids_json TEXT,
            safety_peak_level TEXT DEFAULT 'NORMAL',
            confidence TEXT DEFAULT 'CONFIRMED',
            recurrence_of_episode_id TEXT,
            created_at {timestamp_type} NOT NULL {now_default},
            updated_at {timestamp_type} NOT NULL {now_default}
        )
    """)

    # Indexes for health_episodes
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_user_profile
        ON health_episodes(user_id, profile_type, profile_ref, status, last_updated_at DESC)
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_complaint
        ON health_episodes(user_id, profile_ref, chief_complaint)
    """)

    # 2. health_episode_events
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS health_episode_events (
            id {id_col},
            episode_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            conversation_id TEXT,
            message_id INTEGER,
            client_message_id TEXT,
            event_data_json TEXT NOT NULL,
            occurred_at {timestamp_type} NOT NULL {now_default},
            created_at {timestamp_type} NOT NULL {now_default}
        )
    """)

    # Indexes for health_episode_events
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_episode_events_lookup
        ON health_episode_events(episode_id, occurred_at ASC)
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_episode_events_client_mid
        ON health_episode_events(episode_id, client_message_id)
    """)

    # 3. personal_baselines
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS personal_baselines (
            id {id_col},
            user_id INTEGER NOT NULL,
            profile_type TEXT NOT NULL DEFAULT 'self',
            profile_ref TEXT NOT NULL DEFAULT 'self',
            attribute_name TEXT NOT NULL,
            pattern_value_json TEXT NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 1,
            maturity TEXT NOT NULL DEFAULT 'NONE',
            first_seen {timestamp_type} NOT NULL {now_default},
            last_seen {timestamp_type} NOT NULL {now_default},
            confidence TEXT NOT NULL DEFAULT 'CONFIRMED',
            updated_at {timestamp_type} NOT NULL {now_default},
            UNIQUE(user_id, profile_type, profile_ref, attribute_name)
        )
    """)

    # Index for personal_baselines
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_baselines_lookup
        ON personal_baselines(user_id, profile_type, profile_ref)
    """)

    # 4. personal_fact_states
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS personal_fact_states (
            id {id_col},
            user_id INTEGER NOT NULL,
            profile_type TEXT NOT NULL DEFAULT 'self',
            profile_ref TEXT NOT NULL DEFAULT 'self',
            fact_category TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value_json TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL DEFAULT 'CONFIRMED',
            is_active INTEGER NOT NULL DEFAULT 1,
            conflict_details TEXT,
            updated_at {timestamp_type} NOT NULL {now_default},
            UNIQUE(user_id, profile_type, profile_ref, fact_category, fact_key)
        )
    """)

    # Index for personal_fact_states
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_fact_states_lookup
        ON personal_fact_states(user_id, profile_type, profile_ref, fact_category, is_active)
    """)

    # 5. adaptive_severity_logs
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS adaptive_severity_logs (
            id {id_col},
            assessment_id TEXT UNIQUE NOT NULL,
            user_id INTEGER,
            profile_ref TEXT,
            episode_id TEXT,
            conversation_id TEXT,
            safety_level TEXT NOT NULL,
            adaptive_level TEXT NOT NULL,
            final_level TEXT NOT NULL,
            reason_codes_json TEXT NOT NULL,
            engine_version TEXT NOT NULL DEFAULT '1.0',
            created_at {timestamp_type} NOT NULL {now_default}
        )
    """)

    # Index for adaptive_severity_logs
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_severity_logs_lookup
        ON adaptive_severity_logs(user_id, profile_ref, created_at DESC)
    """)

    logger.info("Phase 9: Personal Health Intelligence schema initialized successfully.")


def drop_personal_intelligence_schema(connection) -> None:
    """Safe rollback helper to drop Phase 9 tables."""
    tables = [
        "adaptive_severity_logs",
        "personal_fact_states",
        "personal_baselines",
        "health_episode_events",
        "health_episodes"
    ]
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    logger.info("Phase 9 tables dropped successfully for rollback.")
