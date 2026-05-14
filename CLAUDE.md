# CLAUDE.md

This file provides guidance to Claude when working in this project.

---

## Project purpose

This project has two goals:

1. **Automate data exports** — pull QDemo usage data (`qdemo_usage_exporter.py`) and AE/QR leaderboard data (`tableau_leaderboard_exporter.py`) on a recurring basis.
2. **Analyze correlations** — measure whether QDemo login frequency correlates with sales rep quota attainment (billing pace attainment), and surface actionable findings for sales leadership.

The owner is Aaron Lewis (`alewis@qualtrics.com`), who works on this analysis to help make the case for QDemo investment and targeted enablement programs.

---

## Folder structure

```
qdemo-usage-reporting/
├── qdemo_usage_exporter.py          # Automates QDemo usage CSV export
├── tableau_leaderboard_exporter.py  # Automates AE/QR leaderboard export
├── qdemo-usage-records/             # QDemo login data (CSV, by date range)
├── ae-qr-leaderboard-records/       # AE/QR leaderboard snapshots (CSV)
├── qdemo_correlation_analysis.xlsx          # 2026 YTD analysis (Jan–May 2026)
├── qdemo_correlation_analysis_2025.xlsx     # Full year 2025 global analysis
├── qdemo_correlation_analysis_2025_NA.xlsx  # Full year 2025 NA-only analysis
└── qdemo_2025_stakeholder_module.html       # Interactive stakeholder presentation
```

---

## Data sources

### QDemo usage (`qdemo-usage-records/`)
Exported from `https://qdemo.yul1.qualtrics.com/admin/reports/user-engagement` using `qdemo_usage_exporter.py`. Key columns: `User Name`, `First Name`, `Last Name`, `Email`, `Login Count`, `Last Login`. Filename pattern: `qdemo_user_engagement_MM-DD-YYYY_to_MM-DD-YYYY.csv`.

### AE/QR leaderboard (`ae-qr-leaderboard-records/`)
Exported from Tableau using `tableau_leaderboard_exporter.py`. UTF-16 tab-separated. Key columns: `User Name`, `Rep Tier`, `Market Unit`, `Billing Pace Attainment` (the primary quota metric, as a decimal — 1.0 = 100% of quota), `Front Line`. Filename: e.g. `2025_leaderboard_export.csv`.

---

## Joining the two datasets

Records are currently joined on **full name** (First Name + Last Name from usage, User Name from leaderboard). This works for ~74–75% of reps. The remaining ~25% are unmatched due to name formatting differences, not because they lack QDemo access (all reps have access via QFL).

**Known improvement**: switch to email as the join key. The leaderboard's `User Name` field often contains the email prefix; the usage file has `Email` directly. This would significantly improve match rate and is worth implementing before the next major analysis run.

---

## Analysis methodology

- **Metric**: `Billing Pace Attainment` — the primary QR metric. Values are decimals (1.0 = at quota). "At quota" is defined as ≥ 1.0.
- **Correlation stats used**: Pearson r (linear) and Spearman ρ (rank-order). Both are reported. Spearman is more robust given the skewed distribution of login counts.
- **Login buckets**: [1–5, 6–15, 16–30, 31–60, 61–100, 100+] annual logins.
- **Population for correlation analysis**: AE and ES tiers only (tiers matching `^(AE|ES)\d`). OD tiers (OD1/OD2/OD3) and PSM/Overlay/PES roles are excluded — they are not measured on billing pace quota. Using the matched-only dataset from the `Rep-Level Data` sheet.
- **OD tiers** (OD1/OD2/OD3): exclude from attainment analysis — they are not measured on billing pace quota.
- **Overlay/PSM roles**: excluded; they have different quota structures. **Important**: earlier analysis runs accidentally included PSM roles. In LATAM particularly, Pablo Santamaria (AE Direct PSM1, 270 logins, 3.32× attainment) was a major outlier that inflated LATAM r from ~0.20 to 0.50. The corrected values below exclude all PSM/overlay roles.

---

## Key findings — full year 2025 (canonical analysis)

The 2025 full-year analysis is the most reliable dataset. Mid-year cuts (e.g. the Jan–May 2026 file) are too noisy to draw conclusions from.

