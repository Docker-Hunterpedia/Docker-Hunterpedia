#!/usr/bin/env python3
"""Refresh the "Open Source on GitHub" block in README.md.

Lists the account's PUBLIC repositories (and those of any configured
organizations) and rewrites the content between the
<!-- PUBLIC-REPOS:START --> / <!-- PUBLIC-REPOS:END --> markers.

Sources:
  * https://api.github.com/users/<GH_USER>/repos   (public only by design)
  * https://api.github.com/orgs/<org>/repos         for each org in GH_ORGS

Safety by design:
  * Only public repositories are ever rendered (a defensive `private == False`
    filter is applied on top of the public endpoints).
  * If the API can't be reached (or returns no repos), the script exits
    non-zero WITHOUT touching README.md, so the section is never blanked.

Local/dry use: set REPOS_JSON_FILE to a JSON file (a list, or an object with
an "items" array of GitHub repo objects) to render from a fixture instead of
calling the API.
"""
import json
import os
import re
import sys
import urllib.request

USER = os.environ.get("GH_USER", "Docker-Hunterpedia")
ORGS = [o.strip() for o in os.environ.get("GH_ORGS", "").split(",") if o.strip()]
README_PATH = os.environ.get("README_PATH", "README.md")
DARK = "0D1117"
START = "<!-- PUBLIC-REPOS:START -->"
END = "<!-- PUBLIC-REPOS:END -->"


def _api_get(url, token):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-readme")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_from_api():
    token = os.environ.get("GITHUB_TOKEN")
    sources = [f"users/{USER}"] + [f"orgs/{o}" for o in ORGS]
    repos = []
    for src in sources:
        page = 1
        while True:
            url = (f"https://api.github.com/{src}/repos"
                   f"?per_page=100&sort=pushed&direction=desc&page={page}")
            batch = _api_get(url, token)
            if not isinstance(batch, list):
                raise RuntimeError(f"Unexpected API response for {src}: {batch}")
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return repos


def load_repos():
    fixture = os.environ.get("REPOS_JSON_FILE")
    if fixture:
        data = json.load(open(fixture))
        return data["items"] if isinstance(data, dict) else data
    return fetch_from_api()


def normalize(r):
    full = r.get("full_name") or f'{(r.get("owner") or {}).get("login", "")}/{r.get("name", "")}'
    return {
        "full": full,
        "owner": full.split("/", 1)[0],
        "private": bool(r.get("private")),
        "fork": bool(r.get("fork")),
        "pushed": r.get("pushed_at") or "",
    }


def pin(full):
    owner, repo = full.split("/", 1)
    src = (f"https://github-readme-stats.vercel.app/api/pin/?username={owner}"
           f"&repo={repo}&show_owner=false&hide_border=true&bg_color={DARK}"
           f"&title_color=FFFFFF&text_color=C9D1D9&icon_color=FFFFFF")
    return (f'<a href="https://github.com/{full}">'
            f'<img src="{src}" alt="{repo}" height="115" /></a>')


def grid(fulls):
    rows = []
    for i in range(0, len(fulls), 2):
        rows.append("\n".join(pin(f) for f in fulls[i:i + 2]))
    return "\n\n".join(rows)


def subsection(heading, fulls):
    if not fulls:
        return ""
    return f'{heading}\n\n<div align="center">\n\n{grid(fulls)}\n\n</div>'


def main():
    repos = [normalize(r) for r in load_repos()]
    # public only, excluding the profile repo itself
    repos = [r for r in repos if not r["private"] and r["full"] != f"{USER}/{USER}"]
    if not repos:
        print("ERROR: no public repositories returned; leaving README unchanged.",
              file=sys.stderr)
        return 1

    def by_pushed(xs):
        return sorted(xs, key=lambda r: r["pushed"], reverse=True)

    originals = [r["full"] for r in by_pushed(
        [r for r in repos if r["owner"] == USER and not r["fork"]])]
    org_repos = [r["full"] for r in by_pushed(
        [r for r in repos if r["owner"] != USER and not r["fork"]])]
    forks = [r["full"] for r in by_pushed([r for r in repos if r["fork"]])]

    block = "\n\n".join(p for p in [
        subsection("**Original projects**", originals),
        subsection("**Organizations**", org_repos),
        subsection("**Forks &amp; contributions**", forks),
    ] if p)

    replacement = f"{START}\n\n{block}\n\n{END}"
    readme = open(README_PATH, encoding="utf-8").read()
    if START not in readme or END not in readme:
        print(f"ERROR: markers not found in {README_PATH}.", file=sys.stderr)
        return 1

    new_readme = re.sub(re.escape(START) + r".*?" + re.escape(END),
                        replacement, readme, count=1, flags=re.S)

    summary = (f"{len(originals)} original, {len(org_repos)} org, "
               f"{len(forks)} forks")
    if new_readme == readme:
        print(f"No changes. Public repos: {summary}.")
        return 0

    open(README_PATH, "w", encoding="utf-8").write(new_readme)
    print(f"Updated {README_PATH}. Public repos: {summary}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
