"""System prompt for injecting demo events into a running CrewSafe server.

One shot:

    python -m crewsafe.prompt "lightning at 664"
    python -m crewsafe.prompt "flood at Turkey Point"
    python -m crewsafe.prompt briefing

Interactive (default, talks to http://127.0.0.1:8000):

    python -m crewsafe.prompt

Commands: lightning, flood, heat, briefing, clear. You can name a site
("flood at Port Everglades") or a distance ("lightning 6 miles from 664").
"""

from __future__ import annotations

import argparse
import sys

import httpx

DEFAULT_URL = "http://127.0.0.1:8000/api/v1"
HELP = """Commands
  lightning [at <site>] [N miles]   strike + 60s stop-work hold
  flood [at <site>]                 heavy rain + Flood Warning
  heat [at <site>]                  heat index 113°F
  briefing [at <site>]              next-day (6 PM) briefing + notification
  clear [at <site>]                 end lightning holds
  help, quit

Sites: EIA id (664) or name (Turkey Point, John R Kelly). Default is 664."""


def send(base: str, prompt: str) -> dict:
    response = httpx.post(f"{base.rstrip('/')}/simulate", json={"prompt": prompt}, timeout=30.0)
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text}
    if response.status_code >= 400:
        raise RuntimeError(body.get("detail") or f"HTTP {response.status_code}")
    return body


def show(result: dict) -> None:
    site = result.get("site_id")
    extra = f"  site {site}" if site is not None else ""
    index = result.get("hazard_index")
    extra += f"  index {index}" if index is not None else ""
    print(f"{result.get('kind', '?')}{extra}")
    print(f"  {result.get('detail', '')}")


def repl(base: str) -> None:
    print(f"Heron prompt  →  {base}")
    print("Type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            line = input("simulate> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line.lower() in {"quit", "exit", "q"}:
            return
        if line.lower() in {"help", "?"}:
            print(HELP)
            continue
        try:
            show(send(base, line))
        except (httpx.HTTPError, RuntimeError) as exc:
            print(f"  error: {exc}")
            if isinstance(exc, httpx.ConnectError):
                print("  is the backend running?  uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a simulate prompt to a running Heron backend.")
    parser.add_argument("prompt", nargs="*", help="e.g. 'lightning at 664' (omit for an interactive prompt)")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"API base (default {DEFAULT_URL})")
    args = parser.parse_args(argv)
    if args.prompt:
        try:
            show(send(args.url, " ".join(args.prompt)))
        except (httpx.HTTPError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                show(send(args.url, line))
        return 0
    repl(args.url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
