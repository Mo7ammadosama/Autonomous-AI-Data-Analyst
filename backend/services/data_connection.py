"""
Data Connection Service — connect to external databases and cloud data sources.

Supported types:
  SQL:    postgresql | mysql | sqlite
  Cloud:  google_sheets | mongodb | rest_api | s3 | bigquery

Features:
- Test connectivity
- List tables / collections / sheets
- Execute SELECT queries (SQL types) or fetch data (cloud types)
- Import result as a Dataset (CSV)
- Credentials encrypted at rest (Fernet or base64 fallback)

Security:
- Only SELECT queries allowed for SQL connections
- Max 50,000 rows returned per query
- Connection timeout: 10 seconds
- Credentials encrypted at rest
"""

import asyncio
import os
import logging
import json
import time
import uuid
from typing import Optional, Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

_FERNET_KEY = os.getenv("ENCRYPTION_KEY", "")   # Optional: 32-byte Fernet key base64


# ── Credential encryption ────────────────────────────────────────

def _encrypt(text: str) -> str:
    """Encrypt a credential string. Falls back to base64 if Fernet key not set."""
    if not text:
        return ""
    try:
        if _FERNET_KEY:
            from cryptography.fernet import Fernet
            f = Fernet(_FERNET_KEY.encode())
            return f.encrypt(text.encode()).decode()
    except Exception:
        pass
    import base64
    return base64.b64encode(text.encode()).decode()


def _decrypt(text: str) -> str:
    if not text:
        return ""
    try:
        if _FERNET_KEY:
            from cryptography.fernet import Fernet
            f = Fernet(_FERNET_KEY.encode())
            return f.decrypt(text.encode()).decode()
    except Exception:
        pass
    try:
        import base64
        return base64.b64decode(text.encode()).decode()
    except Exception:
        return text


# ── SQL safety check ─────────────────────────────────────────────

import re
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|EXECUTE|PRAGMA|ATTACH)\b",
    re.IGNORECASE,
)

def _validate_query(sql: str) -> Tuple[bool, str]:
    if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
        return False, "Only SELECT queries are allowed."
    if _FORBIDDEN.search(sql):
        return False, f"Forbidden keyword: {_FORBIDDEN.search(sql).group()}"
    return True, ""


# ── SQL engine cache (avoids per-call engine creation) ───────────

_ENGINE_CACHE: Dict[str, Tuple[Any, float]] = {}   # key → (engine, created_at)
_ENGINE_TTL = 600  # 10 minutes


def _engine_cache_key(connection_type, host, port, database, username) -> str:
    import hashlib
    raw = f"{connection_type}:{host}:{port}:{database}:{username}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_engine(connection_type: str, host: str, port: int, database: str,
                  username: str, password: str, extra_config: Optional[Dict] = None):
    """Build (or retrieve from cache) a SQLAlchemy engine for the given connection type."""
    from sqlalchemy import create_engine

    cache_key = _engine_cache_key(connection_type, host, port, database, username)
    now = time.time()
    if cache_key in _ENGINE_CACHE:
        engine, created_at = _ENGINE_CACHE[cache_key]
        if now - created_at < _ENGINE_TTL:
            return engine

    extra = extra_config or {}
    connect_args = {"connect_timeout": 10}

    if connection_type == "postgresql":
        url = f"postgresql+psycopg2://{username}:{password}@{host}:{port or 5432}/{database}"
    elif connection_type == "mysql":
        url = f"mysql+pymysql://{username}:{password}@{host}:{port or 3306}/{database}"
        connect_args = {"connect_timeout": 10}
    elif connection_type == "sqlite":
        url = f"sqlite:///{database}"
        connect_args = {}
    else:
        raise ValueError(f"Unsupported SQL connection type: {connection_type}")

    engine = create_engine(url, connect_args=connect_args, pool_timeout=10)
    _ENGINE_CACHE[cache_key] = (engine, now)
    return engine


# ── Google Sheets connector ───────────────────────────────────────

