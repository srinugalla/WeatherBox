#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
import time
from urllib.request import Request, urlopen

START = "<!-- DUBLIN_WEATHER:START -->"
END = "<!-- DUBLIN_WEATHER:END -->"


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
    # compact: "Dublin: 🌦 +8°C"
    txt = http_get("https://wttr.in/Dublin?format=3", timeout=6, retries=2).strip()
    if not txt:
        raise RuntimeError("wttr returned empty response")
    return txt


def weather_from_open_meteo() -> str:
    # Dublin approx coords
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

    # minimal code mapping (enough for a nice README line)
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
    # Try provider A, then provider B
    try:
        return weather_from_wttr()
    except Exception:
        return weather_from_open_meteo()


def update_readme(readme_path: str) -> None:
    with open(readme_path, "r", encoding="utf-8") as f:
        original = f.read()

    if START not in original or END not in original:
        raise SystemExit("Weather markers not found in README.md")

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        weather = fetch_weather()
        new_block = f"**{weather}**\n\n_Last updated: {now}_"
    except Exception as e:
        # Do NOT fail the workflow; write a useful message and still commit
        new_block = f"⚠️ Weather fetch unavailable.\n\n_Last attempt: {now}_"

    pattern = re.compile(rf"{re.escape(START)}.*?{re.escape(END)}", flags=re.DOTALL)
    replacement = f"{START}\n{new_block}\n{END}"
    updated = pattern.sub(replacement, original)

    if updated == original:
        print("No changes needed.")
        return

    with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)

    print("README.md updated.")


def main() -> None:
    readme_path = os.path.join(os.getcwd(), "README.md")
    if not os.path.exists(readme_path):
        raise SystemExit("README.md not found in repo root")

    update_readme(readme_path)


if __name__ == "__main__":
    main()
