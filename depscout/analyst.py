import json
import os
import re
from datetime import date

import ollama

import depscout.deps as _deps
from depscout import config as cfg

DEFAULT_OPENAI_MODEL = "gpt-4.1"


def _build_prompt(deps):
    lines = []
    for name, info in deps.items():
        current = info.get("current", "unknown")
        latest = info.get("latest", "unknown")
        changelog = info.get("changelog", "")

        version_status = f"{current} → {latest}" if current != latest else f"{current} (up to date)"
        lines.append(f"- {name}: {version_status}")
        if info.get("summary"):
            lines.append(f"  summary: {info['summary']}")
        if info.get("github_description") and info.get("github_description") != info.get("summary"):
            lines.append(f"  github description: {info['github_description']}")
        if info.get("github_readme"):
            lines.append(f"  github readme (first 500 chars): {info['github_readme'][:500]}")
        if info.get("dev_status"):
            lines.append(f"  status: {info['dev_status']}")
        if info.get("last_release_date"):
            lines.append(f"  last release: {info['last_release_date']}")
        if info.get("pushed_at"):
            lines.append(f"  last commit: {info['pushed_at']}")
        if info.get("stars") is not None:
            lines.append(f"  stars: {info['stars']}, forks: {info.get('forks', 'unknown')}, open issues: {info.get('open_issues', 'unknown')}")
        if info.get("archived") or info.get("disabled"):
            lines.append(f"  archived: yes")
        if info.get("topics"):
            lines.append(f"  topics: {', '.join(info['topics'])}")
        if info.get("requires_python"):
            lines.append(f"  requires python: {info['requires_python']}")
        if info.get("vulnerabilities"):
            cves = ", ".join(v.get("id", "unknown") for v in info["vulnerabilities"])
            lines.append(f"  known vulnerabilities: {cves}")
        if changelog:
            for entry in changelog:
                notes = entry["notes"].replace("\r\n", "\n").replace("\r", "\n")
                notes = re.sub(r"<!--.*?-->", "", notes, flags=re.DOTALL)
                notes = re.sub(r"^#{1,6}\s+.*$", "", notes, flags=re.MULTILINE)
                notes = re.sub(r"\*\*Full Changelog\*\*.*", "", notes)
                notes = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", notes)
                notes = re.sub(r"\n{2,}", "\n", notes).strip()
                lines.append(f"  [{entry['version']}] {notes[:500]}")

    dep_summary = "\n".join(lines)

    return f"""You are a Python dependency advisor. A developer ran your tool on their project.
Today's date is {date.today()}.

Here are their dependencies:
{dep_summary}

Generate 0 to 5 concise insights that would actually help this developer.

MANDATORY — always generate an insight if any of these are true:
- The changelog contains a CVE or security advisory (non-negotiable, always flag)
- The package is significantly behind and breaking changes affect the developer

OPTIONAL — generate an insight if genuinely useful:
- A better modern alternative exists that the community now prefers
- The package is unmaintained or losing community support
- A deprecated pattern or API is in use

If none of the above apply, return an empty array [].

Rules:
- One insight per package maximum
- Every insight must include all four fields: package, title, body, category
- Do not add any fields beyond the four specified
- Return ONLY a raw JSON array — no markdown, no code fences, no explanation

Each object must have EXACTLY these four keys, no more, no less:
  "package"  — the exact package name this insight is about
  "title"    — one short sentence under 70 characters
  "body"     — 1 to 2 sentences of concrete, specific explanation
  "category" — exactly one of: outdated, alternative, pattern, unmaintained

Example of valid output format (these are NOT based on the dependencies above):
[
  {{
    "package": "example-pkg",
    "title": "example-pkg is 6 major versions behind",
    "body": "You are on 0.1.0 but the latest is 0.6.1. The client API changed significantly — generate() responses are now typed objects, not plain dicts.",
    "category": "outdated"
  }},
  {{
    "package": "another-pkg",
    "title": "another-pkg 2.23.0 has unpatched CVEs — upgrade to 2.32.4+",
    "body": "CVE-2024-47081 (credential leak via netrc) and a cert verification bypass were fixed in 2.32.x. You are 9 versions behind and exposed to these vulnerabilities.",
    "category": "outdated"
  }}
]

Now generate insights for the dependencies listed above:"""


