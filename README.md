# depscout

[![PyPI version](https://img.shields.io/pypi/v/depscout.svg)](https://pypi.org/project/depscout/)

Scans your Python project dependencies and uses an LLM to flag what's worth acting on - outdated packages, unmaintained libraries, and better alternatives.

![depscout-demo-1](https://github.com/user-attachments/assets/7a8d423f-3306-4446-95e4-aadd574c3f12)

![depscout-check-demo-1](https://github.com/user-attachments/assets/85e29aeb-dba4-4dc3-a86a-6231b6078179)

## Install

```bash
pip install depscout
# or
uv tool install depscout
```

## Setup

**Ollama (Local):**
```bash
depscout config provider ollama
ollama pull qwen2.5:4b
depscout config model qwen2.5:4b
```

**OpenAI:**
```bash
depscout config provider openai
depscout config openai-key sk-...
depscout config model gpt-4o-mini
```

**GitHub token (optional):** avoids rate limits if you have many dependencies
```bash
depscout config github-token ghp_...
```

## Commands

```
depscout scan [PATH]        AI analysis — surfaces insights
depscout check [PATH]       Version check only, no AI
depscout status             Show current config
depscout config             List all config options
```

## Contributing
PRs are welcome!
