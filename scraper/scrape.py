#!/usr/bin/env python3
"""JAPANMART data refresh: Komehyo + Netmall (Hard Off) -> data/products.json

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
BROWSER_HEADERS = {  # what an ordinary browser sends when you open a page
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class Fetcher:
    def __init__(self, cfg: dict, browser: bool = False):
        self.cfg, self.last = cfg, 0.0
        self.debug: dict = {}  # first refusal per site: status, server, start of the reply (helps see who blocks us)
        self.delay = float(cfg.get("delay_seconds", 2))
        self.timeout = int(cfg.get("timeout_seconds", 25))
        self.ua = cfg.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
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
            self.s.headers.update({"User-Agent": self.ua, **BROWSER_HEADERS})

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
        for attempt in range(2):
            try:
                r = self.s.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r.content.decode("utf-8", errors="replace"), "ok"
                err = f"HTTP {r.status_code}"
                self.debug.setdefault(urlparse(url).netloc, {
                    "status": r.status_code, "server": r.headers.get("server", ""), "content_type": r.headers.get("content-type", ""),
                    "reply_starts_with": re.sub(r"\s+", " ", r.text[:200])})
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


URL_RE = re.compile(r"""(?:https?:)?//[^\s"'<>)]+|/[^\s"'<>)]+""")
STYLE_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)
SKIP_ATTRS = {"alt", "class", "id", "width", "height", "style", "title", "loading", "decoding", "sizes", "role", "aria-label", "data-alt"}


def _clean_url(u: str, base: str) -> str | None:
    u = u.strip().strip("\"'")
    if not u or u.startswith("data:") or u.startswith("blob:"):
        return None
    full = urljoin(base, u)
    if not full.startswith("http"):
        return None
    if full.startswith("http://"):  # the site is https; browsers block plain-http photos on an https page
        full = "https://" + full[len("http://"):]
    return None if BAD_IMG.search(full) else full


def _candidates(node) -> list[str]:
    """Every string on a photo element that could be a photo address."""
    out: list[str] = []
    for el in node.find_all(["img", "source"]) + ([node] if getattr(node, "name", None) in ("img", "source") else []):
        for k, v in el.attrs.items():
            if k in SKIP_ATTRS:
                continue
            for x in (v if isinstance(v, list) else [v]):
                x = str(x)
                if "srcset" in k or ("," in x and " " in x):
                    parts = [p.strip().split(" ")[0] for p in re.split(r",\s+", x) if p.strip()]
                    out.extend(reversed(parts))  # srcset lists small to large: prefer the last (largest)
                else:
                    out.extend(m.group(0) for m in URL_RE.finditer(x))
    for el in node.find_all(style=True) + ([node] if getattr(node, "attrs", {}).get("style") else []):
        out.extend(STYLE_URL_RE.findall(el["style"]))
    for ns in node.find_all("noscript"):  # lazy-loading pages often keep a plain <img> inside <noscript>
        out.extend(_candidates(BeautifulSoup(ns.get_text(" "), "lxml")))
    return out


def images_in(node, base: str, limit: int = 6) -> list[str]:
    """Photo addresses inside a listing card. Any attribute counts (lazy-load names vary), with or without a file extension."""
    ranked: list[tuple[int, int, str]] = []
    for n, c in enumerate(_candidates(node)):
        u = _clean_url(c, base)
        if not u:
            continue
        ext = bool(IMG_EXT.search(u))
        looks_like_photo = ext or re.search(r"(img|image|photo|item|product|goods|upload|cdn|thumb)", u, re.I)
        if looks_like_photo and u.split("?")[0] not in [r[2].split("?")[0] for r in ranked]:
            ranked.append((0 if ext else 1, n, u))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in ranked][:limit]


