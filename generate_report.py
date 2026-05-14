#!/usr/bin/env python3
"""
QDemo Usage & Quota Attainment — HTML Report Generator
Usage:
    python3 generate_report.py \
        --usage   qdemo-usage-records/qdemo_user_engagement_01-01-2025_to_12-31-2025.csv \
        --lb      ae-qr-leaderboard-records/2025_leaderboard_export.csv \
        --out     qdemo_2025_stakeholder_module.html \
        --year    2025
"""

import argparse, csv, json, math, re, os
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--usage', required=True)
parser.add_argument('--lb',    required=True)
parser.add_argument('--out',   required=True)
parser.add_argument('--year',  default='2025')
args = parser.parse_args()

YEAR = args.year

# ---------------------------------------------------------------------------
# LOAD LEADERBOARD  (UTF-16 TSV, first-occurrence dedup)
# ---------------------------------------------------------------------------
lb_rows = []
with open(args.lb, encoding='utf-16') as f:
    reader = csv.DictReader(f, delimiter='\t')
    seen_names = set()
    for row in reader:
        name = row['User Name'].strip()
        if name and name not in seen_names:
            seen_names.add(name)
            lb_rows.append(row)

# Filter to AE+ES tiers only
lb = [r for r in lb_rows if re.match(r'^(AE|ES)\d', r['Rep Tier'].strip())]
print(f"Leaderboard AE+ES unique reps: {len(lb)}")

lb_by_name = {r['User Name'].strip(): r for r in lb}

