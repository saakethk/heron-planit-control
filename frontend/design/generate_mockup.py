"""Generates crewsafe-mockup.svg, an iPhone mockup board that imports into Figma
as editable layers (File > Import, or drag the SVG onto the canvas).

Run from anywhere: python3 frontend/design/generate_mockup.py
"""

import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GEOJSON = REPO / "model/data/power_plant_data/florida_state_boundary.geojson"
OUT = HERE / "crewsafe-mockup.svg"

W, H = 393, 852  # iPhone 15 Pro points
GAP = 96
TOP = 190
BOARD_W = 3 * W + 4 * GAP
BOARD_H = TOP + H + 130

FONT = "SF Pro Display, -apple-system, Helvetica Neue, Inter, Arial, sans-serif"

BG = "#07090D"
CARD = "#11151C"
STROKE = "#1E2530"
TEXT = "#F5F7FA"
TEXT2 = "#8B95A7"
TEXT3 = "#566072"
BLUE = "#0A84FF"
RED = "#FF453A"
ORANGE = "#FF9F0A"
YELLOW = "#FFD60A"
GREEN = "#30D158"

# Mirrors frontend/ios/CrewSafe/Models/MockData.swift
SITES = [
    (617, "Port Everglades", "Broward", 26.0856, -80.1253, 7.8, ("bolt", "Lightning 8.9")),
    (627, "Bayboro", "Pinellas", 27.758056, -82.63528, 6.9, ("flood", "Flood 8.1")),
    (54466, "Orlando Cogen LP", "Orange", 28.442623, -81.41234, 5.8, ("heat", "Heat 7.9")),
    (56518, "South Energy Center", "Alachua", 29.6383, -82.34, 4.7, ("wildlife", "Wildlife 6.2")),
    (619, "Riviera", "Palm Beach", 26.7653, -80.0525, 4.1, ("flood", "Flood 5.0")),
    (50875, "McKay Bay Facility", "Hillsborough", 27.949528, -82.42118, 3.6, ("soil", "Soil 4.8")),
    (136, "Seminole (FL)", "Putnam", 29.733056, -81.63278, 2.9, ("fire", "Wildfire 3.8")),
    (64546, "Wynwood Energy Storage", "Miami Dade", 25.798978, -80.1971, 1.8, ("heat", "Heat 2.4")),
]


def risk(index):
    """Same bands as RiskLevel(index:) in Models.swift."""
    if index < 3:
        return "Low", GREEN
    if index < 5.5:
        return "Moderate", YELLOW
    if index < 8:
        return "High", ORANGE
    return "Severe", RED


# --- primitives -------------------------------------------------------------

def text(x, y, s, size=15, weight=400, fill=TEXT, anchor="start", ls=0, opacity=1):
    extra = f' letter-spacing="{ls}"' if ls else ""
    extra += f' opacity="{opacity}"' if opacity != 1 else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def rect(x, y, w, h, rx=0, fill="none", stroke=None, sw=1, opacity=1, extra=""):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    o = f' opacity="{opacity}"' if opacity != 1 else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"{s}{o} {extra}/>'


def circle(cx, cy, r, fill="none", stroke=None, sw=1, opacity=1, extra=""):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    o = f' opacity="{opacity}"' if opacity != 1 else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"{s}{o} {extra}/>'


def group(name, body, transform=""):
    t = f' transform="{transform}"' if transform else ""
    return f'<g id="{escape(name)}"{t}>' + "".join(body) + "</g>"