def detail_images(html: str, url: str, limit: int = 4) -> list[str]:
    """Photos from a product page: the social-share image first, then other photos stored next to it."""
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    for sel in ({"property": "og:image"}, {"name": "twitter:image"}, {"property": "og:image:url"}):
        for tag in soup.find_all("meta", attrs=sel):
            u = _clean_url(tag.get("content") or "", url)
            if u and u not in found:
                found.append(u)
    for tag in soup.find_all("link", rel="image_src"):
        u = _clean_url(tag.get("href") or "", url)
        if u and u not in found:
            found.append(u)
    for blk in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(blk.string or blk.get_text() or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                for v in (x.get("image") if isinstance(x.get("image"), list) else [x.get("image")]):
                    v = v.get("url") if isinstance(v, dict) else v
                    u = _clean_url(v or "", url) if isinstance(v, str) else None
                    if u and u not in found:
                        found.append(u)
                stack.extend(v for v in x.values() if isinstance(v, (list, dict)))
    if found:  # other photos of the same item normally sit in the same folder as the share image
        folder = found[0].split("?")[0].rsplit("/", 1)[0] + "/"
        for u in images_in(soup, url, limit=12):
            if u.startswith(folder) and u not in found:
                found.append(u)
    else:
        found = images_in(soup.find("main") or soup, url, limit=limit)
    return found[:limit]


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
    streak = {k: 0 for k in sites}

    for q in cfg["queries"]:
        site = sites[q["site"]]
        if streak[q["site"]] >= 3 and counts[q["site"]]["ok"] == 0:  # refused the first 3 requests: stop asking
            qlog.append({"site": q["site"], "cat": q["cat"], "url": "", "found": 0, "note": "skipped: this site refused the first 3 requests"})
            continue
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
                streak[q["site"]] += 1
                break
            streak[q["site"]] = 0
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

    # Photos: reuse what the last run found, then open product pages for items that still have none,
    # and for the best-looking deals (to get several photos for the carousel). Capped so a run stays short.
    prev_imgs = {i["id"]: i["imgs"] for i in prev.get("items", []) if i.get("imgs")}
    for it in live:
        if not it["imgs"] and it["id"] in prev_imgs:
            it["imgs"] = prev_imgs[it["id"]]
    by_group: dict = {}
    for it in live:
        by_group.setdefault((it["cat"], norm(it["sq"])), []).append(it["jpy"])
    def deal(it):  # how far below the typical used price of its model
        g = by_group[(it["cat"], norm(it["sq"]))]
        return statistics.median(g) / it["jpy"] if len(g) > 1 else 1.0
    todo = sorted((i for i in live if not i["imgs"]), key=deal, reverse=True)
    todo += sorted((i for i in live if i["imgs"] and len(i["imgs"]) < 2 and i["id"] not in prev_imgs), key=deal, reverse=True)
    detail_left, from_detail = int(cfg.get("detail_pages", 80)) if limit is None else 0, 0
    for it in todo:
        if detail_left <= 0:
            break
        detail_left -= 1
        page, _ = fetcher.get(it["url"])
        if page:
            got = detail_images(page, it["url"])
            if got:
                extra = [u for u in it["imgs"] if u.split("?")[0] not in [g.split("?")[0] for g in got]]
                it["imgs"] = (got + extra)[:4]
                from_detail += 1
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
    status = {"generatedAt": now.isoformat(timespec="seconds"), "ok": False, "live_items": len(live), "sites": counts,
              "photos": {"listings_with_photo": sum(1 for i in live if i["imgs"]), "listings_without_photo": sum(1 for i in live if not i["imgs"]),
                         "from_product_pages": from_detail, "examples_without_photo": [i["url"] for i in live if not i["imgs"]][:3]}, "refused_by": getattr(fetcher, "debug", {}), "queries": qlog}
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
            got = images_in(a, url)
            print("    imgs:", got[:2])
            if not got:
                print("    no photo found in this card. Raw markup:", re.sub(r"\s+", " ", str(a))[:700])
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
        try:
            st = run(cfg, f, dry_run=a.dry_run or a.limit is not None, limit=a.limit)
        except Exception as e:  # noqa: BLE001  (never fail the workflow; record why instead)
            import traceback

            traceback.print_exc()
            msg = f"Scraper stopped with {type(e).__name__}: {e}. data/products.json was left unchanged."
            print(msg)
            if not (a.dry_run or a.limit is not None):
                (DATA / "scrape_status.json").write_text(json.dumps({
                    "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "ok": False, "live_items": 0, "message": msg}, ensure_ascii=False, indent=1), encoding="utf-8")
            return 0
        print(st["message"])
        for n, c in st["sites"].items():
            print(f"  {n}: {c['items']} listings, pages ok {c['ok']}, failed {c['failed']}")
        return 0
    finally:
        f.close()


if __name__ == "__main__":
    sys.exit(main())