def _parse_response(raw):
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"```[a-z]*\n?", "", raw).strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    try:
        insights = json.loads(raw[start:end])
        required = {"package", "title", "body", "category"}
        return [i for i in insights if required.issubset(i.keys())]
    except json.JSONDecodeError:
        return []


def _deduplicate(insights):
    seen = set()
    result = []
    for insight in insights:
        pkg = insight.get("package", "")
        if pkg not in seen:
            seen.add(pkg)
            result.append(insight)
    return result


def _filter_factual_errors(insights, deps):
    result = []
    for insight in insights:
        pkg = insight.get("package", "")
        info = deps.get(pkg)
        if insight.get("category") == "outdated" and info:
            if info.get("current") == info.get("latest"):
                continue
        result.append(insight)
    return result


def _resolve_ollama_model(configured_model):
    if configured_model:
        return configured_model
    try:
        installed = [m.model for m in ollama.list().models]
    except Exception:
        raise RuntimeError(
            "Could not connect to Ollama. Make sure it is running: ollama serve\n"
            "Or use OpenAI instead: depscout config openai-key sk-..."
        )
    if not installed:
        raise RuntimeError(
            "No Ollama models installed. Pull one first, for example:\n"
            "  ollama pull qwen2.5:4b\n"
            "Or use OpenAI instead: depscout config openai-key sk-..."
        )
    if len(installed) == 1:
        return installed[0]
    names = "\n".join(f"  {m}" for m in installed)
    raise RuntimeError(
        f"Multiple Ollama models installed. Pick one:\n{names}\n\n"
        f"Run: depscout config model <model-name>"
    )


def _resolve_provider():
    provider = os.environ.get("DEPSCOUT_PROVIDER") or cfg.get("provider")
    model = os.environ.get("DEPSCOUT_MODEL") or cfg.get("model")
    api_key = os.environ.get("OPENAI_API_KEY") or cfg.get("openai_key")

    if provider == "openai":
        if not api_key:
            raise RuntimeError(
                "Provider is set to 'openai' but no API key found.\n"
                "Run: depscout config openai-key sk-..."
            )
        return "openai", model or DEFAULT_OPENAI_MODEL, api_key

    return "ollama", _resolve_ollama_model(model), None


def _call_llm(prompt):
    provider, model, api_key = _resolve_provider()

    if provider == "openai":
        import httpx
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], model

    response = ollama.generate(model=model, prompt=prompt, options={"num_ctx": 8192}, think=False)
    return response["response"], model


def _save_debug(prompt, raw_response, insights, model_used):
    from datetime import datetime
    if _deps.CACHE_DIR is None:
        return
    debug_dir = _deps.CACHE_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(debug_dir / f"{timestamp}.json", "w") as f:
        json.dump({
            "model": model_used,
            "timestamp": timestamp,
            "prompt": prompt,
            "raw_response": raw_response,
            "parsed_insights": insights,
        }, f, indent=2)


def analyze(deps=None):
    if deps is None:
        with open(_deps.DEPS_FILE) as f:
            deps = json.load(f)

    prompt = _build_prompt(deps)
    raw, model_used = _call_llm(prompt)

    if not raw.strip():
        raise RuntimeError(f"Model {model_used!r} returned an empty response.")

    insights = _parse_response(raw)
    insights = _deduplicate(insights)
    insights = _filter_factual_errors(insights, deps)

    # _save_debug(prompt, raw, insights, model_used)

    with open(_deps.CACHE_DIR / "insights.json", "w") as f:
        json.dump(insights, f, indent=4)

    return insights
