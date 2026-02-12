"""
ContentManager — Date-based article archive system.
Scans content/{category}/ folders for .json + .html file pairs.
"""
import json
import os


CATEGORY_LABELS = {
    "wsj": "Wall Street",
    "radar": "Daily Radar",
    "etf": "AX ETF",
    "column": "Editor Column",
}


class ContentManager:
    def __init__(self, content_dir="content"):
        self.content_dir = content_dir

    def _category_dir(self, category):
        return os.path.join(self.content_dir, category)

    def _scan_dates(self, category):
        """Return sorted list of date strings (newest first) that have both .json and .html."""
        cat_dir = self._category_dir(category)
        if not os.path.isdir(cat_dir):
            return []
        dates = []
        for fname in os.listdir(cat_dir):
            if fname.endswith(".json"):
                date_slug = fname[:-5]  # strip .json
                html_path = os.path.join(cat_dir, date_slug + ".html")
                if os.path.isfile(html_path):
                    dates.append(date_slug)
        dates.sort(reverse=True)
        return dates

    def get_latest_date(self, category):
        """Return the latest date slug for a category, or None."""
        dates = self._scan_dates(category)
        return dates[0] if dates else None

    def list_articles(self, category, limit=7):
        """Return list of article summaries for sidebar display."""
        dates = self._scan_dates(category)[:limit]
        result = []
        for date_slug in dates:
            meta = self._load_meta(category, date_slug)
            if meta:
                result.append({
                    "title": meta.get("title", ""),
                    "date": meta.get("date", date_slug),
                    "date_slug": date_slug,
                })
        return result

    def get_article(self, category, date=None):
        """Load a single article (meta + body HTML). Returns None if not found."""
        if date is None:
            date = self.get_latest_date(category)
        if date is None:
            return None

        meta = self._load_meta(category, date)
        body = self._load_body(category, date)
        if meta is None or body is None:
            return None

        return {"meta": meta, "body": body, "date_slug": date}

    def _load_meta(self, category, date_slug):
        path = os.path.join(self._category_dir(category), date_slug + ".json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _load_body(self, category, date_slug):
        path = os.path.join(self._category_dir(category), date_slug + ".html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None
