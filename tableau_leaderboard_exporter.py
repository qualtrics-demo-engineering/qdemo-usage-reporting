#!/usr/bin/env python3
"""
tableau_leaderboard_exporter.py
--------------------------------
Automates the Tableau Leaderboard report export for the Qualtrics site.

Flow:
  1. Log in to Tableau Cloud (email → SSO)
  2. Navigate directly to the Leaderboard view
  3. Set the custom date range
  4. Export Data → select LeaderboardT sheet → CSV → Download

Usage:
  python3 tableau_leaderboard_exporter.py --start 01/01/2026 --end 05/07/2026

Dates default to interactive prompts if --start / --end are omitted.
Accepted formats: MM/DD/YYYY, M/D/YYYY, YYYY-MM-DD.
"""

import argparse
import os
import shutil
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

LOGIN_URL = "https://us-east-1.online.tableau.com/"
REPORT_URL = "https://us-east-1.online.tableau.com/#/site/qualtrics/views/Leaderboard/Leaderboard"
OUTPUT_SUBDIR = "tableau-leaderboard-records"

# ── Helpers ────────────────────────────────────────────────────────────────────

def prompt_date(label: str) -> str:
    """Prompt for a date, accept M/D/YYYY or MM/DD/YYYY, return MM/DD/YYYY."""
    while True:
        raw = input(f"  {label}: ").strip()
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%m/%d/%Y")
            except ValueError:
                continue
        print("    ⚠  Unrecognized format. Try MM/DD/YYYY — e.g. 01/01/2026")


def banner(msg: str):
    print(f"\n{'─' * 55}\n  {msg}\n{'─' * 55}")


