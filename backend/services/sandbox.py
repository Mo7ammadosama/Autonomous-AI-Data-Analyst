"""
Secure Python sandbox — executes user/agent code in a subprocess with
hard timeout, stdout/stderr capture, and dangerous-call blocking.
"""

from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Optional


# Calls that are never allowed in sandboxed code
_BLOCKED_PATTERNS = [
    "os.system",
    "os.popen",
    "subprocess",
    "socket.",
    "urllib.request",
    "urllib.urlopen",
    "requests.",
    "httpx.",
    "aiohttp.",
    "builtins.open",
    "__import__",
    "importlib",
    "shutil",
]


@dataclass
class SandboxResult:
    output: str = ""
    error: str = ""
    figures: list[str] = field(default_factory=list)   # base64-encoded PNGs
    dataframe_html: str = ""
    timed_out: bool = False
    blocked: bool = False
    block_reason: str = ""


class PythonSandbox:
    """
    Execute Python code in an isolated subprocess.

    - Pre-injects `df` (pandas DataFrame) when dataset bytes are provided.
    - Captures matplotlib/plotly figures as base64 PNGs.
    - Blocks dangerous built-ins before execution.
    - Hard-kills the subprocess after `timeout` seconds.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def execute(
        self,
        code: str,
        df_csv: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        t = timeout or self.timeout

        # 1. Static safety check
        blocked, reason = self._check_blocked(code)
        if blocked:
            return SandboxResult(blocked=True, block_reason=reason)

        # 2. Write user code to a separate temp file
        user_code_file = None
        df_csv_file = None
        wrapper_file = None

        try:
            # Write user code to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix="_user.py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                user_code_file = f.name

            # Write df CSV to temp file if provided
            if df_csv:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix="_df.csv", delete=False, encoding="utf-8"
                ) as f:
                    f.write(df_csv)
                    df_csv_file = f.name

            # Build and write wrapper
            wrapper = self._build_wrapper(user_code_file, df_csv_file)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix="_wrapper.py", delete=False, encoding="utf-8"
            ) as f:
                f.write(wrapper)
                wrapper_file = f.name

            # 3. Execute
            proc = subprocess.run(
                [sys.executable, wrapper_file],
                capture_output=True,
                text=True,
                timeout=t,
                env={**os.environ, "MPLBACKEND": "Agg"},
            )
            raw_stdout = proc.stdout or ""
            raw_stderr = proc.stderr or ""

        except subprocess.TimeoutExpired:
            return SandboxResult(timed_out=True, error=f"Execution timed out after {t}s")
        except Exception as exc:
            return SandboxResult(error=str(exc))
        finally:
            for path in [user_code_file, df_csv_file, wrapper_file]:
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

        return self._parse_output(raw_stdout, raw_stderr)

    @staticmethod
    def _check_blocked(code: str) -> tuple[bool, str]:
        lower = code.lower()
        for pat in _BLOCKED_PATTERNS:
            if pat.lower() in lower:
                return True, f"Blocked pattern detected: '{pat}'"
        return False, ""

    @staticmethod
    def _build_wrapper(user_code_path: str, df_csv_path: Optional[str]) -> str:
        """
        Build wrapper script that:
        1. Pre-loads df from CSV if provided
        2. Captures matplotlib figures
        3. Captures stdout
        4. exec()s user code
        5. Outputs structured JSON result
        """
        # Use repr() to safely embed file paths in the script
        user_path_repr = repr(user_code_path)
        df_path_repr = repr(df_csv_path) if df_csv_path else "None"

        script = f"""
import sys
import io
import json
import base64
import traceback

# ── DataFrame pre-load ────────────────────────────────────────────────────
df = None
_df_csv_path = {df_path_repr}
if _df_csv_path is not None:
    try:
        import pandas as _pd
        df = _pd.read_csv(_df_csv_path)
    except Exception as _e:
        pass

# ── Figure capture ────────────────────────────────────────────────────────
_figures = []
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    _orig_show = _plt.show
    def _capture_show(*a, **kw):
        _buf = io.BytesIO()
        _plt.savefig(_buf, format='png', bbox_inches='tight', dpi=100)
        _buf.seek(0)
        _figures.append(base64.b64encode(_buf.read()).decode())
        _plt.close('all')
    _plt.show = _capture_show
    _has_mpl = True
except ImportError:
    _has_mpl = False

# ── Stdout capture ────────────────────────────────────────────────────────
_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = _stdout_buf

_error_text = ""
_df_html = ""

# ── Execute user code ─────────────────────────────────────────────────────
_user_globals = {{'df': df, '__builtins__': __builtins__}}
try:
    _user_code_path = {user_path_repr}
    with open(_user_code_path, 'r', encoding='utf-8') as _f:
        _user_code = _f.read()
    exec(compile(_user_code, _user_code_path, 'exec'), _user_globals)
    # Try to capture a 'result' or updated 'df' as HTML
    try:
        import pandas as _pd2
        for _vname in ('result', 'df'):
            _obj = _user_globals.get(_vname)
            if isinstance(_obj, _pd2.DataFrame):
                _df_html = _obj.head(50).to_html(index=False)
                break
    except Exception:
        pass
except Exception:
    _error_text = traceback.format_exc()
finally:
    sys.stdout = _orig_stdout

# ── Capture unsaved matplotlib figures ───────────────────────────────────
if _has_mpl:
    try:
        if _plt.get_fignums():
            _buf2 = io.BytesIO()
            _plt.savefig(_buf2, format='png', bbox_inches='tight', dpi=100)
            _buf2.seek(0)
            _figures.append(base64.b64encode(_buf2.read()).decode())
            _plt.close('all')
    except Exception:
        pass

# ── Emit structured result ────────────────────────────────────────────────
_result = {{
    "output": _stdout_buf.getvalue(),
    "error": _error_text,
    "figures": _figures,
    "dataframe_html": _df_html,
}}
print("__SANDBOX_RESULT__:" + json.dumps(_result), file=_orig_stdout)
"""
        return script

    @staticmethod
    def _parse_output(raw_stdout: str, raw_stderr: str) -> SandboxResult:
        marker = "__SANDBOX_RESULT__:"
        for line in raw_stdout.splitlines():
            if line.startswith(marker):
                try:
                    payload = json.loads(line[len(marker):])
                    return SandboxResult(
                        output=payload.get("output", ""),
                        error=payload.get("error", "") or raw_stderr,
                        figures=payload.get("figures", []),
                        dataframe_html=payload.get("dataframe_html", ""),
                    )
                except json.JSONDecodeError:
                    pass
        return SandboxResult(output=raw_stdout, error=raw_stderr)