# 24x24 glyphs, drawn as strokes so they scale cleanly.
ICONS = {
    "bolt": ('<path d="M13.5 2 4.5 13.5h6.5L10 22l9.5-12H13z" fill="{c}"/>', False),
    "heat": ('<path d="M10 4a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0z" fill="none" stroke="{c}" stroke-width="2"/>'
             '<circle cx="12" cy="17" r="2" fill="{c}"/><path d="M12 9v7" stroke="{c}" stroke-width="2"/>', False),
    "flood": ('<path d="M12 3s-6 7-6 11a6 6 0 0 0 12 0c0-4-6-11-6-11z" fill="{c}"/>', False),
    "wildlife": ('<circle cx="7" cy="9" r="2.2" fill="{c}"/><circle cx="17" cy="9" r="2.2" fill="{c}"/>'
                 '<circle cx="10" cy="5" r="2.2" fill="{c}"/><circle cx="14" cy="5" r="2.2" fill="{c}"/>'
                 '<path d="M12 11c-3 0-5.5 4-5.5 6.5 0 2 1.8 2.5 3 2s1.6-.6 2.5-.6 1.4.2 2.5.6 3 0 3-2c0-2.5-2.5-6.5-5.5-6.5z" fill="{c}"/>', False),
    "soil": ('<path d="M3 8h18M3 13h18M3 18h18" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-dasharray="3 3"/>', False),
    "fire": ('<path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 0 2 1 3 2 3-1-3 0-6 .5-9z" fill="{c}"/>', False),
    "crew": ('<circle cx="9" cy="8" r="3.2" fill="{c}"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6z" fill="{c}"/>'
             '<circle cx="16.5" cy="9" r="2.6" fill="{c}" opacity=".6"/><path d="M15.5 14.2c3 .1 5.5 2.4 5.5 5.8h-4.5" fill="{c}" opacity=".6"/>', False),
    "shield": ('<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z" fill="{c}"/>', False),
    "pin": ('<path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z" fill="{c}"/><circle cx="12" cy="9" r="2.6" fill="#07090D"/>', False),
    "search": ('<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="{c}" stroke-width="2.2"/><path d="m15.5 15.5 5 5" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>', False),
    "layers": ('<path d="m12 3 9 5-9 5-9-5z" fill="{c}"/><path d="m3 12.5 9 5 9-5M3 16.5l9 5 9-5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>', False),
    "locate": ('<path d="M21 3 3 10.5l7.5 3 3 7.5z" fill="{c}"/>', False),
    "gauge": ('<path d="M3.5 17a9 9 0 1 1 17 0" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/><path d="m12 15 4.5-6" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="15" r="2" fill="{c}"/>', False),
    "map": ('<path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20z" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/><path d="M9 4v13.5M15 6.5V20" stroke="{c}" stroke-width="2"/>', False),
    "bell": ('<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" fill="{c}"/><path d="M10 20.5a2 2 0 0 0 4 0" fill="{c}"/>', False),
    "camera": ('<path d="M4 7h3.5L9 4.5h6L16.5 7H20a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z" fill="{c}"/><circle cx="12" cy="13" r="3.6" fill="#07090D"/>', False),
    "flashlight": ('<path d="M8 2h8v4l-2 4v11a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1V10L8 6z" fill="{c}"/>', False),
    "lock": ('<rect x="5" y="10.5" width="14" height="10.5" rx="2.5" fill="{c}"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" fill="none" stroke="{c}" stroke-width="2.2"/>', False),
    "chevron": ('<path d="m9 5 7 7-7 7" fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>', False),
    "sort": ('<path d="M7 4v16m0 0-3-3m3 3 3-3M17 20V4m0 0-3 3m3-3 3 3" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>', False),
    "up": ('<path d="M12 19V5m0 0-6 6m6-6 6 6" fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>', False),
    "sun": ('<circle cx="12" cy="12" r="4.5" fill="{c}"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="{c}" stroke-width="2" stroke-linecap="round"/>', False),
}


def icon(name, x, y, size, color):
    body = ICONS[name][0].replace("{c}", color)
    return f'<g id="icon/{name}" transform="translate({x:.1f} {y:.1f}) scale({size / 24:.4f})">{body}</g>'


