#!/usr/bin/env python3
"""
Motor Desk – RSS generator
Runs on the 1st of each month via GitHub Actions.
Fetches up to 5 articles per source published in the previous calendar month,
then renders motor-desk.html from template.html.
"""

import os
import re
import json
import html
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from calendar import monthrange
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

ARTICLES_PER_SOURCE = 5

COMPETITORS = [
    "Tesla","BYD","Toyota","Hyundai","Kia","Renault","Stellantis","Geely",
    "Ford","GM","Volkswagen","VW","BMW","Mercedes","Audi","Porsche",
    "Nio","Xpeng","Li Auto","Leapmotor","SAIC","Chery","GAC","Volvo",
    "Peugeot","Opel","Fiat","Jeep","Dodge","Honda","Nissan","Mazda",
    "Rivian","Lucid","Waymo","Zoox",
]

SKODA_CONTEXT = """You are analyzing automotive news for Škoda Auto, a Czech car manufacturer 
and member of Volkswagen Group. Production in Czech Republic (Mladá Boleslav, Kvasiny, Vrchlabí).
Key competitors: Toyota, Hyundai, Kia, Renault, Stellantis, Tesla, BYD, Geely and other Chinese brands.
Main markets: Europe, India, China. Key topics: EV transition, battery tech, EU regulations, 
tariffs on Chinese EVs, VW Group strategy, supply chain."""

def analyze_article(title: str, desc: str) -> dict:
    """Call Anthropic API (Haiku) to get impact signal and competitor tags."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"signal": "info", "competitors": []}
    
    prompt = f"""Analyze this automotive news article for Škoda Auto.

Article: {title}
Summary: {desc}

{SKODA_CONTEXT}

Respond with JSON only, no other text:
{{
  "signal": "threat|opportunity|watch|info",
  "signal_reason": "one short sentence why",
  "competitors": ["list", "of", "competitor", "brands", "mentioned"]
}}

