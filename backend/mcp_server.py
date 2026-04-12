"""
DataMind MCP Server — Model Context Protocol exposure.

Exposes DataMind as an MCP server so Claude Desktop, Cursor, Continue.dev,
and any AI agent can query dashboards, run analyses, and retrieve insights
as first-class tools — Apache Superset / Sigma Computing style.

Usage:
  python mcp_server.py

Add to Claude Desktop config:
  {
    "mcpServers": {
      "datamind": {
        "command": "python",
        "args": ["path/to/mcp_server.py"],
        "env": {"DATAMIND_API_URL": "http://localhost:8001", "DATAMIND_API_KEY": "your-key"}
      }
    }
  }
"""

import asyncio
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

DATAMIND_API_URL = os.getenv("DATAMIND_API_URL", "http://localhost:8001")
DATAMIND_API_KEY = os.getenv("DATAMIND_API_KEY", "")


# ═══════════════════════════════════════════════════════════════
#  HTTP Client
# ═══════════════════════════════════════════════════════════════

async def _api_get(path: str, params: dict = None) -> dict:
    import httpx
    headers = {}
    if DATAMIND_API_KEY:
        headers["X-API-Key"] = DATAMIND_API_KEY
    async with httpx.AsyncClient(base_url=DATAMIND_API_URL, timeout=30) as client:
        resp = await client.get(path, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, body: dict) -> dict:
    import httpx
    headers = {"Content-Type": "application/json"}
    if DATAMIND_API_KEY:
        headers["X-API-Key"] = DATAMIND_API_KEY
    async with httpx.AsyncClient(base_url=DATAMIND_API_URL, timeout=60) as client:
        resp = await client.post(path, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()


# ═══════════════════════════════════════════════════════════════
#  Tool Implementations
# ═══════════════════════════════════════════════════════════════

async def tool_list_datasets(arguments: dict) -> str:
    """List all available datasets in DataMind."""
    data = await _api_get("/api/datasets")
    datasets = data if isinstance(data, list) else data.get("datasets", [])
    if not datasets:
        return "No datasets found."
    lines = [f"Found {len(datasets)} dataset(s):\n"]
    for ds in datasets[:20]:
        lines.append(
            f"- **{ds.get('name')}** (ID: {ds.get('id')})\n"
            f"  Rows: {ds.get('row_count', '?')}, Columns: {ds.get('column_count', '?')}, "
            f"Status: {ds.get('status', '?')}"
        )
    return "\n".join(lines)


async def tool_query_dataset(arguments: dict) -> str:
    """Run a natural language query against a dataset using NL2SQL."""
    dataset_id = arguments.get("dataset_id")
    question = arguments.get("question")
    if not dataset_id or not question:
        return "Error: dataset_id and question are required."
    try:
        result = await _api_post(f"/api/nl2sql/{dataset_id}/query", {"question": question})
        sql = result.get("sql", "")
        error = result.get("error")
        if error:
            return f"Query failed: {error}"
        data = result.get("data", [])
        reasoning = result.get("reasoning", "")
        confidence = result.get("thinking_trace", {}).get("confidence", 0)
        rows_preview = json.dumps(data[:5], indent=2) if data else "No data returned."
        return (
            f"**Question:** {question}\n\n"
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            f"**Confidence:** {confidence:.0%}\n"
            f"**Reasoning:** {reasoning}\n\n"
            f"**Results ({len(data)} rows, showing first 5):**\n```json\n{rows_preview}\n```"
        )
    except Exception as e:
        return f"Error querying dataset: {e}"


async def tool_get_insights(arguments: dict) -> str:
    """Get auto-generated insights for a dataset."""
    dataset_id = arguments.get("dataset_id")
    if not dataset_id:
        return "Error: dataset_id is required."
    try:
        result = await _api_get(f"/api/analytics/{dataset_id}/overview")
        insights = result.get("insights", [])
        if not insights:
            return f"No insights available for dataset {dataset_id} yet."
        lines = [f"**Insights for dataset {dataset_id}:**\n"]
        for ins in insights[:10]:
            lines.append(f"- {ins.get('title', 'Insight')}: {ins.get('content', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching insights: {e}"


async def tool_get_metric(arguments: dict) -> str:
    """Get the value of a governed business metric from the semantic catalog."""
    metric_name = arguments.get("metric_name")
    if not metric_name:
        return "Error: metric_name is required."
    try:
        results = await _api_get("/api/metrics/search", {"q": metric_name})
        if not results:
            return f"No metric named '{metric_name}' found in the semantic catalog."
        metric = results[0]
        return (
            f"**Metric: {metric.get('name')}**\n"
            f"Description: {metric.get('description', 'N/A')}\n"
            f"SQL Expression: `{metric.get('sql_expression', 'N/A')}`\n"
            f"Unit: {metric.get('unit', 'N/A')}\n"
            f"Direction: {metric.get('direction', 'N/A')}\n"
            f"Certified: {'✅ Yes' if metric.get('is_certified') else '❌ No'}"
        )
    except Exception as e:
        return f"Error fetching metric: {e}"


async def tool_search_catalog(arguments: dict) -> str:
    """Search the data catalog for datasets, metrics, and columns."""
    query = arguments.get("query")
    if not query:
        return "Error: query is required."
    try:
        results = await _api_get("/api/catalog/search", {"q": query})
        if not results:
            return f"No catalog entries found for '{query}'."
        lines = [f"**Catalog search results for '{query}':**\n"]
        for entry in results[:10]:
            lines.append(
                f"- **{entry.get('name')}** [{entry.get('resource_type')}] "
                f"{'✅' if entry.get('is_certified') else ''}"
                f"\n  {entry.get('description', '')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching catalog: {e}"


async def tool_run_forecast(arguments: dict) -> str:
    """Run a time-series forecast on a dataset column."""
    dataset_id = arguments.get("dataset_id")
    target_column = arguments.get("target_column")
    periods = arguments.get("periods", 30)
    if not dataset_id or not target_column:
        return "Error: dataset_id and target_column are required."
    try:
        # Auto-detect date column
        auto = await _api_get(f"/api/forecasting/{dataset_id}/auto")
        date_column = auto.get("date_column")
        if not date_column:
            return "Could not auto-detect a date column in the dataset."
        result = await _api_post(f"/api/forecasting/{dataset_id}/forecast", {
            "date_column": date_column,
            "target_column": target_column,
            "periods": periods,
        })
        method = result.get("method", "auto")
        metrics = result.get("metrics", {})
        forecast_data = result.get("forecast_data", [])
        last_pred = forecast_data[-1] if forecast_data else {}
        return (
            f"**Forecast for {target_column} ({periods} periods)**\n"
            f"Method: {method}\n"
            f"MAE: {metrics.get('mae', 'N/A')}\n"
            f"Last predicted value: {last_pred.get('forecast', 'N/A')}\n"
            f"Confidence interval: {last_pred.get('lower', 'N/A')} – {last_pred.get('upper', 'N/A')}\n\n"
            "Use DataMind's /forecasting page to view the full chart."
        )
    except Exception as e:
        return f"Error running forecast: {e}"


async def tool_get_proactive_feed(arguments: dict) -> str:
    """Get the latest proactive intelligence insights."""
    try:
        result = await _api_get("/api/proactive/feed", {"limit": 10})
        if not result:
            return "No proactive insights available yet. Run a scan first."
        lines = ["**Latest Intelligence Insights:**\n"]
        for ins in result[:10]:
            lines.append(
                f"- [{ins.get('severity', 'info').upper()}] **{ins.get('metric_name', 'Metric')}**: "
                f"{ins.get('narrative', '')[:150]}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching proactive feed: {e}"


# ═══════════════════════════════════════════════════════════════
#  MCP Protocol Implementation (stdio)
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "list_datasets",
        "description": "List all available datasets in the DataMind platform with their metadata.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_dataset",
        "description": "Run a natural language question against a dataset. Returns SQL, results, and confidence score.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The dataset ID to query"},
                "question": {"type": "string", "description": "Natural language question about the data"},
            },
            "required": ["dataset_id", "question"],
        },
    },
    {
        "name": "get_insights",
        "description": "Get auto-generated AI insights for a dataset.",
        "inputSchema": {
            "type": "object",
            "properties": {"dataset_id": {"type": "string"}},
            "required": ["dataset_id"],
        },
    },
    {
        "name": "get_metric",
        "description": "Look up a governed business metric definition from the semantic catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {"metric_name": {"type": "string", "description": "Name of the business metric (e.g. 'Revenue', 'Churn Rate')"}},
            "required": ["metric_name"],
        },
    },
    {
        "name": "search_catalog",
        "description": "Search the DataMind data catalog for datasets, metrics, and columns.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "run_forecast",
        "description": "Run a time-series forecast on a dataset column and return predictions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "target_column": {"type": "string", "description": "Column to forecast"},
                "periods": {"type": "integer", "description": "Number of periods to forecast", "default": 30},
            },
            "required": ["dataset_id", "target_column"],
        },
    },
    {
        "name": "get_proactive_feed",
        "description": "Get the latest proactively-detected intelligence insights (anomalies, trends, records).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_HANDLERS = {
    "list_datasets": tool_list_datasets,
    "query_dataset": tool_query_dataset,
    "get_insights": tool_get_insights,
    "get_metric": tool_get_metric,
    "search_catalog": tool_search_catalog,
    "run_forecast": tool_run_forecast,
    "get_proactive_feed": tool_get_proactive_feed,
}


async def handle_request(request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "DataMind", "version": "9.0.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
            }
        try:
            result_text = await handler(arguments)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": result_text}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True},
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}


async def main():
    """Run the MCP server over stdio."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    logger.info("DataMind MCP Server starting...")

    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = await handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            error_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            print(json.dumps(error_resp), flush=True)
        except Exception as e:
            error_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            print(json.dumps(error_resp), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