def ring(cx, cy, r, frac):
    """Clockwise progress ring path starting at 12 o'clock."""
    a = 2 * math.pi * min(frac, 0.9999)
    x1, y1 = cx + r * math.sin(a), cy - r * math.cos(a)
    large = 1 if frac > 0.5 else 0
    return f"M{cx:.2f} {cy - r:.2f} A{r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}"


# --- shared chrome ----------------------------------------------------------

def status_bar(dark_text=False):
    c = "#000" if dark_text else TEXT
    bars = "".join(rect(300 + i * 4.6, 25 - i * 2.2, 3, 4.5 + i * 2.2, 0.8, c) for i in range(4))
    wifi = (f'<path d="M327 22.5a9 9 0 0 1 12.5 0M329.3 25a5.6 5.6 0 0 1 7.9 0" fill="none" stroke="{c}" '
            f'stroke-width="1.8" stroke-linecap="round"/><circle cx="333.25" cy="28" r="1.5" fill="{c}"/>')
    battery = (rect(346, 19.5, 25, 12, 3.5, "none", c, 1, 0.45) + rect(348, 21.5, 19, 8, 2, c)
               + rect(372, 23.5, 1.6, 4, 0.8, c, opacity=0.45))
    return group("Status Bar", [
        text(54, 31, "9:41", 17, 600, c, "middle"),
        bars, wifi, battery,
        rect(133, 11, 126, 37, 18.5, "#000"),
    ])


def home_indicator(color=TEXT):
    return rect(129.5, 838, 134, 5, 2.5, color)


def tab_bar(active):
    tabs = [("Today", "gauge"), ("Sites", "map"), ("Alerts", "bell"), ("Report", "camera")]
    out = [rect(0, 769, W, 83, 0, "#0C0F14", opacity=0.96), rect(0, 769, W, 0.5, 0, "#2A313C")]
    for i, (label, ic) in enumerate(tabs):
        cx = W / 4 * (i + 0.5)
        c = BLUE if label == active else "#6B7385"
        out.append(icon(ic, cx - 13, 778, 26, c))
        out.append(text(cx, 818, label, 10, 500, c, "middle"))
        if label == "Alerts":
            out.append(circle(cx + 14, 781, 9, RED))
            out.append(text(cx + 14, 785, "3", 12, 600, "#fff", "middle"))
    out.append(home_indicator())
    return group("Tab Bar", out)


def phone(name, x, y, screen):
    clip = f"clip-{name.replace(' ', '-').lower()}"
    return group(name, [
        f'<defs><clipPath id="{clip}"><rect width="{W}" height="{H}" rx="55"/></clipPath></defs>',
        rect(-12, -12, W + 24, H + 24, 67, "#1A1D22", "#3A3F47", 1.5),
        rect(-4, -4, W + 8, H + 8, 59, "#000"),
        f'<g clip-path="url(#{clip})">', screen, "</g>",
    ], f"translate({x} {y})")


# --- screen 1: lock screen with notification banners ------------------------

def notification(y, h, tag, tag_color, when, title, lines, icon_name, icon_fill):
    out = [rect(10, y, W - 20, h, 22, "#1E222A", opacity=0.82),
           rect(10, y, W - 20, h, 22, "none", "#FFFFFF", 0.5, 0.08)]
    if tag_color == RED:
        out.append(rect(10, y, W - 20, h, 22, "none", RED, 1, 0.55))
    out.append(rect(24, y + 14, 38, 38, 9, icon_fill))
    out.append(icon(icon_name, 31, y + 21, 24, "#fff"))
    top = y + 26
    if tag:
        out.append(text(76, top, tag, 12, 700, tag_color, ls=0.6))
        top += 19
    out.append(text(W - 26, y + 26, when, 13, 400, TEXT2, "end"))
    out.append(text(76, top, title, 15, 600))
    for i, line in enumerate(lines):
        out.append(text(76, top + 20 + i * 19, line, 15, 400, "#D4D9E2"))
    return group(f"Notification / {title}", out)


