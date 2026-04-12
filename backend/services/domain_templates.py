"""
Domain Templates — pre-built analysis templates for common business domains.
"""

from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
#  Template registry
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_TEMPLATES: dict[str, dict[str, Any]] = {

    # ── Finance ──────────────────────────────────────────────────────────────
    "finance": {
        "p_and_l_analysis": {
            "name": "p_and_l_analysis",
            "domain": "finance",
            "description": "Profit and Loss analysis with revenue, cost, and margin breakdown",
            "required_columns": ["revenue", "cost", "period"],
            "optional_columns": ["category", "region", "product"],
            "analysis_steps": [
                "Load and validate P&L columns",
                "Calculate gross profit = revenue - cost",
                "Calculate gross margin % = (gross_profit / revenue) * 100",
                "Trend revenue and cost over time periods",
                "Identify top and bottom performers by category",
                "Compute YoY or MoM growth rates",
                "Flag anomalies in margin compression",
            ],
            "default_charts": [
                {"type": "bar", "x": "period", "y": ["revenue", "cost"], "title": "Revenue vs Cost"},
                {"type": "line", "x": "period", "y": "gross_margin_pct", "title": "Gross Margin %"},
                {"type": "waterfall", "title": "P&L Waterfall"},
            ],
            "report_sections": [
                "Executive Summary",
                "Revenue Analysis",
                "Cost Analysis",
                "Margin Analysis",
                "Period-over-Period Comparison",
                "Key Risks and Opportunities",
            ],
            "sample_insights": [
                "Revenue grew X% vs prior period driven by category Y",
                "Gross margin compressed by X bps due to rising COGS",
                "Operating expenses as % of revenue improved to X%",
            ],
            "kpis": [
                {"name": "Gross Profit", "formula": "revenue - cost"},
                {"name": "Gross Margin %", "formula": "(revenue - cost) / revenue * 100"},
                {"name": "Revenue Growth %", "formula": "(current_revenue - prior_revenue) / prior_revenue * 100"},
            ],
        },
        "cash_flow_analysis": {
            "name": "cash_flow_analysis",
            "domain": "finance",
            "description": "Cash flow analysis covering operating, investing, and financing activities",
            "required_columns": ["date", "amount", "flow_type"],
            "optional_columns": ["category", "account"],
            "analysis_steps": [
                "Classify flows into operating / investing / financing",
                "Calculate net cash flow by period",
                "Compute rolling 30/60/90-day cash positions",
                "Identify cash burn rate",
                "Forecast cash runway",
                "Flag periods with negative operating cash flow",
            ],
            "default_charts": [
                {"type": "waterfall", "title": "Cash Flow Waterfall"},
                {"type": "line", "x": "date", "y": "cumulative_cash", "title": "Cumulative Cash Position"},
                {"type": "bar", "x": "period", "y": "net_cash_flow", "title": "Net Cash Flow by Period"},
            ],
            "report_sections": [
                "Cash Position Summary",
                "Operating Cash Flow",
                "Investing Activities",
                "Financing Activities",
                "Cash Runway Forecast",
            ],
            "sample_insights": [
                "Operating cash flow turned negative in Q3 — review AR collections",
                "Capital expenditure increased 35% driven by equipment purchases",
                "Cash runway estimated at X months at current burn rate",
            ],
            "kpis": [
                {"name": "Net Cash Flow", "formula": "sum(operating) + sum(investing) + sum(financing)"},
                {"name": "Operating Cash Ratio", "formula": "operating_cash / current_liabilities"},
                {"name": "Cash Burn Rate", "formula": "abs(monthly_net_outflow)"},
            ],
        },
        "variance_report": {
            "name": "variance_report",
            "domain": "finance",
            "description": "Variance analysis comparing actual vs budget/forecast",
            "required_columns": ["actual", "budget", "metric", "period"],
            "optional_columns": ["department", "cost_center"],
            "analysis_steps": [
                "Calculate absolute variance = actual - budget",
                "Calculate variance % = (actual - budget) / budget * 100",
                "Rank variances by absolute magnitude",
                "Classify as favourable / unfavourable",
                "Drill down by department and cost centre",
                "Highlight metrics with variance > 10%",
            ],
            "default_charts": [
                {"type": "bar", "x": "metric", "y": "variance_pct", "title": "Variance % by Metric"},
                {"type": "grouped_bar", "x": "period", "y": ["actual", "budget"], "title": "Actual vs Budget"},
            ],
            "report_sections": [
                "Variance Summary",
                "Favourable Variances",
                "Unfavourable Variances",
                "Root Cause Analysis",
                "Corrective Actions",
            ],
            "sample_insights": [
                "Revenue is X% above budget — driven by new customer acquisitions",
                "Payroll variance of -$Xk is within acceptable range",
                "Marketing spend exceeded budget by X% due to campaign acceleration",
            ],
            "kpis": [
                {"name": "Total Variance", "formula": "sum(actual) - sum(budget)"},
                {"name": "Variance %", "formula": "(sum(actual) - sum(budget)) / sum(budget) * 100"},
                {"name": "Metrics On-Budget", "formula": "count(abs(variance_pct) < 5)"},
            ],
        },
        "budget_vs_actual": {
            "name": "budget_vs_actual",
            "domain": "finance",
            "description": "Budget vs actual tracking with rolling forecast updates",
            "required_columns": ["period", "actual", "budget"],
            "optional_columns": ["category", "department", "forecast"],
            "analysis_steps": [
                "Load actuals and budget by period",
                "Calculate YTD actuals vs YTD budget",
                "Project full-year outcome based on run rate",
                "Highlight categories tracking ahead/behind",
                "Compute forecast accuracy where forecast data exists",
            ],
            "default_charts": [
                {"type": "line", "x": "period", "y": ["actual", "budget", "forecast"], "title": "Actuals vs Budget vs Forecast"},
                {"type": "bar", "x": "category", "y": "ytd_variance_pct", "title": "YTD Variance % by Category"},
            ],
            "report_sections": [
                "YTD Performance Summary",
                "Full-Year Projection",
                "Category Deep-Dive",
                "Forecast Accuracy Review",
            ],
            "sample_insights": [
                "YTD actuals are X% of full-year budget with Q4 remaining",
                "Revenue on track to exceed budget by X% if current trajectory holds",
                "Operating expenses trending X% over budget — action required",
            ],
            "kpis": [
                {"name": "Budget Attainment %", "formula": "ytd_actual / ytd_budget * 100"},
                {"name": "Full-Year Projection", "formula": "ytd_actual / elapsed_periods * 12"},
                {"name": "Forecast Accuracy", "formula": "1 - abs(forecast - actual) / actual"},
            ],
        },
    },

    # ── Retail ────────────────────────────────────────────────────────────────
    "retail": {
        "sales_trend": {
            "name": "sales_trend",
            "domain": "retail",
            "description": "Sales trend analysis with seasonality and growth decomposition",
            "required_columns": ["date", "sales"],
            "optional_columns": ["store", "category", "channel", "region"],
            "analysis_steps": [
                "Aggregate sales by time period",
                "Compute period-over-period growth rates",
                "Decompose trend, seasonality, and residual",
                "Identify peak and trough periods",
                "Compare channel / store / category performance",
                "Detect anomalous sales days",
            ],
            "default_charts": [
                {"type": "line", "x": "date", "y": "sales", "title": "Sales Trend"},
                {"type": "bar", "x": "month", "y": "sales", "title": "Monthly Sales"},
                {"type": "heatmap", "title": "Sales Heatmap by Day/Week"},
            ],
            "report_sections": [
                "Sales Performance Summary",
                "Growth Analysis",
                "Seasonality Patterns",
                "Channel / Store Comparison",
                "Anomaly Detection",
            ],
            "sample_insights": [
                "Sales grew X% YoY with strongest performance in Q4",
                "Weekend sales account for X% of weekly revenue",
                "Online channel growing at X% vs in-store -X%",
            ],
            "kpis": [
                {"name": "Total Sales", "formula": "sum(sales)"},
                {"name": "Sales Growth %", "formula": "(current_period - prior_period) / prior_period * 100"},
                {"name": "Average Daily Sales", "formula": "sum(sales) / count(distinct_dates)"},
            ],
        },
        "inventory_analysis": {
            "name": "inventory_analysis",
            "domain": "retail",
            "description": "Inventory health analysis with turnover, stockout, and overstock detection",
            "required_columns": ["product", "stock_qty", "sales_qty"],
            "optional_columns": ["category", "lead_time_days", "reorder_point", "cost"],
            "analysis_steps": [
                "Calculate inventory turnover ratio",
                "Identify stockout risk (days of stock < lead time)",
                "Flag overstock items (days of stock > 90)",
                "Compute dead stock (zero sales in 90 days)",
                "Calculate carry cost of excess inventory",
                "Recommend reorder quantities",
            ],
            "default_charts": [
                {"type": "bar", "x": "category", "y": "turnover_ratio", "title": "Inventory Turnover by Category"},
                {"type": "scatter", "x": "days_of_stock", "y": "sales_velocity", "title": "Stock vs Sales Velocity"},
            ],
            "report_sections": [
                "Inventory Health Overview",
                "Stockout Risk",
                "Overstock Items",
                "Dead Stock Analysis",
                "Reorder Recommendations",
            ],
            "sample_insights": [
                "X% of SKUs at stockout risk — immediate reorder required",
                "Overstock carrying cost estimated at $Xk/month",
                "Top 10 dead stock SKUs represent $Xk in tied-up capital",
            ],
            "kpis": [
                {"name": "Inventory Turnover", "formula": "COGS / average_inventory"},
                {"name": "Days of Stock", "formula": "stock_qty / avg_daily_sales"},
                {"name": "Stockout Rate", "formula": "stockout_events / total_demand_events * 100"},
            ],
        },
        "customer_segmentation": {
            "name": "customer_segmentation",
            "domain": "retail",
            "description": "RFM-based customer segmentation with lifetime value estimation",
            "required_columns": ["customer_id", "order_date", "order_value"],
            "optional_columns": ["product_category", "channel", "region"],
            "analysis_steps": [
                "Calculate Recency (days since last purchase)",
                "Calculate Frequency (number of orders)",
                "Calculate Monetary value (total spend)",
                "Score each dimension 1-5",
                "Assign segments: Champions, Loyal, At-Risk, Lost, New",
                "Estimate Customer Lifetime Value per segment",
            ],
            "default_charts": [
                {"type": "scatter_3d", "title": "RFM 3D Scatter"},
                {"type": "treemap", "title": "Customer Segments by Revenue"},
                {"type": "bar", "x": "segment", "y": "customer_count", "title": "Customers per Segment"},
            ],
            "report_sections": [
                "Segmentation Overview",
                "Champion & Loyal Customers",
                "At-Risk Customers",
                "Win-Back Opportunities",
                "LTV by Segment",
            ],
            "sample_insights": [
                "Champions (X% of customers) drive Y% of revenue",
                "X customers are at risk of churning — targeted campaign recommended",
                "Average LTV for Loyal segment is $X vs $Y for New customers",
            ],
            "kpis": [
                {"name": "Average Order Value", "formula": "sum(order_value) / count(orders)"},
                {"name": "Purchase Frequency", "formula": "count(orders) / count(distinct_customers)"},
                {"name": "Customer Retention Rate", "formula": "retained_customers / prior_period_customers * 100"},
            ],
        },
        "product_performance": {
            "name": "product_performance",
            "domain": "retail",
            "description": "Product-level performance analysis with margin and velocity metrics",
            "required_columns": ["product", "sales", "units_sold"],
            "optional_columns": ["cost", "category", "margin", "returns"],
            "analysis_steps": [
                "Rank products by revenue and units",
                "Calculate contribution margin per product",
                "Build BCG matrix (growth vs market share)",
                "Identify underperformers and stars",
                "Analyse return rates and their impact on margin",
            ],
            "default_charts": [
                {"type": "bar", "x": "product", "y": "sales", "title": "Top 20 Products by Sales"},
                {"type": "scatter", "x": "sales_growth", "y": "market_share", "title": "BCG Matrix"},
            ],
            "report_sections": [
                "Top Performers",
                "Underperformers",
                "Margin Analysis",
                "Product Mix Optimisation",
            ],
            "sample_insights": [
                "Top 10 products account for X% of total revenue (Pareto principle)",
                "Category Y has highest margin at X% but lowest volume",
                "Return rate for Product Z is X% above average — quality review needed",
            ],
            "kpis": [
                {"name": "Revenue per SKU", "formula": "total_revenue / distinct_products"},
                {"name": "Product Margin %", "formula": "(sales - cost) / sales * 100"},
                {"name": "Return Rate", "formula": "returns / units_sold * 100"},
            ],
        },
    },

    # ── Healthcare ────────────────────────────────────────────────────────────
    "healthcare": {
        "patient_outcomes": {
            "name": "patient_outcomes",
            "domain": "healthcare",
            "description": "Patient outcome analysis including mortality, recovery, and LOS metrics",
            "required_columns": ["patient_id", "admission_date", "discharge_date", "diagnosis"],
            "optional_columns": ["outcome", "los_days", "age", "gender", "department"],
            "analysis_steps": [
                "Calculate length of stay (LOS) distribution",
                "Compute mortality rate by diagnosis and department",
                "Analyse 30-day readmission patterns",
                "Segment patients by acuity score",
                "Benchmark against national averages",
            ],
            "default_charts": [
                {"type": "histogram", "x": "los_days", "title": "Length of Stay Distribution"},
                {"type": "bar", "x": "diagnosis", "y": "mortality_rate", "title": "Mortality Rate by Diagnosis"},
            ],
            "report_sections": [
                "Outcome Summary",
                "Length of Stay Analysis",
                "Mortality & Morbidity",
                "Readmission Analysis",
                "Department Benchmarking",
            ],
            "sample_insights": [
                "Average LOS is X days — X days above benchmark",
                "30-day readmission rate is X% for CHF patients",
                "ICU mortality improved by X% following protocol change",
            ],
            "kpis": [
                {"name": "Average LOS", "formula": "sum(los_days) / count(patients)"},
                {"name": "Mortality Rate", "formula": "deaths / admissions * 100"},
                {"name": "Readmission Rate", "formula": "readmissions_within_30d / total_discharges * 100"},
            ],
        },
        "readmission_risk": {
            "name": "readmission_risk",
            "domain": "healthcare",
            "description": "Predictive readmission risk scoring using clinical features",
            "required_columns": ["patient_id", "discharge_date", "diagnosis", "age"],
            "optional_columns": ["prior_admissions", "medications", "comorbidities", "readmitted"],
            "analysis_steps": [
                "Engineer readmission risk features",
                "Calculate LACE score components",
                "Build logistic regression risk model",
                "Identify high-risk patient cohort",
                "Recommend targeted interventions",
            ],
            "default_charts": [
                {"type": "bar", "x": "risk_tier", "y": "patient_count", "title": "Patients by Risk Tier"},
                {"type": "roc_curve", "title": "Model ROC Curve"},
            ],
            "report_sections": [
                "Risk Stratification Summary",
                "High-Risk Cohort Profile",
                "Model Performance",
                "Intervention Recommendations",
            ],
            "sample_insights": [
                "X% of patients fall into high-risk tier",
                "Prior admission history is the strongest readmission predictor",
                "Intervention programme could prevent X readmissions/month",
            ],
            "kpis": [
                {"name": "High-Risk Patient %", "formula": "high_risk_count / total_patients * 100"},
                {"name": "Model AUC", "formula": "area_under_roc_curve"},
                {"name": "Preventable Readmissions", "formula": "high_risk_count * intervention_effectiveness"},
            ],
        },
        "cost_analysis": {
            "name": "cost_analysis",
            "domain": "healthcare",
            "description": "Healthcare cost analysis by department, diagnosis, and payer",
            "required_columns": ["patient_id", "total_charge", "department"],
            "optional_columns": ["diagnosis", "payer", "los_days", "procedure"],
            "analysis_steps": [
                "Aggregate costs by department and diagnosis",
                "Calculate cost per patient day and per episode",
                "Benchmark against DRG expected costs",
                "Identify high-cost outliers",
                "Analyse payer mix impact on net revenue",
            ],
            "default_charts": [
                {"type": "treemap", "title": "Cost by Department"},
                {"type": "scatter", "x": "los_days", "y": "total_charge", "title": "LOS vs Cost"},
            ],
            "report_sections": [
                "Cost Overview",
                "Department Cost Breakdown",
                "High-Cost Outliers",
                "Payer Mix Analysis",
                "Cost Reduction Opportunities",
            ],
            "sample_insights": [
                "Average cost per inpatient episode is $X vs benchmark $Y",
                "Top 5% of patients account for X% of total costs",
                "Government payer mix increased to X%, compressing net revenue",
            ],
            "kpis": [
                {"name": "Cost per Patient Day", "formula": "total_cost / total_patient_days"},
                {"name": "Cost per Episode", "formula": "total_cost / total_admissions"},
                {"name": "Cost Variance vs DRG", "formula": "(actual_cost - drg_expected) / drg_expected * 100"},
            ],
        },
        "quality_metrics": {
            "name": "quality_metrics",
            "domain": "healthcare",
            "description": "Clinical quality metrics aligned to HEDIS and Joint Commission standards",
            "required_columns": ["measure", "numerator", "denominator", "period"],
            "optional_columns": ["department", "provider", "benchmark"],
            "analysis_steps": [
                "Calculate compliance rate for each quality measure",
                "Compare to national benchmark",
                "Identify measures below threshold",
                "Trend quality scores over time",
                "Generate performance improvement plan",
            ],
            "default_charts": [
                {"type": "gauge", "title": "Quality Score Dashboard"},
                {"type": "bar", "x": "measure", "y": "compliance_rate", "title": "Compliance by Measure"},
            ],
            "report_sections": [
                "Quality Score Summary",
                "Measures Below Target",
                "Benchmark Comparison",
                "Trend Analysis",
                "Improvement Action Plan",
            ],
            "sample_insights": [
                "Overall quality composite score is X% — X points above benchmark",
                "Diabetes management measure fell below threshold — workflow review needed",
                "Hospital-acquired infection rate at X% — lowest in 3 years",
            ],
            "kpis": [
                {"name": "Quality Composite Score", "formula": "weighted_avg(compliance_rates)"},
                {"name": "Measures At or Above Benchmark", "formula": "count(rate >= benchmark) / total_measures * 100"},
                {"name": "HAI Rate", "formula": "hospital_acquired_infections / patient_days * 1000"},
            ],
        },
    },

    # ── Marketing ─────────────────────────────────────────────────────────────
    "marketing": {
        "funnel_analysis": {
            "name": "funnel_analysis",
            "domain": "marketing",
            "description": "Conversion funnel analysis with stage-by-stage drop-off and optimisation",
            "required_columns": ["stage", "users_count"],
            "optional_columns": ["date", "channel", "campaign", "cohort"],
            "analysis_steps": [
                "Calculate stage-to-stage conversion rates",
                "Identify the biggest drop-off stage",
                "Segment funnel by acquisition channel",
                "Compare cohort funnels over time",
                "Estimate revenue impact of improving each stage",
            ],
            "default_charts": [
                {"type": "funnel", "title": "Conversion Funnel"},
                {"type": "bar", "x": "stage", "y": "drop_off_rate", "title": "Drop-off Rate by Stage"},
            ],
            "report_sections": [
                "Funnel Overview",
                "Stage Analysis",
                "Channel Comparison",
                "Optimisation Opportunities",
            ],
            "sample_insights": [
                "Checkout step has highest drop-off at X% — UX improvement opportunity",
                "Email channel converts at X% vs paid search at Y%",
                "Improving cart-to-checkout by 5% adds $Xk in revenue",
            ],
            "kpis": [
                {"name": "Overall Conversion Rate", "formula": "final_stage / top_of_funnel * 100"},
                {"name": "Stage Conversion Rate", "formula": "stage_n_users / stage_n-1_users * 100"},
                {"name": "Revenue Per Visitor", "formula": "total_revenue / top_of_funnel_visitors"},
            ],
        },
        "campaign_roi": {
            "name": "campaign_roi",
            "domain": "marketing",
            "description": "Campaign ROI analysis with attribution and spend efficiency metrics",
            "required_columns": ["campaign", "spend", "revenue"],
            "optional_columns": ["channel", "impressions", "clicks", "conversions", "date"],
            "analysis_steps": [
                "Calculate ROI = (revenue - spend) / spend * 100",
                "Compute ROAS = revenue / spend",
                "Calculate CPA = spend / conversions",
                "Rank campaigns by ROAS and absolute profit",
                "Identify under/over-performing channels",
                "Recommend budget reallocation",
            ],
            "default_charts": [
                {"type": "scatter", "x": "spend", "y": "revenue", "title": "Spend vs Revenue Bubble Chart"},
                {"type": "bar", "x": "campaign", "y": "roas", "title": "ROAS by Campaign"},
            ],
            "report_sections": [
                "Campaign Performance Summary",
                "ROI & ROAS Breakdown",
                "Channel Efficiency",
                "Budget Reallocation Recommendations",
            ],
            "sample_insights": [
                "Top campaign delivered X:1 ROAS — scale budget recommended",
                "Display channel CPA is X% above target — pause and redirect spend",
                "Shifting 20% of budget to top 2 campaigns increases projected ROI by $Xk",
            ],
            "kpis": [
                {"name": "ROAS", "formula": "revenue / spend"},
                {"name": "ROI %", "formula": "(revenue - spend) / spend * 100"},
                {"name": "CPA", "formula": "spend / conversions"},
            ],
        },
        "cohort_analysis": {
            "name": "cohort_analysis",
            "domain": "marketing",
            "description": "User cohort retention analysis with LTV projection",
            "required_columns": ["user_id", "signup_date", "activity_date"],
            "optional_columns": ["revenue", "channel", "plan_type"],
            "analysis_steps": [
                "Define cohorts by signup month",
                "Calculate retention rate for each cohort at M1, M3, M6, M12",
                "Build retention heatmap",
                "Calculate cumulative LTV by cohort",
                "Identify best and worst cohort performance",
            ],
            "default_charts": [
                {"type": "heatmap", "title": "Cohort Retention Heatmap"},
                {"type": "line", "title": "Retention Curves by Cohort"},
                {"type": "bar", "x": "cohort", "y": "ltv_12m", "title": "12-Month LTV by Cohort"},
            ],
            "report_sections": [
                "Cohort Overview",
                "Retention Analysis",
                "LTV by Cohort",
                "Best Performing Cohorts",
                "Churn Drivers",
            ],
            "sample_insights": [
                "Month-1 retention improved from X% to Y% for recent cohorts",
                "Paid channel cohorts show X% higher 6-month retention than organic",
                "LTV payback period is X months on average",
            ],
            "kpis": [
                {"name": "M1 Retention", "formula": "users_active_month_1 / cohort_size * 100"},
                {"name": "12M LTV", "formula": "avg_revenue_per_user * 12m_retention_rate"},
                {"name": "Churn Rate", "formula": "(cohort_start - cohort_end) / cohort_start * 100"},
            ],
        },
        "attribution_model": {
            "name": "attribution_model",
            "domain": "marketing",
            "description": "Multi-touch attribution analysis to credit channels accurately",
            "required_columns": ["user_id", "touchpoint", "channel", "conversion"],
            "optional_columns": ["revenue", "timestamp", "campaign"],
            "analysis_steps": [
                "Build customer journey maps",
                "Apply first-touch, last-touch, and linear attribution",
                "Compare attribution models across channels",
                "Calculate data-driven attribution weights",
                "Recommend budget allocation based on attributed value",
            ],
            "default_charts": [
                {"type": "sankey", "title": "Customer Journey Sankey"},
                {"type": "bar", "x": "channel", "y": ["first_touch", "last_touch", "linear"], "title": "Attribution Comparison"},
            ],
            "report_sections": [
                "Attribution Overview",
                "Channel Credit Comparison",
                "Journey Analysis",
                "Budget Implications",
            ],
            "sample_insights": [
                "Organic search is under-valued by last-touch — 30% more credit in linear model",
                "Average customer journey involves X touchpoints before conversion",
                "Email assists X% of conversions but rarely receives last-touch credit",
            ],
            "kpis": [
                {"name": "Assisted Conversions", "formula": "count(non-last-touch_conversions)"},
                {"name": "Avg Touchpoints to Convert", "formula": "sum(touchpoints) / count(conversions)"},
                {"name": "Attribution Efficiency", "formula": "attributed_revenue / total_spend"},
            ],
        },
    },

    # ── HR ────────────────────────────────────────────────────────────────────
    "hr": {
        "attrition_analysis": {
            "name": "attrition_analysis",
            "domain": "hr",
            "description": "Employee attrition analysis with risk scoring and retention insights",
            "required_columns": ["employee_id", "hire_date", "status"],
            "optional_columns": ["department", "role", "salary", "performance_score", "tenure_years", "exit_reason"],
            "analysis_steps": [
                "Calculate voluntary and involuntary attrition rates",
                "Segment attrition by department, tenure band, and role",
                "Identify early-warning indicators correlated with departure",
                "Build attrition risk score model",
                "Estimate replacement cost per attrition event",
                "Recommend targeted retention interventions",
            ],
            "default_charts": [
                {"type": "bar", "x": "department", "y": "attrition_rate", "title": "Attrition Rate by Department"},
                {"type": "line", "x": "tenure_band", "y": "attrition_rate", "title": "Attrition by Tenure"},
            ],
            "report_sections": [
                "Attrition Overview",
                "High-Risk Segments",
                "Exit Reason Analysis",
                "Financial Impact",
                "Retention Strategy",
            ],
            "sample_insights": [
                "Overall attrition rate is X% — X points above industry benchmark",
                "First-year attrition at X% signals onboarding issues",
                "Engineering department attrition cost estimated at $Xk/year",
            ],
            "kpis": [
                {"name": "Attrition Rate", "formula": "departures / avg_headcount * 100"},
                {"name": "Average Tenure", "formula": "sum(tenure_years) / count(employees)"},
                {"name": "Replacement Cost", "formula": "departures * avg_cost_per_replacement"},
            ],
        },
        "headcount_report": {
            "name": "headcount_report",
            "domain": "hr",
            "description": "Workforce headcount and composition report with trend analysis",
            "required_columns": ["employee_id", "department", "status"],
            "optional_columns": ["hire_date", "role_level", "location", "employment_type"],
            "analysis_steps": [
                "Calculate active headcount by department and level",
                "Track headcount growth month-over-month",
                "Analyse workforce composition (full-time, part-time, contractor)",
                "Calculate span of control for managers",
                "Identify departments with open headcount vs plan",
            ],
            "default_charts": [
                {"type": "bar", "x": "department", "y": "headcount", "title": "Headcount by Department"},
                {"type": "line", "x": "date", "y": "total_headcount", "title": "Headcount Trend"},
            ],
            "report_sections": [
                "Headcount Summary",
                "Departmental Breakdown",
                "Workforce Composition",
                "Open Roles vs Plan",
                "Span of Control",
            ],
            "sample_insights": [
                "Total headcount grew by X% — driven by Engineering and Sales hires",
                "Contractor ratio at X% of total workforce",
                "Average manager span of control is X direct reports",
            ],
            "kpis": [
                {"name": "Total Active Headcount", "formula": "count(status == 'active')"},
                {"name": "Headcount Growth %", "formula": "(current - prior) / prior * 100"},
                {"name": "Span of Control", "formula": "total_employees / total_managers"},
            ],
        },
        "compensation_analysis": {
            "name": "compensation_analysis",
            "domain": "hr",
            "description": "Compensation equity and competitiveness analysis",
            "required_columns": ["employee_id", "salary", "role"],
            "optional_columns": ["department", "performance_score", "tenure_years", "market_salary", "gender"],
            "analysis_steps": [
                "Calculate compensation percentiles by role and level",
                "Benchmark against market data",
                "Identify employees below market midpoint",
                "Run pay equity analysis by gender and tenure",
                "Calculate compa-ratio distribution",
                "Flag compression and inversion issues",
            ],
            "default_charts": [
                {"type": "box", "x": "role", "y": "salary", "title": "Salary Distribution by Role"},
                {"type": "scatter", "x": "tenure_years", "y": "salary", "title": "Salary vs Tenure"},
            ],
            "report_sections": [
                "Compensation Overview",
                "Market Positioning",
                "Pay Equity Analysis",
                "Compression Issues",
                "Budget Requirement for Adjustments",
            ],
            "sample_insights": [
                "X% of employees are below market 25th percentile — retention risk",
                "Pay gap between genders is X% after controlling for role and tenure",
                "Salary compression affecting X managers vs their direct reports",
            ],
            "kpis": [
                {"name": "Compa-Ratio", "formula": "actual_salary / market_midpoint * 100"},
                {"name": "Below Market %", "formula": "count(salary < market_p50) / headcount * 100"},
                {"name": "Pay Equity Gap", "formula": "(male_avg_salary - female_avg_salary) / male_avg_salary * 100"},
            ],
        },
        "performance_review": {
            "name": "performance_review",
            "domain": "hr",
            "description": "Performance review cycle analysis with calibration insights",
            "required_columns": ["employee_id", "rating", "review_period"],
            "optional_columns": ["department", "manager_id", "role", "prior_rating"],
            "analysis_steps": [
                "Analyse rating distribution across all employees",
                "Check for manager-level rating bias",
                "Compare rating distribution vs target bell curve",
                "Identify high performers at risk of attrition (high rating + below market pay)",
                "Correlate performance ratings with business outcomes",
            ],
            "default_charts": [
                {"type": "histogram", "x": "rating", "title": "Performance Rating Distribution"},
                {"type": "bar", "x": "department", "y": "avg_rating", "title": "Avg Rating by Department"},
            ],
            "report_sections": [
                "Rating Distribution",
                "Manager Calibration",
                "High-Performer Risk",
                "Performance-Pay Alignment",
            ],
            "sample_insights": [
                "X% of employees rated 'Exceeds Expectations' vs target of Y%",
                "Department Z shows significant upward rating bias vs calibration target",
                "X high performers are below market pay — flight risk",
            ],
            "kpis": [
                {"name": "Top Performer %", "formula": "count(rating >= 4) / headcount * 100"},
                {"name": "Average Rating", "formula": "sum(ratings) / count(employees)"},
                {"name": "Rating Consistency Score", "formula": "1 - std(dept_avg_ratings) / mean(dept_avg_ratings)"},
            ],
        },
    },

    # ── Operations ────────────────────────────────────────────────────────────
    "operations": {
        "kpi_dashboard": {
            "name": "kpi_dashboard",
            "domain": "operations",
            "description": "Operations KPI dashboard with real-time status and trend alerts",
            "required_columns": ["kpi_name", "actual_value", "target_value", "period"],
            "optional_columns": ["department", "prior_value", "unit", "status"],
            "analysis_steps": [
                "Calculate KPI attainment rate for each metric",
                "Compare actual vs target and prior period",
                "Classify status: on-track, at-risk, off-track",
                "Compute composite operations score",
                "Identify cascading KPI failures",
            ],
            "default_charts": [
                {"type": "gauge", "title": "KPI Health Dashboard"},
                {"type": "bar", "x": "kpi_name", "y": "attainment_pct", "title": "KPI Attainment"},
            ],
            "report_sections": [
                "Operations Scorecard",
                "KPIs On Track",
                "KPIs Off Track",
                "Root Cause Analysis",
                "Action Items",
            ],
            "sample_insights": [
                "X of Y tracked KPIs are meeting or exceeding targets",
                "Throughput KPI trending 15% below target — capacity issue identified",
                "Quality score improved 3 points following process change",
            ],
            "kpis": [
                {"name": "Overall Attainment", "formula": "count(actual >= target) / total_kpis * 100"},
                {"name": "Avg Attainment %", "formula": "mean(actual / target * 100)"},
                {"name": "KPIs Off Track", "formula": "count(actual < target * 0.9)"},
            ],
        },
        "process_efficiency": {
            "name": "process_efficiency",
            "domain": "operations",
            "description": "Process efficiency analysis with cycle time, waste, and throughput metrics",
            "required_columns": ["process", "start_time", "end_time"],
            "optional_columns": ["status", "worker_id", "defects", "rework"],
            "analysis_steps": [
                "Calculate cycle time per process step",
                "Identify bottleneck operations",
                "Compute process efficiency = value-add time / total time",
                "Measure defect and rework rates",
                "Apply Little's Law for queue analysis",
                "Simulate improvement scenarios",
            ],
            "default_charts": [
                {"type": "bar", "x": "process_step", "y": "avg_cycle_time", "title": "Cycle Time by Step"},
                {"type": "control_chart", "title": "Process Control Chart"},
            ],
            "report_sections": [
                "Efficiency Overview",
                "Bottleneck Analysis",
                "Quality & Defects",
                "Improvement Opportunities",
            ],
            "sample_insights": [
                "Step X is the critical bottleneck — X% of total cycle time",
                "Rework rate of X% adds $Xk/month in hidden costs",
                "Eliminating defect loop reduces average cycle time by X%",
            ],
            "kpis": [
                {"name": "Process Efficiency %", "formula": "value_add_time / total_cycle_time * 100"},
                {"name": "Throughput Rate", "formula": "units_completed / time_period"},
                {"name": "Defect Rate", "formula": "defects / total_units * 100"},
            ],
        },
        "supply_chain": {
            "name": "supply_chain",
            "domain": "operations",
            "description": "Supply chain performance analysis including lead times and supplier scorecards",
            "required_columns": ["supplier", "order_date", "delivery_date", "order_value"],
            "optional_columns": ["product", "qty_ordered", "qty_received", "defect_qty", "on_time"],
            "analysis_steps": [
                "Calculate supplier on-time delivery rate",
                "Measure average lead time vs target",
                "Compute purchase price variance (PPV)",
                "Score suppliers on quality, delivery, cost",
                "Identify single-source risk",
                "Analyse demand vs supply gaps",
            ],
            "default_charts": [
                {"type": "radar", "title": "Supplier Scorecard Radar"},
                {"type": "scatter", "x": "lead_time", "y": "defect_rate", "title": "Lead Time vs Quality"},
            ],
            "report_sections": [
                "Supply Chain Overview",
                "Supplier Scorecards",
                "Lead Time Analysis",
                "Supply Risk Assessment",
                "Recommended Actions",
            ],
            "sample_insights": [
                "On-time delivery rate is X% vs target of 95%",
                "Supplier A accounts for X% of spend with single-source risk on critical parts",
                "Average lead time increased by X days — buffer stock review needed",
            ],
            "kpis": [
                {"name": "On-Time Delivery Rate", "formula": "on_time_deliveries / total_deliveries * 100"},
                {"name": "Average Lead Time", "formula": "mean(delivery_date - order_date)"},
                {"name": "Supplier Quality Rate", "formula": "(qty_received - defect_qty) / qty_received * 100"},
            ],
        },
        "quality_control": {
            "name": "quality_control",
            "domain": "operations",
            "description": "Quality control analysis with SPC charts and defect Pareto",
            "required_columns": ["product", "inspection_date", "defects", "units_inspected"],
            "optional_columns": ["defect_type", "line", "shift", "operator"],
            "analysis_steps": [
                "Calculate defect rate (DPU and DPMO)",
                "Build Pareto chart of defect types",
                "Apply statistical process control (3-sigma limits)",
                "Identify out-of-control signals",
                "Compute process capability (Cpk)",
                "Root cause analysis for top defect types",
            ],
            "default_charts": [
                {"type": "pareto", "title": "Defect Pareto Chart"},
                {"type": "control_chart", "title": "p-Chart — Defect Rate"},
                {"type": "bar", "x": "shift", "y": "defect_rate", "title": "Defect Rate by Shift"},
            ],
            "report_sections": [
                "Quality Overview",
                "Defect Pareto",
                "Process Control",
                "Root Cause Analysis",
                "Corrective Actions",
            ],
            "sample_insights": [
                "Top 3 defect types account for X% of all quality failures (Pareto)",
                "Night shift has X% higher defect rate — training opportunity",
                "Process Cpk of X indicates X% of output outside specification",
            ],
            "kpis": [
                {"name": "Defect Rate (DPU)", "formula": "total_defects / units_inspected"},
                {"name": "DPMO", "formula": "total_defects / (units_inspected * opportunities) * 1_000_000"},
                {"name": "First Pass Yield", "formula": "(units_inspected - defective_units) / units_inspected * 100"},
            ],
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def get_all_templates() -> list[dict]:
    """Return flat list of all templates (without full detail)."""
    result = []
    for domain, templates in DOMAIN_TEMPLATES.items():
        for tname, tdata in templates.items():
            result.append({
                "domain": domain,
                "name": tname,
                "description": tdata["description"],
                "required_columns": tdata["required_columns"],
            })
    return result


def get_templates_by_domain(domain: str) -> dict[str, Any] | None:
    return DOMAIN_TEMPLATES.get(domain)


def get_template(domain: str, template_name: str) -> dict[str, Any] | None:
    return DOMAIN_TEMPLATES.get(domain, {}).get(template_name)


def detect_domain(column_names: list[str]) -> tuple[str, str, float]:
    """
    Auto-detect the most likely domain and template from dataset column names.
    Returns (domain, template_name, confidence_score).
    """
    lower_cols = {c.lower() for c in column_names}

    scoring: dict[tuple[str, str], int] = {}
    for domain, templates in DOMAIN_TEMPLATES.items():
        for tname, tdata in templates.items():
            required = {c.lower() for c in tdata["required_columns"]}
            optional = {c.lower() for c in tdata.get("optional_columns", [])}
            # Fuzzy match: count partial overlaps
            req_hits = sum(
                1 for rc in required
                if any(rc in col or col in rc for col in lower_cols)
            )
            opt_hits = sum(
                1 for oc in optional
                if any(oc in col or col in oc for col in lower_cols)
            )
            score = req_hits * 2 + opt_hits
            if score > 0:
                scoring[(domain, tname)] = score

    if not scoring:
        return ("general", "general_analysis", 0.0)

    best = max(scoring, key=lambda k: scoring[k])
    best_score = scoring[best]
    max_possible = len(DOMAIN_TEMPLATES[best[0]][best[1]]["required_columns"]) * 2
    confidence = min(best_score / max(max_possible, 1), 1.0)
    return (best[0], best[1], round(confidence, 2))
