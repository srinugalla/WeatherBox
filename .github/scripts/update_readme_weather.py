#!/usr/bin/env python3

import datetime as dt
import os
import re
from urllib.request import Request, urlopen


START = "<!-- DUBLIN_WEATHER:START -->"
END = "<!-- DUBLIN_WEATHER:END -->"


def fetch_weather():
    """
    Simple no-dependency weather fetch.
    Uses wttr.in for a compact text result.
    """
    url = "https://wttr.in/Dublin?format=3"
    req = Request(url, headers={"User-Agent": "github-actions-weather"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode().strip()


def main():
    readme_path = os.path.join(os.getcwd(), "README.md")

    if not os.path.exists(readme_path):
        raise SystemExit("README.md not found in repo root")

    with open(readme_path, "r", encoding="utf-8") as f:
        original = f.read()

    if START not in original or END not in original:
        raise SystemExit("Weather markers not found in README")

    weather = fetch_weather()

    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    new_block = f"**{weather}**\n\n_Last updated: {now}_"

    # Replace only inside markers
    pattern = re.compile(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        flags=re.DOTALL
    )

    replacement = f"{START}\n{new_block}\n{END}"

    updated = pattern.sub(replacement, original)

    # Write only if changed
    if updated != original:
        with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        print("README updated.")
    else:
        print("No changes needed.")


if __name__ == "__main__":
    main()
