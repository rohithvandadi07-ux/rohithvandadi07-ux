"""
Generates a hacker-terminal-style SVG stats card from live GitHub data.
Run inside GitHub Actions where GITHUB_TOKEN and GH_USERNAME are provided as env vars.
"""

import os
import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

USERNAME = os.environ.get("GH_USERNAME", "rohithvandadi07-ux")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT_FILE = os.environ.get("OUT_FILE", "github-terminal-stats.svg")

API_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
    repositories(first: 100, ownerAffiliation: OWNER, isFork: false) {
      totalCount
      nodes {
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name }
          }
        }
      }
    }
  }
}
"""


def gh_graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USERNAME,
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_streaks(weeks):
    days = []
    for w in weeks:
        for d in w["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort(key=lambda x: x[0])

    longest = 0
    current = 0
    running = 0
    today = datetime.now(timezone.utc).date().isoformat()

    for date_str, count in days:
        if count > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    # current streak: walk backwards from most recent day
    current = 0
    for date_str, count in reversed(days):
        if date_str > today:
            continue
        if count > 0:
            current += 1
        else:
            break

    return current, longest


def top_languages(repo_nodes, top_n=3):
    totals = defaultdict(int)
    for repo in repo_nodes:
        for edge in repo["languages"]["edges"]:
            totals[edge["node"]["name"]] += edge["size"]
    total_size = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [(name, round(size / total_size * 100)) for name, size in ranked]


def esc(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_svg(name, login, followers, commits, prs, total_contribs,
              current_streak, longest_streak, repo_count, langs):
    # lines: each is (text, kind) where kind is "prompt" | "text" | "cursor" | "bar" | "blank"
    lines = []
    lines.append(("$ whoami", "prompt"))
    lines.append((f"{name} (@{login}) \u2014 AI/ML & Cybersecurity", "text"))
    lines.append(("", "blank"))
    lines.append(("$ git log --stat --all", "prompt"))
    lines.append((f"{total_contribs} contributions \u00b7 {commits} commits \u00b7 {prs} PRs opened", "text"))
    lines.append((f"contributed to {repo_count} repositories", "text"))
    lines.append(("", "blank"))
    lines.append(("$ streak --status", "prompt"))
    lines.append((f"current: {current_streak} day(s)   longest: {longest_streak} day(s)", "text"))
    lines.append(("", "blank"))
    lines.append(("$ top --languages", "prompt"))
    for lang, pct in langs:
        lines.append((("bar", lang, pct), "bar"))
    lines.append(("", "blank"))
    lines.append(("$ followers --count", "prompt"))
    lines.append((f"{followers} followers", "text"))
    lines.append(("", "blank"))
    lines.append(("$ _", "cursor"))

    line_height = 22
    top_padding = 56
    width = 760
    height = top_padding + line_height * len(lines) + 30

    svg_lines = []
    svg_lines.append(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    svg_lines.append(f'''
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0f0c29"/>
      <stop offset="100%" stop-color="#050508"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" rx="10" fill="url(#bg)" stroke="#302b63" stroke-width="1.5"/>
  <rect x="0" y="0" width="{width}" height="32" rx="10" fill="#1a1a2e"/>
  <rect x="0" y="20" width="{width}" height="12" fill="#1a1a2e"/>
  <circle cx="22" cy="16" r="6" fill="#ff5f56"/>
  <circle cx="44" cy="16" r="6" fill="#ffbd2e"/>
  <circle cx="66" cy="16" r="6" fill="#27c93f"/>
  <text x="{width/2}" y="21" fill="#8b8ba7" font-family="monospace" font-size="12" text-anchor="middle">{login}@github: ~</text>
''')

    bar_max_width = 220
    bar_height = 10

    for i, (content, kind) in enumerate(lines):
        y = top_padding + i * line_height

        if kind == "blank":
            continue

        if kind == "prompt":
            svg_lines.append(
                f'  <text x="24" y="{y}" fill="#a78bfa" font-family="Courier New, monospace" '
                f'font-size="14" xml:space="preserve">{esc(content)}</text>'
            )
        elif kind == "text":
            svg_lines.append(
                f'  <text x="24" y="{y}" fill="#c8c8e8" font-family="Courier New, monospace" '
                f'font-size="14" xml:space="preserve">{esc(content)}</text>'
            )
        elif kind == "bar":
            _, lang, pct = content
            label_y = y
            bar_y = y - 11
            filled_w = round(bar_max_width * pct / 100)
            svg_lines.append(
                f'  <text x="24" y="{label_y}" fill="#c8c8e8" font-family="Courier New, monospace" '
                f'font-size="14" xml:space="preserve">{esc(lang):<11}</text>'
            )
            bar_x = 160
            svg_lines.append(
                f'  <rect x="{bar_x}" y="{bar_y}" width="{bar_max_width}" height="{bar_height}" '
                f'rx="2" fill="#22223a"/>'
            )
            svg_lines.append(
                f'  <rect x="{bar_x}" y="{bar_y}" width="{filled_w}" height="{bar_height}" '
                f'rx="2" fill="#39ff14"/>'
            )
            svg_lines.append(
                f'  <text x="{bar_x + bar_max_width + 12}" y="{label_y}" fill="#c8c8e8" '
                f'font-family="Courier New, monospace" font-size="14">{pct}%</text>'
            )
        elif kind == "cursor":
            svg_lines.append(
                f'  <text x="24" y="{y}" fill="#39ff14" font-family="Courier New, monospace" '
                f'font-size="14" xml:space="preserve">$</text>'
            )
            svg_lines.append(
                f'  <rect x="42" y="{y - 12}" width="9" height="15" fill="#39ff14">'
                f'<animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/>'
                f'</rect>'
            )

    svg_lines.append("</svg>")
    svg_lines.insert(1, "")  # keep first insert placement simple
    return svg_lines[0] + "\n" + "\n".join(svg_lines[2:])


def main():
    data = gh_graphql(QUERY, {"login": USERNAME})
    if "errors" in data:
        raise SystemExit(f"GraphQL errors: {data['errors']}")

    user = data["data"]["user"]
    cc = user["contributionsCollection"]
    calendar = cc["contributionCalendar"]

    current_streak, longest_streak = compute_streaks(calendar["weeks"])
    langs = top_languages(user["repositories"]["nodes"])

    svg = build_svg(
        name=user["name"] or user["login"],
        login=user["login"],
        followers=user["followers"]["totalCount"],
        commits=cc["totalCommitContributions"],
        prs=cc["totalPullRequestContributions"],
        total_contribs=calendar["totalContributions"],
        current_streak=current_streak,
        longest_streak=longest_streak,
        repo_count=user["repositories"]["totalCount"],
        langs=langs,
    )

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
