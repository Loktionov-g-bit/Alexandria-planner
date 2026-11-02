#!/usr/bin/env python3
"""Alexandria Planner logo variants: shared Alexandria lighthouse + a planner-specific detail."""
from pathlib import Path

OUT = Path(__file__).resolve().parent

DEFS = """
<defs>
  <radialGradient id="bg" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#fdf9f3"/><stop offset="1" stop-color="#f8f0e5"/></radialGradient>
  <linearGradient id="beamL" x1="1" y1="0" x2="0" y2="0"><stop offset="0" stop-color="#f6c84c" stop-opacity=".85"/><stop offset="1" stop-color="#f6c84c" stop-opacity="0"/></linearGradient>
  <linearGradient id="beamR" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f6c84c" stop-opacity=".85"/><stop offset="1" stop-color="#f6c84c" stop-opacity="0"/></linearGradient>
  <linearGradient id="stone" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f4eee5"/><stop offset=".62" stop-color="#ece4d8"/><stop offset=".63" stop-color="#ddd4c6"/><stop offset="1" stop-color="#d6ccbd"/></linearGradient>
  <linearGradient id="flame" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#f08a1c"/><stop offset="1" stop-color="#ffd25a"/></linearGradient>
  <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#6b5a3e" flood-opacity=".18"/></filter>
</defs>"""

FRAME = """
<circle cx="512" cy="512" r="486" fill="url(#bg)"/>
<circle cx="512" cy="512" r="486" fill="none" stroke="#dcaa3c" stroke-width="10"/>
<circle cx="512" cy="512" r="464" fill="none" stroke="#e6d8c2" stroke-width="3"/>"""

BEAMS = """
<path d="M512 288 L168 206 L168 372 Z" fill="url(#beamL)" opacity=".55"/>
<path d="M512 288 L856 206 L856 372 Z" fill="url(#beamR)" opacity=".55"/>
<path d="M512 288 L190 284 L190 292 Z" fill="#fff6dc" opacity=".8"/>
<path d="M512 288 L834 284 L834 292 Z" fill="#fff6dc" opacity=".8"/>"""


def win(x, y, arched=False, w=14, h=26, fill="#2f2f2f"):
    if arched:
        r = w / 2
        return (f'<path d="M{x-r} {y+h/2} V{y-h/2+r} A{r} {r} 0 0 1 {x+r} {y-h/2+r} V{y+h/2} Z" fill="{fill}"/>')
    return f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="1.5" fill="{fill}"/>'


def bricks(x0, x1, y0, y1, step=22):
    lines = []
    for i, y in enumerate(range(y0 + step, y1, step)):
        lines.append(f'<line x1="{x0+4}" y1="{y}" x2="{x1-4}" y2="{y}"/>')
        off = 0 if i % 2 else 26
        for x in range(x0 + 20 + off, x1 - 10, 52):
            lines.append(f'<line x1="{x}" y1="{y-step}" x2="{x}" y2="{y}"/>')
    return f'<g stroke="#cfc4b4" stroke-width="1.2" opacity=".55">{"".join(lines)}</g>'


