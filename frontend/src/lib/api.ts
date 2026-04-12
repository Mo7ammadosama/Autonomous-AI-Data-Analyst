import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('auth_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Simple GET cache — returns stale data instantly while revalidating in background
const _cache = new Map<string, { data: any; ts: number }>();
const CACHE_TTL = 30_000; // 30 seconds

export async function cachedGet(url: string, params?: Record<string, any>) {
  const key = url + JSON.stringify(params || {});
  const hit = _cache.get(key);
  if (hit && Date.now() - hit.ts < CACHE_TTL) {
    return { data: hit.data };
  }
  const res = await api.get(url, { params });
  _cache.set(key, { data: res.data, ts: Date.now() });
  return res;
}

export function invalidateCache(urlPrefix?: string) {
  if (!urlPrefix) { _cache.clear(); return; }
  Array.from(_cache.keys()).forEach((key) => {
    if (key.startsWith(urlPrefix)) _cache.delete(key);
  });
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    // On 401, attempt a silent token refresh once
    if (
      error.response?.status === 401 &&
      typeof window !== 'undefined' &&
      !original._retried
    ) {
      original._retried = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE}/api/auth/refresh`, {
            refresh_token: refreshToken,
          });
          const { access_token, refresh_token: newRefresh } = res.data;
          localStorage.setItem('auth_token', access_token);
          localStorage.setItem('refresh_token', newRefresh);
          original.headers.Authorization = `Bearer ${access_token}`;
          return api(original);
        } catch {
          // Refresh failed — clear session and redirect
        }
      }
      localStorage.removeItem('auth_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('auth_user');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

export default api;

// Auth
export const authApi = {
  login: (email: string, password: string) => api.post('/api/auth/login', { email, password }),
  register: (email: string, username: string, password: string) => api.post('/api/auth/register', { email, username, password }),
  demoLogin: () => api.post('/api/auth/demo-login'),
  refresh: (refreshToken: string) => api.post('/api/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken: string) => api.post('/api/auth/logout', { refresh_token: refreshToken }),
  getMe: () => api.get('/api/auth/me'),
  updateMe: (data: { username?: string; email?: string }) => api.patch('/api/auth/me', data),
};

// Datasets
export const datasetsApi = {
  list: () => cachedGet('/api/datasets/'),
  get: (id: string) => cachedGet(`/api/datasets/${id}`),
  upload: (formData: FormData) => api.post('/api/datasets/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  profile: (id: string) => cachedGet(`/api/datasets/${id}/profile`),
  preview: (id: string, rows?: number) => cachedGet(`/api/datasets/${id}/preview`, rows ? { rows } : undefined),
  clean: (id: string, opts?: {
    missing_strategy?: 'median' | 'mean' | 'mode' | 'drop';
    remove_outliers?: boolean;
    outlier_threshold?: number;
    column_renames?: Record<string, string>;
    drop_columns?: string[];
  }) => api.post(`/api/datasets/${id}/clean`, opts || {}),
  delete: (id: string) => api.delete(`/api/datasets/${id}`),
};

// Analytics
export const analyticsApi = {
  overview: (id: string) => cachedGet(`/api/analytics/${id}/overview`),
  correlations: (id: string) => cachedGet(`/api/analytics/${id}/correlations`),
  outliers: (id: string) => cachedGet(`/api/analytics/${id}/outliers`),
  charts: (id: string, maxCharts?: number) => cachedGet(`/api/analytics/${id}/charts`, maxCharts ? { max_charts: maxCharts } : undefined),
  runML: (id: string, params: { analysis_type: string; target_column?: string; n_clusters?: number }) => api.post(`/api/analytics/${id}/ml`, params),
};

// Chat
export const chatApi = {
  createSession: (datasetId?: string, title?: string) => api.post('/api/chat/sessions', { dataset_id: datasetId, title }),
  listSessions: () => api.get('/api/chat/sessions'),
  getMessages: (sessionId: string) => api.get(`/api/chat/sessions/${sessionId}/messages`),
  sendMessage: (message: string, sessionId?: string, datasetId?: string) => api.post('/api/chat/message', { message, session_id: sessionId, dataset_id: datasetId }),
  deleteSession: (sessionId: string) => api.delete(`/api/chat/sessions/${sessionId}`),
};

// Insights
export const insightsApi = {
  get: (datasetId: string, refresh?: boolean) => refresh ? api.get(`/api/insights/${datasetId}?refresh=true`) : cachedGet(`/api/insights/${datasetId}`),
  listAll: () => cachedGet('/api/insights/'),
};

// Dashboards
export const dashboardsApi = {
  list: () => cachedGet('/api/dashboards/'),
  get: (id: string) => cachedGet(`/api/dashboards/${id}`),
  create: (data: { title: string; description?: string; dataset_id?: string; command?: string; charts?: any[] }) => api.post('/api/dashboards/', data),
  update: (id: string, data: object) => api.put(`/api/dashboards/${id}`, data),
  delete: (id: string) => api.delete(`/api/dashboards/${id}`),
};

// Reports
export const reportsApi = {
  summary: (datasetId: string) => api.get(`/api/reports/summary/${datasetId}`),
  generatePdf: (datasetId: string, title?: string) => api.post('/api/reports/generate-pdf', { dataset_id: datasetId, title }, { responseType: 'blob' }),
};

// ── Enterprise Extensions ──────────────────────────────────

// Universal AI Copilot
export const copilotApi = {
  ask: (question: string, datasetId?: string) =>
    api.post('/api/copilot/ask', { question, dataset_id: datasetId }),
  intents: () => api.get('/api/copilot/intents'),
  classify: (question: string) => api.post('/api/copilot/classify', { question }),
};

// Forecasting
export const forecastingApi = {
  columns: (datasetId: string) => api.get(`/api/forecasting/${datasetId}/columns`),
  auto: (datasetId: string, periods?: number) =>
    api.get(`/api/forecasting/${datasetId}/auto${periods ? `?periods=${periods}` : ''}`),
  forecast: (
    datasetId: string,
    params: { date_column?: string; target_column?: string; periods?: number; method?: string }
  ) => api.post(`/api/forecasting/${datasetId}/forecast`, params),
};

// Auto Pipeline
export const pipelineApi = {
  get: (datasetId: string) => cachedGet(`/api/pipeline/${datasetId}`),
  run: (datasetId: string) => api.post(`/api/pipeline/${datasetId}/run`),
  story: (datasetId: string) => cachedGet(`/api/pipeline/${datasetId}/story`),
  recommendations: (datasetId: string) => cachedGet(`/api/pipeline/${datasetId}/recommendations`),
  anomalies: (datasetId: string) => cachedGet(`/api/pipeline/${datasetId}/anomalies`),
};

// Extended Analytics
export const analyticsExtApi = {
  nlQuery: (datasetId: string, question: string) =>
    api.post(`/api/analytics/${datasetId}/nl-query`, { question }),
  anomaliesFull: (datasetId: string) =>
    api.get(`/api/analytics/${datasetId}/anomalies-full`),
};

// Autonomous Analyst
export const autonomousApi = {
  analyze: (datasetId: string) => api.post('/api/autonomous/analyze', { dataset_id: datasetId }),
  status: (datasetId: string) => api.get(`/api/autonomous/${datasetId}/status`),
  clearCache: (datasetId: string) => api.delete(`/api/autonomous/${datasetId}/cache`),
};

// ── Phase 1 New Features ─────────────────────────────────────────

// Alerts
export const alertsApi = {
  list: () => cachedGet('/api/alerts/'),
  get: (id: string) => cachedGet(`/api/alerts/${id}`),
  create: (data: {
    name: string;
    description?: string;
    dataset_id?: string;
    column_name?: string;
    condition: string;
    threshold?: number;
    aggregation?: string;
    notify_email?: boolean;
    email_recipient?: string;
  }) => api.post('/api/alerts/', data),
  update: (id: string, data: Partial<{
    name: string;
    description: string;
    column_name: string;
    condition: string;
    threshold: number;
    aggregation: string;
    notify_email: boolean;
    email_recipient: string;
    is_active: boolean;
  }>) => api.put(`/api/alerts/${id}`, data),
  delete: (id: string) => api.delete(`/api/alerts/${id}`),
  logs: (id: string, limit?: number) => api.get(`/api/alerts/${id}/logs${limit ? `?limit=${limit}` : ''}`),
  evaluate: (id: string) => api.post(`/api/alerts/${id}/evaluate`),
  evaluateAll: (datasetId: string) => api.post(`/api/alerts/evaluate-all/${datasetId}`),
};

// NL2SQL (Natural Language to SQL)
export const nl2sqlApi = {
  query: (datasetId: string, question: string) =>
    api.post(`/api/nl2sql/${datasetId}/query`, { question }),
  history: (datasetId: string, limit?: number) =>
    api.get(`/api/nl2sql/${datasetId}/history${limit ? `?limit=${limit}` : ''}`),
  feedback: (queryId: string, feedback: 1 | -1) =>
    api.post('/api/nl2sql/feedback', { query_id: queryId, feedback }),
};

// System
export const systemApi = {
  health: () => api.get('/health'),
  version: () => api.get('/api/version'),
};

// Data Connections (Phase 2)
export const connectionsApi = {
  list: () => cachedGet('/api/connections/'),
  get: (id: string) => cachedGet(`/api/connections/${id}`),
  create: (data: {
    name: string; connection_type: string; host?: string; port?: number;
    database: string; username?: string; password?: string; schema_name?: string;
  }) => api.post('/api/connections/', data),
  update: (id: string, data: object) => api.put(`/api/connections/${id}`, data),
  delete: (id: string) => api.delete(`/api/connections/${id}`),
  test: (id: string) => api.post(`/api/connections/${id}/test`),
  tables: (id: string) => api.get(`/api/connections/${id}/tables`),
  schema: (id: string, table: string) => api.get(`/api/connections/${id}/schema/${table}`),
  query: (id: string, sql: string, maxRows?: number) =>
    api.post(`/api/connections/${id}/query`, { sql, max_rows: maxRows || 1000 }),
  importDataset: (id: string, sql: string, datasetName: string) =>
    api.post(`/api/connections/${id}/import`, { sql, dataset_name: datasetName }),
};

// Scheduled Reports (Phase 2)
export const scheduledReportsApi = {
  list: () => cachedGet('/api/scheduled-reports/'),
  get: (id: string) => cachedGet(`/api/scheduled-reports/${id}`),
  create: (data: {
    dataset_id: string; title: string; frequency: string; email_recipient: string;
  }) => api.post('/api/scheduled-reports/', data),
  update: (id: string, data: object) => api.put(`/api/scheduled-reports/${id}`, data),
  delete: (id: string) => api.delete(`/api/scheduled-reports/${id}`),
  sendNow: (id: string) => api.post(`/api/scheduled-reports/${id}/send-now`),
};

// ── Phase 3 / 4 Features ──────────────────────────────────────────

// Export (Phase 3)
export const exportApi = {
  download: (datasetId: string, fmt: string, columns?: string, maxRows?: number) => {
    const params = new URLSearchParams({ fmt });
    if (columns) params.set('columns', columns);
    if (maxRows) params.set('max_rows', String(maxRows));
    return api.get(`/api/datasets/${datasetId}/export?${params}`, { responseType: 'blob' });
  },
};

// Compare datasets (Phase 3)
export const compareApi = {
  compare: (datasetIdA: string, datasetIdB: string) =>
    api.post(`/api/datasets/${datasetIdA}/compare`, { dataset_id_b: datasetIdB }),
};

// AI Dashboard Builder (Phase 4)
export const aiBuildApi = {
  buildDashboard: (datasetId: string, prompt: string, maxCharts?: number) =>
    api.post('/api/dashboards/build-with-ai', { dataset_id: datasetId, prompt, max_charts: maxCharts }),
  duplicate: (dashboardId: string) => api.post(`/api/dashboards/${dashboardId}/duplicate`),
};

// Auth extensions (Phase 3)
export const authExtApi = {
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/api/auth/change-password', { current_password: currentPassword, new_password: newPassword }),
};

// ── Phase 5 Features ──────────────────────────────────────────────

// Workspaces
export const workspacesApi = {
  list: () => cachedGet('/api/workspaces/'),
  current: () => cachedGet('/api/workspaces/current'),
  get: (id: string) => cachedGet(`/api/workspaces/${id}`),
  create: (data: { name: string; description?: string; plan?: string }) =>
    api.post('/api/workspaces/', data),
  update: (id: string, data: { name?: string; description?: string }) =>
    api.put(`/api/workspaces/${id}`, data),
  delete: (id: string) => api.delete(`/api/workspaces/${id}`),
  members: (id: string) => api.get(`/api/workspaces/${id}/members`),
  invite: (id: string, email: string, role?: string) =>
    api.post(`/api/workspaces/${id}/invite`, { email, role }),
  removeMember: (workspaceId: string, userId: string) =>
    api.delete(`/api/workspaces/${workspaceId}/members/${userId}`),
  switchTo: (id: string) => api.post(`/api/workspaces/switch/${id}`),
};

// API Keys
export const apiKeysApi = {
  list: () => api.get('/api/auth/api-keys/'),
  create: (data: { name: string; scopes?: string[]; expires_days?: number }) =>
    api.post('/api/auth/api-keys/', data),
  update: (id: string, data: { name?: string; is_active?: boolean }) =>
    api.patch(`/api/auth/api-keys/${id}`, data),
  revoke: (id: string) => api.delete(`/api/auth/api-keys/${id}`),
};

// Webhooks
export const webhooksApi = {
  list: () => api.get('/api/webhooks/'),
  events: () => api.get('/api/webhooks/events'),
  create: (data: { name: string; url: string; events: string[]; secret?: string }) =>
    api.post('/api/webhooks/', data),
  update: (id: string, data: { name?: string; url?: string; events?: string[]; is_active?: boolean }) =>
    api.patch(`/api/webhooks/${id}`, data),
  delete: (id: string) => api.delete(`/api/webhooks/${id}`),
  test: (id: string) => api.post(`/api/webhooks/${id}/test`),
};

// Notifications
export const notificationsApi = {
  count: () => api.get('/api/notifications/count'),
  list: (unreadOnly?: boolean, limit?: number) => {
    const params = new URLSearchParams();
    if (unreadOnly) params.set('unread_only', 'true');
    if (limit) params.set('limit', String(limit));
    return api.get(`/api/notifications/?${params}`);
  },
  markRead: (ids?: string[]) => api.post('/api/notifications/mark-read', { ids: ids || null }),
  delete: (id: string) => api.delete(`/api/notifications/${id}`),
  activity: (resourceType?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (resourceType) params.set('resource_type', resourceType);
    if (limit) params.set('limit', String(limit));
    return api.get(`/api/notifications/activity?${params}`);
  },
};

// Metrics
export const metricsApi = {
  user: () => api.get('/api/metrics/'),
  system: () => api.get('/api/metrics/system'),
};

// Sharing
export const sharingApi = {
  create: (dashboardId: string, expiresDays?: number) =>
    api.post(`/api/dashboards/${dashboardId}/share`, { expires_days: expiresDays }),
  list: (dashboardId: string) => api.get(`/api/dashboards/${dashboardId}/shares`),
  revoke: (dashboardId: string) => api.delete(`/api/dashboards/${dashboardId}/share`),
  getPublic: (token: string) => api.get(`/api/shared/${token}`),
};

// ── Phase 6 — AI Supremacy ────────────────────────────────────────

// AI Models
export const aiModelsApi = {
  list: () => api.get('/api/ai/models'),
  testModel: (modelKey: string, prompt: string, system?: string) =>
    api.post('/api/ai/test-model', { model_key: modelKey, prompt, system }),
  usage: (days?: number) => api.get(`/api/ai/usage${days ? `?days=${days}` : ''}`),
  usageSummary: () => api.get('/api/ai/usage/summary'),
};

// Root Cause Analysis
export const rcaApi = {
  analyze: (data: {
    dataset_id: string;
    metric_column: string;
    date_column?: string;
    comparison_period?: string;
  }) => api.post('/api/root-cause/analyze', data),
  history: () => api.get('/api/root-cause/history'),
  get: (id: string) => api.get(`/api/root-cause/${id}`),
  regenerate: (id: string) => api.post(`/api/root-cause/${id}/regenerate`),
};

// AutoML
export const automlApi = {
  train: (data: { dataset_id: string; target_column: string; task_type: string }) =>
    api.post('/api/automl/train', data),
  listJobs: () => api.get('/api/automl/jobs'),
  getJob: (jobId: string) => api.get(`/api/automl/jobs/${jobId}`),
  predict: (jobId: string, records: Record<string, any>[]) =>
    api.post(`/api/automl/predict/${jobId}`, { records }),
  deleteModel: (jobId: string) => api.delete(`/api/automl/models/${jobId}`),
};

// ── Phase 7 — Real-time ───────────────────────────────────────────

// WebSocket helper (returns native WebSocket)
export const wsConnect = (path: string): WebSocket => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : '';
  const wsBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001')
    .replace('https://', 'wss://')
    .replace('http://', 'ws://');
  return new WebSocket(`${wsBase}${path}?token=${token || ''}`);
};

// ── Phase 8 — Collaboration ───────────────────────────────────────

// Dashboard Comments
export const commentsApi = {
  list: (dashboardId: string) => api.get(`/api/dashboards/${dashboardId}/comments`),
  create: (dashboardId: string, data: {
    content: string;
    parent_id?: string;
    chart_index?: number;
  }) => api.post(`/api/dashboards/${dashboardId}/comments`, data),
  update: (dashboardId: string, commentId: string, content: string) =>
    api.put(`/api/dashboards/${dashboardId}/comments/${commentId}`, { content }),
  delete: (dashboardId: string, commentId: string) =>
    api.delete(`/api/dashboards/${dashboardId}/comments/${commentId}`),
  resolve: (dashboardId: string, commentId: string) =>
    api.post(`/api/dashboards/${dashboardId}/comments/${commentId}/resolve`),
};

// Dashboard Versions
export const versionsApi = {
  list: (dashboardId: string) => api.get(`/api/dashboards/${dashboardId}/versions`),
  get: (dashboardId: string, versionNumber: number) =>
    api.get(`/api/dashboards/${dashboardId}/versions/${versionNumber}`),
  restore: (dashboardId: string, versionNumber: number) =>
    api.post(`/api/dashboards/${dashboardId}/versions/${versionNumber}/restore`),
};

// Templates
export const templatesApi = {
  list: (industry?: string, search?: string) => {
    const params = new URLSearchParams();
    if (industry) params.set('industry', industry);
    if (search) params.set('search', search);
    return api.get(`/api/templates/?${params}`);
  },
  industries: () => api.get('/api/templates/industries'),
  get: (id: string) => api.get(`/api/templates/${id}`),
  use: (id: string, payload: { dataset_id: string; column_mappings?: Record<string, string> }) =>
    api.post(`/api/templates/${id}/use`, payload),
};

// Data Catalog
export const catalogApi = {
  search: (q: string, resource_type?: string, tag?: string) => {
    const params = new URLSearchParams({ q });
    if (resource_type) params.set('resource_type', resource_type);
    if (tag) params.set('tag', tag);
    return api.get(`/api/catalog/search?${params}`);
  },
  list: (resource_type?: string) => {
    const params = new URLSearchParams();
    if (resource_type) params.set('resource_type', resource_type);
    return api.get(`/api/catalog/?${params}`);
  },
  get: (id: string) => api.get(`/api/catalog/${id}`),
  popular: () => api.get('/api/catalog/popular'),
  tags: () => api.get('/api/catalog/tags'),
  update: (id: string, data: { description?: string; tags?: string[]; sensitivity?: string }) =>
    api.patch(`/api/catalog/${id}`, data),
  certify: (id: string) => api.post(`/api/catalog/${id}/certify`),
};

// ── Phase 9-17 — World-Class Features ────────────────────────────

// Export raw axios instance for pages that need direct access
export const apiClient = api;

// Proactive Intelligence Feed
export const proactiveApi = {
  getFeed: (params?: { unread_only?: boolean; severity?: string; limit?: number }) =>
    api.get('/api/proactive/feed', { params }),
  getUnreadCount: () => api.get('/api/proactive/feed/unread-count'),
  markRead: (id: string) => api.post(`/api/proactive/feed/${id}/read`),
  markAllRead: () => api.post('/api/proactive/feed/mark-all-read'),
  getConfig: () => api.get('/api/proactive/config'),
  updateConfig: (data: Record<string, any>) => api.post('/api/proactive/configure', data),
  scanNow: () => api.post('/api/proactive/scan-now'),
  getHistory: (days?: number) => api.get('/api/proactive/history', { params: { days } }),
};

// Semantic Metric Catalog
export const semanticMetricsApi = {
  define: (data: Record<string, any>) => api.post('/api/metrics/define', data),
  list: (params?: { category?: string; certified_only?: boolean }) =>
    api.get('/api/metrics/definitions', { params }),
  search: (q: string) => api.get('/api/metrics/search', { params: { q } }),
  get: (id: string) => api.get(`/api/metrics/definitions/${id}`),
  update: (id: string, data: Record<string, any>) => api.put(`/api/metrics/definitions/${id}`, data),
  delete: (id: string) => api.delete(`/api/metrics/definitions/${id}`),
  certify: (id: string) => api.post(`/api/metrics/definitions/${id}/certify`),
  lineage: (id: string) => api.get(`/api/metrics/definitions/${id}/lineage`),
  suggest: (datasetId: string) => api.get(`/api/metrics/suggest/${datasetId}`),
};

// What-If Scenarios
export const scenariosApi = {
  simulate: (data: { automl_job_id: string; input_assumptions: Record<string, number>; name?: string; save?: boolean }) =>
    api.post('/api/scenarios/simulate', data),
  list: (automlJobId?: string) => api.get('/api/scenarios/', { params: { automl_job_id: automlJobId } }),
  get: (id: string) => api.get(`/api/scenarios/${id}`),
  delete: (id: string) => api.delete(`/api/scenarios/${id}`),
  share: (id: string) => api.post(`/api/scenarios/${id}/share`),
  getPublic: (token: string) => api.get(`/api/scenarios/public/${token}`),
  getModelFeatures: (jobId: string) => api.get(`/api/scenarios/model-features/${jobId}`),
};

// Real-Time Streams
export const streamsApi = {
  create: (data: Record<string, any>) => api.post('/api/streams/create', data),
  list: () => api.get('/api/streams/'),
  get: (id: string) => api.get(`/api/streams/${id}`),
  update: (id: string, data: Record<string, any>) => api.put(`/api/streams/${id}`, data),
  delete: (id: string) => api.delete(`/api/streams/${id}`),
};

// Personalized Digest
export const digestApi = {
  getConfig: () => api.get('/api/digest/config'),
  updateConfig: (data: Record<string, any>) => api.post('/api/digest/configure', data),
  preview: () => api.get('/api/digest/preview'),
  sendNow: () => api.post('/api/digest/send-now'),
};

// Dashboard PR Reviews
export const reviewsApi = {
  propose: (dashboardId: string, data: Record<string, any>) =>
    api.post(`/api/dashboards/${dashboardId}/propose-change`, data),
  list: (dashboardId: string) => api.get(`/api/dashboards/${dashboardId}/reviews`),
  approve: (dashboardId: string, prId: string) =>
    api.post(`/api/dashboards/${dashboardId}/reviews/${prId}/approve`),
  reject: (dashboardId: string, prId: string, comment?: string) =>
    api.post(`/api/dashboards/${dashboardId}/reviews/${prId}/reject`, { comment }),
};

// Chat: Thread-to-Dashboard
export const chatExtApi = {
  convertToDashboard: (sessionId: string) =>
    api.post(`/api/chat/sessions/${sessionId}/convert-to-dashboard`),
};

// ── Autonomous Agent ───────────────────────────────────────────────
export const agentApi = {
  run: (task: string, datasetId?: string, connectionId?: string, domain?: string) =>
    api.post('/api/agent/run', { task, dataset_id: datasetId, connection_id: connectionId, domain }),
  getRuns: () => api.get('/api/agent/runs'),
  getRun: (id: string) => api.get(`/api/agent/runs/${id}`),
  streamRun: (id: string) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') || '' : '';
    return new EventSource(`${API_BASE}/api/agent/runs/${id}/stream?token=${encodeURIComponent(token)}`);
  },
  deleteRun: (id: string) => api.delete(`/api/agent/runs/${id}`),
  // Memory endpoints
  getMemories: () => api.get('/api/agent/memories'),
  deleteMemory: (id: string) => api.delete(`/api/agent/memories/${id}`),
  saveCorrection: (correction: string, runId?: string) =>
    api.post('/api/agent/memories/correction', { correction, run_id: runId }),
};

// ── Domain Templates ───────────────────────────────────────────────
export const domainTemplatesApi = {
  list: () => cachedGet('/api/domain-templates'),
  getByDomain: (domain: string) => cachedGet(`/api/domain-templates/${domain}`),
  getTemplate: (domain: string, name: string) => cachedGet(`/api/domain-templates/${domain}/${name}`),
  detect: (datasetId?: string, columns?: string[]) =>
    api.post('/api/domain-templates/detect', { dataset_id: datasetId, columns }),
};

// ── Custom Reports ─────────────────────────────────────────────────
export const customReportsApi = {
  list: () => api.get('/api/custom-reports'),
  get: (id: string) => api.get(`/api/custom-reports/${id}`),
  create: (data: Record<string, unknown>) => api.post('/api/custom-reports', data),
  update: (id: string, data: Record<string, unknown>) => api.put(`/api/custom-reports/${id}`, data),
  generate: (id: string) => api.post(`/api/custom-reports/${id}/generate`),
  exportUrl: (id: string, fmt: string) => `${API_BASE}/api/custom-reports/${id}/export?fmt=${fmt}`,
  delete: (id: string) => api.delete(`/api/custom-reports/${id}`),
};

// ── SuperAdmin API ─────────────────────────────────────────────────
export const adminApi = {
  // Stats & Health
  stats: () => api.get('/api/admin/stats'),
  health: () => api.get('/api/admin/health'),

  // Companies
  listCompanies: (params?: { skip?: number; limit?: number; search?: string; status?: string }) =>
    api.get('/api/admin/companies', { params }),
  getCompany: (id: string) => api.get(`/api/admin/companies/${id}`),
  suspendCompany: (id: string, reason?: string) =>
    api.patch(`/api/admin/companies/${id}/suspend`, { reason }),
  activateCompany: (id: string) =>
    api.patch(`/api/admin/companies/${id}/activate`),
  deleteCompany: (id: string) =>
    api.delete(`/api/admin/companies/${id}`),

  // Users
  listUsers: (params?: { skip?: number; limit?: number; search?: string; role?: string; workspace_id?: string; status?: string }) =>
    api.get('/api/admin/users', { params }),
  getUser: (id: string) => api.get(`/api/admin/users/${id}`),
  suspendUser: (id: string, reason?: string) =>
    api.patch(`/api/admin/users/${id}/suspend`, { reason }),
  activateUser: (id: string) =>
    api.patch(`/api/admin/users/${id}/activate`),
  changeUserRole: (id: string, role: string) =>
    api.patch(`/api/admin/users/${id}/role`, { role }),
  deleteUser: (id: string) =>
    api.delete(`/api/admin/users/${id}`),

  // Audit Logs & Usage
  auditLogs: (params?: { skip?: number; limit?: number; user_id?: string; action?: string; from_date?: string; to_date?: string }) =>
    api.get('/api/admin/audit-logs', { params }),
  llmUsage: (params?: { from_date?: string; to_date?: string; group_by?: string }) =>
    api.get('/api/admin/llm-usage', { params }),
};