def widget(cx, cy, value, label, color, frac):
    return group(f"Lock Widget / {label}", [
        circle(cx, cy, 29, "#FFFFFF", opacity=0.10),
        f'<path d="{ring(cx, cy, 25, 1)}" fill="none" stroke="#FFFFFF" stroke-opacity="0.18" stroke-width="4"/>',
        f'<path d="{ring(cx, cy, 25, frac)}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>',
        text(cx, cy + 6, value, 17, 700, "#fff", "middle"),
        text(cx, cy + 46, label, 10, 600, "#fff", "middle", 0.6, 0.75),
    ])


def lock_screen():
    out = [
        '<defs>'
        '<linearGradient id="wall" x1="0" y1="0" x2="0.4" y2="1">'
        '<stop offset="0" stop-color="#0E2A47"/><stop offset="0.55" stop-color="#0A1422"/>'
        '<stop offset="1" stop-color="#1A0F2B"/></linearGradient>'
        '<radialGradient id="glow" cx="0.8" cy="0.15" r="0.6">'
        '<stop offset="0" stop-color="#FF6A3D" stop-opacity="0.35"/><stop offset="1" stop-color="#FF6A3D" stop-opacity="0"/>'
        '</radialGradient>'
        '<linearGradient id="appicon" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#FF7A45"/><stop offset="1" stop-color="{RED}"/></linearGradient>'
        '</defs>',
        rect(0, 0, W, H, 0, "url(#wall)"),
        rect(0, 0, W, H, 0, "url(#glow)"),
        status_bar(),
        icon("lock", W / 2 - 10, 58, 20, "#fff"),
        text(W / 2, 112, "Saturday, October 17", 20, 600, "#fff", "middle", opacity=0.85),
        text(W / 2, 200, "9:41", 96, 700, "#fff", "middle", -2),
        widget(W / 2 - 80, 262, "7.8", "HAZARD", ORANGE, 0.78),
        widget(W / 2, 262, "4.2", "MI STRIKE", RED, 0.42),
        widget(W / 2 + 80, 262, "108°", "HEAT IDX", YELLOW, 0.72),
        notification(326, 120, "TIME SENSITIVE", RED, "now", "Stop work: lightning 4.2 mi away",
                     ["Port Everglades. Strike NE, moving SW.", "Shelter now. All-clear in 30:00."],
                     "bolt", "url(#appicon)"),
        notification(458, 96, None, None, "2h ago", "Flood risk after overnight rain",
                     ["Bayboro: 2.9 in. fell overnight. Check", "trench walls before entry."],
                     "flood", "url(#appicon)"),
        notification(566, 96, None, None, "6:00 PM", "Tomorrow's safety briefing",
                     ["Heat index 107°F on the Atlantic coast.", "Plan outdoor work before 1 PM."],
                     "shield", "url(#appicon)"),
        rect(22, 662, W - 44, 12, 0, "#1E222A", opacity=0.6, extra='ry="10"'),
        rect(36, 674, W - 72, 10, 0, "#1E222A", opacity=0.35, extra='ry="8"'),
        text(W / 2, 712, "2 more from CrewSafe", 13, 500, "#fff", "middle", opacity=0.6),
        circle(70, 770, 25, "#FFFFFF", opacity=0.14),
        icon("flashlight", 59, 759, 22, "#fff"),
        circle(W - 70, 770, 25, "#FFFFFF", opacity=0.14),
        icon("camera", W - 81, 759, 22, "#fff"),
        home_indicator("#fff"),
    ]
    return "".join(out)


# --- screen 2: Today dashboard ----------------------------------------------

