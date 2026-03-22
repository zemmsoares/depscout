import importlib.metadata
import os

import typer
from rich.console import Console

from depscout.analyst import analyze
from depscout.deps import scan as collect
from depscout.enrich import enrich
from depscout import config as cfg

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Upgrade intelligence for your Python dependencies.",
    pretty_exceptions_enable=False,
)
console = Console()

CATEGORY_COLORS = {
    "outdated": "yellow",
    "alternative": "cyan",
    "pattern": "magenta",
    "unmaintained": "red",
}

CONFIG_KEYS = {
    "provider":     ("ollama or openai", "depscout config provider ollama"),
    "model":        ("model name to use", "depscout config model qwen2.5:4b"),
    "openai-key":   ("OpenAI API key",    "depscout config openai-key sk-..."),
    "github-token": ("GitHub token for richer analysis and higher rate limits", "depscout config github-token ghp_..."),
}


def _render_insights(insights):
    if not insights:
        console.print("[green]All dependencies look good.[/green]")
        return

    console.print(f"\n  [bold]{len(insights)} insights for your project[/bold]\n")

    for insight in insights:
        package = insight.get("package", "")
        title = insight.get("title", "")
        body = insight.get("body", "")
        category = insight.get("category", "")
        color = CATEGORY_COLORS.get(category, "white")

        console.print(f"  [bold]{package}[/bold]  [dim {color}]{category}[/dim {color}]")
        console.print(f"  [bold {color}]▸ {title}[/bold {color}]")
        console.print(f"    [dim]{body}[/dim]")
        console.print()


@app.command()
def scan(path: str = typer.Argument(".", help="Project root to scan")):
    """Analyze dependencies with AI and surface actionable insights."""
    with console.status("[dim]Collecting dependencies...[/dim]"):
        deps = collect(path)

    if not deps:
        console.print("[yellow]No dependencies found.[/yellow] Make sure the directory contains a pyproject.toml or requirements*.txt file.")
        raise typer.Exit(1)

    with console.status("[dim]Fetching changelogs...[/dim]"):
        enrich()

    try:
        with console.status("[dim]Analyzing with LLM...[/dim]"):
            insights = analyze()
    except RuntimeError as e:
        console.print(f"[red]Analysis failed:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        if "connection" in str(e).lower() or "refused" in str(e).lower():
            console.print("[red]Could not connect to Ollama.[/red] Make sure Ollama is running: [bold]ollama serve[/bold]")
        else:
            console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(1)

    _render_insights(insights)


@app.command()
def check(path: str = typer.Argument(".", help="Project root to scan")):
    """Check for newer versions without AI — fast and free."""
    with console.status("[dim]Fetching latest versions from PyPI...[/dim]"):
        deps = collect(path)

    if not deps:
        console.print("[yellow]No dependencies found.[/yellow] Make sure the directory contains a pyproject.toml or requirements*.txt file.")
        raise typer.Exit(1)

    outdated = {name: info for name, info in deps.items() if info.get("current") and info.get("latest") and info["current"] != info["latest"]}
    up_to_date = {name: info for name, info in deps.items() if name not in outdated}

    if not outdated:
        console.print(f"\n  [green]All {len(deps)} dependencies are up to date.[/green]\n")
        return

    pkg_width = max(len(n) for n in outdated) + 2

    console.print(f"\n  [bold]{len(outdated)} of {len(deps)} packages have updates[/bold]\n")
    for name, info in sorted(outdated.items()):
        console.print(f"  [bold]{name:<{pkg_width}}[/bold][yellow]{info['current']}[/yellow]  →  [green]{info['latest']}[/green]")

    if up_to_date:
        console.print(f"\n  [dim]{len(up_to_date)} packages are current[/dim]")
    console.print()


@app.command()
def status():
    """Show active provider, model, and configuration."""
    from depscout.analyst import _resolve_provider
    import ollama

    console.print()

    try:
        provider, model, _ = _resolve_provider()
        console.print(f"  [bold]provider[/bold]    {provider}")
        console.print(f"  [bold]model[/bold]       {model}")
    except RuntimeError as e:
        console.print(f"  [bold]provider[/bold]    [red]not configured[/red]  [dim]{e}[/dim]")

    github_token = os.environ.get("GITHUB_TOKEN") or cfg.get("github_token")
    console.print(f"  [bold]github[/bold]      {'[green]token set[/green]' if github_token else '[dim]no token — rate-limited[/dim]'}")

    openai_key = os.environ.get("OPENAI_API_KEY") or cfg.get("openai_key")
    console.print(f"  [bold]openai key[/bold]  {'[green]set[/green]' if openai_key else '[dim]not set[/dim]'}")

    try:
        installed = [m.model for m in ollama.list().models]
        models_str = ", ".join(installed) if installed else "no models installed"
        console.print(f"  [bold]ollama[/bold]      [green]running[/green]  [dim]{models_str}[/dim]")
    except Exception:
        console.print(f"  [bold]ollama[/bold]      [dim]not running[/dim]")

    console.print()
    console.print(f"  [dim]config file: {cfg.CONFIG_FILE}[/dim]")
    console.print()


@app.command()
def config(
    key: str = typer.Argument(None, help="Config key"),
    value: str = typer.Argument(None, help="Value to set"),
):
    """Set a configuration value.

    Available keys:

      provider      ollama or openai
      model         model name (e.g. qwen2.5:4b or gpt-4o-mini)
      openai-key    your OpenAI API key
      github-token  GitHub token for richer analysis

    Examples:

      depscout config provider openai
      depscout config model gpt-4o-mini
      depscout config openai-key sk-...
      depscout config github-token ghp_...
    """
    if key is None or value is None:
        console.print()
        console.print("  [bold]Available config keys:[/bold]\n")
        key_width = max(len(k) for k in CONFIG_KEYS) + 2
        for k, (desc, example) in CONFIG_KEYS.items():
            console.print(f"  [bold]{k:<{key_width}}[/bold][dim]{desc}[/dim]")
            console.print(f"  {' ' * key_width}[dim italic]{example}[/dim italic]")
            console.print()
        raise typer.Exit()

    cfg.set(key.replace("-", "_"), value)
    console.print(f"[dim]{key} saved.[/dim]")


@app.command()
def version():
    """Show depscout version."""
    try:
        v = importlib.metadata.version("depscout")
    except importlib.metadata.PackageNotFoundError:
        v = "dev"
    console.print(f"depscout {v}")


def entrypoint():
    app()
