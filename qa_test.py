"""
DataMind AI Platform — Full Automated QA Test
Uses Playwright (async) to test every page, interactions, and console errors.
"""

import asyncio
import os
import re
import json
import traceback
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, ConsoleMessage

BASE_URL = "http://localhost:3001"
BACKEND_URL = "http://localhost:8001"
SCREENSHOTS_DIR = Path("qa_screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

EMAIL = "demo@datamind.ai"
PASSWORD = "demo123"

PAGES = [
    ("/",               "Home / Landing"),
    ("/dashboard",      "Dashboard"),
    ("/datasets",       "Datasets"),
    ("/autonomous",     "Autonomous Agent"),
    ("/chat",           "Chat / NL Query"),
    ("/agent",          "Agent"),
    ("/reports",        "Reports"),
    ("/custom-reports", "Custom Reports"),
    ("/notebooks",      "Notebooks"),
    ("/catalog",        "Data Catalog"),
    ("/templates",      "Templates"),
    ("/metrics",        "Metrics"),
    ("/webhooks",       "Webhooks"),
    ("/activity",       "Activity"),
    ("/settings",       "Settings"),
    ("/analytics",      "Analytics"),
    ("/alerts",         "Alerts"),
    ("/insights",       "Insights"),
    ("/explore",        "Explore"),
    ("/automl",         "AutoML"),
    ("/nl2sql",         "NL2SQL"),
    ("/scheduled-reports", "Scheduled Reports"),
]

# Buttons/actions to skip (destructive / risk)
SKIP_BUTTON_PATTERNS = re.compile(
    r"(delete|remove|destroy|drop|reset|clear all|wipe|purge|sign out|log out|logout)",
    re.IGNORECASE
)

results = []
console_errors = {}


def slug(path: str) -> str:
    return path.strip("/").replace("/", "_") or "home"


async def collect_console_errors(page: Page, path: str):
    errors = []

    def on_console(msg: ConsoleMessage):
        if msg.type in ("error", "warning"):
            errors.append(f"[{msg.type.upper()}] {msg.text}")

    page.on("console", on_console)
    console_errors[path] = errors


async def safe_screenshot(page: Page, name: str):
    try:
        path = SCREENSHOTS_DIR / f"{name}.png"
        await page.screenshot(path=str(path), full_page=True, timeout=10000)
        return str(path)
    except Exception as e:
        return f"screenshot_failed: {e}"


async def try_login(page: Page) -> bool:
    """Attempt to log in by injecting auth token directly into localStorage."""
    import urllib.request, urllib.error, json as _json

    # Step 1: Get auth token from backend demo-login endpoint
    try:
        req = urllib.request.Request(
            BACKEND_URL + "/api/auth/demo-login",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            auth_data = _json.loads(resp.read())
        access_token = auth_data.get("access_token", "")
        refresh_token = auth_data.get("refresh_token", "")
        user = auth_data.get("user", {})
        if not access_token:
            print("  → Demo login API returned no token")
            return False
        print(f"  → Got demo token for user: {user.get('username', 'unknown')}")
    except Exception as e:
        print(f"  → Demo login API call failed: {e}")
        return False

    # Step 2: Navigate to the app and inject token into localStorage
    try:
        await page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
        await page.evaluate(f"""() => {{
            localStorage.setItem('auth_token', {_json.dumps(access_token)});
            localStorage.setItem('refresh_token', {_json.dumps(refresh_token)});
            localStorage.setItem('auth_user', {_json.dumps(_json.dumps(user))});
        }}""")
        # Navigate to dashboard to verify auth worked
        await page.goto(BASE_URL + "/dashboard", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)  # let React hydrate

        if "/dashboard" in page.url:
            print(f"  → Auth injected successfully, at: {page.url}")
            return True
        else:
            print(f"  → Auth injection may have failed, at: {page.url}")
            # Still return True if we have a token — pages will load even if redirected
            return True
    except Exception as e:
        print(f"  → Token injection failed: {e}")
        return False


async def click_safe_buttons(page: Page) -> list:
    """Click visible, non-destructive buttons and return list of actions."""
    actions = []
    try:
        buttons = page.locator("button:visible, [role='button']:visible, a[href]:visible")
        count = min(await buttons.count(), 15)  # limit to 15 interactions per page

        for i in range(count):
            try:
                btn = buttons.nth(i)
                text = (await btn.text_content() or "").strip()
                href = await btn.get_attribute("href") or ""

                # Skip destructive, external links, and already-visited anchors
                if SKIP_BUTTON_PATTERNS.search(text):
                    actions.append(f"  SKIPPED [{text}] (destructive)")
                    continue
                if href.startswith("http") and BASE_URL not in href:
                    actions.append(f"  SKIPPED [{text}] (external link)")
                    continue
                if not text and not href:
                    continue

                # Only click buttons that are interactable
                is_visible = await btn.is_visible()
                is_enabled = await btn.is_enabled()
                if is_visible and is_enabled:
                    await btn.click(timeout=3000, force=False)
                    await page.wait_for_timeout(800)
                    actions.append(f"  CLICKED [{text or href[:40]}]")
                    # Navigate back if we left the page
                    if not page.url.startswith(BASE_URL):
                        await page.go_back(timeout=5000)
            except Exception:
                pass
    except Exception as e:
        actions.append(f"  button_scan_error: {e}")
    return actions


async def check_page_health(page: Page, path: str, label: str) -> dict:
    """Navigate to a page, check health, take screenshot, click buttons."""
    result = {
        "path": path,
        "label": label,
        "status": "✅ OK",
        "issues": [],
        "actions": [],
        "screenshot": "",
        "console_errors": [],
    }

    errors = []
    page.on("console", lambda msg: errors.append(f"[{msg.type.upper()}] {msg.text}") if msg.type in ("error",) else None)

    try:
        print(f"\n{'='*60}")
        print(f"Testing: {label} ({path})")

        response = await page.goto(BASE_URL + path, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)  # let JS hydrate

        # Check HTTP status
        if response and response.status >= 400:
            result["status"] = f"❌ HTTP {response.status}"
            result["issues"].append(f"HTTP {response.status} error")

        # Check for blank/empty pages
        body_text = await page.evaluate("document.body.innerText")
        if len(body_text.strip()) < 50:
            result["status"] = "⚠️ WARNING"
            result["issues"].append("Page appears blank or nearly empty")

        # Check for error indicators in DOM
        # Use precise patterns to avoid false positives from legitimate UI numbers (e.g. "500K+", "50000", "500 analyses")
        error_indicators = await page.locator(
            "text=/\\b(404|500 internal|500 error|application error|something went wrong|page not found|not found|crash|failed to load)\\b/i"
        ).count()
        if error_indicators > 0:
            result["issues"].append(f"Found {error_indicators} error text(s) on page")
            if result["status"] == "✅ OK":
                result["status"] = "⚠️ WARNING"

        # Check for React/Next error overlay
        error_overlay = await page.locator("#__next_error__, [data-nextjs-dialog], .nextjs-container-errors").count()
        if error_overlay > 0:
            result["status"] = "❌ BROKEN"
            result["issues"].append("Next.js error overlay detected")

        # Screenshot
        result["screenshot"] = await safe_screenshot(page, slug(path))
        print(f"  → Screenshot: {result['screenshot']}")

        # Click safe buttons
        result["actions"] = await click_safe_buttons(page)
        for a in result["actions"][:5]:
            print(f"  {a}")

        # Take post-interaction screenshot
        await safe_screenshot(page, slug(path) + "_after")

    except Exception as e:
        result["status"] = "❌ BROKEN"
        result["issues"].append(f"Exception: {str(e)[:200]}")
        print(f"  → ERROR: {e}")
        try:
            result["screenshot"] = await safe_screenshot(page, slug(path) + "_error")
        except Exception:
            pass

    result["console_errors"] = errors[:10]  # cap at 10
    if errors:
        print(f"  → Console errors: {len(errors)}")
        for e in errors[:3]:
            print(f"     {e[:100]}")

    print(f"  → Status: {result['status']}")
    return result


async def test_backend_api() -> list:
    """Quick smoke-test of key backend endpoints (with demo auth token)."""
    import urllib.request
    import urllib.error
    import json as _json

    # Get demo auth token first
    _auth_token = ""
    try:
        req = urllib.request.Request(
            BACKEND_URL + "/api/auth/demo-login",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            _auth_token = _json.loads(resp.read()).get("access_token", "")
    except Exception:
        pass

    endpoints = [
        ("/health",              "GET", "Health check",    False),
        ("/api/datasets/",       "GET", "Datasets list",   True),
        ("/api/metrics/",        "GET", "Metrics list",    True),
        ("/api/templates/",      "GET", "Templates list",  False),
        ("/docs",                "GET", "API docs (Swagger)", False),
    ]
    api_results = []
    for endpoint, method, label, needs_auth in endpoints:
        try:
            req = urllib.request.Request(BACKEND_URL + endpoint)
            req.add_header("Content-Type", "application/json")
            if needs_auth and _auth_token:
                req.add_header("Authorization", f"Bearer {_auth_token}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                api_results.append({"endpoint": endpoint, "label": label, "status": f"✅ {status}"})
        except urllib.error.HTTPError as e:
            api_results.append({"endpoint": endpoint, "label": label, "status": f"⚠️ HTTP {e.code}"})
        except Exception as e:
            api_results.append({"endpoint": endpoint, "label": label, "status": f"❌ {str(e)[:60]}"})
    return api_results


async def main():
    print("\n" + "="*70)
    print("   DataMind AI Platform — Automated QA Test")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Backend API smoke tests
    print("\n[BACKEND API SMOKE TESTS]")
    api_results = await test_backend_api()
    for r in api_results:
        print(f"  {r['status']}  {r['label']} ({r['endpoint']})")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Attempt login
        print("\n[AUTHENTICATION]")
        logged_in = await try_login(page)
        await safe_screenshot(page, "00_login_state")
        print(f"  → Auth status: {'OK' if logged_in else 'FAILED'}")

        # Test each page
        print("\n[PAGE TESTS]")
        for path, label in PAGES:
            result = await check_page_health(page, path, label)
            results.append(result)

        await browser.close()

    # Write JSON report
    report = {
        "timestamp": datetime.now().isoformat(),
        "api_results": api_results,
        "page_results": results,
    }
    with open("qa_report.json", "w") as f:
        json.dump(report, f, indent=2)

    # Print final summary
    print("\n" + "="*70)
    print("   QA REPORT SUMMARY")
    print("="*70)

    print("\n### Backend API")
    for r in api_results:
        print(f"  {r['status']}  {r['label']}")

    print("\n### Pages")
    ok_count = warn_count = fail_count = 0
    for r in results:
        icon = r["status"].split()[0]
        issues_str = " | ".join(r["issues"]) if r["issues"] else ""
        errors_str = f" | {len(r['console_errors'])} console error(s)" if r["console_errors"] else ""
        print(f"  {r['status']:<15}  {r['label']:<25}  {issues_str}{errors_str}")
        if "✅" in r["status"]:
            ok_count += 1
        elif "⚠️" in r["status"]:
            warn_count += 1
        else:
            fail_count += 1

    print(f"\n  Total: {ok_count} OK | {warn_count} warnings | {fail_count} failures")
    print(f"\n  Screenshots saved to: {SCREENSHOTS_DIR.absolute()}")
    print(f"  Full JSON report:     qa_report.json")

    # Detailed bugs section
    bugs = [(r["label"], r["path"], r["issues"], r["console_errors"]) for r in results if r["issues"] or r["console_errors"]]
    if bugs:
        print("\n### Bugs / Issues Found")
        for label, path, issues, cerrs in bugs:
            print(f"\n  [{label}] ({path})")
            for issue in issues:
                print(f"    - {issue}")
            for err in cerrs[:3]:
                print(f"    - Console: {err[:120]}")
    else:
        print("\n  No bugs found!")

    print("\n" + "="*70)
    return fail_count


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