def briefing_event(y, ic, color, title, when, action, last=False):
    """One timeline row: what is happening and what the crew should do about it."""
    out = [circle(48, y + 17, 15, color, opacity=0.16),
           icon(ic, 39, y + 8, 18, color),
           text(76, y + 22, title, 15, 600)]
    if when == "NOW":
        out += [rect(W - 72, y + 8, 40, 20, 10, color, opacity=0.18),
                text(W - 52, y + 22, "NOW", 11, 700, color, "middle", 0.5)]
    else:
        out.append(text(W - 32, y + 22, when, 12, 600, TEXT2, "end"))
    for i, line in enumerate(action):
        out.append(text(76, y + 42 + i * 17, line, 13, 400, TEXT2))
    if not last:
        out.append(rect(47, y + 36, 2, 38, 1, STROKE))
    return group(f"Briefing Event / {title}", out)


def dashboard():
    index = 7.8
    level, lc = risk(index)

    banner = group("Hazard Alert Banner", [
        '<defs><linearGradient id="alertgrad" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{RED}"/><stop offset="1" stop-color="#B3122E"/></linearGradient>'
        '<pattern id="stripes" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="6" height="14" fill="#fff" opacity="0.05"/></pattern></defs>',
        rect(16, 152, W - 32, 84, 20, "url(#alertgrad)"),
        rect(16, 152, W - 32, 84, 20, "url(#stripes)"),
        circle(54, 194, 20, "#fff", opacity=0.18),
        icon("bolt", 43, 183, 22, "#fff"),
        text(86, 182, "STOP WORK · LIGHTNING", 12, 700, "#fff", ls=0.8, opacity=0.85),
        text(86, 203, "Strike 4.2 mi NE of site", 16, 600, "#fff"),
        text(86, 221, "Shelter now · resets on new strike", 12, 400, "#fff", opacity=0.85),
        f'<path d="{ring(336, 194, 24, 1)}" fill="none" stroke="#fff" stroke-opacity="0.22" stroke-width="5"/>',
        f'<path d="{ring(336, 194, 24, 0.94)}" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>',
        text(336, 198, "28:14", 12, 700, "#fff", "middle"),
    ])

    bands = [(0, 3, GREEN), (3, 5.5, YELLOW), (5.5, 8, ORANGE), (8, 10, RED)]
    bx0, bx1, by = 32, W - 32, 320
    scale = (bx1 - bx0) / 10
    bar = []
    for lo, hi, c in bands:
        active = lo <= index < hi
        bar.append(rect(bx0 + lo * scale + 1.5, by, (hi - lo) * scale - 3, 6, 3, c, opacity=1 if active else 0.22))
    marker_x = bx0 + index * scale
    summary = group("Hazard Index Summary", [
        rect(16, 252, W - 32, 90, 20, CARD, STROKE, 1),
        text(32, 302, f"{index}", 40, 700, lc, ls=-1),
        text(94, 302, "/ 10", 15, 500, TEXT2),
        text(150, 284, f"{level} risk", 17, 600),
        icon("up", 150, 292, 13, ORANGE),
        text(167, 303, "1.9 since 6 AM · lightning-driven", 13, 500, TEXT2),
        *bar,
        circle(marker_x, by + 3, 6, TEXT, BG, 2.5),
    ])

    briefing = group("Live Briefing", [
        rect(16, 386, W - 32, 366, 22, CARD, STROKE, 1),
        text(32, 416, "Storms over the port this morning,", 17, 600),
        text(32, 438, "extreme heat this afternoon.", 17, 600),
        text(32, 459, "From NWS, lightning network and crew reports", 12, 400, TEXT3),
        rect(32, 474, W - 64, 0.5, 0, STROKE),
        briefing_event(486, "bolt", RED, "Lightning 4.2 mi NE, moving SW", "NOW",
                       ["Work is stopped. Shelter in trucks until the", "all-clear, about 28 min."]),
        briefing_event(560, "flood", YELLOW, "King tide at the port", "11:20 AM",
                       ["Move equipment off the east dock before", "high tide. Avoid low vaults."]),
        briefing_event(634, "heat", ORANGE, "Heat index peaks at 108°F", "2 PM",
                       ["Rest 15 min in shade every 45 min.", "Drink water every 15–20 min."], last=True),
        rect(32, 708, W - 64, 0.5, 0, STROKE),
        icon("bolt", 32, 718, 18, TEXT2),
        text(58, 732, "Tomorrow: storms 1–6 PM", 13, 500, TEXT),
        text(W - 48, 732, "6 PM report", 13, 600, BLUE, "end"),
        icon("chevron", W - 46, 721, 13, BLUE),
    ])

    out = [
        rect(0, 0, W, H, 0, BG),
        status_bar(),
        text(20, 72, "SAT, OCT 17", 13, 600, TEXT2, ls=0.6),
        rect(W - 96, 57, 76, 24, 12, GREEN, opacity=0.14),
        circle(W - 82, 69, 4, GREEN),
        text(W - 72, 73.5, "Live", 12, 600, GREEN),
        text(20, 112, "Today", 34, 700, TEXT, ls=-0.5),
        icon("pin", 18, 124, 16, BLUE),
        text(38, 137, "Port Everglades · Broward Co.", 15, 500, TEXT2),
        icon("chevron", 246, 126, 13, TEXT3),
        banner,
        summary,
        text(20, 374, "Briefing", 20, 700),
        text(W - 20, 374, "Updated 9:15 AM", 13, 500, TEXT3, "end"),
        briefing,
        tab_bar("Today"),
    ]
    return "".join(out)