### Global
- **Pearson r = 0.085** (p = 0.036), **Spearman ρ = 0.243** (p < 0.001) — statistically significant positive correlation (AE+ES matched, n=546).
- **100+ login bucket**: 41.5% at quota (n=41) vs 21.3% for the 1–5 bucket. Nearly 2× rate.
- The relationship is broadly monotonic across buckets.
- Overall % at quota (AE+ES matched): 26.0%.

> **Note on previously cited values**: An earlier analysis run (basis for CLAUDE.md prior to May 2025) reported Pearson r=0.171 and Spearman ρ=0.373. Those values were computed on a dataset that inadvertently included OD tiers and PSM/overlay roles, which inflated both statistics. The corrected values above use AE+ES tiers only.

### By region
| Region | n (AE+ES matched) | % at quota | Pearson r | Spearman ρ | Significant? |
|--------|-------------------|------------|-----------|------------|--------------|
| NA     | 337               | 23.7%      | 0.044     | 0.218      | ρ: Yes (p<0.001) |
| LATAM  | 27                | 29.6%      | 0.202     | 0.398      | ρ: Yes (p=0.027) — small sample |
| APJ    | 82                | 28.0%      | 0.167     | 0.280      | ρ: Yes (p=0.011) |
| EMEA   | 100               | 31.0%      | 0.127     | 0.250      | ρ: Yes (p=0.012) |

NA has the weakest correlation despite the largest sample, likely due to territory/segment heterogeneity. LATAM r is now 0.202 (down from the erroneous 0.503); treat as directional given small n.

### By AE tier (global)
| Tier | % at quota | Avg logins | Notes |
|------|------------|------------|-------|
| AE2  | 56.2%      | 55.9       | Small n=16, watch with caution |
| AE3  | 40.7%      | 40.2       | Best-performing tier, strongest enablement target |
| AE4  | 20.7%      | 46.8       | Underperforms despite solid login counts |
| AE5  | 26.4%      | 58.4       | Borderline sig in NA (p=0.056) |
| AE6  | 16.2%      | 45.5       | NA AE6 only 5% at quota — flag for leadership |

### Notable tier findings
- **ES1** (entry-level SEs): r = 0.567, ρ = 0.602 — strongest within-tier correlation (n=20, treat directionally). Build QDemo into SE onboarding.
- **AE3 in NA and EMEA**: both around 40–41% at quota; the clearest target for corporate-tier enablement programs. Note: within-tier r is effectively zero (r=–0.074) — the high attainment rate is baseline performance, not correlated with QDemo intensity.
- **AE4**: r=0.209 (corrected from erroneous 0.391; previous value was inflated by zero-login reps added from leaderboard left-join). Usage lift is real but weaker than previously reported.
- **AE6**: high usage (45.5 avg logins) does not translate to quota attainment (16.2%). Likely reflects effort on complex deals, not a QDemo prep advantage.

### What did NOT replicate from 2026 YTD
The YTD 2026 analysis showed AE3 as the only statistically significant tier (r=0.214, p=0.047). This did not replicate in the 2025 full-year data (AE3 r=–0.074). Treat YTD findings as provisional noise.

---

## Recommendations for future runs

1. **Cadence**: run annually at fiscal year-end (primary), with one mid-year H1 directional check.
2. **Date alignment**: always scope the usage export and the leaderboard to the same date window.
3. **Email join**: implement email-based matching to get from ~75% to ~95%+ match rate.
4. **Exclude OD tiers and PSM/overlay roles** from attainment analysis; they use different quota metrics. Filter to AE+ES tiers only (`Rep Tier` matches `^(AE|ES)\d`).
5. **Run regional cuts separately**: NA's large population dominates the global aggregate and can mask LATAM/APJ/EMEA signals.
6. **Stakeholder module**: `qdemo_2025_stakeholder_module.html` is a self-contained interactive presentation. Update it after each new analysis run by re-running the analysis and regenerating the file.

---

## Exporter scripts

### `qdemo_usage_exporter.py`
Automates the Qualtrics User Engagement Report export for the `qdemo` org.

```bash
export QDEMO_PASSWORD='yourpassword'
python3 qdemo_usage_exporter.py --start 01/01/2025 --end 12/31/2025
```

