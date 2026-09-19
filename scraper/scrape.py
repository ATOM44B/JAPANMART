#!/usr/bin/env python3
"""Scout data refresh: Komehyo + Netmall (Hard Off) -> data/products.json

    python scraper/scrape.py                 full run
    python scraper/scrape.py --limit 3       quick test (3 listing pages), writes nothing
    python scraper/scrape.py --probe URL     show what the parser can read on one page
    python scraper/scrape.py --browser       use headless Chromium (pip install playwright)

How it reads the sites (checked against a live Komehyo listing page on 2026-09-19):
  * A listing page holds ~50 product links. Each link's text already contains the title, rank,
    store and price, e.g. "... ROLEX ランク：中古品A 在庫店舗：名古屋本館 ￥1,250,000(税込)".
    One request therefore yields up to ~50 items and no product page has to be opened.
  * Product links look like komehyo.jp/product/230-000-394-1842/ and netmall.hardoff.co.jp/product/2128568/
  * The new-retail figure ("参考上代") is deliberately ignored. Profit is judged on used prices only.

Safety: if fewer than min_total_live items come back, data/products.json is left untouched and the
reason is written to data/scrape_status.json.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import statistics
import sys
import time
from pathlib import Path
from urllib import robotparser
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

KG = {"earphones": 0.5, "player": 0.4, "speakers": 3.0, "lens": 0.9, "camera": 1.2, "watch": 0.4, "bag": 1.2, "ring": 0.1}
SOLD_RE = re.compile(r"(SOLD\s*OUT|売り切れ|売切れ|在庫なし|販売終了)", re.I)
IMG_EXT = re.compile(r"\.(?:jpe?g|png|webp)(?:\?|$)", re.I)
BAD_IMG = re.compile(r"(logo|icon|sprite|banner|btn|button|blank|noimage|no_image|no-image|loading|spacer|badge|arrow|favicon|\.svg|\.gif|/static/images/parts)", re.I)
YEN_RE = re.compile(r"[¥￥]\s*([\d,]{3,9})")
EN_RE = re.compile(r"([\d,]{3,9})\s*円")
RANK_RE = re.compile(r"ランク[：:]\s*([^\s]+)")
STORE_RE = re.compile(r"在庫店舗[：:]\s*(.+?)(?=\s*(?:参考上代|[¥￥]|$))")
SIZE_RE = re.compile(r"サイズ[：:]\s*\S+")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-/]{2,}")
LENS_RE = re.compile(r"(レンズ|\bLENS\b|\b\d{2,3}(?:-\d{2,3})?\s?mm\b|\bEF[-\s]?[SM]?\b|\bRF\b|\bFE\b|\bAF-S\b)", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]", "", (s or "").lower())


# ------------------------------------------------------------------ fetching
class Fetcher:
    def __init__(self, cfg: dict, browser: bool = False):
        self.cfg, self.last = cfg, 0.0
        self.delay = float(cfg.get("delay_seconds", 2))
        self.timeout = int(cfg.get("timeout_seconds", 25))
        self.ua = cfg.get("user_agent", "Mozilla/5.0 (compatible; ScoutPersonalBot/1.0)")
        self.respect = bool(cfg.get("respect_robots", True))
        self.robots: dict = {}
        self.browser = None
        if browser:
            from playwright.sync_api import sync_playwright  # lazy import

            self._pw = sync_playwright().start()
            self.browser = self._pw.chromium.launch()
            self.ctx = self.browser.new_context(user_agent=self.ua, locale="ja-JP")
        else:
            self.s = requests.Session()  # keeps cookies, which Netmall needs to avoid redirect loops
            self.s.headers.update({"User-Agent": self.ua, "Accept-Language": "ja,en;q=0.8"})

    def _allowed(self, url: str) -> bool:
        if not self.respect:
            return True
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        rp = self.robots.get(root)
        if rp is None:
            rp = robotparser.RobotFileParser()
            try:
                r = requests.get(root + "/robots.txt", headers={"User-Agent": self.ua}, timeout=10)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except Exception:  # noqa: BLE001
                rp.parse([])
            self.robots[root] = rp
        return rp.can_fetch(self.ua, url)

    def get(self, url: str) -> tuple[str | None, str]:
        if not self._allowed(url):
            return None, "blocked by robots.txt"
        wait = self.delay - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        if self.browser:
            try:
                page = self.ctx.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                page.wait_for_timeout(1500)
                html, status = page.content(), (resp.status if resp else 0)
                page.close()
                return (html, "ok") if status == 200 else (None, f"HTTP {status}")
            except Exception as e:  # noqa: BLE001
                return None, f"browser error: {type(e).__name__}"
        err = "no response"
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r.content.decode("utf-8", errors="replace"), "ok"
                err = f"HTTP {r.status_code}"
                if r.status_code in (403, 404, 410):
                    return None, err
            except requests.RequestException as e:
                err = type(e).__name__
            time.sleep(2 * (attempt + 1))
        return None, err

    def close(self):
        if self.browser:
            self.browser.close()
            self._pw.stop()


# ------------------------------------------------------------------ parsing
def to_int(v) -> int | None:
    s = re.sub(r"[^\d]", "", str(v))
    return int(s) if s else None


def find_price(text: str) -> int | None:
    m = YEN_RE.findall(text)
    if m:
        return to_int(m[-1])
    m = EN_RE.findall(text)
    return to_int(m[0]) if m else None


def dedupe_title(text: str) -> str:
    """Komehyo repeats the title (image alt + name). Keep one copy."""
    w = text.split()
    for i in range(1, len(w) // 2 + 1):
        if w[:i] == w[i : 2 * i]:
            return " ".join(w[:i])
    return text


def images_in(node, base: str, limit: int = 6) -> list[str]:
    """Any attribute that holds an image URL counts, so lazy-load attributes are covered too."""
    out: list[str] = []
    for img in node.find_all("img"):
        for k, v in img.attrs.items():
            if k in ("alt", "class", "id", "width", "height", "style"):
                continue
            for x in (v if isinstance(v, list) else [v]):
                for part in re.split(r"\s*,\s*|\s+", str(x)):
                    if not IMG_EXT.search(part):
                        continue
                    u = urljoin(base, part)
                    if u.startswith("http") and not BAD_IMG.search(u) and u.split("?")[0] not in [o.split("?")[0] for o in out]:
                        out.append(u)
    return out[:limit]


def detect_brand(title: str, hint: str, aliases: dict) -> str:
    for jp, en in aliases.items():
        if jp in title:
            return en
    if hint and hint.lower() in title.lower():
        return hint
    return hint or (title.split()[0][:20] if title.split() else "")


def model_key(title: str, brand: str, aliases: dict) -> str:
    """A short key that is the same across listings of one model (used to compare used prices)."""
    t = SIZE_RE.sub(" ", title)
    t = re.sub(r"【[^】]*】|\([^)]*\)|（[^）]*）", " ", t)
    for jp, en in list(aliases.items()) + [(brand, brand)]:
        if jp:
            t = t.replace(jp, " ")
        if en:
            t = re.sub(re.escape(en), " ", t, flags=re.I)
    for tok in TOKEN_RE.findall(t):
        if re.search(r"\d", tok) and not re.fullmatch(r"(19|20)\d\d", tok):
            return tok.strip("-/.")
    words = [w for w in t.split() if w and not re.fullmatch(r"[A-Z]{1,3}番|ランダム番|\d+番台?", w)]
    return " ".join(words[:3])[:40] or title[:32]


def parse_listing(html: str, page_url: str, site: dict, q: dict, aliases: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    link_re = re.compile(site["link_re"])
    seen: set = set()
    items: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"]).split("#")[0]
        m = link_re.search(urlparse(href).path)
        key = href.split("?")[0]
        if not m or key in seen:
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        price = find_price(text)
        if not text or not price or SOLD_RE.search(text):
            continue
        seen.add(key)
        imgs = images_in(a, page_url) or (images_in(a.parent, page_url) if a.parent else [])
        rank = (RANK_RE.search(text) or [None, ""])[1]
        store = (STORE_RE.search(text) or [None, ""])[1].strip()
        if "ランク" in text:
            head = re.split(r"\s+ランク[：:]", text)[0]
        else:
            head = re.sub(r"[¥￥]?\s*[\d,]{3,9}\s*(?:円|\(税込\)|（税込）)", " ", text)
        title = dedupe_title(re.sub(r"\s+", " ", SIZE_RE.sub(" ", head)).strip())
        brand = detect_brand(title, q.get("brand", ""), aliases)
        cat = q["cat"]
        if cat in ("camera", "lens"):
            cat = "lens" if LENS_RE.search(title) else "camera"
        model = model_key(title, brand, aliases)
        cid = re.sub(r"[^A-Za-z0-9]", "", m.group(1)) if m.groups() else hashlib.md5(key.encode()).hexdigest()[:10]
        items.append({
            "id": ("k" if q["site"] == "komehyo" else "n") + cid,
            "cat": cat, "src": q["site"], "brand": brand, "model": model, "desc": title[:90],
            "cond": rank.replace("中古品", "").replace("新品", "New") if rank else "",
            "jpy": price, "kg": KG.get(cat, 0.8), "sq": model, "store": store,
            "imgs": imgs, "snap": False, "url": href,
        })
    return items


# ------------------------------------------------------------------ pricing inputs
def load_comps(path: Path) -> dict:
    """Thai secondhand listings you logged: model_key -> [{s, st, thb, url, note}]."""
    out: dict = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    thb = int(float(str(r.get("thb", "")).replace(",", "")))
                except ValueError:
                    continue
                k = norm(r.get("model_key", ""))
                if k and thb > 0:
                    out.setdefault(k, []).append({"s": (r.get("source") or "Thai listing").strip(), "st": (r.get("status") or "Listed").strip(),
                                                   "thb": thb, "url": (r.get("url") or "").strip(), "note": (r.get("note") or "").strip()})
    return out


def match_comps(comps: dict, key: str) -> list:
    k = norm(key)
    if k in comps:
        return comps[k]
    for ck, v in comps.items():
        if len(ck) >= 5 and len(k) >= 5 and (ck in k or k in ck):
            return v
    return []


def fetch_fx(prev: float) -> tuple[float, str]:
    for u in ("https://open.er-api.com/v6/latest/JPY", "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=THB"):
        try:
            v = float(requests.get(u, timeout=10).json()["rates"]["THB"])
            if 0.05 < v < 1:
                return round(v, 5), dt.date.today().isoformat()
        except Exception:  # noqa: BLE001
            continue
    return prev, ""


# ------------------------------------------------------------------ pipeline
def run(cfg: dict, fetcher, data_dir: Path = DATA, dry_run: bool = False, limit: int | None = None, fx_fn=fetch_fx) -> dict:
    prod_path = data_dir / "products.json"
    prev = json.loads(prod_path.read_text(encoding="utf-8")) if prod_path.exists() else {}
    fx, fx_date = fx_fn(float(prev.get("fx", 0.2118)))
    comps = load_comps(data_dir / "th_comps.csv")
    sites = cfg["sites"]
    pages = int(cfg.get("pages", 2))
    budget = limit if limit is not None else 10**6
    items: dict = {}
    qlog: list = []
    counts = {k: {"items": 0, "ok": 0, "failed": 0} for k in sites}

    for q in cfg["queries"]:
        site = sites[q["site"]]
        for pg in range(1, pages + 1):
            if budget <= 0:
                break
            url = q.get("url") or q.get("url_tpl", site["search_url"]).format(q=quote(q["q"]))
            if pg > 1:
                url += ("&" if "?" in url else "?") + site.get("page_param", "page") + "=" + str(pg)
            budget -= 1
            html, note = fetcher.get(url)
            entry = {"site": q["site"], "cat": q["cat"], "url": url, "found": 0, "note": "" if html else note}
            qlog.append(entry)
            if not html:
                counts[q["site"]]["failed"] += 1
                break
            counts[q["site"]]["ok"] += 1
            got = parse_listing(html, url, site, q, cfg.get("brand_alias", {}))
            entry["found"] = len(got)
            for it in got:
                if cfg.get("min_jpy", 0) <= it["jpy"] <= cfg.get("max_jpy", 10**9):
                    items.setdefault(it["id"], it)
            if len(got) < 10:  # last page
                break
        if budget <= 0:
            break

    live = list(items.values())
    # Japan used-market reference per model: median asking price of all listings of the same model.
    groups: dict = {}
    for it in live:
        groups.setdefault((it["cat"], norm(it["sq"])), []).append(it["jpy"])
    for it in live:
        g = groups[(it["cat"], norm(it["sq"]))]
        it["mkt"], it["mktN"] = int(statistics.median(g)), len(g)
        it["comps"] = match_comps(comps, it["sq"]) or match_comps(comps, it["model"])
        counts[it["src"]]["items"] += 1

    now = dt.datetime.now(dt.timezone.utc)
    status = {"generatedAt": now.isoformat(timespec="seconds"), "ok": False, "live_items": len(live), "sites": counts, "queries": qlog}
    need = int(cfg.get("min_total_live", 15))
    if len(live) < need:
        status["message"] = (f"Only {len(live)} listings parsed (need {need}); products.json left unchanged. "
                             "See queries[].note for HTTP errors or robots.txt blocks, then run scrape.py --probe on a listing URL.")
    else:
        out = {"source": "live", "generated": now.date().isoformat(), "generatedAt": now.isoformat(timespec="seconds"),
               "fx": fx, "fxDate": fx_date, "counts": {"live": len(live), "seed": 0}, "items": live}
        status.update(ok=True, message=f"Wrote {len(live)} listings.")
        if not dry_run:
            prod_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if not dry_run:
        (data_dir / "scrape_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    return status


def probe(url: str, cfg: dict, fetcher) -> None:
    html, note = fetcher.get(url)
    print("fetch:", note)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    print("bytes:", len(html), "| title:", (soup.title.string or "").strip()[:80] if soup.title and soup.title.string else "-")
    for name, s in cfg["sites"].items():
        rx = re.compile(s["link_re"])
        links = [a for a in soup.find_all("a", href=True) if rx.search(urlparse(urljoin(url, a["href"])).path)]
        print(f"  {name}: {len(links)} product links match link_re")
        for a in links[:2]:
            print("    text:", re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:140])
            print("    imgs:", images_in(a, url)[:2])
    if len(soup.find_all("a")) < 15:
        print("Few links found: the page is probably rendered by JavaScript. Retry with --browser.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--limit", type=int, help="max listing pages to fetch; implies --dry-run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--probe", metavar="URL")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    f = Fetcher(cfg, browser=a.browser or bool(cfg.get("use_browser")))
    try:
        if a.probe:
            probe(a.probe, cfg, f)
            return 0
        st = run(cfg, f, dry_run=a.dry_run or a.limit is not None, limit=a.limit)
        print(st["message"])
        for n, c in st["sites"].items():
            print(f"  {n}: {c['items']} listings, pages ok {c['ok']}, failed {c['failed']}")
        return 0
    finally:
        f.close()


if __name__ == "__main__":
    sys.exit(main())
