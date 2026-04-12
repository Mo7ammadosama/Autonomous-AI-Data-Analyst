"""
Generate DataMind AI project documentation (English only).
Run: python generate_doc.py
"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

# ── Helpers ──────────────────────────────────────────────────────────────────

def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    run = p.runs[0] if p.runs else p.add_run(text)
    if level == 1:
        run.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)
        run.font.size = Pt(18)
    elif level == 2:
        run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
        run.font.size = Pt(14)
    else:
        run.font.color.rgb = RGBColor(0x37, 0x47, 0x51)
        run.font.size = Pt(12)
    return p

def body(doc, text, bold=False, italic=False, color=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)
    return p

def bullet(doc, text):
    p = doc.add_paragraph(style='List Bullet')
    run = p.add_run(text)
    run.font.size = Pt(11)
    p.paragraph_format.left_indent = Inches(0.3)
    return p

def table2(doc, rows, header=None, col_widths=(2.6, 4.0)):
    table = doc.add_table(rows=len(rows) + (1 if header else 0), cols=2)
    table.style = 'Table Grid'
    if header:
        hrow = table.rows[0]
        hrow.cells[0].text = header[0]
        hrow.cells[1].text = header[1]
        for cell in hrow.cells:
            set_cell_bg(cell, '4F46E5')
            for run in cell.paragraphs[0].runs:
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.bold = True
                run.font.size = Pt(11)
    offset = 1 if header else 0
    for i, (a, b) in enumerate(rows):
        row = table.rows[i + offset]
        row.cells[0].text = a
        row.cells[1].text = b
        row.cells[0].width = Inches(col_widths[0])
        row.cells[1].width = Inches(col_widths[1])
        if i % 2 == 0:
            set_cell_bg(row.cells[0], 'EEF2FF')
            set_cell_bg(row.cells[1], 'EEF2FF')
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(10.5)
    return table

# ── Build Document ────────────────────────────────────────────────────────────

doc = Document()

for section in doc.sections:
    section.top_margin    = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin   = Cm(3.0)
    section.right_margin  = Cm(2.5)

doc.styles['Normal'].font.name = 'Calibri'
doc.styles['Normal'].font.size = Pt(11)

# ── COVER PAGE ───────────────────────────────────────────────────────────────
doc.add_paragraph('\n\n\n')

title_p = doc.add_paragraph()
title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
t = title_p.add_run('DataMind AI')
t.font.size = Pt(40)
t.font.bold = True
t.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)

sub_p = doc.add_paragraph()
sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
s = sub_p.add_run('Autonomous AI Data Analyst Platform')
s.font.size = Pt(22)
s.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

doc.add_paragraph()
tag = doc.add_paragraph()
tag.alignment = WD_ALIGN_PARAGRAPH.CENTER
tg = tag.add_run('Comprehensive Project Documentation')
tg.font.size = Pt(14)
tg.font.italic = True
tg.font.color.rgb = RGBColor(0x4B, 0x55, 0x63)

doc.add_paragraph('\n\n\n\n')

date_p = doc.add_paragraph()
date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
d = date_p.add_run(f'Date: {datetime.date.today().strftime("%B %d, %Y")}')
d.font.size = Pt(12)
d.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

doc.add_page_break()

# ── 1. PROJECT OVERVIEW ──────────────────────────────────────────────────────
heading(doc, '1. Project Overview')
body(doc,
    'DataMind AI is a fully integrated, enterprise-grade intelligent data analytics platform '
    'powered by cutting-edge AI models. It allows users to upload any data file (CSV, Excel, JSON) '
    'and interact with it using natural language — in English or Arabic — to receive smart insights, '
    'interactive charts, forecasts, and anomaly detection without requiring any coding expertise.')

doc.add_paragraph()
body(doc, 'Core Objectives:', bold=True)
bullet(doc, 'Make data analytics accessible to everyone — technical and non-technical users alike')
bullet(doc, 'Replace traditional tools (Excel, Power BI) with an intelligent conversational interface')
bullet(doc, 'Build an enterprise-grade platform competing with Tableau, ThoughtSpot, and Databricks')
bullet(doc, 'Support full Arabic language in both UI and AI responses')
bullet(doc, 'Deliver production-ready security, multi-tenancy, and real-time capabilities')

doc.add_page_break()

# ── 2. TECHNOLOGY STACK ──────────────────────────────────────────────────────
heading(doc, '2. Technology Stack')
table2(doc, [
    ('Backend Framework',    'FastAPI (Python 3.11) — REST API + WebSocket server'),
    ('Frontend Framework',   'Next.js 14 (React) — App Router + TypeScript'),
    ('Database',             'SQLite (development) / PostgreSQL (production) via SQLAlchemy ORM'),
    ('Primary AI Model',     'Claude Sonnet (Anthropic) — intelligent answers and deep analysis'),
    ('Fallback AI Model',    'GPT-4o-mini (OpenAI) — automatic fallback via LLM Router'),
    ('RAG / Embeddings',     'Sentence-Transformers + pgvector / numpy for semantic search'),
    ('Charts & Visualization','Plotly.js — fully interactive charts (zoom, pan, hover, export)'),
    ('State Management',     'Zustand — lightweight frontend state management'),
    ('UI / Styling',         'Tailwind CSS + Framer Motion animations'),
    ('Background Tasks',     'Celery + Redis — async task processing'),
    ('Authentication',       'JWT (Access Token 15 min + Refresh Token 7 days) + bcrypt'),
    ('Security',             'GZip compression + Security Headers + Rate Limiting (200 req/min)'),
    ('Migrations',           'Alembic — database schema versioning'),
    ('Testing',              'pytest — 50 automated tests, 100% pass rate'),
], header=('Technology', 'Details'))

doc.add_page_break()

# ── 3. SYSTEM ARCHITECTURE ───────────────────────────────────────────────────
heading(doc, '3. System Architecture')
body(doc,
    'The system is split into two main layers: the Backend (Python server) and the Frontend '
    '(user interface). Communication happens via REST API and WebSocket connections.')

doc.add_paragraph()
body(doc, 'Backend Structure (89 endpoints):', bold=True)
bullet(doc, 'routers/ — 30+ router files defining all API endpoints')
bullet(doc, 'services/ — 27+ services containing business logic and AI integrations')
bullet(doc, 'models/ — Database models (SQLAlchemy ORM)')
bullet(doc, 'security/ — Authentication, authorization, and JWT handling')
bullet(doc, 'tasks/ — Celery tasks for background processing')

doc.add_paragraph()
body(doc, 'Frontend Structure (27+ pages):', bold=True)
bullet(doc, 'src/app/ — Next.js pages using App Router')
bullet(doc, 'src/components/ — Reusable React components')
bullet(doc, 'src/lib/ — API client, Zustand store, utilities, caching')

doc.add_paragraph()
body(doc, 'Data Flow:', bold=True)
body(doc,
    'User sends a question  ->  Frontend calls /api/chat/message  ->  '
    'Backend detects intent  ->  Routes to RAG or AI Agent  ->  '
    'Claude/GPT generates the answer  ->  Returns text + charts + insights to user.')

doc.add_page_break()

# ── 4. DETAILED FEATURES ─────────────────────────────────────────────────────
heading(doc, '4. Detailed Features')

# 4.1
heading(doc, '4.1  Authentication System', level=2)
body(doc, 'A complete authentication system based on JWT tokens with automatic session refresh.')
table2(doc, [
    ('User Registration',     'Creates account with email & password — hashed with bcrypt'),
    ('Login',                 'Issues Access Token (15 min) + Refresh Token (7 days)'),
    ('Token Refresh',         'Automatically renews Access Token without re-login'),
    ('Change Password',       'Secure password change from the Settings page'),
    ('Logout',                'Immediately revokes the Refresh Token in the database'),
    ('Demo Login',            'Instant access with a demo account — no registration needed'),
    ('API Protection',        'Every endpoint verifies the JWT — unauthenticated requests get 401'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.2
heading(doc, '4.2  Dataset Management', level=2)
body(doc, 'The heart of the platform — users upload their data and all AI features become available.')
table2(doc, [
    ('File Upload',           'Supports CSV, Excel (.xlsx), JSON, Parquet — up to 100MB'),
    ('Data Preview',          'Instantly displays first 100 rows with column names and data types'),
    ('Data Profiling',        'Auto-statistics: row count, null values, data distribution'),
    ('Export Data',           'Export in CSV, Excel, JSON, Parquet, or TSV format'),
    ('Dataset Comparison',    'Statistical drift analysis between an old and new dataset'),
    ('Delete Dataset',        'Safe deletion with removal of all associated data and indexes'),
    ('Data Isolation',        'Each user sees only their own files — full isolation enforced'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.3
heading(doc, '4.3  AI Chat with Data  (RAG-powered)', level=2)
body(doc,
    'The flagship feature. Users ask questions in natural language and receive intelligent analysis. '
    'Powered by Retrieval-Augmented Generation (RAG) to ensure accurate, data-grounded answers.')
table2(doc, [
    ('Chat without dataset',  'Answers general questions — coding, science, math, casual chat'),
    ('Chat with dataset',     'Analytical questions answered directly from the uploaded data'),
    ('Full Arabic support',   'User types in Arabic — AI automatically responds in Arabic'),
    ('RAG Indexing',          'Data is converted to embeddings; a semantic search index is built'),
    ('Confidence Score',      'Every answer includes a confidence level: high / medium / low'),
    ('Conversation History',  'Every session is saved with its full message history'),
    ('Auto Charts',           'Responses include Plotly charts automatically when relevant'),
    ('Streaming (SSE)',       'Responses appear token-by-token in real time'),
    ('Convert to Dashboard',  'Turn any conversation into a full dashboard in one click'),
    ('Delete Sessions',       'Users can delete any old conversation'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.4
heading(doc, '4.4  Statistical Analytics', level=2)
body(doc, 'Automatic statistical analysis performed immediately after data is uploaded.')
table2(doc, [
    ('Descriptive Statistics','Mean, median, standard deviation, min, max for all numeric columns'),
    ('Correlation Analysis',  'Full correlation matrix with interactive heatmap'),
    ('Outlier Detection',     'IQR + Z-Score to flag outliers in every column'),
    ('Distribution Analysis', 'Histograms and data distribution charts per column'),
    ('Column Profiling',      'Data type, null percentage, unique value count per column'),
    ('Overview Card',         'Quick summary card: size, columns, data quality score'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.5
heading(doc, '4.5  AI Insights', level=2)
body(doc, 'The AI reads the data and automatically surfaces actionable insights.')
table2(doc, [
    ('Auto Insights',         'Claude discovers hidden patterns and relationships in the data'),
    ('Actionable Recommendations', '"Increase sales in Region X by Y%" — specific and practical'),
    ('Insight Classification','Each insight is tagged: Trend / Anomaly / Correlation / Recommendation'),
    ('Data Story',            'A narrative explaining the data for non-technical users'),
    ('Saved Insights',        'All insights are saved and can be revisited at any time'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.6
heading(doc, '4.6  Forecasting', level=2)
body(doc, 'Time-series forecasting model that predicts future values.')
table2(doc, [
    ('Auto Time-Series Detection', 'System automatically detects whether data is time-series'),
    ('Forecast Models',       'Prophet (Facebook) + Linear Regression + Moving Average'),
    ('Forward Prediction',    'Predicts values for the next 30 days (configurable)'),
    ('Forecast Chart',        'Plotly chart showing actual data + forecast + confidence band'),
    ('Cross-sectional Data',  'If data is not time-series, explains why and suggests alternatives'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.7
heading(doc, '4.7  Anomaly Detection', level=2)
table2(doc, [
    ('Isolation Forest',      'Machine learning algorithm for detecting non-linear anomalies'),
    ('Z-Score + IQR',         'Classic statistical methods for fast detection'),
    ('Plain-language Alerts', 'System generates sentences like: "Unusual spike in column X"'),
    ('Anomaly Charts',        'Anomalous points highlighted in a different color on charts'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.8
heading(doc, '4.8  Dashboards', level=2)
body(doc, 'Build, save, and share interactive data dashboards.')
table2(doc, [
    ('Manual Dashboard Build','User selects charts and arranges them in a grid layout'),
    ('AI-Powered Build',      'Type a command in plain English -> Claude builds a full layout'),
    ('Public Sharing',        'Shareable public link — viewable without login'),
    ('Duplicate Dashboard',   'Clone an existing dashboard and customize it independently'),
    ('Drag & Drop Layout',    'Rearrange chart tiles by dragging'),
    ('Convert from Chat',     'Turn an analytical conversation directly into a dashboard'),
    ('Version History',       'Every edit is saved as a version — full change log'),
    ('Comments',              'Users can add comments on any dashboard'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.9
heading(doc, '4.9  Reports', level=2)
table2(doc, [
    ('Auto PDF Report',       'Generates a PDF with: summary, charts, insights, and recommendations'),
    ('Scheduled Reports',     'Send daily / weekly / monthly reports via email automatically'),
    ('Report Templates',      'Pre-built templates for: Sales, Marketing, Finance'),
    ('Excel Export',          'Export data and charts to Excel workbook'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.10
heading(doc, '4.10  Natural Language to SQL  (NL2SQL)', level=2)
body(doc, 'User types a question in plain language; the system generates SQL and executes it.')
table2(doc, [
    ('SQL Generation',        'Claude understands the question and produces an accurate SQL query'),
    ('Query Execution',       'Runs directly on the data and returns results'),
    ('Show Generated SQL',    'User sees the generated code and can edit it before running'),
    ('Injection Protection',  'Parameterized queries — fully protected against SQL injection'),
    ('Query History',         'All past queries are saved and searchable'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.11
heading(doc, '4.11  Autonomous Analysis Pipeline', level=2)
body(doc,
    'The most powerful feature. The user presses one button and the system runs a complete '
    '9-stage analysis in the background — zero manual steps required.')
table2(doc, [
    ('Stage 1: Profiling',    'Comprehensive analysis of every column and its characteristics'),
    ('Stage 2: Statistics',   'All descriptive statistics computed'),
    ('Stage 3: Correlations', 'Full correlation map between all columns'),
    ('Stage 4: Anomalies',    'Isolation Forest detects outliers and unusual values'),
    ('Stage 5: Forecasting',  'Time-series forecast (skipped automatically for cross-sectional data)'),
    ('Stage 6: AI Insights',  'Claude generates smart insights from all analytical results'),
    ('Stage 7: Recommendations', 'Priority-ranked actionable business recommendations'),
    ('Stage 8: Data Story',   'A complete narrative explaining the data in human language'),
    ('Stage 9: Dashboard',    'Auto-creates a dashboard with all generated charts'),
], header=('Stage', 'Description'))

doc.add_paragraph()

# 4.12
heading(doc, '4.12  Floating AI Copilot', level=2)
body(doc,
    'A floating button on every page (bottom right). Users can ask questions from anywhere '
    'without navigating to the Chat page. Supports Arabic and English, and routes automatically '
    'to the most appropriate service.')
table2(doc, [
    ('Intent Detection',      '15 intent types: forecast, anomaly, comparison, recommendation...'),
    ('Smart Routing',         'Routes to Forecasting / Anomaly / Agent based on the question'),
    ('Arabic Language',       'Automatically responds in Arabic if the question is in Arabic'),
    ('Works without dataset', 'Answers general knowledge questions even with no data loaded'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.13
heading(doc, '4.13  Alerts System', level=2)
body(doc, 'Users define rules; every time a condition is met they receive a notification.')
table2(doc, [
    ('Create Alert',          'Define: column + threshold + operator (greater / less / equals)'),
    ('Manual Trigger',        'Test the alert immediately without waiting'),
    ('Alert Log',             'Every time an alert fires, it is logged with a timestamp'),
    ('Delivery Channels',     'Email + Slack + Telegram + Webhook'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.14
heading(doc, '4.14  Data Connections', level=2)
table2(doc, [
    ('PostgreSQL',            'Direct connection to an external PostgreSQL database'),
    ('MySQL',                 'Connect to a MySQL server'),
    ('SQLite',                'Local SQLite database files'),
    ('Test Connection',       'Verify connectivity before saving the connection config'),
    ('Fetch Tables',          'Load tables directly from a connected DB for analysis'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.15
heading(doc, '4.15  AutoML', level=2)
body(doc, 'Train machine learning models without writing a single line of code.')
table2(doc, [
    ('Select Target Column',  'User picks the column they want the model to predict'),
    ('Choose Algorithm',      'Random Forest, XGBoost, Linear Regression, SVM'),
    ('Auto Training',         '80/20 train/test split + training + evaluation in one click'),
    ('Performance Metrics',   'Accuracy, F1-Score, RMSE, R-squared — based on problem type'),
    ('Feature Importance',    'SHAP values — shows which factors influence the prediction most'),
    ('Export Model',          'Save the trained model for later use'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.16
heading(doc, '4.16  Root Cause Analysis', level=2)
table2(doc, [
    ('Describe the Problem',  'User describes the issue in plain language'),
    ('AI Analysis',           'Claude analyzes the data and suggests root causes'),
    ('Ranked Causes',         'Causes ranked by probability and impact'),
    ('Fix Recommendations',   'Practical steps to address each identified cause'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.17
heading(doc, '4.17  What-If Scenario Analysis', level=2)
body(doc, 'User moves sliders and sees results update in real time.')
table2(doc, [
    ('Slider per Variable',   'Adjust any input variable from its minimum to maximum'),
    ('Real-time Update',      'Prediction updates instantly as the slider moves'),
    ('Compare Scenarios',     'Scenario A vs Scenario B side by side'),
    ('Save Scenario',         'Save any scenario to reference later'),
    ('Export to PDF',         'Export scenario results as a report'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.18
heading(doc, '4.18  Proactive Intelligence Feed', level=2)
body(doc,
    'The platform monitors data and pushes insights automatically before the user asks — '
    'inspired by Tableau Pulse.')
table2(doc, [
    ('Automatic Monitoring',  'Scans datasets every 15 minutes for significant changes'),
    ('Pattern Detection',     'Sudden spikes, drops, or new historical records'),
    ('Smart Narrative',       'Plain-language text: "Revenue dropped 12% this week"'),
    ('Personal Feed',         'A LinkedIn-style feed page showing analytical insights'),
    ('Multi-channel Delivery','WebSocket (instant) + Email + Slack + Telegram'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.19
heading(doc, '4.19  Multi-Tenant Admin System', level=2)
body(doc, 'Three-tier role hierarchy: SuperAdmin -> Company Admin -> Analyst / Viewer')
table2(doc, [
    ('SuperAdmin',            'Sees all data, manages all companies and users across the platform'),
    ('Company Admin',         'Manages only their own company members'),
    ('Analyst',               'Analyzes data available within their company workspace'),
    ('Viewer',                'Read-only access — no editing permissions'),
    ('Suspend Company',       'SuperAdmin can suspend a company, blocking all its users instantly'),
    ('Suspend User',          'Disable an individual user with a clear message on login'),
    ('Audit Log',             'Every operation is logged: who did it, when, and what'),
    ('Platform Statistics',   'User count, company count, AI usage, cost breakdown'),
], header=('Role / Feature', 'Description'))

doc.add_paragraph()

# 4.20
heading(doc, '4.20  Workspaces & Collaboration', level=2)
table2(doc, [
    ('Workspace',             'Each company / team has a fully isolated workspace'),
    ('API Keys',              'Generate API keys for programmatic access to the platform'),
    ('Webhooks',              'Send events to external systems when things happen'),
    ('Notification Center',   'In-app notification feed with badge counter'),
    ('WebSocket Real-time',   'Live updates without page refresh'),
    ('Dashboard Comments',    'Add comments on any dashboard for team discussions'),
    ('PR Review Workflow',    'Propose dashboard changes for peer review before publishing'),
], header=('Feature', 'Description'))

doc.add_paragraph()

# 4.21
heading(doc, '4.21  UI / UX & Customization', level=2)
table2(doc, [
    ('Dark / Light Mode',     'Toggle button in the Sidebar — preference saved automatically'),
    ('6 Accent Color Themes', 'Indigo, Violet, Emerald, Cyan, Rose, Amber'),
    ('Glassmorphism Design',  'Frosted-glass backgrounds with backdrop blur'),
    ('Performance Caching',   '30-second GET cache + parallel API calls for instant navigation'),
    ('Interactive Charts',    'Plotly.js — zoom, pan, hover tooltips, image export'),
    ('Sidebar Navigation',    'Organized into 5 sections with role-based visibility'),
    ('Responsive Layout',     'Consistent experience across screen sizes'),
], header=('Feature', 'Description'))

doc.add_page_break()

# ── 5. AI MODELS ─────────────────────────────────────────────────────────────
heading(doc, '5. AI Models & LLM Router')
body(doc,
    'The platform uses a smart LLM Router that automatically selects the best AI model '
    'for each type of task, with circuit breaking and Redis response caching.')

table2(doc, [
    ('Claude Sonnet 4.5',     'Storytelling, reports, deep analysis, root cause analysis'),
    ('GPT-4o-mini',           'Fast general chat, summaries, insights (primary fallback)'),
    ('Gemini 1.5 Flash',      'Long documents, large-context RAG processing'),
    ('Sentence-Transformers', 'Converting text to embeddings for semantic search'),
    ('Circuit Breaker',       'If a model fails 3 times, it is paused 5 min and the next is tried'),
    ('Redis Caching',         'LLM responses are cached for 1 hour to speed up repeated questions'),
    ('Task Routing',          '15 task types, each mapped to its optimal model'),
], header=('Model / Feature', 'Role'))

doc.add_page_break()

# ── 6. SECURITY ──────────────────────────────────────────────────────────────
heading(doc, '6. Security')
table2(doc, [
    ('JWT Authentication',    'Short-lived Access Token + Refresh Token with server-side blacklist'),
    ('bcrypt Password Hashing','Passwords are never stored in plain text'),
    ('Rate Limiting',         '200 requests/minute per IP — prevents DDoS and brute force'),
    ('Security Headers',      'X-Content-Type-Options, X-Frame-Options, XSS-Protection'),
    ('GZip Compression',      'Response compression for faster data transfer'),
    ('SQL Injection Protection','Parameterized queries via SQLAlchemy ORM'),
    ('CORS Policy',           'Only approved origins are allowed to communicate with the API'),
    ('Input Validation',      'Pydantic validates 100% of input data on every endpoint'),
    ('Data Isolation',        'Every query is filtered by user_id — no cross-user data leaks'),
], header=('Security Mechanism', 'Description'))

doc.add_page_break()

# ── 7. PAGES ─────────────────────────────────────────────────────────────────
heading(doc, '7. Platform Pages  (27 Pages)')
table2(doc, [
    ('/dashboard',         'Overview: quick stats, recent activity, summary charts'),
    ('/datasets',          'Upload, preview, profile, export, and delete data files'),
    ('/chat',              'AI-powered conversational analysis (the main feature)'),
    ('/analytics',         'Deep statistical analysis with interactive charts'),
    ('/insights',          'AI-generated insights and recommendations'),
    ('/forecasting',       'Time-series forecasting with confidence intervals'),
    ('/autonomous',        'Launch and monitor the 9-stage auto-analysis pipeline'),
    ('/dashboards',        'Build, share, and manage data dashboards'),
    ('/reports',           'Generate and export PDF reports'),
    ('/alerts',            'Create and manage threshold-based alert rules'),
    ('/nl2sql',            'Convert plain-language questions to SQL queries'),
    ('/automl',            'Train machine learning models without code'),
    ('/root-cause',        'AI-powered root cause analysis'),
    ('/scenarios',         'What-If interactive scenario simulation'),
    ('/proactive',         'Proactive intelligence feed with automatic insights'),
    ('/connections',       'Manage live database connections'),
    ('/compare',           'Compare two datasets for statistical drift'),
    ('/explore',           'No-code Business User Mode for non-technical users'),
    ('/catalog',           'Organized data asset catalog'),
    ('/metrics',           'Semantic Metric Catalog for governed KPIs'),
    ('/reviews',           'Peer review workflow for dashboard changes (PR-style)'),
    ('/templates',         'Ready-made dashboard templates library'),
    ('/scheduled-reports', 'Schedule and manage recurring automated reports'),
    ('/activity',          'Full audit log of all user actions'),
    ('/ai-models',         'AI model health status and usage statistics'),
    ('/settings',          'Account settings, security, appearance, API keys'),
    ('/admin',             'SuperAdmin control panel (restricted access)'),
], header=('Page', 'Content'))

doc.add_page_break()

# ── 8. API ENDPOINTS ─────────────────────────────────────────────────────────
heading(doc, '8. API Endpoints Summary  (89 Endpoints)')
table2(doc, [
    ('/api/auth',              '8 endpoints — register, login, refresh, logout, update profile'),
    ('/api/datasets',          '9 endpoints — upload, preview, profile, export, delete, compare'),
    ('/api/chat',              '8 endpoints — send message, streaming, sessions, convert to dashboard'),
    ('/api/analytics',         '5 endpoints — overview, correlation, outliers, descriptive stats'),
    ('/api/insights',          '4 endpoints — insights, recommendations, data story'),
    ('/api/dashboards',        '8 endpoints — create, edit, duplicate, share, comment, delete'),
    ('/api/copilot',           '3 endpoints — ask, list intents, classify intent'),
    ('/api/forecasting',       '3 endpoints — run forecast, get results, detect dataset type'),
    ('/api/autonomous',        '3 endpoints — start pipeline, check status, get results'),
    ('/api/alerts',            '5 endpoints — create, list, trigger, view log, delete'),
    ('/api/nl2sql',            '3 endpoints — convert, execute, history'),
    ('/api/automl',            '4 endpoints — train, status, results, SHAP explanations'),
    ('/api/root-cause',        '2 endpoints — analyze, get results'),
    ('/api/scenarios',         '3 endpoints — simulate, save, list'),
    ('/api/admin',             '14 endpoints — stats, users, companies, suspend, audit log'),
    ('/api/ai',                '3 endpoints — model status, usage stats, cost breakdown'),
    ('+ 15 additional routers','workspaces, webhooks, notifications, metrics, templates, catalog...'),
], header=('Route Group', 'Endpoints'))

doc.add_page_break()

# ── 9. TESTING ───────────────────────────────────────────────────────────────
heading(doc, '9. Automated Testing')
body(doc, '50 automated tests covering all core functionality — 100% pass rate in ~93 seconds.')

table2(doc, [
    ('test_auth.py',          '10 tests — register, login, token refresh, logout, update profile'),
    ('test_datasets.py',      '10 tests — upload, preview, profile, compare, export, delete'),
    ('test_analytics.py',     '8 tests  — overview, correlation, outlier detection, stats'),
    ('test_alerts.py',        '8 tests  — create, update, trigger, view log, delete'),
    ('test_connections.py',   '7 tests  — PostgreSQL, MySQL, SQLite connection handling'),
    ('test_export_service.py','7 tests  — CSV, Excel, JSON, Parquet, TSV export formats'),
], header=('Test File', 'Coverage'))

doc.add_page_break()

# ── 10. COMPETITIVE COMPARISON ───────────────────────────────────────────────
heading(doc, '10. Competitive Comparison')
body(doc,
    'DataMind was deliberately designed to match or surpass features from the world\'s '
    'leading analytics platforms in every key area.')

table2(doc, [
    ('Tableau Pulse',         'Proactive Intelligence Feed -- automatic insight push before users ask'),
    ('ThoughtSpot',           'Semantic Metric Catalog -- central governed KPI definitions'),
    ('Databricks Genie',      'Transparent AI -- shows generated SQL + reasoning steps'),
    ('Hex',                   'Thread-to-Dashboard -- convert a chat conversation into a dashboard'),
    ('Qlik AutoML',           'What-If Scenarios + AutoML with SHAP explainability'),
    ('Grafana',               'Real-time WebSocket streaming dashboards'),
    ('Power BI Copilot',      'Full Arabic language support in UI and AI responses'),
    ('Tableau / Power BI',    'Zero-Code Business User Mode for non-technical stakeholders'),
    ('Claude Desktop',        'MCP Server -- DataMind exposed as a tool for external AI agents'),
], header=('Competitor', 'Feature Where DataMind Leads'))

doc.add_page_break()

# ── 11. PROJECT STATISTICS ───────────────────────────────────────────────────
heading(doc, '11. Project Statistics & Conclusion')

table2(doc, [
    ('Total API Endpoints',   '89 endpoints'),
    ('Backend Services',      '27+ services'),
    ('Frontend Pages',        '27+ pages'),
    ('AI Models Integrated',  '4 models (Claude, GPT-4o, Gemini, Ollama)'),
    ('Automated Tests',       '50 tests — 100% pass rate'),
    ('Languages Supported',   'English and Arabic (full support)'),
    ('Supported File Formats','CSV, Excel, JSON, Parquet + live database connections'),
    ('Development Phases',    '19 phases (Phase 1 through Phase 19)'),
    ('Backend Routes',        '30+ router files'),
    ('Database Models',       '25+ SQLAlchemy models'),
], header=('Metric', 'Value'))

doc.add_paragraph()
body(doc,
    'DataMind AI is not just an academic project — it is a fully functional, production-ready '
    'platform built to enterprise specifications. It combines the power of modern AI '
    '(Claude, GPT-4) with an accessible interface that serves everyone: the executive who '
    'needs KPI summaries, the analyst who writes SQL, and the researcher building ML models.',
    italic=True, color=(75, 85, 99))

doc.add_paragraph()
body(doc,
    'The core vision: "Data analysis should be accessible to everyone." DataMind delivers on '
    'this vision through a single platform that speaks your language, understands your data, '
    'and proactively surfaces the insights that matter most.',
    bold=True)

# ── Save ─────────────────────────────────────────────────────────────────────
output_path = r'C:\AI copy\MY_AGENT_COPY\AUTONOMOUS_AI_DATA_ANALYST\DataMind_AI_Project_Documentation.docx'
doc.save(output_path)
print(f'DONE: {output_path}')