def set_date_field(frame_or_page, label: str, date_str: str):
    """Clear a Tableau date input and type a new value."""
    # date_str is MM/DD/YYYY — Tableau date fields expect the same format
    inp = frame_or_page.get_by_label(label, exact=False).first
    inp.click(click_count=3, timeout=8_000)
    inp.press("Control+a")
    inp.press("Delete")
    inp.type(date_str, delay=80)
    inp.press("Tab")
    frame_or_page.wait_for_timeout(600)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tableau — Leaderboard Report Exporter")
    parser.add_argument("--username", help="Tableau username (email)")
    parser.add_argument("--start",    help="Start date (MM/DD/YYYY)")
    parser.add_argument("--end",      help="End date (MM/DD/YYYY)")
    args = parser.parse_args()

    banner("Tableau — Leaderboard Report Exporter")

    username   = args.username or os.environ.get("TABLEAU_USERNAME") or "alewis@qualtrics.com"
    start_date = args.start or prompt_date("Start date (MM/DD/YYYY)")
    end_date   = args.end   or prompt_date("End date   (MM/DD/YYYY)")

    download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(download_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(accept_downloads=True)
        page    = context.new_page()

        # ── 1. Login ───────────────────────────────────────────────────────────
        print("[1/4] Logging in…")
        page.goto(LOGIN_URL, wait_until="networkidle")

        # Fill username and submit — SSO handles the rest
        page.locator('input[name="username"], input[type="email"], input[placeholder*="sername"]').first.fill(username)
        page.locator('button:has-text("Sign In"), input[value="Sign In"]').first.click()

        # Wait for SSO redirect away from the login page (up to 90s for MFA)
        try:
            page.wait_for_url(
                lambda url: "sso.online.tableau.com" not in url and "/login" not in url,
                timeout=90_000,
            )
        except PlaywrightTimeoutError:
            print("\n⚠  Timed out waiting for SSO. Complete login manually if needed.")
            input("   Press Enter once you are fully logged in to continue…")

        page.wait_for_load_state("load")
        print("    ✓ Logged in")

        # ── 2. Navigate to the Leaderboard view ───────────────────────────────
        print("[2/4] Navigating to Leaderboard…")
        page.goto(REPORT_URL, wait_until="load")

        # Wait for the viz to fully render — Tableau dashboards can take 15-30s.
        # We watch for a visible input (the date filters) as our ready signal.
        print("    Waiting for viz to render (up to 60s)…")
        try:
            page.locator('input').first.wait_for(state="visible", timeout=60_000)
        except PlaywrightTimeoutError:
            print("    ⚠  Inputs not visible after 60s — viz may still be loading.")
            print("    Frames at this point:")
            for frame in page.frames:
                try:
                    n = frame.locator('input').count()
                    print(f"      {frame.url[:80]!r}  inputs={n}")
                except Exception as e:
                    print(f"      {frame.url[:80]!r}  error={e}")

        page.wait_for_timeout(2_000)  # Extra settle time after inputs appear
        print("    ✓ Leaderboard loaded")

        # ── 3. Set date range via Tableau JavaScript API ───────────────────────
        # Tableau renders its filter controls in Canvas, not HTML — standard
        # Playwright selectors can't find them. Instead we call the Tableau
        # Embedding API directly via JavaScript.
        print(f"[3/4] Setting date range: {start_date} → {end_date}…")

        result = page.evaluate(f"""
            async () => {{
                // Tableau Embedding API v3 — viz is a <tableau-viz> custom element
                const viz = document.querySelector('tableau-viz');
                if (!viz) {{
                    // Collect page info to help debug
                    const tags = [...new Set(
                        Array.from(document.querySelectorAll('*')).map(e => e.tagName)
                    )].join(',');
                    return {{ok: false, reason: 'no tableau-viz element', tags}};
                }}
                try {{
                    const wb = viz.workbook;
                    await wb.changeParameterValueAsync('Start Date', '{start_date}');
                    await wb.changeParameterValueAsync('End Date', '{end_date}');
                    return {{ok: true, method: 'embedding-api-v3'}};
                }} catch(e) {{
                    // Try alternative: window.tableau global
                    try {{
                        const vizzes = window.tableau?.VizManager?.getVizs() ?? [];
                        if (vizzes.length > 0) {{
                            const wb2 = vizzes[0].getWorkbook();
                            await wb2.changeParameterValueAsync('Start Date', '{start_date}');
                            await wb2.changeParameterValueAsync('End Date', '{end_date}');
                            return {{ok: true, method: 'viz-manager'}};
                        }}
                    }} catch(e2) {{}}
                    return {{ok: false, reason: e.toString()}};
                }}
            }}
        """)

        print(f"    JS API result: {result}")

        if result.get("ok"):
            page.wait_for_timeout(3_000)  # Let the viz re-render with new dates
            print("    ✓ Date range applied via JavaScript API")
        else:
            print("    ⚠  JavaScript API did not work.")
            print(f"       Reason: {result.get('reason', 'unknown')}")
            if result.get("tags"):
                print(f"       Page tags: {result['tags'][:200]}")
            print()
            print("    The most reliable fallback is the Tableau REST API.")
            print("    See: https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api.htm")
            print("    Create a Personal Access Token in Tableau Cloud:")
            print("    My Account → Account Settings → Personal Access Tokens")
            print()
            input("   Or set the date range manually in the browser, then press Enter to continue…")

        page.wait_for_timeout(3_000)  # Wait for Tableau to re-render with new dates
        print("    ✓ Date range applied")

        # ── 4. Export ──────────────────────────────────────────────────────────
        print("[4/4] Exporting…")

        # Find Export Data button — debug what's actually on the page
        export_elements = page.evaluate("""
            () => {
                const all = Array.from(document.querySelectorAll(
                    'button, [role="button"], a, [role="menuitem"], [role="option"]'
                ));
                return all
                    .filter(el => el.textContent.toLowerCase().includes('export')
                               || (el.getAttribute('aria-label') || '').toLowerCase().includes('export')
                               || (el.getAttribute('title') || '').toLowerCase().includes('export'))
                    .map(el => ({
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 60),
                        ariaLabel: el.getAttribute('aria-label'),
                        title: el.getAttribute('title'),
                        cls: el.className.substring(0, 80)
                    }));
            }
        """)
        print(f"    Export-related elements found: {export_elements}")

        # Try multiple selectors for the Export Data button
        export_btn = (
            page.get_by_role("button", name="Export Data")
            .or_(page.get_by_role("button", name="Export"))
            .or_(page.locator('[aria-label*="Export Data"], [title*="Export Data"]'))
            .or_(page.get_by_text("Export Data", exact=True))
        )
        export_btn.first.click(timeout=20_000)
        page.wait_for_timeout(800)

        # "Download Crosstab" modal — select LeaderboardT sheet
        try:
            page.get_by_text("LeaderboardT").click(timeout=8_000)
            page.wait_for_timeout(400)
        except PlaywrightTimeoutError:
            print("    ⚠  Could not find LeaderboardT sheet — proceeding with current selection.")

        # Select CSV format
        try:
            page.get_by_label("CSV").click(timeout=5_000)
            page.wait_for_timeout(300)
        except PlaywrightTimeoutError:
            page.locator('input[type="radio"][value="csv"], label:has-text("CSV")').first.click(timeout=5_000)
            page.wait_for_timeout(300)

        # Click Download and capture the file
        start_slug    = start_date.replace("/", "-")
        end_slug      = end_date.replace("/", "-")
        fallback_name = f"tableau_leaderboard_{start_slug}_to_{end_slug}.csv"

        print("    Waiting for download…")
        try:
            with page.expect_download(timeout=60_000) as dl_info:
                page.get_by_role("button", name="Download").click(timeout=10_000)

            download  = dl_info.value
            save_path = os.path.join(download_dir, fallback_name)
            download.save_as(save_path)

            # Move to project records directory
            output_dir = os.path.join(
                os.path.expanduser("~"),
                "Documents", "Claude", "qdemo-usage-reporting",
                OUTPUT_SUBDIR,
            )
            os.makedirs(output_dir, exist_ok=True)
            final_path = os.path.join(output_dir, os.path.basename(save_path))
            shutil.move(save_path, final_path)
            print(f"\n✅  Export saved to:\n    {final_path}\n")

        except PlaywrightTimeoutError:
            print("\n⚠  Download did not start automatically.")
            print("   The file may have been saved to your Downloads folder.")

        browser.close()


if __name__ == "__main__":
    main()