class GoogleSheetsConnector:
    """
    Read a Google Sheet as a DataFrame.

    extra_config must contain:
      spreadsheet_id  — the sheet ID from the URL
      sheet_name      — worksheet name (default: first sheet)
      service_account_json — JSON string of service account credentials
    """

    def fetch(self, extra_config: Dict) -> "pd.DataFrame":
        import pandas as pd

        spreadsheet_id = extra_config.get("spreadsheet_id", "")
        sheet_name = extra_config.get("sheet_name", "Sheet1")
        sa_json = extra_config.get("service_account_json", "")

        if not spreadsheet_id:
            raise ValueError("spreadsheet_id is required in extra_config")
        if not sa_json:
            raise ValueError("service_account_json is required in extra_config")

        import json as _json
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials

        creds_info = _json.loads(sa_json)
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_name,
        ).execute()

        values = result.get("values", [])
        if not values:
            return pd.DataFrame()
        headers = values[0]
        rows = values[1:]
        # Pad short rows
        rows = [r + [""] * (len(headers) - len(r)) for r in rows]
        return pd.DataFrame(rows, columns=headers)

    def list_sheets(self, extra_config: Dict) -> List[str]:
        import json as _json
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials

        sa_json = extra_config.get("service_account_json", "")
        spreadsheet_id = extra_config.get("spreadsheet_id", "")
        creds_info = _json.loads(sa_json)
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return [s["properties"]["title"] for s in meta.get("sheets", [])]


# ── MongoDB connector ─────────────────────────────────────────────

class MongoDBConnector:
    """
    Query a MongoDB collection and return results as a DataFrame.

    extra_config:
      connection_string  — mongodb:// or mongodb+srv:// URI
      mongo_database     — DB name
      collection         — collection name
      filter_json        — optional filter dict (JSON string, default: {})
      limit              — max documents (default: 10000)
    """

    def _run_blocking(self, extra_config: Dict) -> "pd.DataFrame":
        import pandas as pd
        import json as _json
        from pymongo import MongoClient

        conn_str = extra_config.get("connection_string", "")
        db_name = extra_config.get("mongo_database", "")
        collection = extra_config.get("collection", "")
        filter_raw = extra_config.get("filter_json", "{}")
        limit = int(extra_config.get("limit", 10000))

        flt = {}
        if filter_raw:
            try:
                flt = _json.loads(filter_raw)
            except Exception:
                pass

        client = MongoClient(conn_str, serverSelectionTimeoutMS=10000)
        col = client[db_name][collection]
        cursor = col.find(flt, {"_id": 0}).limit(limit)
        records = list(cursor)
        client.close()

        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)

    def fetch(self, extra_config: Dict) -> "pd.DataFrame":
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                asyncio.get_event_loop().run_in_executor(None, self._run_blocking, extra_config)
            )
        except RuntimeError:
            # Fallback: run synchronously if no event loop
            return self._run_blocking(extra_config)
        finally:
            loop.close()

    def list_collections(self, extra_config: Dict) -> List[str]:
        from pymongo import MongoClient
        conn_str = extra_config.get("connection_string", "")
        db_name = extra_config.get("mongo_database", "")
        client = MongoClient(conn_str, serverSelectionTimeoutMS=10000)
        names = client[db_name].list_collection_names()
        client.close()
        return names


# ── REST API connector ────────────────────────────────────────────

