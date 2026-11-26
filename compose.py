"""Deterministic, text-first, 24 November 2026 broadsheet compositor.

Run with Pillow 10.2.0. All type, rules, keys, and map marks are drawn here;
assets contain illustrations only. Source copy is the supplied editorial brief.
The printer drops only a suffix of BRIEFS if the fixed type sizes need space.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
SIZE = 1024
MARGIN = 18
RIGHT = SIZE - MARGIN
WIDTH = RIGHT - MARGIN
PAPER = '#f4efdf'
INK = '#202923'
MUTED = '#596058'
RULE = '#c3bead'
RED = '#a13e2d'
PALE = '#e8e1cf'
DEJAVU = Path('/usr/share/fonts/truetype/dejavu')
LIBERATION = Path('/usr/share/fonts/truetype/liberation')
NOTO = Path('/usr/share/fonts/truetype/noto')
SERIF_BOLD = (LIBERATION / 'LiberationSerif-Bold.ttf'
              if (LIBERATION / 'LiberationSerif-Bold.ttf').exists()
              else DEJAVU / 'DejaVuSerif-Bold.ttf')
# Keep display text as real type rather than squeezing rasterized letters.
FACES = {
    'mast': SERIF_BOLD,
    'sans': DEJAVU / 'DejaVuSans.ttf',
    'bold': DEJAVU / 'DejaVuSans-Bold.ttf',
    'head': SERIF_BOLD,
    'body': NOTO / 'NotoSansDisplay-ExtraCondensed.ttf',
    'label': NOTO / 'NotoSansDisplay-ExtraCondensedBold.ttf',
}
REGIONS = {
    'N AMERICA': '#3b6477',
    'LATIN AMERICA': '#a86338',
    'EUROPE': '#65649a',
    'AFRICA': '#96712e',
    'MIDDLE EAST': '#ac4b3b',
    'SOUTH ASIA': '#387969',
    'EAST ASIA': '#3f7194',
    'SE ASIA': '#9b713b',
    'GLOBAL': '#5a6557',
}


@dataclass(frozen=True)
class Story:
    number: int
    region: str
    field: str
    status: str
    headline: str
    summary: str
    art: str = ''
    chip: str = ''
    source: str = ''


LEADS = [
    Story(1, 'EAST ASIA', 'Security', 'OFFICIAL',
          'KOREA SOUNDS FIRST-EVER AIR ALERT AS RUSSIAN JETS CLOSE IN',
          'Five Russian warplanes enter the defence zone off Ulleung Island; Seoul scrambles F-15Ks and orders islanders to shelter. No airspace breach.',
          'korea', '5 WARPLANES · 3-MINUTE ALERT',
          'JCS via Korea Times/Al Jazeera'),
    Story(2, 'SE ASIA', 'Disasters', 'CONFIRMED',
          'FACTORY FIRE TOLL RISES TO 26 IN INDONESIA',
          'Two more bodies recovered at the Banten candy factory as the search for 28 missing workers goes on.',
          'indonesia', '26 DEAD · 28 MISSING', 'Police via CNA'),
    Story(3, 'MIDDLE EAST', 'Security', 'CLAIM',
          'IRAN SAYS THREE TANKERS HIT MINES IN HORMUZ STRAIT',
          "Tehran's Revolutionary Guards say the ships struck mines while under US escort. No independent confirmation.",
          'hormuz', '3 TANKERS ABLAZE', 'IRGC via TIMAB'),
]
MIDS = [
    Story(4, 'MIDDLE EAST', 'Security', 'CONFIRMED',
          'DRONE STRIKE HITS RIYADH TOWER',
          '11 injured in a second Houthi attack on the financial district in a week.', 'riyadh'),
    Story(5, 'GLOBAL', 'Economy', 'CONFIRMED',
          'GLOBAL MARKETS SURGE',
          'Nasdaq +6.5%, S&P 500 +4.7%, Nikkei +3.9% in a record rally day.', 'markets'),
    Story(6, 'SOUTH ASIA', 'Disasters', 'CONFIRMED',
          '5.6 QUAKE SHAKES NEPAL',
          'Himalayan villages damaged near the China border; no deaths reported.', 'nepal'),
    Story(7, 'SE ASIA', 'Justice', 'CONFIRMED',
          '14 NATIONS BACK ICJ ROHINGYA RULING',
          'Britain sanctions Myanmar generals days after the genocide verdict.', 'icj'),
    Story(8, 'AFRICA', 'Security', 'REPORTED',
          'LIBYA DEMANDS ANSWERS OVER FRIGATE ATTACK',
          'Tripoli seeks an explanation after Ukrainian sea drones sank a Russian frigate off its coast.', 'frigate'),
    Story(9, 'EUROPE', 'Sport', 'CONFIRMED',
          'GUKESH OPENS CHESS TITLE DEFENCE IN GENEVA',
          "The champion faces Uzbekistan's Sindarov in a 14-game match.", 'chess'),
    Story(10, 'MIDDLE EAST', 'Security', 'CONFIRMED',
          'ISRAELI STRIKE KILLS HAMAS SECURITY CHIEF',
          'Gaza City strike reported despite the ceasefire in place since last year.'),
    Story(11, 'EAST ASIA', 'Space', 'CONFIRMED',
          'CHINA OPENS TIANGONG TO FIRST FOREIGN ASTRONAUT',
          "Pakistan's Zeeshan Ali joins the Shenzhou-24 mission."),
    Story(12, 'N AMERICA', 'Disasters', 'CONFIRMED',
          'FLORIDA FLOODS FORCE NEARLY 500 RESCUES',
          'Rivers reach record levels as king tides flood the Bay Area and beyond.'),
    Story(13, 'GLOBAL', 'Technology', 'CONFIRMED',
          'UN CHIEF: GLOBAL AI RISK RULES WITHIN A YEAR',
          'Guterres asks member states for a multilateral framework as his term nears its end.'),
]
# A tag of REPORTED is conservative when the supplied copy does not establish
# corroboration. Explicit official announcements and attributed claims differ.
BRIEFS = [
    Story(14, 'N AMERICA', 'Health', 'REPORTED', 'US HEALTH', 'Measles toll reaches 14 as Pennsylvania records its 9th death; cases near 6,000'),
    Story(15, 'N AMERICA', 'Crime', 'OFFICIAL', 'US CRIME', 'Justice Dept recovers $8bn and charges 800+ in largest anti-scam surge in history'),
    Story(16, 'N AMERICA', 'Technology', 'REPORTED', 'US TECH', 'Huawei guilty of stealing trade secrets, acquitted of racketeering'),
    Story(17, 'N AMERICA', 'Politics', 'REPORTED', 'US POLITICS', 'Trump awards the Medal of Freedom to Rudy Giuliani'),
    Story(18, 'N AMERICA', 'Security', 'REPORTED', 'US SECURITY', 'US soldier pleads guilty to selling military secrets to Chinese buyers'),
    Story(19, 'GLOBAL', 'Security', 'REPORTED', 'WORLD', 'Landmine casualties hit a five-year high of 7,000; Myanmar and Syria top the list'),
    Story(20, 'AFRICA', 'Economy', 'REPORTED', 'AFRICA', 'Congo cobalt export ban sends Chinese miners racing to ship before the deadline'),
    Story(21, 'SOUTH ASIA', 'Economy', 'REPORTED', 'S ASIA', 'Bangladesh growth falls to 3.2%, a 25-year low'),
    Story(22, 'LATIN AMERICA', 'Economy', 'OFFICIAL', 'LATAM', 'Venezuela puts public debt at $237.5bn in a step toward restructuring'),
    Story(23, 'LATIN AMERICA', 'Crime', 'REPORTED', 'LATAM', 'Gunmen hold hostages in Cartagena after a failed armoured-car raid'),
    Story(24, 'LATIN AMERICA', 'Crime', 'REPORTED', 'LATAM', 'Car bomb wrecks buildings in Villavicencio, Colombia; no confirmed victims'),
    Story(25, 'MIDDLE EAST', 'Justice', 'REPORTED', 'IRAN', 'Singer Parastoo Ahmadi sentenced to 74 lashes'),
    Story(26, 'N AMERICA', 'Crime', 'REPORTED', 'MEXICO', 'Mexico will try cartel figure El Chapo Isidro at home despite a US request'),
    Story(27, 'LATIN AMERICA', 'Health', 'REPORTED', 'CUBA', 'WHO chief visits Cuba as its health system deteriorates'),
    Story(28, 'EUROPE', 'Security', 'REPORTED', 'EUROPE', 'NATO weighs reports of a possible nuclear-armed satellite launch'),
    Story(29, 'EUROPE', 'Crime', 'REPORTED', 'UK', "Two men arrested after a break-in at Prince William's Norfolk home"),
    Story(30, 'EUROPE', 'Security', 'REPORTED', 'UKRAINE', 'Zaporizhzhia targeted by new night attacks'),
    Story(31, 'MIDDLE EAST', 'Environment', 'CLAIM', 'GAZA', 'Oxfam says Israeli attacks have turned Gaza into a toxic land'),
    Story(32, 'SOUTH ASIA', 'Diplomacy', 'REPORTED', 'INDIA', 'India holds third place in the Asia Power Index'),
    Story(33, 'SOUTH ASIA', 'Sport', 'REPORTED', 'SPORT', 'India and New Zealand draw the first Test at Wellington'),
    Story(34, 'EUROPE', 'Sport', 'REPORTED', 'SPORT', 'Gao Yang, 22, beats 12-time world champion Reanne Evans 6-1 in UK snooker qualifying'),
    Story(35, 'EUROPE', 'Faith', 'REPORTED', 'VATICAN', 'New book says Pope Francis wrote in his diary of seeing the devil three times'),
]
DATE_COPY = ("the EU's 22nd Russia sanctions package (23 Nov) - the US blacklist of a $14.7bn Iran shadow-bank network (23 Nov) - "
             "the drone strike on Perm's Lukoil plant (23 Nov) - COP31 closing without a pact in Antalya (22 Nov) - "
             "the ICJ genocide ruling itself (19 Nov); only today's reactions to it are above.")
LEGEND = ("HOW SURE: CONFIRMED = two or more outlets - OFFICIAL = on the record - "
          "REPORTED = one outlet - CLAIM = one side's account, unconfirmed")
NUMBERS = [
    ('26', 'dead in Banten'), ('5', 'Russian warplanes'),
    ('3 min', 'Korea alert stood'), ('+6.5%', 'Nasdaq'),
    ('7,000', 'landmine casualties'), ('$8bn', 'recovered from scammers'),
    ('~500', 'Florida rescues'), ('14', 'nations back the ICJ'),
]
TIMELINE = [
    ('22:52 MON', 'Korea shelter alert issued, lifted 3 minutes later'),
    ('EARLY HOURS', 'Iran reports Hormuz mine strikes'),
    ('09:51', 'Indonesia toll rises to 26'),
    ('21:00', 'Wall Street closes on a record rally'),
]
# Embedded, coarse land/water raster: 60 columns, north to south. No external
# map data, network, clock, pseudorandom noise, or platform-dependent hashing.
LAND = (
    '....................#######..................#..............',
    '.#####.......#.....#######.....###################..........',
    '..###############.....###...###############################.',
    '.....###############........#############################...',
    '........###########........#############################....',
    '.........#########.........##########################.......',
    '.........#########........###########################.......',
    '............#####.........########################..........',
    '...............#..........###########....########...........',
    '................####.......###########....#######...........',
    '................######......##########.......###............',
    '.................#######......#######.........#######.......',
    '.................######........######..........######.......',
    '.................######........#####...........########.....',
    '.................######.........####............#######.....',
    '.................#####..........###.............######..#...',
    '.................#####...............................#..###.',
    '.................####....................................#..',
    '....................#.......................................',
    '............................................................',
)


@lru_cache(maxsize=None)
def font(face: str, size: int):
    return ImageFont.truetype(str(FACES[face]), size)


def wrap(text, face, size, width):
    f = font(face, size)
    lines, line = [], ''
    for word in text.split():
        if f.getlength(word) > width:
            raise ValueError(f'Unbreakable word exceeds its column: {word!r}')
        candidate = f'{line} {word}'.strip()
        if line and f.getlength(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


class Printer:
    def __init__(self):
        self.page = Image.new('RGB', (SIZE, SIZE), PAPER)
        self.d = ImageDraw.Draw(self.page)
        self.bounds = []

    def text(self, x, y, text, face='body', size=13, fill=INK, limit=RIGHT):
        f = font(face, size)
        bbox = self.d.textbbox((x, y), text, font=f, anchor='lt')
        if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > limit + 0.5 or bbox[3] > SIZE - 8:
            raise ValueError(f'Type outside its box: {text!r}, {bbox}, right={limit}')
        self.d.text((x, y), text, font=f, fill=fill, anchor='lt')
        self.bounds.append(bbox)
        return f.getlength(text)

    def lines(self, x, y, lines, face, size, step, fill=INK, limit=RIGHT):
        for line in lines:
            self.text(x, y, line, face, size, fill, limit)
            y += step
        return y

    def rule(self, y, x=MARGIN, end=RIGHT, fill=RULE, width=1):
        self.d.line((x, y, end, y), fill=fill, width=width)

    def section(self, y, name, note=''):
        w = self.text(MARGIN, y, name, 'bold', 11)
        self.rule(y + 6, MARGIN + int(w) + 10)
        if note:
            nw = font('label', 10).getlength(note)
            self.d.rectangle((RIGHT - nw - 8, y - 1, RIGHT, y + 12), fill=PAPER)
            self.text(RIGHT - nw, y + 1, note, 'label', 10, MUTED)
        return y + 16

    def art(self, name, x, y, w, h):
        paths = sorted((ROOT / 'assets').glob(f'media-generation-panel-{name}-*.webp'))
        if len(paths) != 1:
            raise ValueError(f'Expected one {name} illustration, found {len(paths)}')
        with Image.open(paths[0]) as source:
            im = ImageOps.fit(source.convert('RGB'), (w, h), method=Image.Resampling.LANCZOS,
                              centering=(0.5, {'indonesia': .62, 'frigate': .52, 'korea': .40}.get(name, .5)))
        # Restrained printed colour without converting the supplied art to text.
        self.page.paste(im, (x, y))

    def tag(self, story, x, y, width):
        colour = REGIONS[story.region]
        label = f'{story.number:02d}  {story.region}'
        self.d.rectangle((x, y, x + 3, y + 10), fill=colour)
        self.text(x + 7, y, label, 'label', 11, colour, x + width)
        sw = font('label', 10).getlength(story.status)
        sx = x + width - sw - 8
        self.d.rectangle((sx, y - 1, x + width, y + 12), fill=colour if story.status != 'CLAIM' else RED)
        self.text(sx + 4, y, story.status, 'label', 10, PAPER, x + width)


def lead_height(story, width):
    return 14 + len(wrap(story.headline, 'head', 30, width)) * 22 + 4 + 60 + 4 + 16 + len(wrap(story.summary, 'body', 14, width)) * 14 + 3 + 11


def draw_leads(p, y):
    gap = 14
    width = (WIDTH - 2 * gap) // 3
    cols = [(MARGIN + i * (width + gap), width if i < 2 else RIGHT - (MARGIN + i * (width + gap))) for i in range(3)]
    height = max(lead_height(s, w) for s, (_, w) in zip(LEADS, cols))
    for story, (x, w) in zip(LEADS, cols):
        p.tag(story, x, y, w)
        cy = p.lines(x, y + 15, wrap(story.headline, 'head', 30, w), 'head', 30, 22, limit=x + w)
        # Different illustration heights absorb different headline lengths.
        summary_lines = wrap(story.summary, 'body', 14, w)
        tail_h = 4 + 16 + len(summary_lines) * 14 + 3 + 11
        art_h = y + height - cy - 5 - tail_h
        p.art(story.art, x, cy + 4, w, art_h)
        cy += 4 + art_h + 5
        p.d.rectangle((x, cy - 1, x + w, cy + 13), fill=REGIONS[story.region])
        p.text(x + 6, cy, story.chip, 'label', 12, PAPER, x + w)
        cy = p.lines(x, cy + 16, summary_lines, 'body', 14, 14, limit=x + w)
        p.text(x, cy + 2, f'Source: {story.source}', 'body', 11, MUTED, x + w)
    for x, _ in cols[1:]:
        p.d.line((x - 7, y, x - 7, y + height - 1), fill=RULE)
    return y + height + 8


def mid_height(story, width):
    head_h = len(wrap(story.headline, 'head', 20, width)) * 16
    if story.number <= 8:
        return 14 + 30 + 4 + head_h + 3 + len(wrap(story.summary, 'body', 13, width)) * 13 + 5
    if story.art:
        return 14 + head_h + 3 + max(36, len(wrap(story.summary, 'body', 13, width - 45)) * 13) + 5
    return 14 + head_h + 3 + len(wrap(story.summary, 'body', 13, width)) * 13 + 5


def draw_mids(p, y):
    y = p.section(y, 'THE NEWS DESK', '04—13  /  DEVELOPMENTS ACROSS THE WORLD')
    gap = 13
    for group, widths in [(MIDS[:5], [184, 146, 173, 210, 223]), (MIDS[5:], [187, 187, 187, 187, 188])]:
        height = max(mid_height(s, w) for s, w in zip(group, widths))
        x = MARGIN
        for i, (story, width) in enumerate(zip(group, widths)):
            p.tag(story, x, y, width)
            cy = y + 15
            if story.number <= 8:
                p.art(story.art, x, cy, width, 30)
                cy += 34
            cy = p.lines(x, cy, wrap(story.headline, 'head', 20, width), 'head', 20, 16, limit=x + width)
            cy += 3
            if story.art and story.number > 8:
                p.art(story.art, x, cy, 39, 36)
                p.lines(x + 45, cy, wrap(story.summary, 'body', 13, width - 45), 'body', 13, 13, limit=x + width)
            else:
                p.lines(x, cy, wrap(story.summary, 'body', 13, width), 'body', 13, 13, limit=x + width)
            if i:
                p.d.line((x - 7, y, x - 7, y + height - 3), fill=RULE)
            x += width + gap
        y += height
        p.rule(y)
        y += 4
    return y


def brief_layout(story, width):
    tag_w = font('head', 10).getlength(story.headline) + 6
    status_w = font('label', 10).getlength(story.status) + 2
    text_w = width - tag_w - status_w
    return tag_w, status_w, wrap(story.summary, 'body', 15, text_w)


def brief_columns(stories, width):
    # Keep story order down the left column, then down the right. Balance using
    # measured line counts, not just item counts; a long one-liner may wrap.
    if not stories:
        return [], [], 0
    costs = [len(brief_layout(s, width)[2]) for s in stories]
    split = min(range(1, len(stories) + 1), key=lambda i: (max(sum(costs[:i]), sum(costs[i:])), abs(2 * i - len(stories))))
    return stories[:split], stories[split:], max(sum(costs[:split]), sum(costs[split:])) * 16


def draw_briefs(p, y, stories, split):
    left, right, height = split
    y = p.section(y, f'{len(stories):02d} QUICK READS', 'REGION / CERTAINTY / THE REPORT')
    col_w = (WIDTH - 14) // 2
    for col, entries in enumerate([left, right]):
        x = MARGIN + col * (col_w + 14)
        cy = y
        for s in entries:
            tag_w, status_w, lines = brief_layout(s, col_w)
            p.d.rectangle((x, cy + 3, x + 2, cy + 13), fill=REGIONS[s.region])
            p.text(x + 4, cy + 3, s.headline, 'head', 10, REGIONS[s.region], x + col_w)
            sx = x + tag_w
            p.text(sx, cy + 3, s.status, 'label', 10, RED if s.status == 'CLAIM' else MUTED, x + col_w)
            p.lines(sx + status_w, cy, lines, 'body', 15, 16, limit=x + col_w)
            cy += len(lines) * 16
    p.d.line((SIZE // 2, y, SIZE // 2, y + height - 2), fill=RULE)
    return y + height + 4


def draw_numbers(p, x, y, width):
    p.text(x, y, 'THE DAY IN NUMBERS', 'bold', 10)
    cell_w = width // 4
    for i, (value, label) in enumerate(NUMBERS):
        cx = x + (i % 4) * cell_w
        cy = y + 15 + (i // 4) * 30
        p.text(cx, cy, value, 'head', 19, RED, cx + cell_w - 3)
        p.text(cx, cy + 18, label, 'body', 10, MUTED, cx + cell_w - 3)


def draw_timeline(p, x, y, width):
    p.text(x, y, 'THE DAY IN UTC', 'bold', 10)
    for i, (time, desc) in enumerate(TIMELINE):
        cy = y + 17 + i * 14
        p.d.ellipse((x, cy + 2, x + 4, cy + 6), fill=RED)
        p.text(x + 9, cy, time, 'label', 11, RED, x + width)
        tw = font('label', 11).getlength(time)
        p.text(x + 15 + tw, cy, desc, 'body', 11, INK, x + width)


def draw_map(p, x, y, width):
    p.text(x, y, 'WHERE IT HAPPENED', 'bold', 10)
    # A water grid and an embedded land mask, not decorative random dots.
    mx, my, mw, mh = x + 3, y + 18, width - 6, 55
    for row, cells in enumerate(LAND):
        for col, cell in enumerate(cells):
            dx = mx + col * mw / 59
            dy = my + row * mh / 19
            radius = .65 if cell == '#' else .20
            p.d.ellipse((dx - radius, dy - radius, dx + radius, dy + radius), fill='#7d8b70' if cell == '#' else '#e1dac8')
    # Geographic anchor (longitude/latitude), with label offsets to keep dense
    # European and Asian markers readable. Leaders go back to true positions.
    coords = [
        (1, 131, 37, 15, -13), (2, 106, -6, 14, 9), (3, 56, 26, 11, -2),
        (4, 47, 25, -2, 10), (5, -74, 41, -8, -9), (6, 86, 29, 12, 7),
        (7, 4, 52, -8, -15), (8, 13, 33, -13, 9), (9, 6, 46, -25, -4),
        (10, 34, 31, -8, -5), (11, 116, 40, 0, -18), (12, -82, 28, -15, 7),
        (13, -74, 41, 5, 11),
    ]
    for number, lon, lat, ox, oy in coords:
        sx = mx + (lon + 180) / 360 * mw
        sy = my + (80 - lat) / 140 * mh
        cx, cy = round(sx + ox), round(sy + oy)
        colour = REGIONS[(LEADS + MIDS)[number - 1].region]
        p.d.line((sx, sy, cx, cy), fill=colour)
        p.d.ellipse((sx - 1, sy - 1, sx + 1, sy + 1), fill=colour)
        p.d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=colour, outline=PAPER)
        text = str(number)
        f = font('label', 9)
        p.text(cx - f.getlength(text) / 2, cy - 4, text, 'label', 9, PAPER, x + width)


def draw_furniture(p, y):
    p.rule(y, fill=INK, width=2)
    y += 8
    draw_numbers(p, MARGIN, y, 370)
    p.d.line((400, y, 400, y + 67), fill=RULE)
    draw_timeline(p, 411, y, 315)
    p.d.line((742, y, 742, y + 67), fill=RULE)
    draw_map(p, 753, y, 253)
    y += 75
    p.rule(y, fill=RED, width=2)
    y += 7
    p.text(MARGIN, y, 'DATE CHECK — LEFT OUT ON PURPOSE', 'bold', 11, RED)
    y += 15
    lines = wrap(DATE_COPY, 'body', 13, WIDTH)
    y = p.lines(MARGIN, y, lines, 'body', 13, 14, fill=RED)
    p.rule(y + 4)
    y += 9
    p.text(MARGIN, y, LEGEND, 'body', 12)
    y += 14
    p.text(MARGIN, y, 'Sources: wire and national outlets of record, 24 Nov 2026.', 'body', 12, MUTED)
    p.text(RIGHT - font('label', 10).getlength('ONE DAY. A WHOLE WORLD.'), y, 'ONE DAY. A WHOLE WORLD.', 'label', 10, MUTED)
    return y + 12


def furniture_height():
    return 8 + 75 + 7 + 15 + len(wrap(DATE_COPY, 'body', 13, WIDTH)) * 14 + 9 + 14 + 12


def draw_masthead(p, stories):
    counts = (len(stories), len({s.region for s in stories}), len({s.field for s in stories}))
    title = 'THE WORLD IN ONE DAY'
    fw = font('mast', 56).getlength(title)
    p.text((SIZE - fw) / 2, 7, title, 'mast', 56)
    p.rule(56, fill=INK, width=2)
    date = 'TUESDAY · 24 NOVEMBER · 2026'
    p.text(MARGIN, 63, date, 'bold', 14, RED)
    strap = f'{counts[0]} STORIES · {counts[1]} REGIONS · {counts[2]} FIELDS  /  EVERY ONE FROM THIS TUESDAY'
    sw = font('label', 14).getlength(strap)
    p.text(RIGHT - sw, 63, strap, 'label', 14)
    p.rule(82, fill=INK, width=3)


def build_page():
    p = Printer()
    # Lay out required stories first. Count and print only the brief prefix that
    # fits; no font size is ever silently reduced and no ellipsis discards copy.
    y = draw_leads(p, 92)
    y = draw_mids(p, y)
    brief_width = (WIDTH - 14) // 2
    selected = list(BRIEFS)
    while selected:
        split = brief_columns(selected, brief_width)
        if y + 16 + split[2] + 4 + furniture_height() <= 1014:
            break
        selected.pop()
    else:
        split = ([], [], 0)
        if y + 26 + furniture_height() > 1014:
            raise ValueError('Required stories exceed the layout at the type floors')
    stories = LEADS + MIDS + selected
    draw_masthead(p, stories)
    y = draw_briefs(p, y, selected, split)
    end_y = draw_furniture(p, y)
    assert end_y <= 1015, end_y
    assert font('head', 30).size >= 30
    assert font('head', 20).size >= 20
    assert font('body', 15).size >= 15
    # Preserve RGB antialiasing when it fits. A deterministic palette fallback
    # also enforces the byte ceiling if future illustrations have more entropy.
    output = ROOT / 'entry.png'
    for i, a in enumerate(p.bounds):
        for b in p.bounds[i + 1:]:
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                raise ValueError(f'Text rectangles overlap: {a}, {b}')
    p.page.save(output, format='PNG', optimize=True, compress_level=9)
    if output.stat().st_size > 1_048_576:
        indexed = p.page.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        indexed.save(output, format='PNG', optimize=True, compress_level=9)
    with Image.open(output) as final:
        final.convert('RGB').resize((300, 300), Image.Resampling.LANCZOS).save(
            ROOT / 'entry-300.png', format='PNG', optimize=True)
    with Image.open(output) as check:
        check.verify()
    assert output.stat().st_size <= 1_048_576
    report = {
        'stories': len(stories),
        'leads': len(LEADS), 'mid_panels': len(MIDS), 'briefs': len(selected),
        'regions': dict(Counter(s.region for s in stories)),
        'fields': sorted({s.field for s in stories}),
        'dropped_briefs': [{'tag': s.headline, 'copy': s.summary} for s in BRIEFS[len(selected):]],
        'content_bottom': end_y,
        'entry_bytes': output.stat().st_size,
        'sha256': sha256(output.read_bytes()).hexdigest(),
    }
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    build_page()