Signal definitions:
- threat: directly threatens Škoda's market position, sales or business
- opportunity: creates opportunity for Škoda
- watch: relevant trend to monitor, not immediately impactful  
- info: general industry info, low direct impact"""

    try:
        req_data = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        text = data["content"][0]["text"].strip()
        # strip markdown fences if present
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"  [AI] analyze failed: {e}")
        return {"signal": "info", "signal_reason": "", "competitors": []}

SOURCE_URLS = {
    "Electrek": "https://electrek.co", "InsideEVs": "https://insideevs.com",
    "CleanTechnica": "https://cleantechnica.com", "Electrive": "https://www.electrive.com",
    "Green Car Reports": "https://www.greencarreports.com", "Motor1": "https://www.motor1.com",
    "The Drive": "https://www.thedrive.com", "Autocar": "https://www.autocar.co.uk",
    "Auto Express": "https://www.autoexpress.co.uk", "Autovista24": "https://autovista24.autovistagroup.com",
    "Automotive News": "https://www.autonews.com", "Reuters Autos": "https://www.reuters.com",
    "TechCrunch Transport": "https://techcrunch.com", "The Verge": "https://www.theverge.com",
    "CnEVPost": "https://cnevpost.com", "CarNewsChina": "https://carnewschina.com",
    "Gasgoo": "https://autonews.gasgoo.com", "Hybrid.cz": "https://www.hybrid.cz",
    "Auto.cz": "https://www.auto.cz", "AutoRevue.cz": "https://www.autorevue.cz",
    "iDnes Auto": "https://www.idnes.cz/auto", "Autoforum.cz": "https://www.autoforum.cz",
    "EV Magazin CZ": "https://www.evmagazin.cz",
}

SOURCES = [
    # Global – EV & automotive
    {"name": "Electrek",          "url": "https://electrek.co/feed/",                                              "region": "world", "cat": "ev"},
    {"name": "InsideEVs",         "url": "https://insideevs.com/rss/articles/all/",                                "region": "world", "cat": "ev"},
    {"name": "CleanTechnica",     "url": "https://cleantechnica.com/feed/",                                         "region": "world", "cat": "ev"},
    {"name": "Electrive",         "url": "https://www.electrive.com/feed/",                                         "region": "world", "cat": "ev"},
    {"name": "Green Car Reports",  "url": "https://www.greencarreports.com/rss",                                    "region": "world", "cat": "ev"},
    {"name": "Motor1",            "url": "https://www.motor1.com/rss/news/all/",                                    "region": "world", "cat": "auto"},
    {"name": "The Drive",         "url": "https://www.thedrive.com/feed",                                           "region": "world", "cat": "auto"},
    {"name": "Automotive News",   "url": "https://www.autonews.com/arc/outboundfeeds/rss/",                         "region": "world", "cat": "industry"},
    {"name": "Reuters Autos",     "url": "https://feeds.reuters.com/reuters/businessNews",                          "region": "world", "cat": "industry"},
    {"name": "TechCrunch Transport","url": "https://techcrunch.com/category/transportation/feed/",                  "region": "world", "cat": "autonomy"},
    {"name": "The Verge",         "url": "https://www.theverge.com/rss/index.xml",                                  "region": "world", "cat": "auto"},
    # Europe
    {"name": "Autocar",           "url": "https://www.autocar.co.uk/rss",                                           "region": "europe", "cat": "auto"},
    {"name": "Auto Express",      "url": "https://www.autoexpress.co.uk/rss",                                       "region": "europe", "cat": "auto"},
    {"name": "Autovista24",       "url": "https://autovista24.autovistagroup.com/feed/",                             "region": "europe", "cat": "industry"},
    # China
    {"name": "CnEVPost",          "url": "https://cnevpost.com/feed/",                                              "region": "china",  "cat": "ev"},
    {"name": "CarNewsChina",      "url": "https://carnewschina.com/feed/",                                          "region": "china",  "cat": "auto"},
    {"name": "Gasgoo",            "url": "https://autonews.gasgoo.com/rss/70000001.xml",                            "region": "china",  "cat": "industry"},
    # Czech Republic
    {"name": "Hybrid.cz",        "url": "https://www.hybrid.cz/rss",                                               "region": "cz",    "cat": "ev"},
    {"name": "Auto.cz",          "url": "https://www.auto.cz/rss",                                                  "region": "cz",    "cat": "auto"},
    {"name": "AutoRevue.cz",     "url": "https://www.autorevue.cz/rss.xml",                                         "region": "cz",    "cat": "auto"},
    {"name": "iDnes Auto",       "url": "https://www.idnes.cz/auto/rss",                                            "region": "cz",    "cat": "auto"},
    {"name": "Autoforum.cz",     "url": "https://www.autoforum.cz/feed/",                                           "region": "cz",    "cat": "auto"},
    {"name": "EV Magazin CZ",    "url": "https://www.evmagazin.cz/feed/",                                           "region": "cz",    "cat": "ev"},
]

CAT_COLORS = {
    "ev":       "#34d9b5",
    "auto":     "#60a5fa",
    "autonomy": "#fb923c",
    "policy":   "#c084fc",
    "industry": "#818cf8",
    "tech":     "#fbbf24",
}
CAT_LABELS = {
    "ev":       "BEV / PHEV",
    "auto":     "Automotive",
    "autonomy": "Autonomous",
    "policy":   "Policy",
    "industry": "Industry",
    "tech":     "Battery / Tech",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

NS = {
    "media":   "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "atom":    "http://www.w3.org/2005/Atom",
}


def strip_tags(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[|\]\]>", "", text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(ent, ch)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(item) -> datetime | None:
    """Try every common date field an RSS/Atom item might have."""
    for tag in ("pubDate", "published", "updated", "date",
                "{http://purl.org/dc/elements/1.1/}date",
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated"):
        el = item.find(tag)
        if el is not None and el.text and el.text.strip():
            txt = el.text.strip()
            try:
                return parsedate_to_datetime(txt).astimezone(timezone.utc)
            except Exception:
                pass
            try:
                return datetime.fromisoformat(
                    txt.replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def extract_image(item) -> str:
    """Return the best image URL found in the item, or empty string."""
    # 1. media:content
    for el in item.findall(".//media:content", NS):
        url = el.get("url", "")
        if url and re.search(r"\.(jpe?g|png|webp)", url, re.I):
            return url
    # 2. media:thumbnail
    for el in item.findall(".//media:thumbnail", NS):
        url = el.get("url", "")
        if url:
            return url
    # 3. enclosure
    enc = item.find("enclosure")
    if enc is not None:
        url = enc.get("url", "")
        if url and re.search(r"\.(jpe?g|png|webp)", url, re.I):
            return url
    # 4. first <img> in description/content
    for tag in ("description", "content:encoded",
                "{http://purl.org/rss/1.0/modules/content/}encoded"):
        el = item.find(tag)
        if el is not None and el.text:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', el.text)
            if m:
                return m.group(1)
    return ""


def fetch_feed(source: dict, month_start: datetime, month_end: datetime) -> list[dict]:
    """Download one RSS/Atom feed and return up to ARTICLES_PER_SOURCE items."""
    try:
        req = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "MotorDesk/1.0 (+https://github.com)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"  [WARN] {source['name']}: fetch failed – {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  [WARN] {source['name']}: XML parse error – {e}")
        return []

    # Support both RSS (<item>) and Atom (<entry>)
    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry"
    )

    results = []
    for item in items:
        pub = parse_date(item)
        if pub is None:
            continue
        if not (month_start <= pub <= month_end):
            continue

        title_el = item.find("title")
        if title_el is None:
            title_el = item.find("{http://www.w3.org/2005/Atom}title")

        link_el = item.find("link")
        if link_el is None:
            link_el = item.find("{http://www.w3.org/2005/Atom}link")

        desc_el = item.find("description")
        if desc_el is None:
            desc_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        if desc_el is None:
            desc_el = item.find("{http://www.w3.org/2005/Atom}summary")
        if desc_el is None:
            desc_el = item.find("{http://www.w3.org/2005/Atom}content")

        title = strip_tags(title_el.text if title_el is not None else "").strip()
        if not title:
            continue

        # <link> can be text content OR href attribute (Atom)
        link = ""
        if link_el is not None:
            link = (link_el.text or link_el.get("href", "")).strip()

        desc = strip_tags(desc_el.text if desc_el is not None else "")[:300]

        from datetime import timedelta as _td
        is_new = (datetime.now(timezone.utc) - pub) < _td(hours=48)
        # tag competitors mentioned in title+desc
        combined = (title + " " + desc).lower()
        mentioned = [b for b in COMPETITORS if b.lower() in combined]
        results.append({
            "title":    title[:140],
            "desc":     desc,
            "url":      link,
            "img":      extract_image(item),
            "source":   source["name"],
            "region":   source["region"],
            "cat":      source["cat"],
            "date":     pub.strftime("%-d %b %Y"),
            "ts":       pub.timestamp(),
            "is_new":   is_new,
            "signal":   "info",
            "signal_reason": "",
            "competitors": mentioned,
        })

        if len(results) >= ARTICLES_PER_SOURCE:
            break

    print(f"  {source['name']}: {len(results)} articles")
    return results


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    from datetime import timedelta

    today = datetime.now(timezone.utc)

    # Label = current month
    month_label = today.strftime("%B %Y")

    # Search window = past 30 days so RSS feeds always have matching articles
    month_end   = today
    month_start = today - timedelta(days=30)
    print(f"Motor Desk – collecting articles for {month_label}")

    # ── LOAD existing archive ──
    archive_path = Path(__file__).parent / "articles.json"
    try:
        with open(archive_path, "r", encoding="utf-8") as f:
            archive = json.load(f)
        print(f"Loaded {len(archive)} articles from archive")
    except (FileNotFoundError, json.JSONDecodeError):
        archive = []
        print("No archive found, starting fresh")

    # ── FETCH new articles ──
    new_articles: list[dict] = []
    for source in SOURCES:
        print(f"Fetching {source['name']}…")
        new_articles.extend(fetch_feed(source, month_start, month_end))

    # ── MERGE: add new articles not already in archive (deduplicate by URL+title) ──
    existing_keys = set()
    for a in archive:
        key = (a.get("url","") or a.get("title",""))[:100]
        existing_keys.add(key)

    added = 0
    for a in new_articles:
        key = (a.get("url","") or a.get("title",""))[:100]
        if key and key not in existing_keys:
            archive.append(a)
            existing_keys.add(key)
            added += 1

    print(f"Added {added} new articles to archive (total: {len(archive)})")

    # ── SAVE archive ──
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, separators=(",",":"))

    # ── AI ANALYSIS: signal + competitor enrichment for new articles ──
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        needs_analysis = [a for a in archive if a.get("signal") == "info" and a.get("signal_reason") == ""]
        print(f"Running AI analysis on {len(needs_analysis)} articles...")
        for i, a in enumerate(needs_analysis[:50]):  # max 50 per run to control cost
            result = analyze_article(a["title"], a["desc"])
            a["signal"] = result.get("signal", "info")
            a["signal_reason"] = result.get("signal_reason", "")
            # merge AI competitors with already-detected ones
            ai_comps = result.get("competitors", [])
            existing = set(a.get("competitors", []))
            a["competitors"] = list(existing | set(ai_comps))
            if (i+1) % 10 == 0:
                print(f"  Analyzed {i+1}/{min(len(needs_analysis),50)}...")
        # save enriched archive
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, separators=(",",":"))
        print(f"AI analysis complete")
    else:
        print("[WARN] No ANTHROPIC_API_KEY found, skipping AI analysis")

    # ── FILTER to last 30 days for display ──
    all_articles = [a for a in archive if a.get("ts",0) >= month_start.timestamp()]

    world  = [a for a in all_articles if a["region"] == "world"]
    europe = [a for a in all_articles if a["region"] == "europe"]
    china  = [a for a in all_articles if a["region"] == "china"]
    cz     = [a for a in all_articles if a["region"] == "cz"]
    for lst in [world, europe, china, cz]:
        lst.sort(key=lambda a: a["ts"], reverse=True)

    print(f"\nDisplaying: {len(world)} world + {len(europe)} europe + {len(china)} china + {len(cz)} CZ = {len(all_articles)} articles")

    # Build HTML cards
    def card_html(a: dict, size: str) -> str:
        col   = CAT_COLORS.get(a["cat"], "#94b8a8")
        label = CAT_LABELS.get(a["cat"], a["cat"])
        new_badge = '<span class="badge badge-new">New</span>' if a.get("is_new") else ""
        # Breaking: published in last 6 hours
        from datetime import timedelta as _td2
        is_breaking = a.get("ts", 0) > (datetime.now(timezone.utc) - _td2(hours=6)).timestamp()
        breaking_badge = '<span class="badge badge-breaking">Breaking</span>' if is_breaking else ""
        # Must Read: title contains high-signal keywords
        must_keywords = ["recall", "bankruptcy", "acquisition", "merger", "ipo", "shuts down",
                        "record", "billion", "million units", "world car", "award"]
        is_must = any(k in a.get("title","").lower() for k in must_keywords)
        must_badge = '<span class="badge badge-mustread">Must Read</span>' if is_must and not is_breaking else ""
        badges = f'<div class="badge-wrap">{breaking_badge}{new_badge}{must_badge}</div>' if (is_breaking or a.get("is_new") or is_must) else ""
        search_str = (a['title'] + ' ' + a['desc'] + ' ' + a['source']).lower()
        img_block = ""
        if a["img"]:
            wid = f"iw_{id(a)}"
            img_block = (
                f'<div class="iw" id="{wid}">{badges}'
                f'<img class="ci" src="{html.escape(a["img"])}" alt="" loading="lazy" '
                f'onerror="document.getElementById(\'{wid}\').classList.add(\'ie\')">'
                f'<div class="cfb">🚗</div>'
                f'</div>'
            )
        else:
            img_block = f'<div class="iw ie">{badges}<div class="cfb">🚗</div></div>'

        # Use article URL or fallback to source homepage
        link_url = a["url"] or SOURCE_URLS.get(a["source"], "")
        read_link = ""
        if link_url:
            read_link = (
                f'<a class="cl" href="{html.escape(link_url)}" '
                f'target="_blank" rel="noopener">Read →</a>'
            )

        img_url = a.get("img","")
        signal = a.get("signal","info")
        signal_reason = html.escape(a.get("signal_reason",""))
        competitors_str = html.escape(",".join(a.get("competitors",[])))
        return f"""
        <div class="card {size}" data-region="{html.escape(a['region'])}" data-cat="{html.escape(a['cat'])}" data-search="{html.escape(search_str)}" data-source="{html.escape(a['source'])}" data-title="{html.escape(a['title'])}" data-desc="{html.escape(a['desc'])}" data-url="{html.escape(a.get('url',''))}" data-img="{html.escape(img_url)}" data-date="{html.escape(a['date'])}" data-signal="{signal}" data-signal-reason="{signal_reason}" data-competitors="{competitors_str}">
          {img_block}
          <div class="cb">
            <div class="ccat">
              <span class="pip" style="background:{col}"></span>
              <span style="color:{col}">{label}</span>
            </div>
            <div class="ct">{html.escape(a["title"])}</div>
            <div class="cd">{html.escape(a["desc"])}…</div>
            <div class="cf">
              <span class="cs">{html.escape(a["source"])}</span>
              <span class="xhint">▼ read more</span>
              <span class="ca">{a["date"]}</span>
              {read_link}
            </div>
          </div>
        </div>"""

    def section_html(articles: list[dict], flag: str, label: str, hero: bool = False) -> str:
        if not articles:
            return ""
        slug = {"Global":"world","World":"world","Europe":"europe","China":"china","Czech Republic":"cz"}.get(label, label.lower())

        if hero and len(articles) > 0:
            # Hero layout: big card left + side stack right, then rest in grid
            hero_main = card_html(articles[0], "hero-main")
            side_cards = "".join(card_html(a, "s4") for a in articles[1:3])
            rest_cards = "".join(card_html(a, "s4" if i % 3 == 0 else "s4") for i, a in enumerate(articles[3:]))
            rest_grid = f'<div class="grid">{"".join(card_html(a,"s4" if len(articles[3:])>4 else "s4") for a in articles[3:6])}{"".join(card_html(a,"s3") for a in articles[6:])}</div>' if articles[3:] else ""
            return f"""
      <div class="rsec section-wrap" data-region="{slug}">
        <div class="rh">
          <span class="rh-t">{flag} {label}</span>
          <span class="rh-c">{len(articles)} articles</span>
        </div>
        <div class="hero hero-grid">
          {hero_main}
          <div class="hero-side">{side_cards}</div>
        </div>
        {rest_grid}
      </div>"""
        else:
            cards = []
            for i, a in enumerate(articles):
                size = "s8" if i == 0 else ("s6" if i == 1 else "s4")
                cards.append(card_html(a, size))
            grid = "\n".join(cards)
            return f"""
      <div class="rsec" data-region="{slug}">
        <div class="rh">
          <span class="rh-t">{flag} {label}</span>
          <span class="rh-c">{len(articles)} articles</span>
        </div>
        <div class="grid">{grid}</div>
      </div>"""

    europe = [a for a in all_articles if a["region"] == "europe"]
    china  = [a for a in all_articles if a["region"] == "china"]
    europe.sort(key=lambda a: a["ts"], reverse=True)
    china.sort(key=lambda a: a["ts"], reverse=True)

    world_section  = section_html(world,  "🌍", "Global", hero=True)
    europe_section = section_html(europe, "🇪🇺", "Europe", hero=True)
    china_section  = section_html(china,  "🇨🇳", "China")
    cz_section     = section_html(cz,     "🇨🇿", "Czech Republic")
    content        = world_section + europe_section + china_section + cz_section

    if not content.strip():
        content = '<p style="text-align:center;padding:80px;color:#6a8e7c">No articles found for this period.</p>'

    # Read template and inject
    template_path = Path(__file__).parent / "template.html"
    template = template_path.read_text(encoding="utf-8")

    updated = today.strftime("%-d %B %Y").upper()
    output = (
        template
        .replace("{{MONTH_LABEL}}", month_label)
        .replace("{{UPDATED}}", updated)
        .replace("{{ARTICLE_COUNT}}", str(len(all_articles)))
        .replace("{{CONTENT}}", content)
    )

    out_path = Path(__file__).parent / "motor-desk.html"
    out_path.write_text(output, encoding="utf-8")
    print(f"\n✓ Written to {out_path}  ({len(all_articles)} articles)")

    # ── GENERATE ARCHIVE ──
    archive_template_path = Path(__file__).parent / "archive_template.html"
    if archive_template_path.exists():
        archive_tmpl = archive_template_path.read_text(encoding="utf-8")

        # Group ALL archive articles by month
        from collections import defaultdict
        by_month = defaultdict(lambda: {"world":[], "europe":[], "china":[], "cz":[]})
        for a in sorted(archive, key=lambda x: x.get("ts",0), reverse=True):
            try:
                month_key = datetime.fromtimestamp(a["ts"], tz=timezone.utc).strftime("%B %Y")
            except:
                continue
            region = a.get("region","world")
            if region in by_month[month_key]:
                by_month[month_key][region].append(a)

        archive_content = ""
        for month_key, regions in by_month.items():
            month_articles = sum(len(v) for v in regions.values())
            if not month_articles:
                continue
            archive_content += f'<div class="month-sec">'
            archive_content += f'<div class="month-hd"><span class="month-hd-t">{month_key}</span><span class="month-hd-c">{month_articles} articles</span></div>'
            for region_key, region_label in [("world","🌍 Global"),("europe","🇪🇺 Europe"),("china","🇨🇳 China"),("cz","🇨🇿 Czech Republic")]:
                arts = regions.get(region_key, [])
                if not arts:
                    continue
                archive_content += f'<div class="rsec" data-region="{region_key}">'
                archive_content += f'<div class="rh"><span class="rh-t">{region_label}</span><span class="rh-c">{len(arts)} articles</span></div>'
                archive_content += '<div class="grid">'
                for i, a in enumerate(arts):
                    archive_content += card_html(a, "s8" if i==0 else ("s6" if i==1 else "s4"))
                archive_content += '</div></div>'
            archive_content += '</div>'

        archive_output = (archive_tmpl
            .replace("{{ARCHIVE_CONTENT}}", archive_content)
            .replace("{{ARCHIVE_COUNT}}", str(len(archive)))
            .replace("{{MONTH_COUNT}}", str(len(by_month))))

        archive_path_html = Path(__file__).parent / "archive.html"
        archive_path_html.write_text(archive_output, encoding="utf-8")
        print(f"✓ Archive written ({len(archive)} total articles, {len(by_month)} months)")


if __name__ == "__main__":
    main()
