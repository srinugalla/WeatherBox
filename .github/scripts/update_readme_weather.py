#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
import time
from urllib.request import Request, urlopen

START = "<!-- DUBLIN_WEATHER:START -->"
END = "<!-- DUBLIN_WEATHER:END -->"

# Keep entries newer than this many days (rolling window)
KEEP_DAYS = 10

# Matches a single log line like:
# - 2026-02-24 09:00 UTC — Dublin: 🌦 +8°C
LINE_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC — (.*)$")


def http_get(url: str, timeout: int = 8, retries: int = 2, backoff_sec: float = 1.0) -> str:
    last_err = None
    for i in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "github-actions-weather-bot"})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(backoff_sec * (i + 1))
    raise last_err


def weather_from_wttr() -> str:
    txt = http_get("https://wttr.in/Dublin?format=3", timeout=6, retries=2).strip()
    if not txt:
        raise RuntimeError("wttr returned empty response")
    return txt


def weather_from_open_meteo() -> str:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=53.3498&longitude=-6.2603"
        "&current=temperature_2m,weather_code,wind_speed_10m"
        "&timezone=UTC"
    )
    raw = http_get(url, timeout=8, retries=2)
    data = json.loads(raw)
    cur = data.get("current") or {}
    temp = cur.get("temperature_2m")
    wind = cur.get("wind_speed_10m")
    code = cur.get("weather_code")

    code_map = {
        0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Rime fog",
        51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain",
        71: "Light snow", 73: "Snow", 75: "Heavy snow",
        80: "Rain showers", 81: "Showers", 82: "Violent showers",
        95: "Thunderstorm",
    }
    cond = code_map.get(code, f"Weather code {code}")

    if temp is None:
        raise RuntimeError("open-meteo missing temperature")

    parts = [f"Dublin: {cond}, {temp}°C"]
    if wind is not None:
        parts.append(f"Wind {wind} km/h")
    return " | ".join(parts)


def fetch_weather() -> str:
    try:
        return weather_from_wttr()
    except Exception:
        return weather_from_open_meteo()


def extract_block(readme: str) -> str:
    if START not in readme or END not in readme:
        raise SystemExit("Weather markers not found in README.md")
    m = re.search(rf"{re.escape(START)}\n(.*)\n{re.escape(END)}", readme, flags=re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def build_new_block(existing_block: str, new_line: str, now_date: dt.date) -> str:
    # Parse existing lines, keep only those within KEEP_DAYS window
    kept_lines = []
    cutoff = now_date - dt.timedelta(days=KEEP_DAYS - 1)  # inclusive rolling window

    for line in existing_block.splitlines():
        line = line.rstrip()
        mm = LINE_RE.match(line)
        if not mm:
            # keep non-log lines (like headers) as-is
            if line.strip():
                kept_lines.append(line)
            continue

        d = dt.date.fromisoformat(mm.group(1))
        if d >= cutoff:
            kept_lines.append(line)

    # Ensure a header line
    header = "### Dublin weather (last 10 days)"
    if not kept_lines or kept_lines[0] != header:
        # remove any duplicate header occurrences
        kept_lines = [ln for ln in kept_lines if ln != header]
        kept_lines.insert(0, header)

  
    # Also ensures we don't duplicate if workflow re-runs quickly with same timestamp
    if len(kept_lines) >= 2 and kept_lines[1] == new_line:
        return "\n".join(kept_lines)

    kept_lines.insert(1, new_line)
    return "\n".join(kept_lines).strip()


def update_readme(readme_path: str) -> bool:
    with open(readme_path, "r", encoding="utf-8") as f:
        original = f.read()

    now_dt = dt.datetime.now(dt.timezone.utc)
    now_stamp = now_dt.strftime("%Y-%m-%d %H:%M UTC")
    now_date = now_dt.date()

    try:
        weather = fetch_weather()
        entry = f"- {now_stamp} — {weather}"
    except Exception:
        entry = f"- {now_stamp} — ⚠️ Weather fetch unavailable."

    existing_block = extract_block(original)
    new_block = build_new_block(existing_block, entry, now_date)

    pattern = re.compile(rf"{re.escape(START)}.*?{re.escape(END)}", flags=re.DOTALL)
    replacement = f"{START}\n{new_block}\n{END}"
    updated = pattern.sub(replacement, original)

    if updated == original:
        print("No changes needed.")
        return False

    with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)

    print("README.md updated.")
    return True


def main() -> None:
    readme_path = os.path.join(os.getcwd(), "README.md")
    if not os.path.exists(readme_path):
        raise SystemExit("README.md not found in repo root")

    changed = update_readme(readme_path)
    # Exit success regardless; commit step decides based on git diff
    if not changed:
        print("Nothing changed.")


if __name__ == "__main__":
    main()
