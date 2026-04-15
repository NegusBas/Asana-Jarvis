"""Daily briefing: RSS headlines + Amharic word + proverb."""

from __future__ import annotations

import random
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional


DEFAULT_FEEDS = {
    "nba": "https://www.nba.com/news/rss.xml",
    "tech": "https://techcrunch.com/feed/",
    "stocks": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "ethiopia": "https://www.aljazeera.com/xml/rss/all",
}

AMHARIC_WORDS = [
    {"word": "ሰላም", "meaning": "Peace (also used as hello)."},
    {"word": "አመሰግናለሁ", "meaning": "Thank you."},
    {"word": "ውሃ", "meaning": "Water."},
    {"word": "መጽሐፍ", "meaning": "Book."},
    {"word": "ቤት", "meaning": "House / home."},
]

PROVERBS = [
    {"source": "African proverb", "text": "If you want to go fast, go alone. If you want to go far, go together."},
    {"source": "Kemetic teaching (popular)", "text": "Know yourself, and you will know the gods and the world."},
    {"source": "Rastafarian proverb", "text": "The greatness of a man is not in how much wealth he acquires, but in his integrity and his ability to affect those around him positively."},
    {"source": "Orthodox Christian wisdom", "text": "Humility is the path that opens the heart to wisdom."},
]


@dataclass
class BriefingAgent:
    feeds: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FEEDS))
    timeout_sec: int = 15

    def fetch_feed_titles(self, url: str, limit: int = 5) -> List[str]:
        req = urllib.request.Request(url, headers={"User-Agent": "AsanaBriefingBot/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        titles: List[str] = []
        for el in root.iter():
            if el.tag.endswith("item") or el.tag == "item":
                title_el = el.find("title")
                if title_el is not None and title_el.text:
                    titles.append(title_el.text.strip())
                if len(titles) >= limit:
                    break
        if not titles:
            for el in root.iter():
                if el.tag.endswith("title") or el.tag == "title":
                    if el.text and el.text.strip():
                        titles.append(el.text.strip())
                    if len(titles) >= limit + 3:
                        break
            titles = [t for t in titles if not t.lower().startswith("rss ")][:limit]
        return titles[:limit]

    def amharic_word_of_the_day(self, seed: Optional[str] = None) -> Dict[str, str]:
        rng = random.Random(seed)
        pick = rng.choice(AMHARIC_WORDS)
        return {"word": pick["word"], "meaning": pick["meaning"]}

    def proverb_of_the_day(self, seed: Optional[str] = None) -> Dict[str, str]:
        rng = random.Random(seed)
        pick = rng.choice(PROVERBS)
        return {"source": pick["source"], "text": pick["text"]}

    def run_daily_briefing(self, date_key: Optional[str] = None) -> str:
        """Returns a plain-text briefing for TTS or logs."""
        seed = date_key
        lines: List[str] = ["=== Daily briefing ==="]

        for label, url in self.feeds.items():
            try:
                titles = self.fetch_feed_titles(url)
                lines.append(f"\n-- {label.upper()} --")
                lines.extend(f"• {t}" for t in titles)
            except Exception as e:
                lines.append(f"\n-- {label.upper()} (failed) --\n{repr(e)}")

        w = self.amharic_word_of_the_day(seed)
        p = self.proverb_of_the_day(seed)
        lines.append("\n-- Amharic word of the day --")
        lines.append(f"{w['word']}: {w['meaning']}")
        lines.append("\n-- Proverb of the day --")
        lines.append(f"({p['source']}) {p['text']}")

        return textwrap.dedent("\n".join(lines)).strip()
