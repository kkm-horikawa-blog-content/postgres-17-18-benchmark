#!/usr/bin/env python3
"""
結果グラフ生成
==============
results/ 配下の pg17_*.json / pg18_*.json を読み、
シナリオ別に PG17 vs PG18 の実行時間を横棒で比較する PNG を出力する。
体感ラベル（一瞬/わずかな待ち/待たされる/固まる）も添える。
"""
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

OUT = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT, exist_ok=True)

# 日本語フォントがあれば使う（無ければラベルは英語にフォールバック）
JP = None
for cand in ["/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
             "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]:
    if os.path.exists(cand):
        JP = font_manager.FontProperties(fname=cand)
        break

SCEN_LABEL = {
    "s1_aggregate": "(1) Large aggregate scan",
    "s2_skipscan":  "(2) Skip scan (range only)",
    "s4_deepjoin":  "(4) Deep multi-table join",
    "auth_lookup":  "Auth point lookup",
    "cms_fuzzy":    "CMS fuzzy search",
}
BRAND = "#059669"
GRAY = "#94a3b8"


def load(tag, scale):
    fn = f"results/{tag}_{scale}.json"
    if not os.path.exists(fn):
        return {}
    return {r["scenario"]: r for r in json.load(open(fn))}


def chart_scale(scale):
    pg17 = load("pg17", scale)
    pg18 = load("pg18", scale)
    scenarios = [s for s in SCEN_LABEL if s in pg17 and s in pg18]
    if not scenarios:
        return
    fig, ax = plt.subplots(figsize=(9, 0.9 * len(scenarios) + 1.5))
    y = range(len(scenarios))
    h = 0.38
    v17 = [pg17[s]["median_ms"] for s in scenarios]
    v18 = [pg18[s]["median_ms"] for s in scenarios]
    ax.barh([i + h/2 for i in y], v17, height=h, color=GRAY, label="PostgreSQL 17.9")
    ax.barh([i - h/2 for i in y], v18, height=h, color=BRAND, label="PostgreSQL 18")
    for i, s in enumerate(scenarios):
        ax.text(v17[i], i + h/2, f" {v17[i]:.0f}ms", va="center", fontsize=9)
        ax.text(v18[i], i - h/2, f" {v18[i]:.0f}ms", va="center", fontsize=9, color=BRAND)
    ax.set_yticks(list(y))
    ax.set_yticklabels([SCEN_LABEL[s] for s in scenarios], fontsize=10)
    ax.set_xlabel("median execution time (ms, lower is better)")
    ax.set_title(f"PostgreSQL 17.9 vs 18  /  {int(scale):,} rows", fontsize=12)
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    out = os.path.join(OUT, f"bench_{scale}.png")
    plt.savefig(out, dpi=130)
    print("wrote", out)


def main():
    scales = set()
    for f in glob.glob("results/pg1*_*.json"):
        scales.add(f.rsplit("_", 1)[1].replace(".json", ""))
    for s in sorted(scales, key=int):
        chart_scale(s)


if __name__ == "__main__":
    main()