# --- screen 3: sites map ----------------------------------------------------

LAT0, LON0 = 27.77, -81.34          # map centre
PX_PER_DEG = 70
COS = math.cos(math.radians(LAT0))
MAP_CX, MAP_CY = W / 2 + 6, 312


def project(lat, lon):
    return MAP_CX + (lon - LON0) * PX_PER_DEG * COS, MAP_CY - (lat - LAT0) * PX_PER_DEG


def florida_path():
    data = json.loads(GEOJSON.read_text())
    geom = data["features"][0]["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    parts = []
    for poly in polys:
        ring_pts = [project(lat, lon) for lon, lat in poly[0]]
        xs, ys = [p[0] for p in ring_pts], [p[1] for p in ring_pts]
        if max(xs) - min(xs) < 3 and max(ys) - min(ys) < 3:
            continue
        if max(xs) < -40 or min(xs) > W + 40 or max(ys) < -40 or min(ys) > H:
            continue
        kept = [ring_pts[0]]
        for p in ring_pts[1:]:
            if math.dist(p, kept[-1]) >= 1.2:
                kept.append(p)
        if len(kept) < 3:
            continue
        parts.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in kept) + " Z")
    return " ".join(parts)


def site_row(y, rank, site, last=False):
    _, name, county, _, _, idx, (ic, factor) = site
    level, c = risk(idx)
    out = [text(24, y + 33, str(rank), 15, 700, TEXT3, "middle"),
           rect(40, y + 12, 4, 32, 2, c),
           text(56, y + 25, name, 16, 600),
           icon(ic, 56, y + 32, 13, c),
           text(73, y + 43, f"{county} · {factor}", 13, 400, TEXT2),
           rect(W - 88, y + 15, 52, 26, 13, c, opacity=0.16),
           text(W - 62, y + 32.5, f"{idx:.1f}", 14, 700, c, "middle"),
           icon("chevron", W - 32, y + 21, 13, TEXT3)]
    if not last:
        out.append(rect(56, y + 56, W - 72, 0.5, 0, STROKE))
    return group(f"Site Row / {name}", out)


