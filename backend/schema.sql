-- Initial schema for StudyAgent
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create resource table
CREATE TABLE IF NOT EXISTS resource (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(512) NOT NULL,
    topic VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'processing',
    file_path_or_uri VARCHAR(1024),
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE,
    pipeline_version VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Create chunk table
CREATE TABLE IF NOT EXISTS chunk (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    section_heading VARCHAR(512),
    chunk_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    pedagogy_role VARCHAR(64),
    difficulty VARCHAR(32),
    embedding vector(384),
    enrichment_metadata JSONB,
    embedding_model_id VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(resource_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS ix_chunk_resource_id ON chunk(resource_id);
CREATE INDEX IF NOT EXISTS ix_chunk_resource_chunk_index ON chunk(resource_id, chunk_index);

-- Create chunk_concept table
CREATE TABLE IF NOT EXISTS chunk_concept (
    id SERIAL PRIMARY KEY,
    chunk_id UUID NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    concept_id VARCHAR(256) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'mentions'
);
CREATE INDEX IF NOT EXISTS ix_chunk_concept_chunk_id ON chunk_concept(chunk_id);
CREATE INDEX IF NOT EXISTS ix_chunk_concept_concept_id ON chunk_concept(concept_id);

-- Create formula table
CREATE TABLE IF NOT EXISTS formula (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    name VARCHAR(256),
    expression TEXT NOT NULL,
    expression_plain TEXT,
    variables JSONB,
    concept_ids JSONB,
    source_chunk_id UUID REFERENCES chunk(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_formula_resource_id ON formula(resource_id);

-- Create resource_concept_stats table
CREATE TABLE IF NOT EXISTS resource_concept_stats (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    concept_id VARCHAR(256) NOT NULL,
    teach_count INTEGER NOT NULL DEFAULT 0,
    mention_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    first_position_mean FLOAT,
    last_position_mean FLOAT,
    avg_quality FLOAT,
    source_types JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(resource_id, concept_id)
);
CREATE INDEX IF NOT EXISTS ix_resource_concept_stats_resource ON resource_concept_stats(resource_id);
CREATE INDEX IF NOT EXISTS ix_resource_concept_stats_concept ON resource_concept_stats(concept_id);

-- Create resource_concept_evidence table
CREATE TABLE IF NOT EXISTS resource_concept_evidence (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    concept_id VARCHAR(256) NOT NULL,
    chunk_id UUID NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    role VARCHAR(32) DEFAULT 'mentions',
    weight FLOAT DEFAULT 1.0,
    quality_score FLOAT,
    position_index INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_resource_concept_evidence_resource_concept ON resource_concept_evidence(resource_id, concept_id);
CREATE INDEX IF NOT EXISTS ix_resource_concept_evidence_resource_chunk ON resource_concept_evidence(resource_id, chunk_id);

-- Create resource_concept_graph table
CREATE TABLE IF NOT EXISTS resource_concept_graph (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    source_concept_id VARCHAR(256) NOT NULL,
    target_concept_id VARCHAR(256) NOT NULL,
    assoc_weight FLOAT DEFAULT 0.0,
    dir_forward FLOAT,
    dir_backward FLOAT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_resource_concept_graph_source ON resource_concept_graph(resource_id, source_concept_id);
CREATE INDEX IF NOT EXISTS ix_resource_concept_graph_target ON resource_concept_graph(resource_id, target_concept_id);

-- Create resource_bundle table
CREATE TABLE IF NOT EXISTS resource_bundle (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    primary_concept_id VARCHAR(256) NOT NULL,
    support_concepts JSONB,
    prereq_hints JSONB,
    evidence_prototypes JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(resource_id, primary_concept_id)
);
CREATE INDEX IF NOT EXISTS ix_resource_bundle_resource ON resource_bundle(resource_id);

-- Create resource_topic_bundle table
CREATE TABLE IF NOT EXISTS resource_topic_bundle (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    topic_id VARCHAR(256) NOT NULL,
    topic_name VARCHAR(512) NOT NULL,
    primary_concepts JSONB,
    support_concepts JSONB,
    prereq_topic_ids JSONB,
    representative_chunk_ids JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(resource_id, topic_id)
);
CREATE INDEX IF NOT EXISTS ix_resource_topic_bundle_resource ON resource_topic_bundle(resource_id);

-- Create resource_topic table
CREATE TABLE IF NOT EXISTS resource_topic (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    topic_string VARCHAR(512) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_resource_topic_resource ON resource_topic(resource_id);

-- Create resource_learning_objective table
CREATE TABLE IF NOT EXISTS resource_learning_objective (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    objective_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_resource_learning_objective_resource ON resource_learning_objective(resource_id);

-- Create resource_prereq_hint table
CREATE TABLE IF NOT EXISTS resource_prereq_hint (
    id SERIAL PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    source_concept_id VARCHAR(256) NOT NULL,
    target_concept_id VARCHAR(256) NOT NULL,
    support_count INTEGER DEFAULT 0,
    sources JSONB
);
CREATE INDEX IF NOT EXISTS ix_resource_prereq_hint_resource ON resource_prereq_hint(resource_id);

-- Create user_profile table
CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(256) UNIQUE,
    display_name VARCHAR(256),
    email VARCHAR(512),
    global_mastery JSONB,
    preferences JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Create user_session table
CREATE TABLE IF NOT EXISTS user_session (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_profile(id) ON DELETE CASCADE,
    resource_id UUID REFERENCES resource(id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    plan_state JSONB,
    mastery JSONB,
    token_usage JSONB,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_user_session_user_id ON user_session(user_id);
CREATE INDEX IF NOT EXISTS ix_user_session_resource_id ON user_session(resource_id);

-- Create tutor_turn table
CREATE TABLE IF NOT EXISTS tutor_turn (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES user_session(id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    student_message TEXT,
    tutor_response TEXT,
    tutor_question TEXT,
    curriculum_phase_index INTEGER,
    current_step VARCHAR(64),
    target_concepts JSONB,
    pedagogical_action VARCHAR(64),
    progression_decision INTEGER,
    policy_output JSONB,
    evaluator_output JSONB,
    retrieved_chunks JSONB,
    mastery_before JSONB,
    mastery_after JSONB,
    rl_reward FLOAT,
    rl_state_embedding vector(384),
    rl_action_embedding vector(384),
    token_count INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(session_id, turn_index)
);
CREATE INDEX IF NOT EXISTS ix_tutor_turn_session_id ON tutor_turn(session_id);

-- Create ingestion_job table
CREATE TABLE IF NOT EXISTS ingestion_job (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    resource_id UUID NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    current_stage VARCHAR(64),
    stages_completed JSONB,
    progress_percent INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    error_stage VARCHAR(64),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ingestion_job_resource_id ON ingestion_job(resource_id);

-- Create session_feedback_entry table
CREATE TABLE IF NOT EXISTS session_feedback_entry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES user_session(id) ON DELETE CASCADE,
    turn_id UUID REFERENCES tutor_turn(id) ON DELETE SET NULL,
    feedback_type VARCHAR(64) NOT NULL,
    rating INTEGER,
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_session_feedback_entry_session_id ON session_feedback_entry(session_id);

-- Create api_key table
CREATE TABLE IF NOT EXISTS api_key (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_profile(id) ON DELETE CASCADE,
    key_hash VARCHAR(512) NOT NULL UNIQUE,
    name VARCHAR(256),
    is_active BOOLEAN DEFAULT TRUE,
    rate_limit_rpm INTEGER,
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Create HNSW indexes for vector similarity search
CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_tutor_turn_state_embedding_hnsw ON tutor_turn USING hnsw (rl_state_embedding vector_cosine_ops);

-- Create alembic_version table to track migrations
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('001') ON CONFLICT DO NOTHING;