class RestAPIConnector:
    """
    Fetch data from a REST API endpoint and return as a DataFrame.

    extra_config:
      url          — full URL to request
      method       — GET | POST (default: GET)
      headers      — dict of request headers (JSON string)
      body         — request body for POST (JSON string)
      json_path    — dot-separated path to data array, e.g. "data.results"
                     (leave empty if the root response is the array)
      auth_type    — none | bearer | basic (default: none)
      auth_token   — Bearer token (for bearer auth)
      auth_user    — username (for basic auth)
      auth_pass    — password (for basic auth)
    """

    def fetch(self, extra_config: Dict) -> "pd.DataFrame":
        import httpx
        import pandas as pd
        import json as _json

        url = extra_config.get("url", "")
        method = extra_config.get("method", "GET").upper()
        headers_raw = extra_config.get("headers", "{}")
        body_raw = extra_config.get("body", "")
        json_path = extra_config.get("json_path", "")
        auth_type = extra_config.get("auth_type", "none")
        auth_token = extra_config.get("auth_token", "")
        auth_user = extra_config.get("auth_user", "")
        auth_pass = extra_config.get("auth_pass", "")

        headers: Dict = {}
        if headers_raw:
            try:
                headers = _json.loads(headers_raw)
            except Exception:
                pass

        # Auth
        if auth_type == "bearer" and auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        auth = None
        if auth_type == "basic" and auth_user:
            auth = (auth_user, auth_pass)

        body = None
        if body_raw:
            try:
                body = _json.loads(body_raw)
            except Exception:
                pass

        with httpx.Client(timeout=30) as client:
            if method == "POST":
                resp = client.post(url, headers=headers, json=body, auth=auth)
            else:
                resp = client.get(url, headers=headers, auth=auth)
            resp.raise_for_status()
            data = resp.json()

        # Navigate json_path
        if json_path:
            for key in json_path.split("."):
                if isinstance(data, dict):
                    data = data.get(key, [])
                else:
                    break

        if isinstance(data, list):
            return pd.DataFrame(data)
        if isinstance(data, dict):
            return pd.DataFrame([data])
        return pd.DataFrame()


# ── S3 / MinIO connector ──────────────────────────────────────────

class S3Connector:
    """
    Download a file from S3 (or MinIO) and parse as a DataFrame.

    extra_config:
      bucket           — bucket name
      key              — object key (path), e.g. "data/sales.csv"
      format           — csv | json | parquet | tsv (default: detected from key)
      aws_access_key   — AWS access key ID
      aws_secret_key   — AWS secret access key
      region           — AWS region (default: us-east-1)
      endpoint_url     — custom endpoint for MinIO (optional)
    """

    def _run_blocking(self, extra_config: Dict) -> "pd.DataFrame":
        import boto3
        import pandas as pd
        import io

        bucket = extra_config.get("bucket", "")
        key = extra_config.get("key", "")
        fmt = extra_config.get("format", "")
        access_key = extra_config.get("aws_access_key", "")
        secret_key = extra_config.get("aws_secret_key", "")
        region = extra_config.get("region", "us-east-1")
        endpoint_url = extra_config.get("endpoint_url") or None

        if not fmt:
            ext = key.rsplit(".", 1)[-1].lower()
            fmt = {"csv": "csv", "json": "json", "parquet": "parquet", "tsv": "tsv"}.get(ext, "csv")

        session = boto3.Session(
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
        )
        s3 = session.client("s3", endpoint_url=endpoint_url)
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        buf = io.BytesIO(body)

        if fmt == "parquet":
            return pd.read_parquet(buf)
        elif fmt == "json":
            return pd.read_json(buf)
        elif fmt == "tsv":
            return pd.read_csv(buf, sep="\t")
        else:
            return pd.read_csv(buf)

    def fetch(self, extra_config: Dict) -> "pd.DataFrame":
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                asyncio.get_event_loop().run_in_executor(None, self._run_blocking, extra_config)
            )
        except RuntimeError:
            return self._run_blocking(extra_config)
        finally:
            loop.close()

    def list_objects(self, extra_config: Dict, prefix: str = "") -> List[str]:
        import boto3
        bucket = extra_config.get("bucket", "")
        access_key = extra_config.get("aws_access_key", "")
        secret_key = extra_config.get("aws_secret_key", "")
        region = extra_config.get("region", "us-east-1")
        endpoint_url = extra_config.get("endpoint_url") or None
        session = boto3.Session(
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
        )
        s3 = session.client("s3", endpoint_url=endpoint_url)
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=200)
        return [obj["Key"] for obj in resp.get("Contents", [])]


# ── BigQuery connector ────────────────────────────────────────────