def sites_map():
    land = florida_path()
    grid = []
    for lat in range(24, 32):
        _, y = project(lat, LON0)
        grid.append(f'<path d="M0 {y:.1f} H{W}" stroke="#FFFFFF" stroke-opacity="0.035"/>')
    for lon in range(-88, -78):
        x, _ = project(LAT0, lon)
        grid.append(f'<path d="M{x:.1f} 0 V{H}" stroke="#FFFFFF" stroke-opacity="0.035"/>')

    pe = project(26.0856, -80.1253)
    storm = group("Storm Cell Overlay", [
        '<defs><radialGradient id="storm"><stop offset="0" stop-color="#FF453A" stop-opacity="0.55"/>'
        '<stop offset="0.6" stop-color="#FF9F0A" stop-opacity="0.18"/><stop offset="1" stop-color="#FF9F0A" stop-opacity="0"/>'
        '</radialGradient></defs>',
        f'<ellipse cx="{pe[0] + 16:.1f}" cy="{pe[1] - 14:.1f}" rx="40" ry="30" fill="url(#storm)"/>',
        circle(pe[0], pe[1], 30, "none", RED, 1.5, 0.9, 'stroke-dasharray="4 4"'),
        icon("bolt", pe[0] + 20, pe[1] - 34, 14, YELLOW),
        icon("bolt", pe[0] + 32, pe[1] - 18, 11, YELLOW),
    ])

    pins = []
    for site in sorted(SITES, key=lambda s: s[5]):
        _, name, _, lat, lon, idx, _ = site
        x, y = project(lat, lon)
        _, c = risk(idx)
        g = []
        if idx >= 5.5:
            g.append(circle(x, y, 19, c, opacity=0.18))
        g += [circle(x, y, 12.5, c, BG, 2.5),
              text(x, y + 3.8, f"{idx:.1f}", 10, 800, "#0B0E13", "middle")]
        pins.append(group(f"Pin / {name}", g))

    callout_x, callout_y = pe[0] - 148, pe[1] - 70
    callout = group("Pin Callout", [
        rect(callout_x, callout_y, 132, 50, 14, "#151A22", STROKE, 1),
        f'<path d="M{callout_x + 120} {callout_y + 50} L{pe[0] - 12} {pe[1] - 10} L{callout_x + 104} {callout_y + 50} Z" fill="#151A22"/>',
        text(callout_x + 12, callout_y + 20, "Port Everglades", 13, 600),
        circle(callout_x + 16, callout_y + 36, 4, RED),
        text(callout_x + 25, callout_y + 40, "Stop work · 28:14", 11, 600, RED),
    ])

    chips = [("All 8", True), ("Lightning", False), ("Flood", False), ("Heat", False), ("Wildlife", False)]
    chip_out, cx = [], 16
    for label, active in chips:
        w = 13 + len(label) * 7.4 + 13
        chip_out.append(rect(cx, 114, w, 32, 16, TEXT if active else "#151A22",
                             None if active else STROKE, 1, 1 if active else 0.94))
        chip_out.append(text(cx + w / 2, 134.5, label, 13, 600, BG if active else TEXT, "middle"))
        cx += w + 8

    legend = group("Legend", [
        '<defs><linearGradient id="legend" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GREEN}"/><stop offset="0.45" stop-color="{YELLOW}"/>'
        f'<stop offset="0.75" stop-color="{ORANGE}"/><stop offset="1" stop-color="{RED}"/></linearGradient></defs>',
        rect(16, 420, 150, 34, 12, "#151A22", STROKE, 1, 0.94),
        text(28, 433, "HAZARD INDEX", 9, 700, TEXT2, ls=0.6),
        rect(28, 440, 106, 5, 2.5, "url(#legend)"),
        text(140, 446, "0–10", 9, 600, TEXT2),
    ])

    ranked = sorted(SITES, key=lambda s: -s[5])[:4]
    sheet = group("Bottom Sheet / Ranked Sites", [
        rect(0, 470, W, 400, 26, "#0E1218", "#232B36", 0.5),
        rect(W / 2 - 18, 478, 36, 5, 2.5, "#3A4250"),
        text(20, 514, "Highest risk sites", 22, 700, ls=-0.3),
        text(20, 534, "Ranked by Hazard Index · updated 2 min ago", 13, 400, TEXT2),
        rect(W - 52, 494, 34, 34, 17, "#1A2029"),
        icon("sort", W - 44, 502, 18, TEXT2),
        *[site_row(546 + i * 56, i + 1, s, i == len(ranked) - 1) for i, s in enumerate(ranked)],
    ])

    out = [
        '<defs><linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#0B1B2D"/><stop offset="1" stop-color="#081320"/></linearGradient></defs>',
        rect(0, 0, W, H, 0, "url(#sea)"),
        *grid,
        f'<path id="Florida" d="{land}" fill="#18212C" stroke="#2C3949" stroke-width="1" stroke-linejoin="round"/>',
        storm,
        *pins,
        callout,
        rect(0, 0, W, 54, 0, "#081320", opacity=0.6),
        status_bar(),
        group("Search Bar", [
            rect(16, 58, W - 92, 46, 15, "#151A22", STROKE, 1, 0.96),
            icon("search", 30, 71, 20, TEXT2),
            text(60, 86, "Search 8 sites", 16, 400, TEXT2),
            rect(W - 64, 58, 48, 46, 15, "#151A22", STROKE, 1, 0.96),
            icon("layers", W - 52, 69, 24, TEXT),
        ]),
        group("Filter Chips", chip_out),
        group("Locate Button", [rect(W - 64, 410, 48, 48, 15, "#151A22", STROKE, 1, 0.96),
                                icon("locate", W - 51, 423, 22, BLUE)]),
        legend,
        sheet,
        tab_bar("Sites"),
    ]
    return "".join(out)


