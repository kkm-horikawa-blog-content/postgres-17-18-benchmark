#!/usr/bin/env python3
"""
ブログ記事用の図を再生成する（記事の「追加検証」で得た実測値を埋め込み）。
出力先: charts/output/*.png （リポジトリ相対）

注: ここに直書きした数値は「ある1つの環境（16コア・37GB・ローカルNVMe・2000万件）」
での実測中央値。自分の環境の結果に置き換えて使うことを想定している。
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

# 日本語フォント（あれば使う。無ければ既定）
for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
          "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
        plt.rcParams["font.family"] = "Noto Sans CJK JP"
        break
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT, exist_ok=True)


def fig_s1_recovery():
    labels = ["PG17.9 既定\n(並列・2ワーカー)", "PG18 既定\n(直列・並列なし)",
              "PG18  mpw=8\n(並列を取り戻す)", "PG17.9 + 拡張統計", "PG18 + 拡張統計"]
    vals = [3.1, 5.7, 2.9, 1.5, 1.4]
    colors = ["#64748b", "#dc2626", "#059669", "#2563eb", "#2563eb"]
    fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=200)
    ax.barh(range(len(labels)), vals, color=colors, height=0.62, zorder=3)
    ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels, fontsize=13)
    ax.invert_yaxis(); ax.set_xlabel("実行時間（秒・小さいほど速い）", fontsize=13)
    ax.set_xlim(0, 6.4); ax.grid(axis="x", color="#e5e7eb", zorder=0)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    for i, v in enumerate(vals):
        ax.text(v + 0.08, i, f"{v:.1f}秒", va="center", fontsize=14, fontweight="bold", color=colors[i])
    ax.set_title("大きな集計：18は既定で約2倍に転落 → 並列を取り戻せば回復、推定を直せば両版とも最速",
                 fontsize=14, fontweight="bold", color="#0f172a", pad=14)
    fig.tight_layout(); fig.savefig(f"{OUT}/s1_recovery.png", facecolor="white")


def fig_s4_aio():
    groups = ["PG17.9\n(AIOなし)", "PG18 sync\n(AIOオフ)", "PG18 worker\n(AIO)", "PG18 io_uring\n(AIO)"]
    iowait = [1.60, 1.65, 0.05, 0.26]; wall = [1.97, 1.79, 1.56, 1.55]
    x = np.arange(len(groups)); w = 0.38
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=200)
    ax.bar(x - w / 2, iowait, w, label="I/O待ち時間", color="#93c5fd", zorder=3)
    ax.bar(x + w / 2, wall, w, label="実行時間（実時間）", color="#1d4ed8", zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=12)
    ax.set_ylabel("秒（小さいほど速い）", fontsize=13); ax.set_ylim(0, 2.4)
    ax.grid(axis="y", color="#e5e7eb", zorder=0)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.legend(fontsize=12, loc="upper right")
    ax.set_title("深いJOIN（cold）：非同期I/Oは「I/O待ち」を激減させるが、速いNVMeでは「実時間」はほぼ縮まない",
                 fontsize=12.5, fontweight="bold", color="#0f172a", pad=12)
    fig.tight_layout(); fig.savefig(f"{OUT}/s4_aio.png", facecolor="white")


def fig_concurrency():
    conc = [1, 16, 32, 64, 96]
    series = [("sync（非同期I/Oオフ）", [778, 3009, 2926, 2806, 2765], "#059669", "-o"),
              ("io_uring（AIO）", [755, 2514, 2419, 2442, 2421], "#2563eb", "-o"),
              ("worker・io_workers=16（AIO）", [None, 2265, 2421, 2503, 2425], "#f59e0b", "-s"),
              ("worker・既定 io_workers=3（AIO）", [345, 1456, 2299, 2467, 2460], "#dc2626", "-o")]
    fig, ax = plt.subplots(figsize=(11, 6), dpi=200)
    for label, y, c, st in series:
        ax.plot(conc, y, st, color=c, lw=2.4, ms=7, label=label)
    ax.set_xlabel("同時接続数（クライアント）", fontsize=13)
    ax.set_ylabel("スループット TPS（大きいほど良い）", fontsize=13)
    ax.set_xticks(conc); ax.set_ylim(0, 3400); ax.grid(color="#e5e7eb", zorder=0)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.legend(fontsize=11.5, loc="lower right", framealpha=0.95)
    ax.set_title("同時アクセスが多い時：非同期I/Oの優位は消え、既定workerはむしろ最も遅い\n"
                 "（ディスク律速・ランダム読み。多数の接続自体がI/Oを並行化するためAIOの先読みが不要に）",
                 fontsize=13, fontweight="bold", color="#0f172a", pad=14)
    fig.tight_layout(); fig.savefig(f"{OUT}/concurrency.png", facecolor="white")


if __name__ == "__main__":
    fig_s1_recovery(); fig_s4_aio(); fig_concurrency()
    print(f"saved 3 figures to {OUT}/")
