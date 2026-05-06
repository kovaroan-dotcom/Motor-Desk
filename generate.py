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
        results.append({
            "title":  title[:140],
            "desc":   desc,
            "url":    link,
            "img":    extract_image(item),
            "source": source["name"],
            "region": source["region"],
            "cat":    source["cat"],
            "date":   pub.strftime("%-d %b %Y"),
            "ts":     pub.timestamp(),
            "is_new": is_new,
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

    all_articles: list[dict] = []
    for source in SOURCES:
        print(f"Fetching {source['name']}…")
        all_articles.extend(fetch_feed(source, month_start, month_end))

    # Sort each source's articles by date desc (already done in fetch_feed),
    # then interleave: world first, cz second
    world = [a for a in all_articles if a["region"] == "world"]
    cz    = [a for a in all_articles if a["region"] == "cz"]
    world.sort(key=lambda a: a["ts"], reverse=True)
    cz.sort(key=lambda a: a["ts"], reverse=True)

    print(f"\nTotal: {len(world)} world + {len(cz)} CZ = {len(all_articles)} articles")

    # Build HTML cards
    def card_html(a: dict, size: str) -> str:
        col   = CAT_COLORS.get(a["cat"], "#94b8a8")
        label = CAT_LABELS.get(a["cat"], a["cat"])
        new_badge = '<span class="new-badge">New</span>' if a.get("is_new") else ""
        search_str = (a['title'] + ' ' + a['desc'] + ' ' + a['source']).lower()
        img_block = ""
        if a["img"]:
            wid = f"iw_{id(a)}"
            img_block = (
                f'<div class="iw" id="{wid}">{new_badge}'
                f'<img class="ci" src="{html.escape(a["img"])}" alt="" loading="lazy" '
                f'onerror="document.getElementById(\'{wid}\').classList.add(\'ie\')">'
                f'<div class="cfb">🚗</div>'
                f'</div>'
            )
        else:
            img_block = f'<div class="iw ie">{new_badge}<div class="cfb">🚗</div></div>'

        # Use article URL or fallback to source homepage
        link_url = a["url"] or SOURCE_URLS.get(a["source"], "")
        read_link = ""
        if link_url:
            read_link = (
                f'<a class="cl" href="{html.escape(link_url)}" '
                f'target="_blank" rel="noopener">Read →</a>'
            )

        return f"""
        <div class="card {size}" data-region="{html.escape(a['region'])}" data-cat="{html.escape(a['cat'])}" data-search="{html.escape(search_str)}" data-source="{html.escape(a['source'])}">
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

    def section_html(articles: list[dict], flag: str, label: str) -> str:
        if not articles:
            return ""
        cards = []
        for i, a in enumerate(articles):
            # First card of each source group gets a wider slot
            size = "s8" if i == 0 else ("s6" if i == 1 else "s4")
            cards.append(card_html(a, size))
        grid = "\n".join(cards)
        return f"""
      <div class="rsec">
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

    world_section  = section_html(world,  "🌍", "World")
    europe_section = section_html(europe, "🇪🇺", "Europe")
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


if __name__ == "__main__":
    main()