- **Username**: hardcoded as `alewis@qualtrics.com#qdemo`
- **Password**: `--password` flag → `QDEMO_PASSWORD` env var → interactive prompt
- **Login**: `https://login.qualtrics.com/login` → navigates to `https://qdemo.yul1.qualtrics.com/admin/reports/user-engagement`
- **MFA**: waits up to 90s; pauses for manual completion if it times out
- **Date picker**: triple-click → Delete → `press_sequentially` with `"Mmm D, YYYY"` format → Tab
- **Export flow**: Export button → format modal (CSV pre-selected) → Download button → `expect_download`
- **Output**: saved to `qdemo-usage-records/qdemo_user_engagement_MM-DD-YYYY_to_MM-DD-YYYY.csv`

Dependencies:
```bash
pip install playwright
playwright install chromium
```

### `tableau_leaderboard_exporter.py`
Automates the AE/QR leaderboard export from Tableau.

---

## HTML report generation (`generate_report.py`)

**`generate_report.py`** reads the source CSV files, computes all statistics from scratch, and writes a fully self-contained `qdemo_YYYY_stakeholder_module.html`. No numbers are hardcoded — every figure in the HTML comes directly from the data.

### How to run it

When Aaron provides new data files and asks for an updated report:

```bash
cd /sessions/inspiring-great-albattani/mnt/qdemo-usage-reporting
python3 generate_report.py \
  --usage qdemo-usage-records/qdemo_user_engagement_01-01-2026_to_12-31-2026.csv \
  --lb    ae-qr-leaderboard-records/2026_leaderboard_export.csv \
  --out   qdemo_2026_stakeholder_module.html \
  --year  2026
```

The script prints a verification summary — always check it before presenting the file. Key numbers to spot-check against CLAUDE.md canonical values: `n`, `overall_qr`, global `r` and `rho`, bucket pcts.

### What the script computes

- **Join**: First Name + Last Name (usage) matched to User Name (leaderboard). First occurrence of each rep name in the leaderboard is used when a rep appears in multiple market unit rows.
- **Filter**: AE+ES tiers only (`^(AE|ES)\d`), reps with ≥1 login only.
- **Stats**: Pearson r (linear) and Spearman ρ (rank-order), computed from scratch using numpy-free Python (no external stats library needed).
- **Buckets**: [1–5, 6–15, 16–30, 31–60, 61–100, 100+] annual logins.
- **Corp vs Enterprise**: `'Corporate' in Market Unit` = Corporate; all others = Enterprise.
- **Usage lift KPI**: 61+ logins vs 1–30 logins (not vs 1–5). The 1.46× figure uses this definition.
- **Region/CU mapping**: NA checks HLS/FSI/Public/Canada/Enterprise *before* Corporate to avoid misclassifying "NA FSI Corporate" → "NA Corporate". APJ India and South Korea roll up into APJ SEA & GC.

### What is NOT data-driven (requires human review after each run)

The following tooltip texts are editorial and hardcoded in the script — review them after a new analysis run to ensure the narrative still fits:

- **AE3 lift tip**: explains why heavy AE3 users don't show a correlation lift (high baseline, reverse causality argument)
- **AE6 lift tip**: explains why AE6 high usage doesn't translate to attainment (deal complexity)
- **NA Public lift tip**: explains why the public sector signal is weak (procurement-driven deals)
- **Region sig text** (in `region_sig_html()`): p-values and directional language for each region card — update if new data changes significance

These are in the `# Apply editorial tips` block and the `region_sig_html()` function near the bottom of the data-computation section.

### Iterating on the HTML design

The HTML template lives as a Python f-string at the bottom of `generate_report.py` (the `html = f"""..."""` block). To change layout, styling, or add new sections:

1. Edit the template in `generate_report.py`
2. Re-run the script to regenerate the HTML
3. Never manually edit `qdemo_YYYY_stakeholder_module.html` directly — changes will be overwritten on the next run

The CSS, tab structure, chart configs, and all JavaScript are in the template. Chart.js 4.4.1 is loaded from CDN. All charts are bar charts (converted from line charts in May 2026).

### Known limitations / future improvements

- **Match rate ~83%**: ~115 reps unmatched due to name formatting differences between systems. Switching the join key to email would raise this to ~95%+. The leaderboard `User Name` field contains the rep's display name; the usage file has `Email` directly.
- **Dedup strategy**: takes the first leaderboard row per rep name. If Tableau ever changes sort order, the "first" row changes. Email-based joining would eliminate this ambiguity.
- **EMEA DACH n**: the script combines `EMEA Central DACH *` and `EMEA DACH *` market units. If Qualtrics reorganizes EMEA territories, check the CU mapping in `get_region_and_cu()`.