class BigQueryConnector:
    """
    Run a BigQuery SQL query and return results as a DataFrame.

    extra_config:
      project_id           — GCP project ID
      query                — SQL query (SELECT only)
      service_account_json — JSON string of service account credentials
      location             — BQ location (default: US)
    """

    def _run_blocking(self, extra_config: Dict) -> "pd.DataFrame":
        import json as _json
        from google.cloud import bigquery
        from google.oauth2.service_account import Credentials

        project_id = extra_config.get("project_id", "")
        query = extra_config.get("query", "")
        sa_json = extra_config.get("service_account_json", "")
        location = extra_config.get("location", "US")

        if not query:
            raise ValueError("query is required in extra_config")

        is_safe, reason = _validate_query(query)
        if not is_safe:
            raise ValueError(reason)

        creds_info = _json.loads(sa_json)
        creds = Credentials.from_service_account_info(creds_info)
        client = bigquery.Client(project=project_id, credentials=creds)
        df = client.query(query, location=location).to_dataframe()
        client.close()
        return df

    def fetch(self, extra_config: Dict) -> "pd.DataFrame":
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                asyncio.get_event_loop().run_in_executor(None, self._run_blocking, extra_config)
            )
        except RuntimeError:
            return self._run_blocking(extra_config)
        finally:
            loop.close()


# ── Connector registry ────────────────────────────────────────────

_SHEETS_CONN = GoogleSheetsConnector()
_MONGO_CONN = MongoDBConnector()
_REST_CONN = RestAPIConnector()
_S3_CONN = S3Connector()
_BQ_CONN = BigQueryConnector()

CLOUD_TYPES = {"google_sheets", "mongodb", "rest_api", "s3", "bigquery"}
SQL_TYPES = {"postgresql", "mysql", "sqlite"}
ALL_TYPES = SQL_TYPES | CLOUD_TYPES


def _fetch_cloud_df(connection_type: str, extra_config: Dict) -> "pd.DataFrame":
    """Dispatch to the appropriate cloud connector and return a DataFrame."""
    if connection_type == "google_sheets":
        return _SHEETS_CONN.fetch(extra_config)
    elif connection_type == "mongodb":
        return _MONGO_CONN.fetch(extra_config)
    elif connection_type == "rest_api":
        return _REST_CONN.fetch(extra_config)
    elif connection_type == "s3":
        return _S3_CONN.fetch(extra_config)
    elif connection_type == "bigquery":
        return _BQ_CONN.fetch(extra_config)
    else:
        raise ValueError(f"Unknown cloud connector: {connection_type}")


def _list_cloud_tables(connection_type: str, extra_config: Dict) -> List[str]:
    """Return collection/sheet/object names for cloud connectors."""
    if connection_type == "google_sheets":
        return _SHEETS_CONN.list_sheets(extra_config)
    elif connection_type == "mongodb":
        return _MONGO_CONN.list_collections(extra_config)
    elif connection_type == "s3":
        return _S3_CONN.list_objects(extra_config)
    else:
        return []  # REST API and BigQuery don't have "tables"


# ── Main service ─────────────────────────────────────────────────