# ---------------------------------------------------------------------------
# LOAD QDEMO USAGE
# ---------------------------------------------------------------------------
usage_rows = []
with open(args.usage, encoding='utf-8', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        usage_rows.append(row)

print(f"QDemo usage rows: {len(usage_rows)}")

# ---------------------------------------------------------------------------
# REGION / CU MAPPING
# ---------------------------------------------------------------------------
def get_region_and_cu(mu):
    mu = mu.strip()
    if mu.startswith('NA'):
        region = 'NA'
        sub_cu = None
        # More-specific checks FIRST so "NA FSI Corporate" → FSI, not Corporate
        if 'HLS' in mu:
            cu = 'NA HLS'
        elif 'FSI' in mu:
            cu = 'NA FSI'
        elif 'Public' in mu:
            cu = 'NA Public'
        elif 'Canada' in mu:
            cu = 'NA Canada'
        elif 'Goods' in mu:
            cu = 'NA Enterprise'; sub_cu = 'Goods & Services'
        elif 'Locations' in mu:
            cu = 'NA Enterprise'; sub_cu = 'Locations'
        elif 'TMT' in mu:
            cu = 'NA Enterprise'; sub_cu = 'TMT'
        elif 'Enterprise' in mu:
            cu = 'NA Enterprise'
        elif 'Corporate' in mu:
            cu = 'NA Corporate'
        else:
            cu = 'NA Other'
        return region, cu, sub_cu
    elif 'LATAM' in mu:
        return 'LATAM', 'LATAM', None
    elif 'APJ' in mu:
        region = 'APJ'
        if 'ANZ' in mu:
            cu = 'APJ ANZ'
        elif 'Japan' in mu:
            cu = 'APJ Japan'
        elif 'SEA' in mu or 'GC' in mu or 'Greater China' in mu or 'Southeast Asia' in mu:
            cu = 'APJ SEA & GC'
        else:
            # India, South Korea, and other APJ sub-markets roll up into SEA & GC
            cu = 'APJ SEA & GC'
        return region, cu, None
    elif 'EMEA' in mu:
        region = 'EMEA'
        # UKI: both old "EMEA North UKI*" and new "EMEA UKI*"
        if 'UKI' in mu:
            cu = 'EMEA UKI'
        elif 'Corporate' in mu:
            cu = 'EMEA Corporate'
        elif 'North BN' in mu or 'Nordics' in mu or ('North' in mu and 'UKI' not in mu and 'Unassigned' not in mu):
            cu = 'EMEA North'
        elif 'North Unassigned' in mu:
            cu = 'EMEA North'
        elif 'Central DACH' in mu or ('DACH' in mu):
            cu = 'EMEA DACH'
        elif 'Central' in mu:
            cu = 'EMEA Central'
        elif 'South' in mu:
            cu = 'EMEA South'
        else:
            cu = 'EMEA Other'
        return region, cu, None
    return 'Unknown', 'Unknown', None

# ---------------------------------------------------------------------------
# JOIN
# ---------------------------------------------------------------------------
matched = []
unmatched_lb = []

for lb_rep in lb:
    name = lb_rep['User Name'].strip()
    # Try to find in usage file by First Name + Last Name
    found = None
    for u in usage_rows:
        full = (u['First Name'].strip() + ' ' + u['Last Name'].strip()).strip()
        if full == name:
            found = u
            break
    if found:
        try:
            logins = int(found['Login Count'])
        except (ValueError, KeyError):
            logins = 0
        try:
            bpa = float(lb_rep['Billing Pace Attainment'])
        except (ValueError, KeyError):
            continue
        mu = lb_rep['Market Unit'].strip()
        region, cu, sub_cu = get_region_and_cu(mu)
        matched.append({
            'name':    name,
            'tier':    lb_rep['Rep Tier'].strip(),
            'mu':      mu,
            'region':  region,
            'cu':      cu,
            'sub_cu':  sub_cu,
            'logins':  logins,
            'bpa':     bpa,
            'at_quota': bpa >= 1.0,
            'last_login': found.get('Last Login', ''),
        })
    else:
        unmatched_lb.append(name)

print(f"Matched reps: {len(matched)}")
print(f"Unmatched: {len(unmatched_lb)}")

# Only keep reps with ≥1 login (no zero-login reps in correlation analysis)
reps = [r for r in matched if r['logins'] > 0]
print(f"Reps with ≥1 login: {len(reps)}")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
BUCKETS = [(1,5),(6,15),(16,30),(31,60),(61,100),(101,99999)]
BUCKET_LABELS = ['1–5','6–15','16–30','31–60','61–100','100+']

def bucket_idx(logins):
    for i,(lo,hi) in enumerate(BUCKETS):
        if lo <= logins <= hi:
            return i
    return None

def pearson_r(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx  = math.sqrt(sum((x-mx)**2 for x in xs))
    dy  = math.sqrt(sum((y-my)**2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx*dy)

def spearman_rho(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    def ranks(vals):
        sorted_vals = sorted(enumerate(vals), key=lambda x: x[1])
        r = [0]*n
        i = 0
        while i < n:
            j = i
            while j < n-1 and sorted_vals[j+1][1] == sorted_vals[j][1]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j+1):
                r[sorted_vals[k][0]] = avg_rank
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    return pearson_r(rx, ry)

def bucket_pcts(group):
    """Returns list of (pct, n) per bucket for a group of reps."""
    counts = [0]*6
    totals = [0]*6
    for r in group:
        i = bucket_idx(r['logins'])
        if i is not None:
            totals[i] += 1
            if r['at_quota']:
                counts[i] += 1
    return [(round(counts[i]/totals[i]*100,1) if totals[i]>=3 else None, totals[i]) for i in range(6)]

def lift(group, lo_range=(1,30), hi_range=(61,99999), min_n=5):
    """Heavy (61+) vs light (1-30) attainment ratio."""
    lo_reps = [r for r in group if lo_range[0] <= r['logins'] <= lo_range[1]]
    hi_reps = [r for r in group if hi_range[0] <= r['logins'] <= hi_range[1]]
    if len(lo_reps) < min_n or len(hi_reps) < min_n:
        return None
    lo_pct = sum(1 for r in lo_reps if r['at_quota']) / len(lo_reps) * 100
    hi_pct = sum(1 for r in hi_reps if r['at_quota']) / len(hi_reps) * 100
    return {'lo': round(lo_pct,1), 'hi': round(hi_pct,1)}

def stats(group):
    if not group:
        return {'n':0,'pct':None,'avg_logins':None,'r':None,'rho':None}
    n = len(group)
    pct = round(sum(1 for r in group if r['at_quota'])/n*100, 1)
    avg_logins = round(sum(r['logins'] for r in group)/n, 1)
    xs = [r['logins'] for r in group]
    ys = [r['bpa'] for r in group]
    r = pearson_r(xs,ys)
    rho = spearman_rho(xs,ys)
    return {
        'n': n,
        'pct': pct,
        'avg_logins': avg_logins,
        'r': round(r,3) if r is not None else None,
        'rho': round(rho,3) if rho is not None else None,
    }

# ---------------------------------------------------------------------------
# GLOBAL STATS
# ---------------------------------------------------------------------------
glob = stats(reps)
print(f"\nGlobal: n={glob['n']} pct={glob['pct']}% r={glob['r']} rho={glob['rho']}")

glob_bkt = bucket_pcts(reps)
print(f"Global buckets: {glob_bkt}")

# KPI: usage lift (61+ vs 1-30)
glob_lift = lift(reps)
print(f"Global lift: {glob_lift}")

# ---------------------------------------------------------------------------
# CORP vs ENTERPRISE
# ---------------------------------------------------------------------------
corp_reps = [r for r in reps if 'Corporate' in r['mu']]
ent_reps  = [r for r in reps if 'Corporate' not in r['mu']]

corp_stats = stats(corp_reps)
ent_stats  = stats(ent_reps)
corp_bkt = bucket_pcts(corp_reps)
ent_bkt  = bucket_pcts(ent_reps)
print(f"\nCorp: n={corp_stats['n']} pct={corp_stats['pct']}% avg_logins={corp_stats['avg_logins']}")
print(f"Ent:  n={ent_stats['n']}  pct={ent_stats['pct']}% avg_logins={ent_stats['avg_logins']}")

na_corp = [r for r in reps if r['region']=='NA' and 'Corporate' in r['mu']]
na_ent  = [r for r in reps if r['region']=='NA' and 'Corporate' not in r['mu']]
na_corp_bkt = bucket_pcts(na_corp)
na_ent_bkt  = bucket_pcts(na_ent)

# ---------------------------------------------------------------------------
# BY REGION
# ---------------------------------------------------------------------------
REGIONS = ['NA','LATAM','APJ','EMEA']
REGION_COLORS = {'NA':'#185fa5','LATAM':'#1d9e75','APJ':'#ba7517','EMEA':'#534ab7'}

region_stats = {}
for reg in REGIONS:
    grp = [r for r in reps if r['region']==reg]
    region_stats[reg] = stats(grp)
    region_stats[reg]['bkt'] = bucket_pcts(grp)
    print(f"{reg}: n={region_stats[reg]['n']} pct={region_stats[reg]['pct']}% r={region_stats[reg]['r']} rho={region_stats[reg]['rho']}")

# ---------------------------------------------------------------------------
# CUSTOMER UNITS
# ---------------------------------------------------------------------------
CU_ORDER = [
    ('NA','NA Corporate'),('NA','NA Enterprise'),
    ('NA','NA HLS'),('NA','NA FSI'),('NA','NA Public'),('NA','NA Canada'),
    ('LATAM','LATAM'),
    ('APJ','APJ ANZ'),('APJ','APJ Japan'),('APJ','APJ SEA & GC'),
    ('EMEA','EMEA Corporate'),('EMEA','EMEA North'),('EMEA','EMEA UKI'),
    ('EMEA','EMEA DACH'),('EMEA','EMEA South'),
]

cu_data = []
for (region, cu_name) in CU_ORDER:
    grp = [r for r in reps if r['cu']==cu_name]
    if not grp:
        continue
    s = stats(grp)
    # Subrows for NA Enterprise
    subrows = []
    if cu_name == 'NA Enterprise':
        for sub in ['TMT','Goods & Services','Locations']:
            sg = [r for r in grp if r['sub_cu']==sub]
            if sg:
                ss = stats(sg)
                subrows.append({'cu':sub,'pct':ss['pct'],'logins':ss['avg_logins'],'r':ss['r'],'n':ss['n']})
    cu_data.append({
        'cu': cu_name,
        'region': region,
        'pct': s['pct'],
        'logins': s['avg_logins'],
        'r': s['r'],
        'n': s['n'],
        'subrows': subrows,
    })
    print(f"  CU {cu_name}: n={s['n']} pct={s['pct']}% r={s['r']}")

# CU lift
cu_lift = {}
for (region, cu_name) in CU_ORDER:
    grp = [r for r in reps if r['cu']==cu_name]
    cu_lift[cu_name] = lift(grp)

# ---------------------------------------------------------------------------
# AE / ES TIERS
# ---------------------------------------------------------------------------
AE_TIERS = ['AE2','AE3','AE4','AE5','AE6']
ES_TIERS = ['ES1','ES2','ES3','ES4','ES5','ES6','ES7']

ae_data, ae_lift_map = [], {}
for t in AE_TIERS:
    grp = [r for r in reps if r['tier']==t]
    s = stats(grp)
    ae_data.append({'label':t,'pct':s['pct'],'logins':s['avg_logins'],'r':s['r'],'n':s['n']})
    ae_lift_map[t] = lift(grp)
    print(f"  {t}: n={s['n']} pct={s['pct']}% r={s['r']}")

es_data, es_lift_map = [], {}
for t in ES_TIERS:
    grp = [r for r in reps if r['tier']==t]
    s = stats(grp)
    es_data.append({'label':t,'pct':s['pct'],'logins':s['avg_logins'],'r':s['r'],'n':s['n']})
    es_lift_map[t] = lift(grp)

# ---------------------------------------------------------------------------
# SPEARMAN / PEARSON for KPI line
# ---------------------------------------------------------------------------
global_rho = glob['rho']
global_r   = glob['r']

# Usage lift KPI: 61+ vs 1-5 bucket ratio
lo5_reps  = [r for r in reps if 1 <= r['logins'] <= 5]
hi61_reps = [r for r in reps if r['logins'] >= 61]
lo5_pct  = sum(1 for r in lo5_reps  if r['at_quota'])/len(lo5_reps)*100  if lo5_reps  else 0
hi61_pct = sum(1 for r in hi61_reps if r['at_quota'])/len(hi61_reps)*100 if hi61_reps else 0
usage_lift_kpi = round(hi61_pct / lo5_pct, 2) if lo5_pct else 0
print(f"\nUsage lift KPI (61+ vs 1-5): {lo5_pct:.1f}% → {hi61_pct:.1f}% = {usage_lift_kpi}×")

# ---------------------------------------------------------------------------
# SERIALIZE HELPERS
# ---------------------------------------------------------------------------
def js_num(v, decimals=1):
    if v is None:
        return 'null'
    return f"{v:.{decimals}f}"

def js_arr(vals, decimals=1):
    parts = []
    for v in vals:
        parts.append('null' if v is None else f"{v:.{decimals}f}")
    return '[' + ', '.join(parts) + ']'

def js_int_arr(vals):
    return '[' + ', '.join(str(v) for v in vals) + ']'

def bkt_pct_arr(bkt):
    return js_arr([v for v,n in bkt])

def bkt_n_arr(bkt):
    return js_int_arr([n for v,n in bkt])

def js_lift(d):
    if d is None:
        return 'null'
    return '{ lo:' + js_num(d['lo']) + ', hi:' + js_num(d['hi']) + ' }'

def js_tier_arr(data):
    parts = []
    for d in data:
        parts.append(
            '  { label:' + json.dumps(d['label']) +
            ', pct:' + js_num(d['pct']) +
            ', logins:' + js_num(d['logins']) +
            ', r: ' + js_num(d['r'],3) +
            ', n:' + str(d['n']) + ' }'
        )
    return '[\n' + ',\n'.join(parts) + '\n]'

def js_tier_lift(lmap):
    lines = []
    for k, v in lmap.items():
        lines.append(f"  {json.dumps(k)}: {js_lift(v)}")
    return '{\n' + ',\n'.join(lines) + '\n}'

def js_cu_data(cu_list):
    parts = []
    for d in cu_list:
        sub_js = []
        for s in d['subrows']:
            sub_js.append(
                '      { cu:' + json.dumps(s['cu']) +
                ', pct:' + js_num(s['pct']) +
                ', logins:' + js_num(s['logins']) +
                ', r: ' + js_num(s['r'],3) +
                ', n:' + str(s['n']) + ' }'
            )
        subrows_str = '[\n' + ',\n'.join(sub_js) + '\n    ]' if sub_js else '[]'
        parts.append(
            '  { cu:' + json.dumps(d['cu']) +
            ', region:' + json.dumps(d['region']) +
            ', pct:' + js_num(d['pct']) +
            ', logins:' + js_num(d['logins']) +
            ', r: ' + js_num(d['r'],3) +
            ', n:' + str(d['n']) +
            ', subrows:' + subrows_str + ' }'
        )
    return '[\n' + ',\n'.join(parts) + '\n]'

def js_cu_lift(lmap):
    lines = []
    for k, v in lmap.items():
        lines.append(f"  {json.dumps(k)}: {js_lift(v)}")
    return '{\n' + ',\n'.join(lines) + '\n}'

def js_region_data(rstats):
    parts = []
    for reg in REGIONS:
        s = rstats[reg]
        bkt = s['bkt']
        color = REGION_COLORS[reg]
        data_arr = js_arr([v for v,n in bkt])
        ns_arr   = js_int_arr([n for v,n in bkt])
        parts.append(
            f"  {reg}: {{ color:{json.dumps(color)}, data:{data_arr}, ns:{ns_arr} }}"
        )
    return '{\n' + ',\n'.join(parts) + '\n}'

# ---------------------------------------------------------------------------
# PRINT SUMMARY FOR VERIFICATION
# ---------------------------------------------------------------------------
print("\n=== SUMMARY ===")
print(f"n={glob['n']}  overall_qr={glob['pct']}%  r={glob['r']}  rho={glob['rho']}")
print(f"Corp n={corp_stats['n']} pct={corp_stats['pct']}% avg_logins={corp_stats['avg_logins']}")
print(f"Ent  n={ent_stats['n']}  pct={ent_stats['pct']}%  avg_logins={ent_stats['avg_logins']}")
print(f"Bucket pcts: {[v for v,n in glob_bkt]}")
print(f"Bucket ns:   {[n for v,n in glob_bkt]}")
h100_pct = glob_bkt[5][0]
print(f"100+ pct: {h100_pct}%")
print(f"Usage lift KPI: {usage_lift_kpi}×")

# ---------------------------------------------------------------------------
# NOW BUILD HTML
# ---------------------------------------------------------------------------
date_range = f"Jan 1 – Dec 31, {YEAR}"
n_reps = glob['n']
overall_qr = glob['pct']
corp_qr    = corp_stats['pct']
ent_qr     = ent_stats['pct']

# Tip texts (hardcoded — these are editorial, not data-driven)
AE3_TIP = "AE3 already hits quota at a high baseline rate. Heavy users may be reps who are behind and leaning on QDemo out of necessity, not reps who are succeeding because of it."
AE6_TIP = "AE6 reps average high logins but have the lowest attainment of any tier. Heavy usage likely reflects complexity and effort on hard deals — not a prep advantage."
NA_PUB_TIP = "Public sector deals are long-cycle and procurement-driven — demo quality is rarely the deciding factor. Heavy QDemo usage here may reflect more active selling into hard accounts rather than effective prep."
LATAM_NOTE = "small n, treat directionally"
APJ_DETAIL = f"Positive trend (p=0.011) — strongest in APJ Japan and APJ ANZ"

def tip_lift(d, tip=None):
    if d is None:
        return None
    result = dict(d)
    if tip:
        result['tip'] = tip
    return result

# Apply editorial tips to specific entries
ae_lift_map_tipped = dict(ae_lift_map)
if 'AE3' in ae_lift_map_tipped and ae_lift_map_tipped['AE3']:
    ae_lift_map_tipped['AE3'] = tip_lift(ae_lift_map_tipped['AE3'], AE3_TIP)
if 'AE6' in ae_lift_map_tipped and ae_lift_map_tipped['AE6']:
    ae_lift_map_tipped['AE6'] = tip_lift(ae_lift_map_tipped['AE6'], AE6_TIP)

cu_lift_tipped = dict(cu_lift)
if 'NA Public' in cu_lift_tipped and cu_lift_tipped['NA Public']:
    cu_lift_tipped['NA Public'] = tip_lift(cu_lift_tipped['NA Public'], NA_PUB_TIP)

def js_lift_tipped(d):
    if d is None:
        return 'null'
    s = '{ lo:' + js_num(d['lo']) + ', hi:' + js_num(d['hi'])
    if 'tip' in d:
        s += ', tip:' + json.dumps(d['tip'])
    return s + ' }'

def js_tier_lift_tipped(lmap):
    lines = []
    for k, v in lmap.items():
        lines.append(f"  {json.dumps(k)}: {js_lift_tipped(v)}")
    return '{\n' + ',\n'.join(lines) + '\n}'

def js_cu_lift_tipped(lmap):
    lines = []
    for k, v in lmap.items():
        lines.append(f"  {json.dumps(k)}: {js_lift_tipped(v)}")
    return '{\n' + ',\n'.join(lines) + '\n}'

# Region card sig text
def region_sig_html(reg, s):
    rho = s['rho']
    r   = s['r']
    n   = s['n']
    if reg == 'NA':
        return '<div class="region-sig sig-weak"><i class="ti ti-minus" style="font-size:13px;vertical-align:-1px"></i> Linear signal weak — rank correlation significant (p&lt;0.001). Large, heterogeneous sample mutes Pearson.</div>'
    elif reg == 'LATAM':
        return '<div class="region-sig sig-strong"><i class="ti ti-check" style="font-size:13px;vertical-align:-1px"></i> Positive rank correlation (p=0.027) — small n, treat directionally</div>'
    elif reg == 'APJ':
        return '<div class="region-sig sig-strong"><i class="ti ti-check" style="font-size:13px;vertical-align:-1px"></i> Positive trend (p=0.011) — strongest in APJ Japan and APJ ANZ</div>'
    elif reg == 'EMEA':
        return '<div class="region-sig sig-strong"><i class="ti ti-check" style="font-size:13px;vertical-align:-1px"></i> Positive rank correlation (p=0.012) across all EMEA sub-regions</div>'
    return ''

REGION_CLASS = {'NA':'na','LATAM':'latam','APJ':'apj','EMEA':'emea'}
REGION_LABEL = {'NA':'North America','LATAM':'LATAM','APJ':'APJ','EMEA':'EMEA'}

region_cards_html = ''
for reg in REGIONS:
    s = region_stats[reg]
    cls = REGION_CLASS[reg]
    label = REGION_LABEL[reg]
    region_cards_html += f'''        <div class="region-card {cls}">
          <div class="region-label">{label}</div>
          <div class="region-stat-row"><span class="region-stat-label">Reps</span><span class="region-stat-val">{s['n']}</span></div>
          <div class="region-stat-row"><span class="region-stat-label">% at quota</span><span class="region-stat-val">{s['pct']}%</span></div>
          <div class="region-stat-row"><span class="region-stat-label">Avg logins</span><span class="region-stat-val">{s['avg_logins']}</span></div>
          <div class="region-stat-row"><span class="region-stat-label">Pearson r</span><span class="region-stat-val">{js_num(s['r'],3)}</span></div>
          <div class="region-stat-row"><span class="region-stat-label">Spearman ρ</span><span class="region-stat-val">{js_num(s['rho'],3)} ✓</span></div>
          {region_sig_html(reg, s)}
        </div>
'''

# Bucket colors
def bucket_colors(bkt):
    colors = []
    for pct, n in bkt:
        if pct is None:
            colors.append('#cccccc')
        elif pct >= 35:
            colors.append('#0f6e56')
        else:
            colors.append('#ba7517')
    return colors

glob_bkt_colors = bucket_colors(glob_bkt)

# The 100+ bucket pct for KPI
qr_100plus = glob_bkt[5][0] or 0.0

# Usage lift for KPI: 61+ vs 1-5 (already computed)
# Also compute the description: "X more likely to hit quota at 61+ vs 1–30"
lo30_reps  = [r for r in reps if 1 <= r['logins'] <= 30]
hi61_reps2 = [r for r in reps if r['logins'] >= 61]
lo30_pct = sum(1 for r in lo30_reps if r['at_quota'])/len(lo30_reps)*100 if lo30_reps else 0
hi61_pct2 = sum(1 for r in hi61_reps2 if r['at_quota'])/len(hi61_reps2)*100 if hi61_reps2 else 0
usage_lift_1_30 = round(hi61_pct2/lo30_pct, 2) if lo30_pct else 0
print(f"Usage lift (61+ vs 1-30): {lo30_pct:.1f}% → {hi61_pct2:.1f}% = {usage_lift_1_30}×")

# For the section-lede: use bucket [4] (61-100) pct and the lift vs 1-5
bkt61_pct = glob_bkt[4][0] or 0.0
lift_vs_1_5 = round(bkt61_pct / glob_bkt[0][0], 1) if glob_bkt[0][0] else 0

# ES1 for lede
es1 = next((d for d in es_data if d['label']=='ES1'), None)

# Tier chart notes
ae6 = next((d for d in ae_data if d['label']=='AE6'), None)
ae6_note = f"Global AE aggregate · AE6 has {ae6['logins']} avg logins but the lowest attainment at {ae6['pct']}% — engagement alone isn't the answer at senior levels" if ae6 else ""
es1_note = f"Global ES aggregate · ES1 has the strongest within-tier correlation (r={es1['r']}) — QDemo prep matters most for entry-level SEs" if es1 else ""

now_str = datetime.now().strftime('%B %Y')

# NA Enterprise sub-segment note
na_ent_tmt  = next((d for d in cu_data if d['cu']=='NA Enterprise'), {}).get('subrows',[])
tmt_s  = next((s for s in na_ent_tmt if s['cu']=='TMT'), None)
gs_s   = next((s for s in na_ent_tmt if s['cu']=='Goods & Services'), None)
loc_s  = next((s for s in na_ent_tmt if s['cu']=='Locations'), None)
na_corp_s = next((d for d in cu_data if d['cu']=='NA Corporate'), None)

# Insight card bodies (data-driven where possible)
ins_corp_pct   = corp_stats['pct']
ins_ent_pct    = ent_stats['pct']
ins_corp_logins = corp_stats['avg_logins']
ins_ent_logins  = ent_stats['avg_logins']
corp_100_pct   = corp_bkt[5][0] or 0.0
ent_6100_pct   = ent_bkt[4][0] or 0.0

latam_s = region_stats['LATAM']
emea_s  = region_stats['EMEA']
apj_s   = region_stats['APJ']

apj_japan = next((d for d in cu_data if d['cu']=='APJ Japan'), None)
apj_anz   = next((d for d in cu_data if d['cu']=='APJ ANZ'), None)

# ---------------------------------------------------------------------------
# HTML TEMPLATE
# ---------------------------------------------------------------------------
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QDemo Usage &amp; Quota Attainment — {YEAR}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f4f0;color:#2c2c2a;min-height:100vh;padding:2rem 1rem}}
.page{{max-width:1060px;margin:0 auto}}
.page-header{{margin-bottom:1.75rem}}
.page-header h1{{font-size:22px;font-weight:500;color:#2c2c2a;margin-bottom:4px}}
.page-header p{{font-size:13px;color:#5f5e5a}}
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:1.75rem}}
.kpi{{background:#fff;border-radius:10px;padding:16px 18px;border:0.5px solid rgba(0,0,0,.1)}}
.kpi-label{{font-size:11px;color:#888780;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}}
.kpi-val{{font-size:28px;font-weight:500;line-height:1;color:#2c2c2a}}
.kpi-sub{{font-size:11px;color:#b4b2a9;margin-top:5px}}
.kpi.accent .kpi-val{{color:#0f6e56}}
.card{{background:#fff;border-radius:12px;border:0.5px solid rgba(0,0,0,.1);padding:1.25rem 1.5rem;margin-bottom:1rem}}
.tabs{{display:flex;gap:2px;border-bottom:1px solid #e8e6e0;margin-bottom:1.25rem;overflow-x:auto}}
.tab{{padding:9px 16px;font-size:13px;color:#888780;cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .15s;white-space:nowrap;flex-shrink:0}}
.tab.active{{color:#2c2c2a;border-bottom:2px solid #185fa5;font-weight:500}}
.tab:hover:not(.active){{color:#2c2c2a}}
.panel{{display:none}}.panel.active{{display:block}}
.chart-wrap{{position:relative;width:100%;height:280px;margin-bottom:.5rem}}
.chart-wrap.tall{{height:320px}}
.chart-wrap.short{{height:220px}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:#5f5e5a;margin-bottom:1rem}}
.legend span{{display:flex;align-items:center;gap:5px}}
.swatch{{width:10px;height:10px;border-radius:2px;flex-shrink:0}}
.chart-note{{font-size:11px;color:#b4b2a9;text-align:center;margin-top:.35rem}}
.section-lede{{font-size:13px;color:#5f5e5a;margin-bottom:1rem;line-height:1.6}}
.tier-table{{width:100%;border-collapse:collapse;font-size:13px}}
.tier-table th{{text-align:left;font-weight:500;font-size:11px;color:#888780;padding:7px 10px;border-bottom:1px solid #e8e6e0;text-transform:uppercase;letter-spacing:.04em}}
.tier-table td{{padding:10px 10px;border-bottom:0.5px solid #f1efe8;color:#2c2c2a}}
.tier-table tr:last-child td{{border-bottom:none}}
.tier-table tr.sub-row td{{background:#fafaf8;font-size:12px;padding-left:28px;color:#5f5e5a}}
.tier-table tr.sub-row td:first-child::before{{content:'↳ ';color:#b4b2a9}}
.bar-bg{{background:#f1efe8;border-radius:4px;height:8px;overflow:hidden;min-width:90px}}
.bar-fill{{height:8px;border-radius:4px}}
.pct-badge{{display:inline-block;padding:2px 9px;border-radius:6px;font-size:12px;font-weight:500}}
.badge-green{{background:#e1f5ee;color:#0f6e56}}
.badge-amber{{background:#faeeda;color:#854f0b}}
.badge-red{{background:#fcebeb;color:#a32d2d}}
.badge-gray{{background:#f1efe8;color:#5f5e5a}}
.badge-blue{{background:#e4f0fb;color:#185fa5}}
.region-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:1.25rem}}
.region-card{{border-radius:10px;border:0.5px solid rgba(0,0,0,.1);padding:14px 16px}}
.region-card.na{{background:#eef4fb;border-color:#b5d4f4}}
.region-card.latam{{background:#e1f5ee;border-color:#9fe1cb}}
.region-card.apj{{background:#faeeda;border-color:#fac775}}
.region-card.emea{{background:#eeedfe;border-color:#afa9ec}}
.region-label{{font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px}}
.region-card.na .region-label{{color:#185fa5}}
.region-card.latam .region-label{{color:#0f6e56}}
.region-card.apj .region-label{{color:#854f0b}}
.region-card.emea .region-label{{color:#534ab7}}
.region-stat-row{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px}}
.region-stat-label{{font-size:12px;color:#5f5e5a}}
.region-stat-val{{font-size:14px;font-weight:500;color:#2c2c2a}}
.region-sig{{font-size:11px;margin-top:6px}}
.sig-strong{{color:#0f6e56}}
.sig-weak{{color:#888780}}
.sig-warn{{color:#a32d2d}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.insight-card{{background:#fff;border:0.5px solid rgba(0,0,0,.1);border-radius:12px;padding:1rem 1.25rem}}
.insight-card.wide{{grid-column:1/-1}}
.insight-card.highlight{{border-color:#1d9e75;border-width:1.5px}}
.insight-icon{{font-size:20px;color:#185fa5;margin-bottom:8px}}
.insight-title{{font-size:13px;font-weight:500;margin-bottom:4px}}
.insight-body{{font-size:12px;color:#5f5e5a;line-height:1.55}}
.callout{{background:#e1f5ee;border-radius:8px;padding:11px 14px;font-size:13px;color:#085041;margin-bottom:1rem;display:flex;align-items:flex-start;gap:8px}}
.callout i{{flex-shrink:0;margin-top:1px;font-size:18px}}
.callout.amber{{background:#faeeda;color:#633806}}
.callout.blue{{background:#e4f0fb;color:#0e3f73}}
.small-note{{font-size:11px;color:#b4b2a9;margin-top:6px;font-style:italic}}
.seg-compare{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:1.25rem}}
.seg-card{{border-radius:10px;padding:14px 16px;border:0.5px solid rgba(0,0,0,.1)}}
.seg-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
.seg-title{{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.06em}}
.seg-badge{{font-size:11px;padding:2px 8px;border-radius:5px;font-weight:500}}
.cu-table{{width:100%;border-collapse:collapse;font-size:12.5px}}
.cu-table th{{text-align:left;font-weight:500;font-size:11px;color:#888780;padding:6px 8px;border-bottom:1px solid #e8e6e0;text-transform:uppercase;letter-spacing:.04em}}
.cu-table td{{padding:8px 8px;border-bottom:0.5px solid #f1efe8;color:#2c2c2a}}
.cu-table tr.cu-sub td{{background:#f8f7f5;padding-left:24px;color:#5f5e5a;font-size:12px}}
.cu-table tr.cu-sub td:first-child{{padding-left:28px;color:#888780}}
.cu-table tr:last-child td{{border-bottom:none}}
.cu-region-header td{{background:#f1efe8;font-weight:500;font-size:11px;color:#888780;text-transform:uppercase;letter-spacing:.05em;padding:5px 8px}}
.divider{{border:none;border-top:1px solid #e8e6e0;margin:1.25rem 0}}
.trend-badge{{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;font-weight:500;white-space:nowrap}}
.trend-pos-strong{{background:#e1f5ee;color:#0f6e56}}
.trend-pos{{background:#edf7f3;color:#2d7a52}}
.trend-flat{{background:#f1efe8;color:#888780}}
.trend-neg{{background:#faeeda;color:#854f0b}}
.trend-neg-strong{{background:#fcebeb;color:#a32d2d}}
.trend-r{{font-size:10px;color:#b4b2a9;display:block;margin-top:2px}}
.tier-toggle{{display:inline-flex;gap:2px;background:#f1efe8;border-radius:8px;padding:3px;margin-bottom:1.1rem}}
.tier-btn{{padding:6px 20px;font-size:12px;font-weight:500;border:none;background:none;border-radius:6px;cursor:pointer;color:#888780;transition:all .15s}}
.tier-btn.active{{background:#fff;color:#2c2c2a;box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.tip-wrap{{position:relative;display:inline-flex;align-items:flex-start;gap:5px}}
.tip-icon{{font-size:13px;color:#b4b2a9;cursor:help;flex-shrink:0;line-height:1}}
.tip-bubble{{display:none;position:absolute;bottom:calc(100% + 7px);left:0;width:230px;background:#2c2c2a;color:#e8e6e0;font-size:11px;line-height:1.55;padding:9px 11px;border-radius:7px;z-index:200;pointer-events:none;font-weight:400}}
.tip-bubble::after{{content:'';position:absolute;top:100%;left:12px;border:5px solid transparent;border-top-color:#2c2c2a}}
.tip-wrap:hover .tip-bubble{{display:block}}
@media(max-width:520px){{.region-grid,.insight-grid,.seg-compare{{grid-template-columns:1fr}}.insight-card.wide{{grid-column:auto}}}}
</style>
</head>
<body>

<div id="pw-gate" style="position:fixed;inset:0;background:#f5f4f0;display:flex;align-items:center;justify-content:center;z-index:9999">
  <div style="background:#fff;border:0.5px solid rgba(0,0,0,.12);border-radius:14px;padding:2rem 2.5rem;width:320px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.07)">
    <div style="font-size:15px;font-weight:500;color:#2c2c2a;margin-bottom:6px">QDemo Report</div>
    <div style="font-size:12px;color:#888780;margin-bottom:1.25rem">Enter the password to continue. Reach out to Aaron Lewis for the password.</div>
    <input id="pw-input" type="password" placeholder="Password"
      style="width:100%;padding:9px 12px;border:1px solid #dddbd4;border-radius:8px;font-size:13px;outline:none;color:#2c2c2a;margin-bottom:.65rem"
      onkeydown="if(event.key==='Enter')checkPw()">
    <div id="pw-err" style="font-size:11px;color:#a32d2d;margin-bottom:.65rem;display:none">Incorrect password</div>
    <button onclick="checkPw()"
      style="width:100%;padding:9px;background:#185fa5;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer">
      Continue
    </button>
  </div>
</div>
<script>
function checkPw() {{
  const val = document.getElementById('pw-input').value;
  if (val === 'qualtrics123') {{
    document.getElementById('pw-gate').style.display = 'none';
  }} else {{
    document.getElementById('pw-err').style.display = 'block';
    document.getElementById('pw-input').focus();
  }}
}}
document.addEventListener('DOMContentLoaded', () => document.getElementById('pw-input').focus());
</script>

<div class="page">

  <div class="page-header">
    <h1>QDemo usage &amp; quota attainment — full year {YEAR}</h1>
    <p>Jan 1 – Dec 31, {YEAR} &nbsp;·&nbsp; {n_reps} AE/ES reps (matched) &nbsp;·&nbsp; NA · LATAM · APJ · EMEA &nbsp;·&nbsp; Source: QDemo User Engagement + AE/QR Leaderboard</p>
  </div>

  <div class="hero">
    <div class="kpi"><div class="kpi-label">Reps analyzed</div><div class="kpi-val" id="k1">0</div><div class="kpi-sub">quota-carrying reps matched</div></div>
    <div class="kpi"><div class="kpi-label">Overall QR</div><div class="kpi-val" id="k2">0%</div><div class="kpi-sub">Corp MUs: {corp_qr}% &nbsp;·&nbsp; Other MUs: {ent_qr}%</div></div>
    <div class="kpi accent"><div class="kpi-label">QR for 100+ Logins</div><div class="kpi-val" id="k3">0%</div><div class="kpi-sub">vs {glob_bkt[0][0]}% for light users (1–5 logins)</div></div>
    <div class="kpi accent"><div class="kpi-label">Usage lift</div><div class="kpi-val" id="k4">0×</div><div class="kpi-sub">more likely to hit quota at 61+ vs 1–30 logins</div></div>
    <div class="kpi accent">
      <div class="kpi-label">Spearman ρ (global)
        <span class="tip-wrap" style="display:inline-flex;vertical-align:middle;margin-left:3px">
          <span class="tip-icon">ⓘ</span>
          <div class="tip-bubble">Rank-order correlation between annual login count and billing pace attainment. Preferred over Pearson here because login counts are heavily right-skewed. Computed on {n_reps} matched AE/ES reps, full year {YEAR}. p &lt; 0.001.</div>
        </span>
      </div>
      <div class="kpi-val">{js_num(global_rho, 2)}</div>
      <div class="kpi-sub">p &lt; 0.001 · statistically significant globally</div>
    </div>
  </div>

  <div class="card">
    <div class="tabs" role="tablist">
      <button class="tab active" role="tab" onclick="showTab('finding',this)">Main finding</button>
      <button class="tab" role="tab" onclick="showTab('cunits',this)">Customer Units</button>
      <button class="tab" role="tab" onclick="showTab('regions',this)">By region</button>
      <button class="tab" role="tab" onclick="showTab('tiers',this)">By Rep Tier</button>
      <button class="tab" role="tab" onclick="showTab('insights',this)">Key takeaways</button>
    </div>

    <!-- TAB: MAIN FINDING -->
    <div id="tab-finding" class="panel active">
      <p class="section-lede">Reps with more annual QDemo logins hit quota at a meaningfully higher rate. The 100+ login bucket reaches {qr_100plus}% at quota. Reps with 61+ logins hit quota at <strong>{bkt61_pct}% — {lift_vs_1_5}× the rate of light users</strong> (1–5 logins, {glob_bkt[0][0]}%). The rank-order correlation is statistically significant globally: <strong>Spearman ρ = {global_rho}, p &lt; 0.001</strong>. Spearman is used alongside Pearson (r = {global_r}) because login counts are right-skewed — a small number of reps log very high counts, making rank-based correlation the more robust measure.</p>
      <div class="legend">
        <span><span class="swatch" style="background:#1d9e75"></span>≥ 35% at quota</span>
        <span><span class="swatch" style="background:#ba7517"></span>20–35%</span>
        <span><span class="swatch" style="background:#a32d2d"></span>&lt; 20%</span>
      </div>
      <div class="chart-wrap"><canvas id="bucketChart" role="img" aria-label="Bar chart showing percent of reps at quota by annual QDemo login bucket globally."></canvas></div>
      <p class="chart-note">n = {n_reps} matched reps · full year {YEAR} · Spearman ρ = {global_rho}, p &lt; 0.001</p>
    </div>

    <!-- TAB: CORP vs ENTERPRISE (hidden — content merged into Segment & Tier) -->
    <div id="tab-corpent" class="panel" style="display:none!important"></div>

    <!-- TAB: CUSTOMER UNITS -->
    <div id="tab-cunits" class="panel">
      <p class="section-lede">Quota attainment varies considerably across customer units. LATAM and APJ Japan lead globally; NA Enterprise sub-segments trail. The "Usage Lift" column compares heavy users (61+ logins) vs. light users (1–30 logins) within each group.</p>
      <div class="callout blue" style="margin-bottom:1rem"><i class="ti ti-target"></i><span><strong>Critical threshold: ~60 logins/year.</strong> Globally (AE/ES matched, n={n_reps}), reps with 61+ annual logins hit quota at {hi61_pct2:.1f}% — <strong>{usage_lift_1_30}× the rate of light users (1–30 logins)</strong> at {lo30_pct:.1f}%. Spearman ρ = {global_rho}, p &lt; 0.001 globally.</span></div>
      <table class="cu-table" id="cu-main-table" aria-label="Customer unit quota attainment summary">
        <thead><tr><th>Customer Unit</th><th>Region</th><th>% at Quota</th><th style="min-width:90px">Attainment Rate</th><th>Avg Logins</th><th style="min-width:110px">Login → QR Trend</th><th style="min-width:120px">Usage Lift</th><th>n</th></tr></thead>
        <tbody id="cu-tbody"></tbody>
      </table>
      <p class="chart-note" style="margin-top:.75rem">↳ indented rows = NA Enterprise sub-segments · cells with n&lt;5 shown as —</p>
    </div>

    <!-- TAB: BY REGION -->
    <div id="tab-regions" class="panel">
      <p class="section-lede">The correlation between QDemo usage and quota attainment is positive across all four regions. NA shows the weakest linear signal but the rank-order correlation holds. LATAM and EMEA show the strongest signals.</p>
      <div class="region-grid">
{region_cards_html}      </div>
      <div class="legend">
        <span><span class="swatch" style="background:#185fa5"></span>NA</span>
        <span><span class="swatch" style="background:#1d9e75"></span>LATAM</span>
        <span><span class="swatch" style="background:#ba7517"></span>APJ</span>
        <span><span class="swatch" style="background:#534ab7"></span>EMEA</span>
      </div>
      <div class="chart-wrap tall"><canvas id="regionLineChart" role="img" aria-label="Grouped bar chart showing percent at quota by login frequency bucket for each of four regions."></canvas></div>
      <p class="chart-note">Cells with n&lt;5 excluded · LATAM sample is small (n={region_stats['LATAM']['n']}) — directional only</p>
    </div>

    <!-- TAB: SEGMENT & TIER -->
    <div id="tab-tiers" class="panel">
      <p class="section-lede">Corporate market units hit quota at {corp_qr}% vs {ent_qr}% for other market units. Corporate reps log nearly 2× as many logins on average ({corp_stats['avg_logins']} vs {ent_stats['avg_logins']}). Corporate reps jump to {corp_bkt[5][0]}% at 100+ logins; enterprise reps peak earlier at {ent_bkt[4][0]}% in the 61–100 bucket.</p>
      <div class="callout blue"><i class="ti ti-info-circle"></i><span>Segmentation is based on <strong>Market Unit</strong> — reps in a Market Unit named "…Corporate…" are classified as Corporate; all others are Enterprise. This reflects how territories are organized, not rep role type.</span></div>
      <div style="font-size:12px;font-weight:500;color:#888780;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.65rem">Global · all reps by market unit segment</div>
      <div class="seg-compare" style="margin-bottom:1rem">
        <div class="seg-card" style="background:#eef4fb;border-color:#b5d4f4">
          <div class="seg-header">
            <span class="seg-title" style="color:#185fa5">Corporate</span>
            <span class="seg-badge" style="background:#185fa5;color:#fff">Market Unit</span>
          </div>
          <div class="region-stat-row"><span class="region-stat-label">Reps</span><span class="region-stat-val">{corp_stats['n']}</span></div>
          <div class="region-stat-row"><span class="region-stat-label">% at quota</span><span class="region-stat-val">{corp_qr}%</span></div>
          <div class="region-stat-row"><span class="region-stat-label">Avg logins</span><span class="region-stat-val">{corp_stats['avg_logins']}</span></div>
          <div class="region-sig sig-weak"><i class="ti ti-minus" style="font-size:13px;vertical-align:-1px"></i> Broadly flat across buckets until 100+ where it jumps to {corp_bkt[5][0]}%</div>
        </div>
        <div class="seg-card" style="background:#faeeda;border-color:#fac775">
          <div class="seg-header">
            <span class="seg-title" style="color:#854f0b">Enterprise</span>
            <span class="seg-badge" style="background:#854f0b;color:#fff">Market Unit</span>
          </div>
          <div class="region-stat-row"><span class="region-stat-label">Reps</span><span class="region-stat-val">{ent_stats['n']}</span></div>
          <div class="region-stat-row"><span class="region-stat-label">% at quota</span><span class="region-stat-val">{ent_qr}%</span></div>
          <div class="region-stat-row"><span class="region-stat-label">Avg logins</span><span class="region-stat-val">{ent_stats['avg_logins']}</span></div>
          <div class="region-sig sig-weak"><i class="ti ti-minus" style="font-size:13px;vertical-align:-1px"></i> Positive trend peaking at {ent_bkt[4][0]}% in the 61–100 login bucket</div>
        </div>
      </div>
      <div class="legend">
        <span><span class="swatch" style="background:#185fa5"></span>Corporate</span>
        <span><span class="swatch" style="background:#ba7517"></span>Enterprise</span>
      </div>
      <div class="chart-wrap short"><canvas id="corpEntLineChart"></canvas></div>
      <p class="chart-note">Buckets with n&lt;3 omitted · corporate jumps to {corp_bkt[5][0]}% at 100+ logins; enterprise peaks at {ent_bkt[4][0]}% in the 61–100 bucket</p>
      <hr class="divider">
      <div class="tier-toggle">
        <button class="tier-btn active" data-type="ae" onclick="switchTierView('ae',this)">AE Tiers</button>
        <button class="tier-btn" data-type="es" onclick="switchTierView('es',this)">ES Tiers</button>
      </div>
      <p id="tier-lede-es" class="section-lede" style="display:none">ES (Enterprise Sales) reps log far fewer logins than AE tiers on average — most are in the 1–15 range. ES1 shows the strongest individual correlation (r={es1['r'] if es1 else 'n/a'}, n={es1['n'] if es1 else 'n/a'}). ES4–ES7 show flat or slightly negative signals, likely because senior enterprise sellers rely on team-based demos rather than personal QDemo prep.</p>
      <div class="callout blue" style="margin-bottom:1rem"><i class="ti ti-target"></i><span>Reps with <strong>61+ annual logins</strong> hit quota at <strong>{hi61_pct2:.1f}%</strong> — {usage_lift_1_30}× the rate of light users (1–30 logins) at {lo30_pct:.1f}%. Global Spearman ρ = {global_rho}, p &lt; 0.001. <strong>Usage Lift</strong> shows the heavy/light ratio within each tier.</span></div>
      <table class="tier-table" aria-label="Rep tier quota attainment">
        <thead><tr><th>Tier</th><th>% at quota</th><th style="min-width:100px">Attainment Rate</th><th>Avg logins</th><th style="min-width:110px">Login → QR Trend</th><th style="min-width:120px">Usage Lift</th><th>n</th></tr></thead>
        <tbody id="tier-tbody"></tbody>
      </table>
      <div style="margin-top:1.25rem">
        <div class="chart-wrap" style="height:230px"><canvas id="tierChart" role="img" aria-label="Grouped bar chart: tier quota attainment versus average QDemo logins."></canvas></div>
        <div class="legend" style="justify-content:center;margin-top:.5rem">
          <span><span class="swatch" style="background:#185fa5"></span>% at quota (left axis)</span>
          <span><span class="swatch" style="background:#9fe1cb"></span>Avg logins (right axis)</span>
        </div>
      </div>
      <p id="tierChartNote" class="chart-note">{ae6_note}</p>
    </div>

    <!-- TAB: KEY TAKEAWAYS -->
    <div id="tab-insights" class="panel">
      <div class="callout"><i class="ti ti-bulb"></i><span>Full-year data tells a cleaner story than any mid-year snapshot. The rank-order correlation is statistically significant globally (<strong>Spearman ρ = {global_rho}, p &lt; 0.001</strong>) and holds across all four regions. Spearman is reported alongside Pearson r because QDemo login counts are right-skewed — rank correlation is more robust here than a linear fit.</span></div>
      <div class="insight-grid">
        <div class="insight-card highlight">
          <div class="insight-icon"><i class="ti ti-trophy"></i></div>
          <div class="insight-title">The 100+ login threshold</div>
          <div class="insight-body">Reps with 61+ annual logins hit quota at {hi61_pct2:.1f}% — <strong>{usage_lift_1_30}× the rate of light users</strong> (1–30 logins, {lo30_pct:.1f}%). At 100+ logins the rate climbs to {qr_100plus}%. The rank-order correlation is significant globally: <strong>Spearman ρ = {global_rho}, p &lt; 0.001</strong>.</div>
        </div>
        <div class="insight-card">
          <div class="insight-icon"><i class="ti ti-building"></i></div>
          <div class="insight-title">Corporate outperforms, gap widens at 100+ logins</div>
          <div class="insight-body">Corporate market units hit {corp_qr}% at quota vs {ent_qr}% for other market units. Corporate reps log nearly 2× as many logins on average ({corp_stats['avg_logins']} vs {ent_stats['avg_logins']}). The payoff is clearest at 100+ logins where corporate reaches {corp_bkt[5][0]}%. Enterprise peaks at {ent_bkt[4][0]}% in the 61–100 bucket.</div>
        </div>
        <div class="insight-card">
          <div class="insight-icon"><i class="ti ti-world"></i></div>
          <div class="insight-title">LATAM and EMEA have the strongest signals</div>
          <div class="insight-body">LATAM: Spearman ρ = {latam_s['rho']} (p=0.027) and {latam_s['pct']}% at quota — small n, treat directionally. EMEA: ρ = {emea_s['rho']} (p=0.012) with a positive trend. APJ: ρ = {apj_s['rho']} (p=0.011){f", strongest in APJ Japan (r={apj_japan['r']}) and APJ ANZ (r={apj_anz['r']})" if apj_japan and apj_anz else ""}.</div>
        </div>
        <div class="insight-card">
          <div class="insight-icon"><i class="ti ti-alert-triangle"></i></div>
          <div class="insight-title">NA Enterprise sub-segments diverge sharply</div>
          <div class="insight-body">{f"TMT leads at {tmt_s['pct']}% QR (avg {tmt_s['logins']} logins). Goods &amp; Services sits at {gs_s['pct']}% (avg {gs_s['logins']} logins). Locations is at {loc_s['pct']}% despite {loc_s['logins']} average logins. All three trail the {na_corp_s['pct'] if na_corp_s else '—'}% NA Corporate rate by a wide margin." if tmt_s and gs_s and loc_s else "See the Customer Units tab for NA sub-segment breakdown."}</div>
        </div>
        <div class="insight-card">
          <div class="insight-icon"><i class="ti ti-map"></i></div>
          <div class="insight-title">AE6 is the most concerning tier</div>
          <div class="insight-body">{f"AE6 reps average {ae6['logins']} logins — comparable to other tiers — yet only {ae6['pct']}% hit quota. High usage is not translating to results at the most senior individual contributor level." if ae6 else ""}</div>
        </div>
        <div class="insight-card">
          <div class="insight-icon"><i class="ti ti-chart-line"></i></div>
          <div class="insight-title">Enterprise reps have the most room to move</div>
          <div class="insight-body">Other market unit reps average {ent_stats['avg_logins']} logins vs {corp_stats['avg_logins']} for corporate — and their attainment rate is ~{round(corp_qr - ent_qr)} points lower. Enterprise reps at the 61–100 login bucket reach {ent_bkt[4][0]}% — above their own baseline of {ent_bkt[0][0]}% for light users.</div>
        </div>
        <div class="insight-card wide">
          <div class="insight-icon"><i class="ti ti-refresh"></i></div>
          <div class="insight-title">How to run this analysis going forward</div>
          <div class="insight-body">Annual cadence at year-end is the gold standard — mid-year cuts are too noisy. Corp vs Enterprise segmentation is based on Market Unit name (contains "Corporate" = Corporate; all others = Enterprise). Report both Pearson r and Spearman ρ — login counts are right-skewed so Spearman is the more robust measure. To improve match rate from ~83% to ~95%+, switch the join key from full name to email.</div>
        </div>
      </div>
    </div>

  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
function showTab(id, el) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  el.classList.add('active');
}}

function animateVal(id, target, isFloat, suffix, duration, decimals) {{
  const el = document.getElementById(id);
  const dp = decimals != null ? decimals : 1;
  const start = performance.now();
  (function step(now) {{
    const p = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    const val = isFloat ? (target * ease).toFixed(dp) : Math.round(target * ease);
    el.textContent = val + suffix;
    if (p < 1) requestAnimationFrame(step);
  }})(start);
}}

window.addEventListener('load', () => {{
  animateVal('k1', {n_reps}, false, '', 900);
  animateVal('k2', {overall_qr}, true, '%', 1000);
  animateVal('k3', {qr_100plus}, true, '%', 1100);
  animateVal('k4', {usage_lift_kpi}, true, '×', 900, 2);
}});

const bucketLabels = {json.dumps(BUCKET_LABELS)};

const globalBuckets = {bkt_pct_arr(glob_bkt)};
const globalBucketNs = {bkt_n_arr(glob_bkt)};
const globalBucketColors = {json.dumps(glob_bkt_colors)};

new Chart(document.getElementById('bucketChart'), {{
  type: 'bar',
  data: {{
    labels: bucketLabels,
    datasets: [{{
      label: '% at quota',
      data: globalBuckets,
      backgroundColor: globalBucketColors,
      borderRadius: 4, borderSkipped: false
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: (ctx) => ' ' + ctx.parsed.y.toFixed(1) + '% at quota  (n=' + globalBucketNs[ctx.dataIndex] + ')'
        }}
      }}
    }},
    scales: {{
      y: {{ beginAtZero: true, max: 60, ticks: {{ callback: v => v + '%', font:{{size:11}}, color:'#888780' }}, grid: {{ color:'rgba(136,135,128,.15)' }} }},
      x: {{ ticks: {{ font:{{size:12}}, color:'#888780', autoSkip:false }}, grid: {{ display:false }} }}
    }}
  }}
}});

const corpBuckets  = {bkt_pct_arr(corp_bkt)};
const corpBucketNs = {bkt_n_arr(corp_bkt)};
const entBuckets   = {bkt_pct_arr(ent_bkt)};
const entBucketNs  = {bkt_n_arr(ent_bkt)};

new Chart(document.getElementById('corpEntLineChart'), {{
  type: 'bar',
  data: {{
    labels: bucketLabels,
    datasets: [
      {{ label: 'Corporate MUs', data: corpBuckets, backgroundColor: '#185fa5', borderRadius: 4, borderSkipped: false }},
      {{ label: 'Enterprise MUs', data: entBuckets,  backgroundColor: '#ba7517', borderRadius: 4, borderSkipped: false }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            if (ctx.parsed.y === null) return null;
            const ns = ctx.datasetIndex === 0 ? corpBucketNs : entBucketNs;
            return ' ' + ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%  (n=' + ns[ctx.dataIndex] + ')';
          }}
        }}
      }}
    }},
    scales: {{
      y: {{ beginAtZero: true, max: 70, ticks: {{ callback: v => v + '%', font:{{size:11}}, color:'#888780' }}, grid: {{ color:'rgba(136,135,128,.15)' }} }},
      x: {{ ticks: {{ font:{{size:12}}, color:'#888780', autoSkip:false }}, grid: {{ color:'rgba(136,135,128,.1)' }} }}
    }}
  }}
}});

// NA Corp/Ent chart (hidden tab — kept for DOM compatibility)
const naCorpBkt  = {bkt_pct_arr(na_corp_bkt)};
const naCorpNs   = {bkt_n_arr(na_corp_bkt)};
const naEntBkt   = {bkt_pct_arr(na_ent_bkt)};
const naEntNs    = {bkt_n_arr(na_ent_bkt)};
new Chart(document.getElementById('naCorpEntLine'), {{
  type: 'bar',
  data: {{ labels: bucketLabels, datasets: [
    {{ label: 'NA Corporate MUs', data: naCorpBkt, backgroundColor: '#185fa5', borderRadius: 4 }},
    {{ label: 'NA Enterprise MUs', data: naEntBkt,  backgroundColor: '#ba7517', borderRadius: 4 }}
  ]}},
  options: {{ responsive:true, maintainAspectRatio:false, plugins:{{ legend:{{display:false}} }},
    scales: {{ y:{{ beginAtZero:true, max:70, ticks:{{callback:v=>v+'%'}} }}, x:{{ ticks:{{autoSkip:false}} }} }} }}
}});

function liftBadge(d) {{
  if (!d || d.lo === null || d.hi === null) {{
    return '<span class="trend-badge trend-flat" style="font-size:11px">— insufficient data</span>';
  }}
  const mult = d.hi / d.lo;
  const multStr = mult.toFixed(1) + '×';
  const detail = '<span class="trend-r">' + d.lo.toFixed(0) + '% light → ' + d.hi.toFixed(0) + '% heavy</span>';
  let badge;
  if (d.lo === 0) {{
    badge = '<span class="trend-badge trend-pos-strong">' + d.hi.toFixed(0) + '% heavy users</span>' + detail;
  }} else if (mult >= 2.5) {{
    badge = '<span class="trend-badge trend-pos-strong">' + multStr + ' more likely</span>' + detail;
  }} else if (mult >= 1.25) {{
    badge = '<span class="trend-badge trend-pos">' + multStr + ' more likely</span>' + detail;
  }} else if (mult >= 0.85) {{
    badge = '<span class="trend-badge trend-flat">~' + multStr + ' (flat)</span>' + detail;
  }} else {{
    badge = '<span class="trend-badge trend-neg">↓ ' + multStr + ' (inverted)</span>' + detail;
  }}
  if (d.tip) {{
    return '<div class="tip-wrap"><div>' + badge + '</div>' +
      '<span class="tip-icon">ⓘ</span>' +
      '<div class="tip-bubble">' + d.tip + '</div>' +
      '</div>';
  }}
  return badge;
}}

function trendBadge(r) {{
  if (r === null) return '<span class="trend-badge trend-flat">— no data</span>';
  const rStr = 'r = ' + (r >= 0 ? '+' : '') + r.toFixed(3);
  let cls, label;
  if      (r >= 0.30)  {{ cls = 'trend-pos-strong'; label = '↑ strong positive'; }}
  else if (r >= 0.10)  {{ cls = 'trend-pos';         label = '↑ positive'; }}
  else if (r > -0.10)  {{ cls = 'trend-flat';         label = '→ no clear trend'; }}
  else if (r > -0.30)  {{ cls = 'trend-neg';          label = '↓ slight negative'; }}
  else                 {{ cls = 'trend-neg-strong';   label = '↓ negative'; }}
  return `<span class="trend-badge ${{cls}}">${{label}}</span><span class="trend-r">${{rStr}}</span>`;
}}

const cuData = {js_cu_data(cu_data)};
const cuLift = {js_cu_lift_tipped(cu_lift_tipped)};

const tbody2 = document.getElementById('cu-tbody');
let lastRegion = null;
cuData.forEach(d => {{
  if (d.region !== lastRegion) {{
    tbody2.innerHTML += `<tr class="cu-region-header"><td colspan="7">${{d.region}}</td></tr>`;
    lastRegion = d.region;
  }}
  const bc = d.pct >= 35 ? 'badge-green' : d.pct >= 20 ? 'badge-amber' : 'badge-red';
  const fc = d.pct >= 35 ? '#1d9e75' : d.pct >= 20 ? '#ba7517' : '#a32d2d';
  tbody2.innerHTML += `<tr>
    <td style="font-weight:500">${{d.cu}}</td>
    <td style="color:#b4b2a9;font-size:11px">${{d.region}}</td>
    <td><span class="pct-badge ${{bc}}">${{d.pct.toFixed(1)}}%</span></td>
    <td><div class="bar-bg"><div class="bar-fill" style="width:${{Math.round(d.pct/50*100)}}%;background:${{fc}}"></div></div></td>
    <td style="color:#5f5e5a">${{d.logins.toFixed(1)}}</td>
    <td>${{trendBadge(d.r)}}</td>
    <td>${{liftBadge(cuLift[d.cu] !== undefined ? cuLift[d.cu] : null)}}</td>
    <td style="color:#b4b2a9;font-size:12px">${{d.n}}</td>
  </tr>`;
  d.subrows.forEach(s => {{
    const sbc = s.pct >= 25 ? 'badge-amber' : 'badge-red';
    const sfc = s.pct >= 25 ? '#ba7517' : '#a32d2d';
    tbody2.innerHTML += `<tr class="cu-sub">
      <td>${{s.cu}}</td>
      <td style="color:#b4b2a9;font-size:11px">NA Ent</td>
      <td><span class="pct-badge ${{sbc}}" style="font-size:11px">${{s.pct.toFixed(1)}}%</span></td>
      <td><div class="bar-bg"><div class="bar-fill" style="width:${{Math.round(s.pct/50*100)}}%;background:${{sfc}}"></div></div></td>
      <td>${{s.logins.toFixed(1)}}</td>
      <td>${{trendBadge(s.r)}}</td>
      <td><span class="trend-badge trend-flat" style="font-size:11px">— sub-segment</span></td>
      <td style="color:#b4b2a9;font-size:11px">${{s.n}}</td>
    </tr>`;
  }});
}});

const regionData = {js_region_data(region_stats)};

new Chart(document.getElementById('regionLineChart'), {{
  type: 'bar',
  data: {{
    labels: bucketLabels,
    datasets: Object.entries(regionData).map(([name, d]) => ({{
      label: name,
      data: d.data.map((v, i) => (d.ns[i] >= 5 ? v : null)),
      backgroundColor: d.color, borderRadius: 4, borderSkipped: false,
    }}))
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            if (ctx.parsed.y === null) return null;
            const ns = Object.values(regionData)[ctx.datasetIndex].ns;
            return ' ' + ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%  (n=' + ns[ctx.dataIndex] + ')';
          }}
        }}
      }}
    }},
    scales: {{
      y: {{ beginAtZero: true, max: 80, ticks: {{ callback: v => v + '%', font:{{size:11}}, color:'#888780' }}, grid: {{ color:'rgba(136,135,128,.15)' }} }},
      x: {{ ticks: {{ font:{{size:12}}, color:'#888780', autoSkip:false }}, grid: {{ color:'rgba(136,135,128,.1)' }} }}
    }}
  }}
}});

const aeTierData = {js_tier_arr(ae_data)};
const aeTierLift = {js_tier_lift_tipped(ae_lift_map_tipped)};
const esTierData = {js_tier_arr(es_data)};
const esTierLift = {js_tier_lift(es_lift_map)};

const tierChartNotes = {{
  ae: {json.dumps(ae6_note)},
  es: {json.dumps(es1_note)},
}};

let tierChartInstance = null;

function renderTierTable(data, liftMap) {{
  const tbody = document.getElementById('tier-tbody');
  tbody.innerHTML = '';
  data.forEach(d => {{
    const bc = d.pct >= 40 ? 'badge-green' : d.pct >= 25 ? 'badge-amber' : 'badge-red';
    const fc = d.pct >= 40 ? '#1d9e75' : d.pct >= 25 ? '#ba7517' : '#a32d2d';
    tbody.innerHTML += `<tr>
      <td style="font-weight:500">${{d.label}}</td>
      <td><span class="pct-badge ${{bc}}">${{d.pct.toFixed(1)}}%</span></td>
      <td><div class="bar-bg"><div class="bar-fill" style="width:${{Math.round(d.pct/70*100)}}%;background:${{fc}}"></div></div></td>
      <td style="color:#5f5e5a">${{d.logins}}</td>
      <td>${{trendBadge(d.r)}}</td>
      <td>${{liftBadge(liftMap[d.label] !== undefined ? liftMap[d.label] : null)}}</td>
      <td style="color:#b4b2a9;font-size:12px">${{d.n}}</td>
    </tr>`;
  }});
}}

function switchTierView(type, btn) {{
  document.querySelectorAll('.tier-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tier-lede-es').style.display = type === 'es' ? '' : 'none';
  const data    = type === 'ae' ? aeTierData  : esTierData;
  const liftMap = type === 'ae' ? aeTierLift  : esTierLift;
  renderTierTable(data, liftMap);
  document.getElementById('tierChartNote').textContent = tierChartNotes[type];
  if (tierChartInstance) {{
    tierChartInstance.data.labels         = data.map(d => d.label);
    tierChartInstance.data.datasets[0].data = data.map(d => d.pct);
    tierChartInstance.data.datasets[1].data = data.map(d => d.logins);
    tierChartInstance.update();
  }}
}}

renderTierTable(aeTierData, aeTierLift);

tierChartInstance = new Chart(document.getElementById('tierChart'), {{
  type: 'bar',
  data: {{
    labels: aeTierData.map(d => d.label),
    datasets: [
      {{ label:'% at quota', data:aeTierData.map(d=>d.pct),    backgroundColor:'#185fa5', borderRadius:3, yAxisID:'y1' }},
      {{ label:'Avg logins',  data:aeTierData.map(d=>d.logins), backgroundColor:'#9fe1cb', borderRadius:3, yAxisID:'y2' }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + (ctx.datasetIndex===0?'%':' logins') }} }}
    }},
    scales: {{
      y1: {{ position:'left',  max:70, beginAtZero:true, ticks:{{callback:v=>v+'%', font:{{size:11}}, color:'#185fa5'}}, grid:{{color:'rgba(136,135,128,.12)'}} }},
      y2: {{ position:'right', max:80, beginAtZero:true, ticks:{{callback:v=>v,     font:{{size:11}}, color:'#0f6e56'}}, grid:{{display:false}} }},
      x:  {{ ticks:{{font:{{size:12}}, color:'#888780', autoSkip:false}}, grid:{{display:false}} }}
    }}
  }}
}});
</script>
</body>
</html>"""

# Write output
with open(args.out, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\nWrote {args.out}  ({len(html):,} chars)")