def tower(middle_windows=None):
    if middle_windows is None:
        middle_windows = "".join(win(x, y) for x in (448, 512, 576) for y in (505, 565))
    return f"""
<g filter="url(#soft)">
  <!-- spire, dome, lantern -->
  <line x1="512" y1="128" x2="512" y2="172" stroke="#3a3a3a" stroke-width="4" stroke-linecap="round"/>
  <circle cx="512" cy="180" r="11" fill="#3a3a3a"/>
  <rect x="505" y="188" width="14" height="10" fill="#3a3a3a"/>
  <path d="M462 240 A50 44 0 0 1 562 240 Z" fill="#3d3d3d"/>
  <rect x="452" y="236" width="120" height="11" rx="5" fill="#333"/>
  <rect x="466" y="247" width="92" height="72" fill="#fff4d6"/>
  <g fill="#333"><rect x="464" y="247" width="7" height="72"/><rect x="487" y="247" width="5" height="72"/>
  <rect x="532" y="247" width="5" height="72"/><rect x="553" y="247" width="7" height="72"/></g>
  <path d="M512 262 C524 278 528 290 522 302 C518 310 506 310 502 302 C497 292 504 284 508 276 C509 284 512 286 514 284 C516 278 512 270 512 262 Z" fill="url(#flame)"/>
  <rect x="496" y="306" width="32" height="8" rx="2" fill="#3a3a3a"/>
  <rect x="456" y="318" width="112" height="13" rx="2" fill="#333"/>
  <rect x="442" y="331" width="140" height="24" rx="2" fill="#3a3a3a"/>
  <!-- top tier -->
  <rect x="428" y="360" width="168" height="84" fill="url(#stone)"/>
  {bricks(428, 596, 360, 444)}
  <rect x="424" y="355" width="176" height="9" rx="2" fill="#d8d0c3"/>
  {win(452, 404, True)}{win(512, 404, False, 14, 24)}{win(572, 404, True)}
  <!-- middle tier -->
  <rect x="408" y="440" width="208" height="11" rx="2" fill="#3f3f3f"/>
  <rect x="416" y="451" width="192" height="8" fill="#cfc6b8"/>
  <rect x="420" y="459" width="184" height="166" fill="url(#stone)"/>
  {bricks(420, 604, 459, 625)}
  {middle_windows}
  {win(512, 616, False, 14, 18)}
  <!-- base tier -->
  <rect x="388" y="625" width="248" height="12" rx="2" fill="#3f3f3f"/>
  <rect x="398" y="637" width="10" height="8" fill="#cfc6b8"/><rect x="616" y="637" width="10" height="8" fill="#cfc6b8"/>
  <rect x="358" y="672" width="40" height="34" fill="#c4baab"/><rect x="626" y="672" width="40" height="34" fill="#b9ae9e"/>
  <rect x="398" y="645" width="228" height="140" fill="url(#stone)"/>
  {bricks(398, 626, 645, 785)}
  <rect x="398" y="637" width="228" height="10" fill="#d8d0c3"/>
  <path d="M474 785 V722 A38 38 0 0 1 550 722 V785" fill="none" stroke="#e0d7ca" stroke-width="5"/>
  <path d="M486 785 V728 A26 26 0 0 1 538 728 V785 Z" fill="#2c2c2c"/>
  <!-- wings -->
  <rect x="320" y="711" width="78" height="74" fill="#efe8dd"/><rect x="626" y="711" width="80" height="74" fill="#ddd4c6"/>
  <rect x="316" y="704" width="82" height="8" rx="2" fill="#3f3f3f"/><rect x="626" y="704" width="84" height="8" rx="2" fill="#3f3f3f"/>
  {win(346, 748, True, 12, 22)}{win(680, 748, True, 12, 22)}
  <!-- plinth -->
  <rect x="300" y="778" width="424" height="16" rx="2" fill="#4a4a4a"/>
  <rect x="392" y="785" width="240" height="25" fill="#5a5a5a"/>
  <rect x="289" y="792" width="447" height="19" rx="2" fill="#3c3c3c"/>
</g>"""


def svg(body, label, frame=FRAME, defs=DEFS):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="{label}">'
            f"{defs}{frame}{body}</svg>\n")


# A — sticker: tilted note with check, taped to the ring (no paperclips)
STICKER = """
<g transform="translate(790 786) rotate(-8) scale(1.08)" filter="url(#soft)">
  <path d="M-92 -92 H92 V60 Q92 92 60 92 H-92 Z" fill="#fde9a6"/>
  <path d="M92 60 Q92 92 60 92 L60 74 Q60 60 74 60 Z" fill="#f2cf6e"/>
  <rect x="-40" y="-110" width="80" height="30" rx="3" fill="#efe3cf" opacity=".9" transform="rotate(4)"/>
  <path d="M-50 2 L-14 38 L54 -34" fill="none" stroke="#3a3a3a" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
</g>"""

# B — dial: the gold ring becomes a planner clock face
def dial():
    import math
    ticks = []
    for i in range(12):
        a = math.radians(i * 30)
        big = i % 3 == 0
        r0, r1 = (432, 462) if big else (442, 460)
        x0, y0 = 512 + r0 * math.sin(a), 512 - r0 * math.cos(a)
        x1, y1 = 512 + r1 * math.sin(a), 512 - r1 * math.cos(a)
        ticks.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#dcaa3c" '
                     f'stroke-width="{9 if big else 5}" stroke-linecap="round"/>')
    arc = '<path d="M512 26 A486 486 0 0 1 932.9 269" fill="none" stroke="#c8902a" stroke-width="16" stroke-linecap="round"/>'
    return "".join(ticks) + arc