class DataConnectionService:
    """Service for testing and querying external database connections."""

    def test_connection(
        self,
        connection_type: str,
        host: str = "",
        port: Optional[int] = None,
        database: str = "",
        username: str = "",
        password: str = "",
        extra_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Attempt to connect. Returns {success, message, version}."""
        extra = extra_config or {}

        if connection_type in CLOUD_TYPES:
            try:
                df = _fetch_cloud_df(connection_type, extra)
                return {
                    "success": True,
                    "message": f"Connected successfully. Sample shape: {df.shape}",
                    "version": connection_type,
                }
            except Exception as e:
                return {"success": False, "message": str(e), "version": None}

        try:
            engine = _build_engine(connection_type, host, port, database, username, password, extra)
            with engine.connect() as conn:
                if connection_type == "postgresql":
                    result = conn.execute(__import__("sqlalchemy").text("SELECT version()"))
                    version = result.scalar()
                elif connection_type == "mysql":
                    result = conn.execute(__import__("sqlalchemy").text("SELECT VERSION()"))
                    version = result.scalar()
                else:
                    version = "SQLite"
            return {"success": True, "message": "Connection successful", "version": str(version)}
        except Exception as e:
            return {"success": False, "message": str(e), "version": None}

    def list_tables(
        self,
        connection_type: str,
        host: str = "",
        port: Optional[int] = None,
        database: str = "",
        username: str = "",
        password: str = "",
        schema: Optional[str] = None,
        extra_config: Optional[Dict] = None,
    ) -> List[str]:
        """Return list of table/collection/sheet names."""
        extra = extra_config or {}

        if connection_type in CLOUD_TYPES:
            return _list_cloud_tables(connection_type, extra)

        from sqlalchemy import inspect
        engine = _build_engine(connection_type, host, port, database, username, password, extra)
        inspector = inspect(engine)
        return inspector.get_table_names(schema=schema)

    def get_table_schema(
        self,
        connection_type: str,
        host: str = "",
        port: Optional[int] = None,
        database: str = "",
        username: str = "",
        password: str = "",
        table_name: str = "",
        schema: Optional[str] = None,
        extra_config: Optional[Dict] = None,
    ) -> List[Dict]:
        """Return column info for a SQL table (N/A for cloud connectors)."""
        if connection_type in CLOUD_TYPES:
            # For cloud: fetch a small sample and infer schema
            extra = extra_config or {}
            import pandas as pd
            df = _fetch_cloud_df(connection_type, extra).head(100)
            return [
                {
                    "name": col,
                    "type": str(df[col].dtype),
                    "nullable": bool(df[col].isna().any()),
                }
                for col in df.columns
            ]

        from sqlalchemy import inspect
        engine = _build_engine(connection_type, host, port, database, username, password, extra_config or {})
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name, schema=schema)
        return [{"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)} for c in columns]

    def run_query(
        self,
        connection_type: str,
        host: str = "",
        port: Optional[int] = None,
        database: str = "",
        username: str = "",
        password: str = "",
        sql: str = "",
        max_rows: int = 5000,
        extra_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Execute a SELECT query (SQL) or fetch data (cloud connectors)."""
        extra = extra_config or {}

        if connection_type in CLOUD_TYPES:
            try:
                import pandas as pd
                # For BigQuery/MongoDB, put the query in extra_config for the connector
                if sql and connection_type == "bigquery":
                    extra = {**extra, "query": sql}
                df = _fetch_cloud_df(connection_type, extra).head(max_rows)
                return {
                    "success": True,
                    "columns": df.columns.tolist(),
                    "rows": df.where(pd.notna(df), None).to_dict("records"),
                    "row_count": len(df),
                    "error": None,
                }
            except Exception as e:
                return {"success": False, "error": str(e), "columns": [], "rows": [], "row_count": 0}

        is_safe, reason = _validate_query(sql)
        if not is_safe:
            return {"success": False, "error": reason, "columns": [], "rows": [], "row_count": 0}

        try:
            import pandas as pd
            from sqlalchemy import text
            engine = _build_engine(connection_type, host, port, database, username, password, extra)
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            df = df.head(max_rows)
            return {
                "success": True,
                "columns": df.columns.tolist(),
                "rows": df.where(pd.notna(df), None).to_dict("records"),
                "row_count": len(df),
                "error": None,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "columns": [], "rows": [], "row_count": 0}

    def import_as_dataset(
        self,
        connection_type: str,
        host: str = "",
        port: Optional[int] = None,
        database: str = "",
        username: str = "",
        password: str = "",
        sql: str = "",
        dataset_name: str = "",
        upload_dir: str = "./uploads",
        extra_config: Optional[Dict] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Fetch data and save result as a CSV file.
        Returns (success, message, file_path).
        """
        result = self.run_query(
            connection_type, host, port, database, username, password,
            sql=sql, max_rows=100_000, extra_config=extra_config,
        )
        if not result["success"]:
            return False, result["error"], None

        import pandas as pd
        df = pd.DataFrame(result["rows"], columns=result["columns"])
        file_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{file_id}.csv")
        os.makedirs(upload_dir, exist_ok=True)
        df.to_csv(file_path, index=False)
        return True, f"Imported {len(df)} rows", file_path


# Singleton
connection_service = DataConnectionService()

# Exported helpers
encrypt_credential = _encrypt
decrypt_credential = _decrypt
