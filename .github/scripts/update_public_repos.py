#!/usr/bin/env python3
"""Refresh the "Open Source on GitHub" block in README.md.

Lists ONLY the account's public repositories and rewrites the content
between the <!-- PUBLIC-REPOS:START --> / <!-- PUBLIC-REPOS:END --> markers.

Safety by design:
  * Data comes from GitHub's `/users/{user}/repos` endpoint, which returns
    public repositories only. Private repos can never appear here.
  * A defensive `private == False` filter is applied as a second guard.
  * If the API can't be reached (or returns no repos), the script exits
    non-zero WITHOUT touching README.md, so the section is never blanked.

Local/dry use: set REPOS_JSON_FILE to a JSON file (a list, or an object with
an "items" array) to render from a fixture instead of calling the API.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error

USER = os.environ.get("GH_USER", "Docker-Hunterpedia")
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
        return json.loads(resp.read().decode()), resp.headers


def fetch_from_api():
    token = os.environ.get("GITHUB_TOKEN")
    repos, page = [], 1
    while True:
        url = (f"https://api.github.com/users/{USER}/repos"
               f"?per_page=100&type=owner&sort=pushed&direction=desc&page={page}")
        batch, _ = _api_get(url, token)
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected API response: {batch}")
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


def pin(repo):
    src = (f"https://github-readme-stats.vercel.app/api/pin/?username={USER}"
           f"&repo={repo}&show_owner=false&hide_border=true&bg_color={DARK}"
           f"&title_color=FFFFFF&text_color=C9D1D9&icon_color=FFFFFF")
    return (f'<a href="https://github.com/{USER}/{repo}">'
            f'<img src="{src}" alt="{repo}" height="115" /></a>')


def grid(repos):
    rows = []
    for i in range(0, len(repos), 2):
        rows.append("\n".join(pin(r) for r in repos[i:i + 2]))
    return "\n\n".join(rows)


def subsection(heading, repos):
    if not repos:
        return ""
    return f'{heading}\n\n<div align="center">\n\n{grid(repos)}\n\n</div>'


def build_block(originals, forks):
    parts = [subsection("**Original projects**", originals),
             subsection("**Forks &amp; contributions**", forks)]
    return "\n\n".join(p for p in parts if p)


def main():
    repos = load_repos()
    # public-only, exclude the profile repo itself
    repos = [r for r in repos if not r.get("private") and r.get("name") != USER]
    if not repos:
        print("ERROR: no public repositories returned; leaving README unchanged.",
              file=sys.stderr)
        return 1

    def pushed(r):
        return r.get("pushed_at") or ""

    originals = [r["name"] for r in sorted(
        (r for r in repos if not r.get("fork")), key=pushed, reverse=True)]
    forks = [r["name"] for r in sorted(
        (r for r in repos if r.get("fork")), key=pushed, reverse=True)]

    block = build_block(originals, forks)
    replacement = f"{START}\n\n{block}\n\n{END}"

    readme = open(README_PATH, encoding="utf-8").read()
    if START not in readme or END not in readme:
        print(f"ERROR: markers {START} / {END} not found in {README_PATH}.",
              file=sys.stderr)
        return 1

    new_readme = re.sub(re.escape(START) + r".*?" + re.escape(END),
                        replacement, readme, count=1, flags=re.S)

    if new_readme == readme:
        print(f"No changes. Public repos: {len(originals)} original, {len(forks)} forks.")
        return 0

    open(README_PATH, "w", encoding="utf-8").write(new_readme)
    print(f"Updated {README_PATH}. Public repos: "
          f"{len(originals)} original, {len(forks)} forks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
