-- NormaAI Database Initialization
-- Run automatically by Docker on first startup

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Organizations (consulenze, studi legali)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    plan VARCHAR(50) DEFAULT 'starter',  -- starter, professional, enterprise
    max_clients INTEGER DEFAULT 5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Users within organizations
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(512) NOT NULL DEFAULT '',
    role VARCHAR(50) DEFAULT 'member',  -- admin, member, viewer
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Client companies monitored by the organization
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    employee_count INTEGER,
    revenue_eur BIGINT,
    jurisdictions TEXT[] DEFAULT '{}',  -- ['IT', 'DE', 'FR']
    applicable_frameworks TEXT[] DEFAULT '{}',  -- ['CSRD', 'CSDDD', 'AI_ACT']
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- EU Regulations stored
CREATE TABLE regulations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    celex VARCHAR(50) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    framework VARCHAR(50) NOT NULL,  -- CSRD, CSDDD, AI_ACT, DORA, NIS2, TAXONOMY, GDPR
    doc_type VARCHAR(50),  -- directive, regulation, delegated_act, implementing_act
    date_document DATE,
    date_in_force DATE,
    is_in_force BOOLEAN DEFAULT true,
    full_text_url TEXT,
    raw_html TEXT,
    last_crawled_at TIMESTAMP WITH TIME ZONE,
    last_amended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_regulations_celex ON regulations(celex);
CREATE INDEX idx_regulations_framework ON regulations(framework);

-- Amendments tracking
CREATE TABLE amendments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    original_regulation_id UUID REFERENCES regulations(id),
    amending_celex VARCHAR(50) NOT NULL,
    amending_title TEXT,
    amendment_date DATE,
    summary TEXT,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Regulatory alerts generated
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    regulation_id UUID REFERENCES regulations(id),
    severity VARCHAR(20) NOT NULL,  -- critical, high, medium, low, info
    framework VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    actions_required TEXT[],
    deadline DATE,
    is_read BOOLEAN DEFAULT false,
    is_dismissed BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_alerts_client ON alerts(client_id, created_at DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity);

-- Compliance assessments (gap analysis results)
CREATE TABLE assessments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    framework VARCHAR(50) NOT NULL,
    overall_score FLOAT,  -- 0.0 to 1.0
    status VARCHAR(50) DEFAULT 'in_progress',  -- in_progress, completed, stale
    gaps JSONB DEFAULT '[]',
    recommendations JSONB DEFAULT '[]',
    assessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assessed_by UUID REFERENCES users(id)
);

CREATE INDEX idx_assessments_client ON assessments(client_id, framework);

-- Q&A conversation history
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(id),
    user_id UUID NOT NULL REFERENCES users(id),
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Crawl job tracking
CREATE TABLE crawl_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type VARCHAR(50) NOT NULL,  -- full_crawl, amendment_check, single_regulation
    status VARCHAR(50) DEFAULT 'pending',  -- pending, running, completed, failed
    regulations_processed INTEGER DEFAULT 0,
    amendments_found INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Row-Level Security (RLS)
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- RLS Policies: users can only see their organization's data
CREATE POLICY clients_org_policy ON clients
    USING (org_id = current_setting('app.current_org_id')::UUID);

CREATE POLICY alerts_org_policy ON alerts
    USING (client_id IN (
        SELECT id FROM clients WHERE org_id = current_setting('app.current_org_id')::UUID
    ));

CREATE POLICY assessments_org_policy ON assessments
    USING (client_id IN (
        SELECT id FROM clients WHERE org_id = current_setting('app.current_org_id')::UUID
    ));

-- Seed: EU Framework reference data
INSERT INTO regulations (celex, title, framework, doc_type, date_document, is_in_force) VALUES
('32022L2464', 'Directive (EU) 2022/2464 - Corporate Sustainability Reporting Directive (CSRD)', 'CSRD', 'directive', '2022-12-14', true),
('32024L1760', 'Directive (EU) 2024/1760 - Corporate Sustainability Due Diligence Directive (CSDDD)', 'CSDDD', 'directive', '2024-07-05', true),
('32024R1689', 'Regulation (EU) 2024/1689 - Artificial Intelligence Act', 'AI_ACT', 'regulation', '2024-07-12', true),
('32022R2554', 'Regulation (EU) 2022/2554 - Digital Operational Resilience Act (DORA)', 'DORA', 'regulation', '2022-12-14', true),
('32022L2555', 'Directive (EU) 2022/2555 - NIS 2 Directive', 'NIS2', 'directive', '2022-12-14', true),
('32020R0852', 'Regulation (EU) 2020/852 - Taxonomy Regulation', 'TAXONOMY', 'regulation', '2020-06-18', true),
('32016R0679', 'Regulation (EU) 2016/679 - General Data Protection Regulation (GDPR)', 'GDPR', 'regulation', '2016-04-27', true),
('32023R2772', 'Commission Delegated Regulation (EU) 2023/2772 - ESRS Set 1', 'CSRD', 'delegated_act', '2023-07-31', true),
('32025L0794', 'Directive (EU) 2025/794 - Stop-the-Clock Directive (Omnibus)', 'CSRD', 'directive', '2025-04-14', true);