# C — matrix: middle-tier windows form a lit 2x2 grid (Eisenhower board)
def matrix_windows():
    cells = [(474, 506, "#f6c84c"), (550, 506, "#2f2f2f"), (474, 578, "#2f2f2f"), (550, 578, "#2f2f2f")]
    out = ['<rect x="436" y="472" width="152" height="140" rx="10" fill="#3a3a3a"/>']
    for x, y, c in cells:
        out.append(f'<rect x="{x-30}" y="{y-28}" width="60" height="56" rx="6" fill="{c}"/>')
    out.append('<path d="M458 506 L470 518 L492 494" fill="none" stroke="#3a3a3a" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    return "".join(out)



# D — milestone pennant flying from the spire
FLAG = """
<line x1="512" y1="96" x2="512" y2="172" stroke="#3a3a3a" stroke-width="4" stroke-linecap="round"/>
<path d="M514 98 C548 92 566 112 600 104 L586 124 L600 146 C566 154 548 134 514 140 Z" fill="#dcaa3c"/>
<path d="M514 98 C548 92 566 112 600 104 L594 112 C562 120 546 102 514 108 Z" fill="#e9c46a" opacity=".7"/>"""

# E — right beam breaks into a three-line checklist
LIST_BEAMS = """
<path d="M512 288 L168 206 L168 372 Z" fill="url(#beamL)" opacity=".55"/>
<path d="M512 288 L190 284 L190 292 Z" fill="#fff6dc" opacity=".8"/>
<g fill="#f6c84c" opacity=".5">
  <path d="M562 280 L790 236 Q800 234 800 244 L800 252 Q800 262 790 262 L562 286 Z"/>
  <path d="M562 286 L790 278 Q800 278 800 288 L800 292 Q800 302 790 302 L562 292 Z"/>
  <path d="M562 292 L790 320 Q800 322 800 332 L800 336 Q800 346 790 346 L562 298 Z"/>
</g>
<g fill="none" stroke="#c8902a" stroke-width="9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M818 246 l11 11 l20 -22"/><path d="M818 290 l11 11 l20 -22"/>
  <circle cx="833" cy="336" r="11" stroke-width="6"/>
</g>"""

# F — quadrant cross behind the tower (Eisenhower matrix), very faint
QUADS = """
<g stroke="#dcaa3c" stroke-width="4" opacity=".45" stroke-linecap="round">
  <line x1="512" y1="60" x2="512" y2="964"/><line x1="60" y1="512" x2="964" y2="512"/>
</g>
<g fill="#dcaa3c" opacity=".14">
  <path d="M512 512 V40 A472 472 0 0 0 40 512 Z"/>
</g>"""

# G — same mark, planner accent colour instead of gold
SAGE_DEFS = DEFS.replace("#f6c84c", "#7fb8a8")
SAGE_FRAME = FRAME.replace("#dcaa3c", "#5f9e8f").replace("#e6d8c2", "#cfe0d9")


GOLD, DEEP, BEAM = "#dcaa3c", "#c8902a", "#f6c84c"
LEFT_BEAM = """
<path d="M512 288 L168 206 L168 372 Z" fill="url(#beamL)" opacity=".55"/>
<path d="M512 288 L190 284 L190 292 Z" fill="#fff6dc" opacity=".8"/>"""
RIGHT_BEAM = """
<path d="M512 288 L856 206 L856 372 Z" fill="url(#beamR)" opacity=".55"/>
<path d="M512 288 L834 284 L834 292 Z" fill="#fff6dc" opacity=".8"/>"""


def stripes(side=1, end=800, op=".5", fill=BEAM):
    """Three rounded light stripes fanning out from the lantern; side=-1 mirrors left."""
    out = []
    for y0, y1 in ((236, 262), (278, 302), (322, 346)):
        out.append(f'<path d="M562 {283 + (y0-278)//14} L{end-10} {y0} Q{end} {y0} {end} {y0+10} L{end} {y1-10} '
                   f'Q{end} {y1} {end-10} {y1} L562 {289 + (y1-302)//14} Z"/>')
    tf = "" if side == 1 else ' transform="translate(1024 0) scale(-1 1)"'
    return f'<g fill="{fill}" opacity="{op}"{tf}>{"".join(out)}</g>'


def check(x, y, c=DEEP, w=9, k=1.0):
    return (f'<path d="M{x} {y} l{11*k:.1f} {11*k:.1f} l{20*k:.1f} {-22*k:.1f}" fill="none" stroke="{c}" '
            f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')


def ring_dot(x, y, c=DEEP, r=11, w=6):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{c}" stroke-width="{w}"/>'


# H — Gantt beams: staggered bars of different length
GANTT = LEFT_BEAM + f"""
<g fill="{BEAM}">
  <rect x="566" y="236" width="170" height="24" rx="12" opacity=".75"/>
  <rect x="626" y="278" width="214" height="24" rx="12" opacity=".6"/>
  <rect x="596" y="320" width="120" height="24" rx="12" opacity=".45"/>
</g>
<circle cx="736" cy="248" r="7" fill="{DEEP}"/><circle cx="840" cy="290" r="7" fill="{DEEP}"/><circle cx="716" cy="332" r="7" fill="{DEEP}"/>"""

# I — plan on the left (open circles), done on the right (checks)
BOTH = stripes(-1) + stripes(1) + "".join(ring_dot(191, y) for y in (249, 290, 334)) + \
    check(818, 246) + check(818, 290) + ring_dot(833, 334)

# J — rays made of sticky-note squares flying out of the lantern
def sticker_rays():
    out = [LEFT_BEAM]
    for i, (x, sz) in enumerate(((600, 30), (664, 40), (742, 52), (834, 64))):
        for dy, rot in ((-1, -8), (1, 6)):
            y = 288 + dy * (x - 540) * 0.18
            op = .55 + i * .1
            out.append(f'<rect x="{x-sz/2:.0f}" y="{y-sz/2:.0f}" width="{sz}" height="{sz}" rx="{sz*.18:.0f}" '
                       f'fill="{BEAM}" opacity="{op:.2f}" transform="rotate({rot} {x} {y:.0f})"/>')
    return "".join(out)

# K — the flame inside the lantern becomes a glowing check
FLAME_CHECK = BEAMS.replace('opacity=".55"', 'opacity=".55"')
def tower_check():
    t = tower()
    i = t.index('<path d="M512 262'); j = t.index("/>", i) + 2
    return t[:i] + '<path d="M495 287 l12 12 l22 -26" fill="none" stroke="#f08a1c" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>' + t[j:]

# L — dotted route to a goal flag
ROUTE = LEFT_BEAM + f"""
<path d="M512 288 L856 230 L856 346 Z" fill="url(#beamR)" opacity=".35"/>
<g fill="{DEEP}">{"".join(f'<circle cx="{x}" cy="288" r="{r}"/>' for x, r in ((610,5),(660,6),(710,7),(760,8)))}</g>
<line x1="812" y1="300" x2="812" y2="226" stroke="#3a3a3a" stroke-width="5" stroke-linecap="round"/>
<path d="M815 228 C836 222 848 236 868 230 L860 244 L868 258 C848 264 836 250 815 256 Z" fill="{GOLD}"/>"""

# M — beam lands on a calendar dot grid
def calendar():
    out = [LEFT_BEAM, f'<path d="M512 288 L740 220 L740 356 Z" fill="url(#beamR)" opacity=".45"/>']
    for r in range(3):
        for c in range(3):
            x, y = 760 + c * 34, 252 + r * 34
            hit = (r, c) == (1, 1)
            out.append(f'<rect x="{x-12}" y="{y-12}" width="24" height="24" rx="6" fill="{DEEP if hit else BEAM}" '
                       f'opacity="{1 if hit else .55}"/>')
    return "".join(out)

# N — progress ring: three quarters of the frame glow, dot at the head
PROGRESS = f"""
<path d="M512 26 A486 486 0 1 1 26 512" fill="none" stroke="{DEEP}" stroke-width="18" stroke-linecap="round"/>
<circle cx="26" cy="512" r="20" fill="{DEEP}"/><circle cx="26" cy="512" r="9" fill="#fff6dc"/>""" + BEAMS

# O — lit window strips in the middle tier read as a Gantt chart
def gantt_windows():
    bars = ((436, 96, "#f6c84c"), (468, 112, "#2f2f2f"), (452, 80, "#2f2f2f"))
    out = []
    for i, (x, w, c) in enumerate(bars):
        out.append(f'<rect x="{x}" y="{488 + i*42}" width="{w}" height="22" rx="11" fill="{c}"/>')
    return "".join(out)

# P — E in planner green
SAGE = "#5f9e8f"
E_SAGE = LEFT_BEAM + stripes(1, fill="#7fb8a8") + check(818, 246, SAGE) + check(818, 290, SAGE) + ring_dot(833, 336, SAGE)

# Q — checks drawn inside the light stripes
INSIDE = LEFT_BEAM + stripes(1, end=840, op=".7") + check(772, 241, "#3a3a3a", 7, .8) + \
    check(772, 283, "#3a3a3a", 7, .8) + ring_dot(784, 334, "#3a3a3a", 8, 4)

VARIANTS = {
    "h-gantt": GANTT + tower(),
    "i-plan-done": BOTH + tower(),
    "j-sticker-rays": sticker_rays() + tower(),
    "k-flame-check": BEAMS + tower_check(),
    "l-route": ROUTE + tower(),
    "m-calendar": calendar() + tower(),
    "n-progress": PROGRESS + tower(),
    "o-window-gantt": BEAMS + tower(gantt_windows()),
    "p-checklist-green": E_SAGE + tower(),
    "q-checks-inside": INSIDE + tower(),
}
FRAMES = {"p-checklist-green": (SAGE_FRAME, SAGE_DEFS)}

for name, body in VARIANTS.items():
    frame, defs = FRAMES.get(name, (FRAME, DEFS))
    (OUT / f"planner-logo-{name}.svg").write_text(svg(body, "Alexandria Planner", frame, defs))
print("ok")