# --- board ------------------------------------------------------------------

def board():
    xs = [GAP + i * (W + GAP) for i in range(3)]
    captions = [
        ("01", "Lock screen", "Time-sensitive alerts, briefing, hazard widgets"),
        ("02", "Today", "Stop-work banner, hazard index, live briefing"),
        ("03", "Sites", "Risk-ranked map with live storm overlay"),
    ]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{BOARD_W}" height="{BOARD_H}" viewBox="0 0 {BOARD_W} {BOARD_H}">',
        '<defs><radialGradient id="boardglow" cx="0.5" cy="0" r="0.9">'
        '<stop offset="0" stop-color="#16202E"/><stop offset="1" stop-color="#0A0D12"/></radialGradient></defs>',
        rect(0, 0, BOARD_W, BOARD_H, 0, "url(#boardglow)"),
        rect(GAP, 64, 34, 34, 9, RED),
        icon("shield", GAP + 6, 70, 22, "#fff"),
        text(GAP + 48, 90, "CrewSafe", 30, 700, TEXT, ls=-0.5),
        text(GAP + 190, 90, "iOS mockup · v1", 18, 500, TEXT2),
        text(GAP, 128, "Field-crew hazard monitoring for utility sites. Dark UI for high contrast outdoors; "
                       "risk colors follow the Hazard Index bands in Models.swift.", 15, 400, TEXT2),
    ]
    sw_x = BOARD_W - GAP
    for i, (name, c) in enumerate(reversed([("Low", GREEN), ("Moderate", YELLOW), ("High", ORANGE), ("Severe / Stop work", RED)])):
        w = 26 + len(name) * 7.6
        sw_x -= w + 10
        out += [rect(sw_x, 70, w, 28, 14, c, opacity=0.14), circle(sw_x + 14, 84, 4.5, c),
                text(sw_x + 24, 88.5, name, 12, 600, c)]
    screens = [("01 Lock Screen", lock_screen()), ("02 Today", dashboard()), ("03 Sites Map", sites_map())]
    for x, (name, body), (num, title, sub) in zip(xs, screens, captions):
        out.append(phone(name, x, TOP, body))
        out.append(text(x, TOP + H + 62, num, 14, 700, BLUE))
        out.append(text(x + 30, TOP + H + 62, title, 18, 700))
        out.append(text(x, TOP + H + 86, sub, 14, 400, TEXT2))
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    OUT.write_text(board())
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
