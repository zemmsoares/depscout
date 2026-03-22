import json
import os
import base64

import httpx

import depscout.deps as _deps
from depscout import config as cfg


def _github_headers():
    token = os.environ.get("GITHUB_TOKEN") or cfg.get("github_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _github_api(path, params=""):
    url = f"https://api.github.com/{path.lstrip('/')}{params}"
    try:
        r = httpx.get(url, headers=_github_headers(), timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _repo_path(github_url):
    return github_url.replace("https://github.com/", "").rstrip("/")


def _fetch_repo_info(github_url):
    data = _github_api(f"repos/{_repo_path(github_url)}")
    if not data:
        return {}
    return {
        "github_description": data.get("description"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "license": data["license"]["name"] if data.get("license") else None,
        "homepage": data.get("homepage"),
        "topics": data.get("topics") or [],
        "archived": data.get("archived", False),
        "pushed_at": (data.get("pushed_at") or "")[:10],
    }


def _fetch_readme(github_url):
    data = _github_api(f"repos/{_repo_path(github_url)}/readme")
    if not data or not data.get("content"):
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    except Exception:
        return None


def _fetch_changelog(github_url, current_version):
    data = _github_api(f"repos/{_repo_path(github_url)}/releases", "?per_page=50")
    if not data:
        return []

    entries = []
    for release in data:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name", "").lstrip("v")
        body = release.get("body", "").strip()
        if tag == current_version:
            break
        if tag and body:
            entries.append({"version": release["tag_name"], "notes": body})

    return entries[:10]


def enrich():
    with open(_deps.DEPS_FILE) as f:
        deps = json.load(f)

    changed = False
    for _, info in deps.items():
        github_url = info.get("github_url")
        if not github_url:
            continue

        repo_info = _fetch_repo_info(github_url)
        if repo_info:
            info.update(repo_info)
            changed = True

        readme = _fetch_readme(github_url)
        if readme is not None:
            info["github_readme"] = readme
            changed = True

        current = info.get("current")
        latest = info.get("latest")
        is_outdated = current and latest and current != latest
        already_enriched = "changelog" in info and info.get("changelog_fetched_for_version") == latest

        if is_outdated and not already_enriched:
            info["changelog"] = _fetch_changelog(github_url, current)
            info["changelog_fetched_for_version"] = latest
            changed = True

    if changed:
        with open(_deps.DEPS_FILE, "w") as f:
            json.dump(deps, f, indent=4)

    return deps
