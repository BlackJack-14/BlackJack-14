"""Render a contribution stats card from GitHub's public contribution calendar.

Third-party stats services send Cache-Control: max-age=86400, and GitHub's camo
proxy honours that, so their cards can sit a full day stale in a README. This
runs in CI, writes the SVG into the repo, and is then served from
raw.githubusercontent.com with a 5 minute cache instead.

Reads the public calendar, which already includes private contributions when
"Include private contributions on my profile" is enabled.
"""
import os
import re
import sys
import urllib.request
from datetime import date, timedelta

USER = os.environ.get("PROFILE_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "byRudra"
OUT = os.environ.get("STATS_OUT", "dist/stats.svg")
UA = "Mozilla/5.0 (compatible; profile-stats/1.0; +https://github.com/%s)" % USER

MONTHS = ("January February March April May June July August September "
          "October November December").split()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")


def year_counts(user, year):
    """date -> contribution count for one calendar year."""
    html = fetch(f"https://github.com/users/{user}/contributions"
                 f"?from={year}-01-01&to={year}-12-31")
    ids = dict(re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="([^"]+)"', html))
    tips = dict(re.findall(r'<tool-tip[^>]*\sfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', html))
    out = {}
    for d, el in ids.items():
        text = tips.get(el, "")
        m = re.match(r"([\d,]+)\s+contribution", text)
        out[d] = int(m.group(1).replace(",", "")) if m else 0
    return out


def created_year(user):
    try:
        import json
        data = json.loads(fetch(f"https://api.github.com/users/{user}"))
        return int(data["created_at"][:4])
    except Exception:
        return 2021


def streaks(counts, today):
    """(current, longest) streak in days, counting back from today."""
    longest = run = 0
    for d in sorted(counts):
        if counts[d] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    current, cur = 0, today
    # today not yet contributed shouldn't break a streak that ran through yesterday
    if counts.get(cur.isoformat(), 0) == 0:
        cur -= timedelta(days=1)
    while counts.get(cur.isoformat(), 0) > 0:
        current += 1
        cur -= timedelta(days=1)
    return current, longest


def human(n):
    return f"{n:,}"


def render(stats):
    W, H = 660, 132
    cells = [
        (human(stats["total"]), "Total contributions"),
        (human(stats["this_year"]), f"In {stats['year']}"),
        (human(stats["current"]), "Current streak"),
        (human(stats["longest"]), "Longest streak"),
    ]
    step = W / len(cells)
    parts = []
    for i, (num, label) in enumerate(cells):
        cx = step * i + step / 2
        parts.append(
            f'  <text x="{cx:.1f}" y="62" class="n" text-anchor="middle">{num}</text>\n'
            f'  <text x="{cx:.1f}" y="88" class="l" text-anchor="middle">{label}</text>'
        )
        if i:
            x = step * i
            parts.append(f'  <line x1="{x:.1f}" y1="34" x2="{x:.1f}" y2="94" class="d"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     role="img" aria-label="Contribution stats: {stats['total']} total, {stats['current']} day current streak">
<style>
  .n {{ font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
        font-size: 30px; font-weight: 700; fill: #2f5fe0; }}
  .l {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: 12px; fill: #59636e; letter-spacing: .4px; }}
  .d {{ stroke: #d1d9e0; stroke-width: 1; }}
  .f {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 10px; fill: #8b949e; }}
  @media (prefers-color-scheme: dark) {{
    .n {{ fill: #8fd6e3; }}
    .l {{ fill: #8b949e; }}
    .d {{ stroke: #30363d; }}
  }}
</style>
{chr(10).join(parts)}
  <text x="{W/2}" y="118" class="f" text-anchor="middle">updated {stats['updated']} UTC</text>
</svg>
'''


def main():
    today = date.today()
    start = created_year(USER)
    counts = {}
    for y in range(start, today.year + 1):
        try:
            counts.update(year_counts(USER, y))
        except Exception as e:  # one bad year shouldn't kill the card
            print(f"warn: {y}: {e}", file=sys.stderr)
    if not counts:
        print("no contribution data parsed", file=sys.stderr)
        return 1

    current, longest = streaks(counts, today)
    stats = {
        "total": sum(counts.values()),
        "this_year": sum(v for d, v in counts.items() if d.startswith(str(today.year))),
        "current": current,
        "longest": longest,
        "year": today.year,
        "updated": today.isoformat(),
    }
    print("stats:", stats)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(render(stats))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
