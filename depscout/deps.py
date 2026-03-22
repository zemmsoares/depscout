import glob
import hashlib
import importlib.metadata
import json
import os
import pathlib
import re
import tomllib

import httpx


def _cache_dir(root: str) -> pathlib.Path:
    project_hash = hashlib.md5(str(pathlib.Path(root).resolve()).encode()).hexdigest()[:8]
    return pathlib.Path.home() / ".cache" / "depscout" / project_hash

CACHE_DIR: pathlib.Path | None = None
DEPS_FILE: str | None = None


def _parse_dep_spec(dep_str):
    dep_str = dep_str.strip()
    match = re.match(r"^([A-Za-z0-9_.-]+).*?==([A-Za-z0-9_.]+)", dep_str)
    if match:
        return match.group(1).lower(), match.group(2)
    name = re.split(r"[><=!;\[\s]", dep_str)[0].strip().lower()
    return name, None


def _parse_pyproject(path):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    deps = {}
    for dep in data.get("project", {}).get("dependencies", []):
        name, version = _parse_dep_spec(dep)
        if name and name != "python":
            deps[name] = version
    return deps


def _parse_requirements(path):
    deps = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            name, version = _parse_dep_spec(line)
            if name:
                deps[name] = version
    return deps


def _normalize_github_url(url):
    if not url:
        return None
    match = re.search(r"github\.com/([^/]+/[^/\s?#]+)", url)
    if not match:
        return None
    return f"https://github.com/{match.group(1).rstrip('/')}"


def _pypi_info(name):
    try:
        r = httpx.get(f"https://pypi.org/pypi/{name}/json", timeout=5)
        if r.status_code == 200:
            data = r.json()
            info = data["info"]
            urls = info.get("project_urls") or {}
            raw_github = next((u for u in urls.values() if "github.com" in u), None)
            github_url = _normalize_github_url(raw_github)
            classifiers = info.get("classifiers") or []
            dev_status = next((c.split(" :: ")[-1] for c in classifiers if c.startswith("Development Status")), None)
            latest_files = data["releases"].get(info["version"], [])
            last_release_date = latest_files[0]["upload_time"][:10] if latest_files else None
            docs_url = urls.get("Documentation") or urls.get("Docs") or info.get("docs_url")
            return {
                "latest": info["version"],
                "github_url": github_url,
                "docs_url": docs_url,
                "summary": info.get("summary"),
                "description": info.get("description"),
                "dev_status": dev_status,
                "last_release_date": last_release_date,
                "requires_python": info.get("requires_python"),
                "requires_dist": info.get("requires_dist") or [],
                "vulnerabilities": data.get("vulnerabilities") or [],
            }
    except Exception:
        pass
    return None


def scan(root="."):
    global CACHE_DIR, DEPS_FILE
    CACHE_DIR = _cache_dir(root)
    DEPS_FILE = str(CACHE_DIR / "deps.json")

    deps_by_name = {}

    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.exists(pyproject):
        deps_by_name.update(_parse_pyproject(pyproject))

    for req in glob.glob(os.path.join(root, "requirements*.txt")):
        deps_by_name.update(_parse_requirements(req))

    deps = {}
    for name, _ in deps_by_name.items():
        try:
            current = importlib.metadata.version(name)
        except Exception:
            current = None
        info = _pypi_info(name)
        deps[name] = {
            "current": current,
            "latest": info["latest"] if info else None,
            "github_url": info["github_url"] if info else None,
            "docs_url": info["docs_url"] if info else None,
            "summary": info["summary"] if info else None,
            "description": info["description"] if info else None,
            "dev_status": info["dev_status"] if info else None,
            "last_release_date": info["last_release_date"] if info else None,
            "requires_python": info["requires_python"] if info else None,
            "requires_dist": info["requires_dist"] if info else [],
            "vulnerabilities": info["vulnerabilities"] if info else [],
        }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DEPS_FILE, "w") as f:
        json.dump(deps, f, indent=4)

    return deps
