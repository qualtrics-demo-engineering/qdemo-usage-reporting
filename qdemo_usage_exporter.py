#!/usr/bin/env python3
"""
qdemo_export.py
---------------
Automates the Qualtrics User Engagement Report export.

Flow:
  1. Prompt for credentials (password is hidden)
  2. Prompt for date range
  3. Open Chrome, log in to Qualtrics
  4. Navigate: hamburger menu → Admin → User engagement
  5. Set custom date range
  6. Click Export and save the file to ~/Downloads

Usage:
  python qdemo_export.py
"""

import argparse
import getpass
import os
import shutil
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

# ── Helpers ────────────────────────────────────────────────────────────────────

def type_date_in_picker(page, input_index, date_str):
    """Type a date directly into a Qualtrics date text box."""
    # Convert MM/DD/YYYY → "May 6, 2026"
    formatted = datetime.strptime(date_str, "%m/%d/%Y").strftime("%b %-d, %Y")
    inp = page.locator('input').nth(input_index)
    inp.click(click_count=3, timeout=5_000)
    page.wait_for_timeout(300)
    inp.press("Delete")
    page.wait_for_timeout(200)
    inp.press_sequentially(formatted, delay=50)
    inp.press("Tab")
    page.wait_for_timeout(400)

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


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QDemo — User Engagement Report Exporter")
    parser.add_argument("--username", help="Qualtrics username")
    parser.add_argument("--password", help="Qualtrics password")
    parser.add_argument("--start", help="Start date (MM/DD/YYYY)")
    parser.add_argument("--end", help="End date (MM/DD/YYYY)")
    args = parser.parse_args()

    banner("QDemo — User Engagement Report Exporter")

    username = args.username or os.environ.get("QDEMO_USERNAME") or "alewis@qualtrics.com#qdemo"
    password = args.password or os.environ.get("QDEMO_PASSWORD") or getpass.getpass("Password: ")

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
        page.goto("https://login.qualtrics.com/login", wait_until="networkidle")

        page.locator('input[placeholder="Username"], input[name="username"]').first.fill(username)
        page.locator('input[placeholder="Password"], input[type="password"]').first.fill(password)
        page.locator('button:has-text("Sign In"), input[value="Sign In"]').first.click()

        # Wait for redirect away from the login domain (handles SSO / MFA too)
        try:
            page.wait_for_url(
                lambda url: "login.qualtrics.com/login" not in url,
                timeout=90_000,   # 90 s — enough time for MFA prompts
            )
        except PlaywrightTimeoutError:
            print("\n⚠  Timed out waiting for login. Check credentials or complete MFA manually.")
            input("   Press Enter once you are logged in to continue…")

        page.wait_for_load_state("networkidle")
        print("    ✓ Logged in")

        # ── 2. Navigate directly to User Engagement ────────────────────────────
        print("[2/4] Navigating to User Engagement…")
        page.goto("https://qdemo.yul1.qualtrics.com/admin/reports/user-engagement", wait_until="networkidle")
        print("    ✓ User Engagement page loaded")

        # ── 3. Set custom date range ───────────────────────────────────────────
        print(f"[3/4] Setting date range: {start_date} → {end_date}…")

        # Open the styled date-range dropdown and choose Custom
        page.get_by_text("Last 1 month").click(timeout=10_000)
        page.wait_for_timeout(400)
        page.get_by_role("option", name="Custom").click(timeout=10_000)
        page.wait_for_timeout(800)

        # Type dates directly into the text boxes
        type_date_in_picker(page, 0, start_date)
        type_date_in_picker(page, 1, end_date)

        # Let the page reload with the new date range
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1_500)
        print("    ✓ Date range applied")

        # ── 4. Export ──────────────────────────────────────────────────────────
        print("[4/4] Exporting…")

        # Step 1: click the page-level Export button to open the format modal
        page.get_by_role("button", name="Export").first.click(timeout=10_000)
        page.wait_for_timeout(600)

        # Step 2: modal appears — CSV is pre-selected, just click Export in the modal
        page.get_by_role("button", name="Export").last.click(timeout=10_000)
        page.wait_for_timeout(800)

        # Step 3: second modal appears with a Download button — click it
        start_slug    = start_date.replace('/', '-')
        end_slug      = end_date.replace('/', '-')
        fallback_name = f"qdemo_user_engagement_{start_slug}_to_{end_slug}.csv"
        save_path     = os.path.join(download_dir, fallback_name)

        print("    Waiting for download…")
        try:
            with page.expect_download(timeout=60_000) as dl_info:
                page.get_by_role("button", name="Download").click(timeout=10_000)

            download  = dl_info.value
            save_path = os.path.join(download_dir, fallback_name)
            download.save_as(save_path)

            # Move file to Claude/usage records/
            usage_dir  = os.path.join(os.path.expanduser("~"), "Documents", "Claude", "qdemo-usage-reporting", "qdemo-usage-records")
            os.makedirs(usage_dir, exist_ok=True)
            final_path = os.path.join(usage_dir, os.path.basename(save_path))
            shutil.move(save_path, final_path)
            print(f"\n✅  Export saved to:\n    {final_path}\n")

        except PlaywrightTimeoutError:
            print("\n⚠  Download did not start automatically.")
            print("   Check Admin → Your downloads in the browser.")

        browser.close()


if __name__ == "__main__":
    main()
