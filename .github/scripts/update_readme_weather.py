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
    # compact: "Dublin: 🌦 +8°C"
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
    Animated SVG banner (CSS-based). Note: GitHub's README renderer may not
    animate SVG consistently everywhere; it will still display as a static banner
    if animation is blocked.
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

    css = """
  <style>
    .title { font: 44px system-ui, -apple-system, Segoe UI, Roboto, Arial; fill: #fff; }
    .sub   { font: 24px system-ui, -apple-system, Segoe UI, Roboto, Arial; fill: #dbeafe; opacity: .95; }
    .card  { fill: rgba(0,0,0,0.28); }

    /* Animations (GitHub may or may not run these; static fallback still looks good) */
    @keyframes rainFall { from { transform: translateY(-70px); } to { transform: translateY(80px); } }
    @keyframes windMove { from { transform: translateX(-90px); } to { transform: translateX(90px); } }
    @keyframes fogSlide { from { transform: translateX(-140px); } to { transform: translateX(140px); } }
    @keyframes snowDrift{ from { transform: translate(0,-30px); } to { transform: translate(50px,45px); } }
    @keyframes flash    { 0%,92%,100% { opacity: 0; } 93%,96% { opacity: .65; } 97% { opacity: .12; } }

    .rain { animation: rainFall 1.1s linear infinite; }
    .wind { animation: windMove 2.6s ease-in-out infinite alternate; }
    .fog  { animation: fogSlide 7.5s ease-in-out infinite alternate; }
    .snow { animation: snowDrift 3.8s linear infinite; }
    .flash{ animation: flash 4.8s infinite; }
  </style>
"""

    # Prebuild decorative geometry
    rain_lines = "\n".join(
        f'<line x1="{x}" y1="{y}" x2="{x-6}" y2="{y+18}" stroke="#bcd6ff" stroke-width="2" />'
        for x in range(40, 1200, 70)
        for y in range(40, 320, 90)
    )

    wind_paths = """
    <path d="M 60 90 C 140 65, 200 115, 280 90" />
    <path d="M 120 160 C 200 135, 260 185, 340 160" />
    <path d="M 40 230 C 140 205, 220 255, 320 230" />
    <path d="M 180 260 C 280 235, 360 285, 480 260" />
"""

    fog_bands = """
    <path d="M 70 110 H 1130" />
    <path d="M 120 170 H 1080" />
    <path d="M 90 230 H 1110" />
"""

    snow_flakes = "\n".join(
        f'<circle cx="{x}" cy="{y}" r="{r}" />'
        for x, y, r in [(90,80,3),(180,140,2),(260,70,2),(380,190,3),(520,110,2),
                        (660,80,3),(780,170,2),(920,120,3),(1040,200,2),(1140,90,3)]
    )

    clouds = """
    <ellipse cx="260" cy="150" rx="140" ry="70"/>
    <ellipse cx="360" cy="140" rx="120" ry="60"/>
    <ellipse cx="980" cy="170" rx="160" ry="80"/>
    <ellipse cx="1080" cy="160" rx="130" ry="65"/>
"""

    # Choose overlay
    overlay = ""
    if theme == "rain":
        overlay = f'<g class="rain" opacity="0.35">{rain_lines}</g>'
    elif theme == "wind":
        overlay = f'<g class="wind" opacity="0.35" fill="none" stroke="#bff3ff" stroke-width="3" stroke-linecap="round">{wind_paths}</g>'
    elif theme == "fog":
        overlay = f'<g class="fog" opacity="0.35" fill="none" stroke="#dbeafe" stroke-width="10" stroke-linecap="round">{fog_bands}</g>'
    elif theme == "snow":
        overlay = f'<g class="snow" opacity="0.45" fill="#eaf2ff">{snow_flakes}</g>'
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
        overlay = '<g opacity="0.35" fill="#ffd36a"><circle cx="1030" cy="120" r="55"/></g>'
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

        # Drop any previous banner line; we'll always re-add it at top.
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