#!/usr/bin/env python3
"""Offline test (no network): python scraper/test_scrape.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrape  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))


def kome(code, title, brand, rank, store, price, img=True, retail=""):
    """Anchor text copied from the live Komehyo listing format (title appears twice)."""
    im = f'<img alt="{title}" data-src="https://img.komehyo.jp/items/{code}/1.jpg" src="data:image/gif;base64,R0lG">' if img else ""
    return (f'<li><a href="https://komehyo.jp/product/{code}/">{im}<p>{title} {title} {brand} ランク：{rank} '
            f'在庫店舗：{store} {retail}￥{price:,}(税込) ￥{price:,}(税込)</p></a></li>')


def netmall(pid, model, price, brand, kind, img=True, sold=False):
    im = f'<img src="https://netmall.hardoff.co.jp/img/{pid}.jpg">' if img else ""
    return f'<li><a href="/product/{pid}/">{im}<span>{kind}</span><span>{model}</span><span>{price:,}円</span><span>{brand}</span>{"<i>SOLD OUT</i>" if sold else ""}</a></li>'


def pages():
    p = {}
    watch = "".join(kome(f"270-004-000-{i:04d}", "セイコー プレザージュ SARW035 自動巻", "SEIKO", "中古品A", "名古屋本館", 60000 + i * 5000, retail="参考上代:￥132,000 ") for i in range(6))
    watch += kome("270-004-000-9999", "ロレックス デイトジャスト 16233 SSxYG 自動巻 L番", "ROLEX", "中古品B", "KOMEHYO SHINJUKU", 1250000)  # over budget
    p["https://komehyo.jp/watch-mens/?q=" + quote("セイコー")] = f"<ul>{watch}</ul>"
    bag = "".join(kome(f"230-000-100-{i:04d}", "ルイ・ヴィトン モノグラム キーポル55 M41424", "LOUIS VUITTON", "中古品B", "梅田店", 90000 + i * 20000) for i in range(4))
    bag += kome("230-000-100-8888", "シャネル マトラッセ チェーンショルダーバッグ", "CHANEL", "中古品A", "天神店", 330000, img=False)
    p["https://komehyo.jp/brandbag/?q=" + quote("ルイ・ヴィトン")] = f"<ul>{bag}</ul>"
    ring = "".join(kome(f"260-004-200-{i:04d}", "カルティエ ラブリング サイズ：13.5(54)号", "Cartier", "中古品A", "神戸三宮店", 100000 + i * 10000, retail="参考上代:￥231,000 ") for i in range(4))
    p["https://komehyo.jp/brandjewelry_ring/?q=" + quote("カルティエ")] = f"<ul>{ring}</ul>"
    cam = kome("230-000-300-0001", "キヤノン EOS R6 ボディ", "Canon", "中古品A", "新宿", 190000) + kome("230-000-300-0002", "キヤノン RF24-70mm F2.8 L IS USM レンズ", "Canon", "中古品A", "新宿", 150000)
    p["https://komehyo.jp/camera/?q=" + quote("キヤノン")] = f"<ul>{cam}</ul>"
    nm = "".join(netmall(2000000 + i, "WH-1000XM4", 22000 + i * 1000, "SONY", "ワイヤレスヘッドホン") for i in range(6))
    nm += netmall(2999999, "WH-1000XM4", 18000, "SONY", "ワイヤレスヘッドホン", img=False, sold=True)
    p["https://netmall.hardoff.co.jp/search/?q=" + quote("SONY ヘッドホン")] = f"<ul>{nm}</ul>"
    return p


class Fake:
    def __init__(self, pg):
        self.pg = pg
        self.asked = []

    def get(self, url):
        self.asked.append(url)
        return (self.pg[url], "ok") if url in self.pg else (None, "HTTP 404")


def main():
    pg = pages()
    qs = [q for q in CFG["queries"] if (q["site"], q["q"]) in {("komehyo", "セイコー"), ("komehyo", "ルイ・ヴィトン"), ("komehyo", "カルティエ"), ("komehyo", "キヤノン"), ("netmall", "SONY ヘッドホン")}]
    qs = [q for q in qs if not (q["site"] == "komehyo" and q["cat"] == "watch" and q["brand"] != "セイコー") and not (q["cat"] == "ring" and q["brand"] != "カルティエ") and not (q["cat"] == "camera" and q["q"] != "キヤノン") and not (q["cat"] == "lens")]
    cfg = {**CFG, "queries": qs + [{"site": "komehyo", "cat": "lens", "brand": "CANON", "q": "キヤノン", "url_tpl": "https://komehyo.jp/camera/?q={q}"}], "min_total_live": 15, "pages": 1}
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "data" / "th_comps.csv", tmp / "th_comps.csv")
    (tmp / "products.json").write_text(json.dumps({"source": "empty", "fx": 0.2118, "items": []}), encoding="utf-8")

    st = scrape.run(cfg, Fake(pg), data_dir=tmp, fx_fn=lambda a: (0.2118, "2026-09-19"))
    assert st["ok"], st
    out = json.loads((tmp / "products.json").read_text(encoding="utf-8"))
    items = out["items"]
    by = {i["id"]: i for i in items}

    # over-budget, sold-out listings are dropped
    assert not any(i["jpy"] > 480000 for i in items), "budget filter"
    assert not any("2999999" in i["id"] for i in items), "sold-out filter"
    cats = {}
    for i in items:
        cats.setdefault(i["cat"], []).append(i)
    assert {"watch", "bag", "ring", "camera", "lens", "earphones"} <= set(cats), sorted(cats)

    w = cats["watch"][0]
    assert w["brand"] == "SEIKO" and w["model"] == "SARW035" and w["cond"] == "A" and w["store"] == "名古屋本館", w
    assert w["url"].startswith("https://komehyo.jp/product/270-004-000-") and w["imgs"] == [f"https://img.komehyo.jp/items/{w['url'].rstrip('/').split('/')[-1]}/1.jpg"], w["imgs"]
    assert "参考上代" not in json.dumps(items, ensure_ascii=False) and not any("ref" in i for i in items), "retail price must not be stored"
    # Japan used-market median per model (6 watches: 60k..85k => 72.5k)
    assert w["mktN"] == 6 and w["mkt"] == 72500, (w["mkt"], w["mktN"])
    assert cats["watch"][0]["desc"].count("SARW035") == 1, "title de-duplicated"

    bag = [i for i in cats["bag"] if i["brand"] == "LOUIS VUITTON"][0]
    assert bag["model"] == "M41424", bag["model"]
    ring = cats["ring"][0]
    assert ring["brand"] == "CARTIER" and "13.5" not in ring["model"] and ring["mktN"] == 4, ring
    assert {i["model"] for i in cats["camera"]} != {i["model"] for i in cats["lens"]}
    assert any("レンズ" in i["desc"] for i in cats["lens"]) and all("レンズ" not in i["desc"] for i in cats["camera"])
    xm4 = cats["earphones"][0]
    assert xm4["model"] == "WH-1000XM4" and xm4["jpy"] >= 22000 and xm4["src"] == "netmall" and xm4["url"].startswith("https://netmall.hardoff.co.jp/product/"), xm4
    assert xm4["comps"] and xm4["comps"][0]["thb"] == 6000, "Thai used comps attach by model"

    # too few results must not overwrite good data
    before = (tmp / "products.json").read_text(encoding="utf-8")
    st2 = scrape.run(cfg, Fake({}), data_dir=tmp, fx_fn=lambda a: (0.2118, "x"))
    assert not st2["ok"] and (tmp / "products.json").read_text(encoding="utf-8") == before and "left unchanged" in st2["message"]
    print("scraper OK:", {k: len(v) for k, v in cats.items()}, "|", st["message"])
    (Path(tempfile.gettempdir()) / "scout_scraped.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
