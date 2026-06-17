// ─── Auth Types ─────────────────────────────────────────────

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'member' | 'viewer'
  organization_name: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
  organization_name: string
}

// ─── Company Profile ────────────────────────────────────────

export interface CompanyProfile {
  name: string
  sector: string
  employee_count: number
  revenue_eur: number
  jurisdictions: string[]
  applicable_frameworks: string[]
  existing_documents: string
}

// ─── Intelligence Types ─────────────────────────────────────

export type Framework = 'CSRD' | 'CSDDD' | 'AI_ACT' | 'DORA' | 'NIS2' | 'TAXONOMY' | 'GDPR'

// NormaAI brand framework colors - mirrors dashboard/styles.css --fw-* tokens.
// Updated 2026-04-28 (G7.2): aligned to design system, no longer using
// generic Tailwind palette.
export const FRAMEWORKS: { value: Framework; label: string; color: string }[] = [
  { value: 'CSRD',     label: 'CSRD - Sustainability Reporting', color: '#34d399' },
  { value: 'CSDDD',    label: 'CSDDD - Due Diligence',           color: '#5fbcff' },
  { value: 'AI_ACT',   label: 'AI Act - AI Regulation',          color: '#b08bff' },
  { value: 'DORA',     label: 'DORA - Digital Resilience',       color: '#ff8c5a' },
  { value: 'NIS2',     label: 'NIS2 - Cybersecurity',            color: '#f4b740' },
  { value: 'TAXONOMY', label: 'EU Taxonomy - Green Finance',     color: '#4ad6c2' },
  { value: 'GDPR',     label: 'GDPR - Data Protection',          color: '#ef4f63' },
]

// Q&A
export interface QARequest {
  question: string
  company_profile?: CompanyProfile
  language?: string
}

export interface Citation {
  framework: string
  reference: string
  quote_snippet: string
}

export interface QAResponse {
  answer: string
  citations: Citation[]
  confidence_score: number
  requires_expert_review: boolean
  related_frameworks: string[]
  caveats: string[]
}

// Gap Analysis
export interface GapAnalysisRequest {
  framework: Framework
  company_profile: CompanyProfile
}

export type ComplianceStatus = 'COMPLIANT' | 'PARTIALLY_COMPLIANT' | 'NON_COMPLIANT' | 'NOT_APPLICABLE' | 'IN_EVOLUTION'

export interface Requirement {
  requirement_id: string
  description: string
  article_reference: string
  status: ComplianceStatus
  evidence: string
  gap_description: string
  remediation_effort: string
  priority: 'P1' | 'P2' | 'P3' | 'P4'
  notes: string
}

export interface GapAnalysisResponse {
  framework: string
  overall_score: number
  status_summary: {
    compliant: number
    partially_compliant: number
    non_compliant: number
    not_applicable: number
    in_evolution: number
  }
  requirements: Requirement[]
  top_recommendations: string[]
  confidence_score: number
  requires_expert_review: boolean
}

// Monitor
export interface MonitorRequest {
  regulation_change: string
  company_profile: CompanyProfile
}

export interface MonitorResponse {
  applicability: 'YES' | 'NO' | 'CONDITIONAL'
  applicability_reason: string
  urgency: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFORMATIONAL'
  impact_summary: string
  required_actions: string[]
  deadline: string
  deadline_is_confirmed: boolean
  cross_framework_impacts: string[]
  confidence_score: number
  requires_expert_review: boolean
  citations: string[]
}

// ─── Client Types ───────────────────────────────────────────

export interface Client {
  id: string
  org_id: string
  name: string
  sector: string
  employee_count: number
  revenue_eur: number
  jurisdictions: string[]
  applicable_frameworks: string[]
  created_at: string
  updated_at: string
}

export interface ClientCreate {
  name: string
  sector?: string
  employee_count?: number
  revenue_eur?: number
  jurisdictions?: string[]
  applicable_frameworks?: string[]
}

// ─── Alert Types ────────────────────────────────────────────

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFORMATIONAL'

export interface Alert {
  id: string
  client_id: string
  regulation_id?: string
  severity: Severity
  framework: string
  title: string
  description: string
  actions_required: string[]
  deadline?: string
  is_read: boolean
  is_dismissed: boolean
  created_at: string
}

export interface AlertSummary {
  total: number
  unread: number
  by_severity: Record<Severity, number>
  by_framework: Record<string, number>
}

// ─── Report Types ───────────────────────────────────────────

export interface ReportHistory {
  id: string
  framework: string
  company_name: string
  overall_score: number
  generated_at: string
}

// ─── Conversation Types ─────────────────────────────────────

export interface Conversation {
  id: string
  user_id: string
  client_id?: string
  messages: ConversationMessage[]
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  metadata?: Record<string, unknown>
}

// ─── System Types ───────────────────────────────────────────

export interface SystemStats {
  status: string
  version: string
  environment: string
  llm_provider: string
  llm_model: string
  timestamp: string
  qdrant_available: boolean
  llm_available: boolean
  qdrant?: {
    status: string
    points_count?: number
  }
  metrics: {
    total_requests: number
    error_count: number
    endpoints: Record<string, {
      count: number
      avg_latency_ms: number
      max_latency_ms: number
    }>
  }
}

export interface ApiResponse<T> {
  status: string
  data: T
  metadata?: Record<string, unknown>
}

export interface ApiError {
  detail: string
}

// ─── Audit Trail Types ─────────────────────────────────────

export interface AuditEvent {
  id: string
  timestamp: string
  user_id: string
  user_name: string
  user_email: string
  action: string
  resource_type: 'qa' | 'gap_analysis' | 'monitor' | 'report' | 'alert' | 'client' | 'document' | 'system' | 'auth'
  resource_id?: string
  details: string
  ip_address: string
  framework?: string
}

// ─── RBAC Types ────────────────────────────────────────────

export type Permission =
  | 'qa.query' | 'qa.export'
  | 'gap_analysis.run' | 'gap_analysis.approve'
  | 'monitor.analyze' | 'monitor.configure'
  | 'reports.generate' | 'reports.export' | 'reports.approve'
  | 'alerts.view' | 'alerts.manage' | 'alerts.configure'
  | 'clients.view' | 'clients.create' | 'clients.edit' | 'clients.delete'
  | 'documents.view' | 'documents.upload' | 'documents.delete'
  | 'audit.view' | 'audit.export'
  | 'admin.users' | 'admin.roles' | 'admin.system' | 'admin.sso'

export interface Role {
  id: string
  name: string
  description: string
  permissions: Permission[]
  user_count: number
  is_system: boolean  // system roles can't be deleted
  created_at: string
}

// ─── Workflow Types ────────────────────────────────────────

export type WorkflowStatus = 'ai_generated' | 'under_review' | 'validated' | 'approved' | 'rejected'

export interface WorkflowItem {
  id: string
  title: string
  description: string
  source: 'gap_analysis' | 'monitor' | 'qa'
  framework: string
  status: WorkflowStatus
  priority: 'P1' | 'P2' | 'P3' | 'P4'
  assigned_to: string | null
  assigned_to_name: string | null
  created_at: string
  updated_at: string
  deadline: string | null
  client_name: string
  approval_chain: { role: string; user: string; status: 'pending' | 'approved' | 'rejected'; date: string | null }[]
}

// ─── Client Compliance Types ───────────────────────────────

export interface ClientComplianceScore {
  framework: string
  score: number
  previous_score: number
  trend: 'up' | 'down' | 'stable'
  last_assessed: string
}

export interface ClientComplianceHistory {
  month: string
  scores: Record<string, number>
}
