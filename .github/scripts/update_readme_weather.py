#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
import time
from urllib.request import Request, urlopen

START = "<!-- DUBLIN_WEATHER:START -->"
END = "<!-- DUBLIN_WEATHER:END -->"

KEEP_DAYS = 10

# Matches:
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


def escape_svg_text(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;"))


def classify_weather(weather_text: str) -> str:
    t = weather_text.lower()
    if any(k in t for k in ["thunder", "storm"]):
        return "thunder"
    if any(k in t for k in ["snow", "sleet", "blizzard"]):
        return "snow"
    if any(k in t for k in ["rain", "drizzle", "shower"]):
        return "rain"
    if any(k in t for k in ["fog", "mist", "haze"]):
        return "fog"
    if "wind" in t:
        return "wind"
    if any(k in t for k in ["overcast", "cloud"]):
        return "cloud"
    return "clear"


def write_weather_svg(path: str, theme: str, title: str, subtitle: str) -> None:
    """
    More "full-banner" continuous animations using tiled patterns that scroll
    across the entire banner. If GitHub blocks animation, it still renders nicely.
    """
    bg = {
        "clear":   ("#0b1020", "#1b3a7a"),
        "cloud":   ("#0f172a", "#334155"),
        "rain":    ("#0b1020", "#1f3b6d"),
        "wind":    ("#071018", "#123a4a"),
        "fog":     ("#0b1020", "#2b2b2b"),
        "snow":    ("#0b1020", "#2b4c7e"),
        "thunder": ("#090514", "#3b1a6b"),
    }
    c1, c2 = bg.get(theme, bg["cloud"])

    # CSS: continuous scrolling layers across full banner
    css = """
  <style>
    .title { font: 44px system-ui, -apple-system, Segoe UI, Roboto, Arial; fill: #fff; }
    .sub   { font: 24px system-ui, -apple-system, Segoe UI, Roboto, Arial; fill: #dbeafe; opacity: .95; }
    .card  { fill: rgba(0,0,0,0.28); }

    /* Smooth infinite motion across entire banner */
    @keyframes scrollDown { from { transform: translateY(-320px); } to { transform: translateY(0px); } }
    @keyframes scrollRight{ from { transform: translateX(-600px); } to { transform: translateX(0px); } }
    @keyframes scrollLeft { from { transform: translateX(0px); } to { transform: translateX(-600px); } }
    @keyframes driftDiag  { from { transform: translate(-180px,-140px); } to { transform: translate(180px,140px); } }

    /* Thunder flash */
    @keyframes flash { 0%,90%,100% { opacity: 0; } 91%,93% { opacity: .65; } 94% { opacity: .1; } 95% { opacity: .45; } }

    .layerSlow  { opacity: .22; }
    .layerMed   { opacity: .30; }
    .layerFast  { opacity: .40; }

    .rainSlow { animation: scrollDown 2.6s linear infinite; }
    .rainMed  { animation: scrollDown 1.7s linear infinite; }
    .rainFast { animation: scrollDown 1.1s linear infinite; }

    .windSlow { animation: scrollRight 7.2s linear infinite; }
    .windMed  { animation: scrollRight 4.8s linear infinite; }
    .windFast { animation: scrollRight 3.2s linear infinite; }

    .fogSlow  { animation: scrollLeft 18s ease-in-out infinite; }
    .fogMed   { animation: scrollLeft 12s ease-in-out infinite; }
    .fogFast  { animation: scrollLeft 8s  ease-in-out infinite; }

    .snowSlow { animation: driftDiag 10s linear infinite; }
    .snowMed  { animation: driftDiag 7s  linear infinite; }
    .snowFast { animation: driftDiag 5s  linear infinite; }

    .flash { animation: flash 4.8s infinite; }
  </style>
"""

    # Helper: build a tiled group by repeating shapes
    def rain_tile(x_offset: int, y_offset: int, step_x: int, step_y: int, count_x: int, count_y: int) -> str:
        lines = []
        for ix in range(count_x):
            for iy in range(count_y):
                x = x_offset + ix * step_x
                y = y_offset + iy * step_y
                lines.append(
                    f'<line x1="{x}" y1="{y}" x2="{x-8}" y2="{y+22}" stroke="#bcd6ff" stroke-width="2" />'
                )
        return "\n".join(lines)

    def snow_tile(count: int, seed_x: int, seed_y: int) -> str:
        # deterministic "random-ish" scatter
        circles = []
        x = seed_x
        y = seed_y
        for i in range(count):
            x = (x * 73 + 41) % 1200
            y = (y * 91 + 19) % 320
            r = 1 + ((x + y + i) % 3)
            circles.append(f'<circle cx="{x}" cy="{y}" r="{r}" />')
        return "\n".join(circles)

    # Patterns: repeat wider than banner so translation looks continuous
    rain1 = rain_tile(30, 10, 75, 95, 20, 6)
    rain2 = rain_tile(60, 40, 85, 90, 18, 6)
    rain3 = rain_tile(10, 20, 65, 100, 22, 6)

    wind_paths = """
    <path d="M 60 90 C 180 40, 300 140, 420 90 S 660 140, 780 90 S 1020 140, 1140 90" />
    <path d="M 20 170 C 160 120, 280 220, 420 170 S 680 220, 820 170 S 1080 220, 1220 170" />
    <path d="M 80 250 C 220 200, 340 300, 480 250 S 740 300, 880 250 S 1140 300, 1280 250" />
"""

    fog_bands = """
    <path d="M -200 110 H 1400" />
    <path d="M -260 170 H 1360" />
    <path d="M -220 230 H 1380" />
"""

    clouds = """
    <ellipse cx="260" cy="150" rx="140" ry="70"/>
    <ellipse cx="360" cy="140" rx="120" ry="60"/>
    <ellipse cx="980" cy="170" rx="160" ry="80"/>
    <ellipse cx="1080" cy="160" rx="130" ry="65"/>
"""

    sun = '<g opacity="0.35" fill="#ffd36a"><circle cx="1030" cy="120" r="55"/></g>'

    # Build animated overlay layers
    overlay = ""
    if theme == "rain":
        overlay = f"""
  <g class="layerSlow rainSlow">{rain1}</g>
  <g class="layerMed rainMed">{rain2}</g>
  <g class="layerFast rainFast">{rain3}</g>
"""
    elif theme == "wind":
        overlay = f"""
  <g class="layerSlow windSlow" fill="none" stroke="#bff3ff" stroke-width="3" stroke-linecap="round">{wind_paths}</g>
  <g class="layerMed windMed"  fill="none" stroke="#bff3ff" stroke-width="2.5" stroke-linecap="round">{wind_paths}</g>
  <g class="layerFast windFast" fill="none" stroke="#bff3ff" stroke-width="2" stroke-linecap="round">{wind_paths}</g>
"""
    elif theme == "fog":
        overlay = f"""
  <g class="layerSlow fogSlow" fill="none" stroke="#dbeafe" stroke-width="14" stroke-linecap="round">{fog_bands}</g>
  <g class="layerMed fogMed"   fill="none" stroke="#dbeafe" stroke-width="10" stroke-linecap="round">{fog_bands}</g>
  <g class="layerFast fogFast" fill="none" stroke="#dbeafe" stroke-width="8"  stroke-linecap="round">{fog_bands}</g>
"""
    elif theme == "snow":
        overlay = f"""
  <g class="layerSlow snowSlow" fill="#eaf2ff">{snow_tile(160, 17, 23)}</g>
  <g class="layerMed snowMed"   fill="#eaf2ff">{snow_tile(140, 29, 31)}</g>
  <g class="layerFast snowFast" fill="#eaf2ff">{snow_tile(120, 41, 37)}</g>
"""
    elif theme == "thunder":
        overlay = """
  <g class="flash">
    <rect width="1200" height="320" fill="#ffffff"/>
  </g>
  <g opacity="0.55">
    <polygon points="620,70 560,190 635,190 590,310 705,165 635,165" fill="#f7d34a"/>
  </g>
"""
    elif theme == "clear":
        overlay = sun
    else:  # cloud
        overlay = f'<g opacity="0.35" fill="#e2e8f0">{clouds}</g>'

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 1200 320">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c1}"/>
      <stop offset="1" stop-color="{c2}"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#000" flood-opacity="0.35"/>
    </filter>
  </defs>
{css}

  <rect width="1200" height="320" rx="22" fill="url(#g)"/>
  {overlay}

  <g filter="url(#shadow)">
    <rect x="56" y="60" width="1088" height="200" rx="18" class="card"/>
    <text x="96" y="135" class="title">{escape_svg_text(title)}</text>
    <text x="96" y="195" class="sub">{escape_svg_text(subtitle)}</text>
  </g>
</svg>
"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)


def extract_block(readme: str) -> str:
    if START not in readme or END not in readme:
        raise SystemExit("Weather markers not found in README.md")
    m = re.search(rf"{re.escape(START)}\n(.*)\n{re.escape(END)}", readme, flags=re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def build_new_block(existing_block: str, banner_line: str, new_line: str, now_date: dt.date) -> str:
    cutoff = now_date - dt.timedelta(days=KEEP_DAYS - 1)  # inclusive

    kept_lines = []
    for line in existing_block.splitlines():
        line = line.rstrip()

        if line.strip() == banner_line.strip():
            continue

        mm = LINE_RE.match(line)
        if not mm:
            if line.strip():
                kept_lines.append(line)
            continue

        d = dt.date.fromisoformat(mm.group(1))
        if d >= cutoff:
            kept_lines.append(line)

    header = f"### Dublin weather (last {KEEP_DAYS} days)"
    kept_lines = [ln for ln in kept_lines if ln != header]

    block_lines = [banner_line, "", header, new_line]
    rest = [ln for ln in kept_lines if ln != new_line and ln.strip() != header]
    block_lines.extend(rest)

    out = "\n".join(block_lines).strip() + "\n"
    return out.strip()


def update_readme(readme_path: str) -> bool:
    with open(readme_path, "r", encoding="utf-8") as f:
        original = f.read()

    now_dt = dt.datetime.now(dt.timezone.utc)
    now_stamp = now_dt.strftime("%Y-%m-%d %H:%M UTC")
    now_date = now_dt.date()

    try:
        weather = fetch_weather()
        entry = f"- {now_stamp} — {weather}"
        theme = classify_weather(weather)
    except Exception:
        weather = "⚠️ Weather fetch unavailable."
        entry = f"- {now_stamp} — {weather}"
        theme = "cloud"

    banner_path = os.path.join(os.getcwd(), "assets", "dublin-weather.svg")
    write_weather_svg(
        path=banner_path,
        theme=theme,
        title="Dublin Weather",
        subtitle=f"{weather} • Updated {now_stamp}",
    )

    banner_line = '<img src="assets/dublin-weather.svg" width="100%" alt="Dublin weather banner" />'

    existing_block = extract_block(original)
    new_block = build_new_block(existing_block, banner_line, entry, now_date)

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

    update_readme(readme_path)


if __name__ == "__main__":
    main()