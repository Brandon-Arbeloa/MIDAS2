-- MIDAS Database Initialization Script

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS midas;
CREATE SCHEMA IF NOT EXISTS celery;

-- Set search path
SET search_path TO midas, public;

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    content_hash VARCHAR(64),
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    user_id INTEGER,
    tags TEXT[],
    CONSTRAINT unique_file_path UNIQUE(file_path)
);

-- Create indexes for documents
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX idx_documents_filename_trgm ON documents USING GIST(filename gist_trgm_ops);

-- Search queries table
CREATE TABLE IF NOT EXISTS search_queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_text TEXT NOT NULL,
    query_embedding vector(384),
    results_count INTEGER DEFAULT 0,
    response_time_ms INTEGER,
    user_id INTEGER,
    session_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for search queries
CREATE INDEX idx_search_queries_created_at ON search_queries(created_at DESC);
CREATE INDEX idx_search_queries_user_id ON search_queries(user_id);
CREATE INDEX idx_search_queries_embedding ON search_queries USING ivfflat(query_embedding vector_cosine_ops);

-- SQL query results cache
CREATE TABLE IF NOT EXISTS sql_query_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_hash VARCHAR(64) NOT NULL,
    database_name VARCHAR(255) NOT NULL,
    query_text TEXT NOT NULL,
    result_path TEXT,
    result_rows INTEGER,
    execution_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    CONSTRAINT unique_query_cache UNIQUE(query_hash, database_name)
);

-- Create indexes for query cache
CREATE INDEX idx_sql_query_cache_hash ON sql_query_cache(query_hash);
CREATE INDEX idx_sql_query_cache_expires ON sql_query_cache(expires_at);

-- Database connections table
CREATE TABLE IF NOT EXISTS database_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    db_type VARCHAR(50) NOT NULL,
    connection_config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    last_tested TIMESTAMP WITH TIME ZONE,
    test_status VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for database connections
CREATE INDEX idx_database_connections_active ON database_connections(is_active);
CREATE INDEX idx_database_connections_type ON database_connections(db_type);

-- Dashboard configurations table
CREATE TABLE IF NOT EXISTS dashboards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    config JSONB NOT NULL,
    theme VARCHAR(50) DEFAULT 'light',
    author VARCHAR(255),
    is_public BOOLEAN DEFAULT false,
    is_template BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1
);

-- Create indexes for dashboards
CREATE INDEX idx_dashboards_author ON dashboards(author);
CREATE INDEX idx_dashboards_public ON dashboards(is_public);
CREATE INDEX idx_dashboards_template ON dashboards(is_template);

-- Dashboard versions table
CREATE TABLE IF NOT EXISTS dashboard_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dashboard_id UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    config JSONB NOT NULL,
    change_description TEXT,
    author VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_dashboard_version UNIQUE(dashboard_id, version)
);

-- Create indexes for dashboard versions
CREATE INDEX idx_dashboard_versions_dashboard ON dashboard_versions(dashboard_id);

-- Shared dashboards table
CREATE TABLE IF NOT EXISTS shared_dashboards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dashboard_id UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    share_token VARCHAR(255) NOT NULL UNIQUE,
    shared_by VARCHAR(255),
    shared_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE
);

-- Create indexes for shared dashboards
CREATE INDEX idx_shared_dashboards_token ON shared_dashboards(share_token);
CREATE INDEX idx_shared_dashboards_expires ON shared_dashboards(expires_at);

-- User sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_id INTEGER,
    user_data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for user sessions
CREATE INDEX idx_user_sessions_session ON user_sessions(session_id);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);

-- System metrics table
CREATE TABLE IF NOT EXISTS system_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(255) NOT NULL,
    metric_value NUMERIC,
    metric_data JSONB DEFAULT '{}',
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    host_name VARCHAR(255),
    service_name VARCHAR(255)
);

-- Create indexes for system metrics
CREATE INDEX idx_system_metrics_type ON system_metrics(metric_type);
CREATE INDEX idx_system_metrics_name ON system_metrics(metric_name);
CREATE INDEX idx_system_metrics_recorded ON system_metrics(recorded_at DESC);
CREATE INDEX idx_system_metrics_service ON system_metrics(service_name);

-- Create update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply update timestamp triggers
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_database_connections_updated_at BEFORE UPDATE ON database_connections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dashboards_updated_at BEFORE UPDATE ON dashboards
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_sessions_updated_at BEFORE UPDATE ON user_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create cleanup function for expired data
CREATE OR REPLACE FUNCTION cleanup_expired_data()
RETURNS void AS $$
BEGIN
    -- Clean expired query cache
    DELETE FROM sql_query_cache WHERE expires_at < CURRENT_TIMESTAMP;
    
    -- Clean expired shared dashboards
    DELETE FROM shared_dashboards WHERE expires_at < CURRENT_TIMESTAMP;
    
    -- Clean expired user sessions
    DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP;
    
    -- Clean old system metrics (keep 30 days)
    DELETE FROM system_metrics WHERE recorded_at < CURRENT_TIMESTAMP - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA midas TO midas_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA midas TO midas_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA midas TO midas_user;

-- Create Celery tables in celery schema
SET search_path TO celery, public;

-- Celery task results
CREATE TABLE IF NOT EXISTS celery_taskmeta (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(155) UNIQUE,
    status VARCHAR(50),
    result BYTEA,
    date_done TIMESTAMP WITH TIME ZONE,
    traceback TEXT,
    name VARCHAR(155),
    args BYTEA,
    kwargs BYTEA,
    worker VARCHAR(155),
    retries INTEGER,
    queue VARCHAR(155)
);

-- Celery group results
CREATE TABLE IF NOT EXISTS celery_groupmeta (
    id SERIAL PRIMARY KEY,
    taskset_id VARCHAR(155) UNIQUE,
    result BYTEA,
    date_done TIMESTAMP WITH TIME ZONE
);

-- Grant Celery permissions
GRANT ALL PRIVILEGES ON SCHEMA celery TO midas_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA celery TO midas_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA celery TO midas_user;

-- Reset search path
SET search_path TO public;