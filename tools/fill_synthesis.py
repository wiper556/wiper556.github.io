# -*- coding: utf-8 -*-
"""合成表(synthesisTable)が空の武将に、ixanary の合成テーブルから表を入れる。

**なぜ機械でやるか。** 2026-09-11 時点で表が空の武将が1332体あり、
その初期スキルは1092種、うち1034種は**その1体しか持っていない**。
まとめ買いが効かないので、1体ずつ人が調べると1000回の調査になる。
一方で中身は推測の余地が無い。A-3-0 の対応そのままで、

    武将の synthesisTable の S枠の skill       = 初期スキルのページの 1次・S枠
    同じ行の afterSkill                        = 同じページの 2次・S枠

**スロットは推測しない**(A-3-8)。ページに無い枠は書かない。

■ 数値(対象/確率/効果)をどこから取るか

ページに出るのはスキル名とランクだけなので、性能は別に要る。順に、

  1. **既に埋まっている他の武将の合成表**にある同じスキルの行(最頻値)。
     同じスキルなら同じ値になるはずで、実際 1365体ぶんの行のうち
     値が2通り以上あるのは書式のゆれが中心。最頻値を採る。
  2. `data/skill/{名前}.json`(うちがページを持つスキル)の対象と baseRate。
     効果文はページの書式(effectSummary)が合成表の書式と違うので使わない。
  3. どちらにも無ければ **null を入れる**(D-07。フィールドごと省略しない)。
     あとで人が埋められるよう、件数とスキル名を出す。

つまりこの道具が作るのは「スキル名・ランク・スロットは ixanary 由来、
数値はうちの既存データ由来」の表。**新しい数値をどこからも発明しない。**

■ 使い方

    python tools/fill_synthesis.py --dry                 # 下見(既定)
    python tools/fill_synthesis.py --apply               # 書き込む
    python tools/fill_synthesis.py --apply --dir busho-kyoku --limit 50
    python tools/fill_synthesis.py --check               # 既存の表と付き合わせるだけ

**書く前に必ず --check を通すこと。** 既に埋まっている表を同じ手順で作り直して
一致するかを見る検査で、ここがずれたまま流し込むと1000体ぶん間違える。
"""
import argparse
import collections
import glob
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import audit_characters as A          # 取得口と合成テーブル解析を借りる

SLOTS = ("A", "B", "C", "S1", "S2")


def load_chars():
    out = []
    for d in sorted(glob.glob(os.path.join(ROOT, "data", "busho*"))):
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            e = json.load(io.open(f, encoding="utf-8"),
                          object_pairs_hook=collections.OrderedDict)
            out.append((f, os.path.basename(d), e))
    return out


def known_values(chars):
    """既存の合成表から「スキル名 -> (対象, 確率, 効果)」の最頻値を作る。"""
    seen = collections.defaultdict(collections.Counter)
    for _, _, e in chars:
        for r in (e.get("synthesisTable") or []):
            if r.get("skill") and r.get("effectShort"):
                seen[r["skill"]][(r.get("target"), r.get("rate"),
                                  r.get("effectShort"))] += 1
            if r.get("afterSkill") and r.get("afterEffectShort"):
                seen[r["afterSkill"]][(r.get("afterTarget"), r.get("afterRate"),
                                       r.get("afterEffectShort"))] += 1
    return {k: c.most_common(1)[0][0] for k, c in seen.items()}


def consensus_after(chars):
    """「このスキルの移植後は何か」を、うちの既存データの多数決で持つ。

    ixanary の2次が空のときの受け皿(after_of 参照)。**空欄を自己参照と
    読み違えない**ためだけに使い、ixanary に答えが書いてあるときは使わない。
    """
    seen = collections.defaultdict(collections.Counter)
    for _, _, e in chars:
        for r in (e.get("synthesisTable") or []):
            if r.get("skill") and r.get("afterSkill"):
                seen[r["skill"]][r["afterSkill"]] += 1
    out = {}
    for k, c in seen.items():
        top, n = c.most_common(1)[0]
        if n * 2 > sum(c.values()):        # 割れているものは使わない
            out[k] = top
    return out


def skill_pages():
    """data/skill のページから、対象・確率・ランクを借りる。"""
    out = {}
    for p in glob.glob(os.path.join(ROOT, "data", "skill", "*.json")):
        j = json.load(io.open(p, encoding="utf-8"))
        rate = j.get("baseRate")
        if isinstance(rate, float) and rate == int(rate):
            rate = int(rate)
        out[j.get("name")] = (j.get("target"),
                              ("%s%%" % rate) if rate is not None else None,
                              j.get("rank"))
    return out


def rank_for(name, ixanary_rank, pages):
    """ランクは、うちがページを持っているならそちらを正とする。

    **ixanary と食い違うことがある**(2026-09-11、60体の照合で3体)。
    例: 星神闘覇 は ixanary が SSS、うちのスキルページは SS。
    監査 S-17 は「合成表のランク = うちのスキルページのランク」を見ているので、
    ixanary の値をそのまま入れると内部で食い違う。
    **どちらが本当かはこの道具では決められない**ので、ここでは内部整合を採り、
    食い違ったスキルは一覧に出して人が調べられるようにする。
    """
    if name in pages and pages[name][2]:
        return pages[name][2], (ixanary_rank if ixanary_rank
                                and ixanary_rank != pages[name][2] else None)
    return ixanary_rank, None


def values_for(name, known, pages):
    """(対象, 確率, 効果) を返す。分からないところは None。"""
    if name in known:
        return known[name]
    if name in pages:
        t, r, _ = pages[name]
        return (t, r, None)
    return (None, None, None)


def after_of(a, b, g1, initial, consensus):
    """移植後のスキル名を決める。

    **2次のセルが空のときに、1次の名前をそのまま移植後にしてはいけない。**
    空は「そのスキルのまま」という意味ではなく、ixanary が持っていないだけ。
    2026-09-11、この取り違えで 瀬名姫（3）No.2577 の C枠が
    「戦陣 破軍→戦陣 破軍」になり、同じスキルを持つ他の50体(→天穿神滅)と
    食い違って監査 S-11 が鳴った。空のときは、**同じ1次スキルが他の武将で
    何になっているか**(うちのデータの多数決)を使い、それも無ければ自己参照にする。

    **A-3-13 はここでは当てない(2026-09-11、うぐさん待ち)。**
    A-3-13 は「1次がその武将の初期スキルの枠は、移植後が必ず S1 の中身になる」と
    定めていて、そのとおりに書き換えると3体(No.1121/1125/1967)で監査 S-11
    「同じスキルが武将により別の afterSkill になっている」が HIGH で鳴る。
    A-3-13 は武将ごとの規則、S-11 は全体で1つという前提で、**両立しない。**
    どちらを正にするかはルールの判断なので、ここでは ixanary の2次をそのまま使い、
    3体が MID(移植後がS1と不一致)で残る状態にして報告する。
    """
    name = b[0] if b and b[0] else None
    if name:
        return name
    # ここから下は「2次のセルが空」のとき。**空の意味は枠によって違う。**
    #   ・その枠が**そのページのスキル自身**(= 武将の初期スキル)なら、
    #     それ以上変化しないという意味で、自己参照でよい。
    #     勝軍神撃・無間国崩しのC枠がこれで、スキル側に登録済みの
    #     ownHiddenCandidate も自己参照になっている。
    #   ・その枠が**別のスキル**なら、単に ixanary が持っていないだけ。
    #     そのスキルが他の武将で何になっているか(うちのデータの多数決)を使う。
    #     重めな正室のC枠(戦陣 破軍)がこれで、自己参照にすると
    #     他50体の「戦陣 破軍→天穿神滅」と食い違って監査 S-11 が鳴る。
    if initial and A.norm(a[0]) == A.norm(initial):
        return a[0]
    return consensus.get(a[0]) or a[0]


def build_rows(gens, known, pages, clash=None, initial=None, consensus=None):
    """解析した 1次/2次 から synthesisTable の行を組み立てる。"""
    rows = []
    consensus = consensus or {}
    g1, g2 = gens.get("1次") or {}, gens.get("2次") or {}
    for slot in SLOTS:
        a, b = g1.get(slot), g2.get(slot)
        if not a or not a[0]:
            continue                      # 枠が無いものは書かない(推測しない)
        t, rate, eff = values_for(a[0], known, pages)
        rank, cl = rank_for(a[0], a[1], pages)
        if cl and clash is not None:
            clash[(a[0], pages[a[0]][2], cl)] += 1
        row = collections.OrderedDict()
        row["slot"] = slot
        row["skill"] = a[0]
        row["rank"] = rank
        row["afterSkill"] = after_of(a, b, g1, initial, consensus)
        _ix = (b[1] if b and b[0] and b[0] == row["afterSkill"]
               else (a[1] if row["afterSkill"] == a[0] else None))
        arank, acl = rank_for(row["afterSkill"], _ix, pages)
        if acl and clash is not None:
            clash[(row["afterSkill"], pages[row["afterSkill"]][2], acl)] += 1
        row["afterRank"] = arank
        row["target"] = t
        row["rate"] = rate
        row["effectShort"] = eff
        if row["afterSkill"] != row["skill"]:
            at, ar, ae = values_for(row["afterSkill"], known, pages)
            row["afterTarget"] = at
            row["afterRate"] = ar
            row["afterEffectShort"] = ae
        rows.append(row)
    return rows


def gens_for(skill):
    html = A.fetch_skill(skill)
    return A.parse_generations(html)


def cmd_check(chars, known, pages, limit, consensus=None):
    """既に埋まっている表を作り直して、一致するかを見る。"""
    done = [(f, d, e) for f, d, e in chars
            if e.get("synthesisTable") and e.get("initialSkill")]
    done = done[:limit] if limit else done
    ok = ng = skip = 0
    diffs = collections.Counter()
    clash = collections.Counter()
    for f, d, e in done:
        gens = gens_for(e["initialSkill"])
        if not gens:
            skip += 1
            continue
        made = {r["slot"]: r for r in
                build_rows(gens, known, pages, clash,
                           e.get("initialSkill"), consensus)}
        cur = {r.get("slot"): r for r in e["synthesisTable"]}
        bad = []
        for slot in SLOTS:
            m, c = made.get(slot), cur.get(slot)
            if not m or not c:
                continue
            for key in ("skill", "afterSkill", "rank", "afterRank"):
                if m.get(key) and c.get(key) and A.norm(m[key]) != A.norm(c[key]):
                    bad.append("%s枠 %s: 既存=%s / 作り直し=%s"
                               % (slot, key, c[key], m[key]))
                    diffs[key] += 1
        if bad:
            ng += 1
            print("★ No.%-6s %s" % (e.get("no"), e.get("name")))
            for b in bad[:4]:
                print("     " + b)
        else:
            ok += 1
    print()
    print("照合 %d体: 一致 %d / 不一致 %d / 表が取れない %d"
          % (len(done), ok, ng, skip))
    if diffs:
        print("食い違った項目: %s" % dict(diffs))
    show_clash(clash)
    return 1 if ng else 0


def show_clash(clash):
    if not clash:
        return
    print()
    print("ランクが ixanary と食い違うスキル(うちのページを正とした):")
    for (nm, ours, theirs), n in clash.most_common(12):
        print("   %-16s うち=%-4s ixanary=%-4s (%d行)" % (nm, ours, theirs, n))


def cmd_patch(chars, known, pages, apply_it):
    """既に在る表の、空いている性能欄だけを埋める。

    スキル名・ランク・枠には触らない。**新しくスキルページを作った直後**に使う。
    ページを作るまでは値の出どころが無く null のままになるので(D-07)、
    出どころができた時点で入れ直す。
    """
    n = rows = 0
    for f, d, e in chars:
        tbl = e.get("synthesisTable") or []
        if not tbl:
            continue
        touched = False
        for r in tbl:
            if r.get("skill") and not r.get("effectShort"):
                t, rate, eff = values_for(r["skill"], known, pages)
                for k, v in (("target", t), ("rate", rate), ("effectShort", eff)):
                    if v and not r.get(k):
                        r[k] = v
                        touched = True
                        rows += 1
            af = r.get("afterSkill")
            if af and af != r.get("skill") and not r.get("afterEffectShort"):
                t, rate, eff = values_for(af, known, pages)
                for k, v in (("afterTarget", t), ("afterRate", rate),
                             ("afterEffectShort", eff)):
                    if v and not r.get(k):
                        r[k] = v
                        touched = True
                        rows += 1
        if touched:
            n += 1
            if apply_it:
                with io.open(f, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(e, fh, ensure_ascii=False, indent=1)
                    fh.write("\n")
    print("性能欄を埋めた武将 %d体 / 項目 %d件%s"
          % (n, rows, "" if apply_it else "(下見)"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--patch", action="store_true",
                    help="既に在る表の空欄だけを埋める(名前と枠は触らない)")
    ap.add_argument("--dir", default=None, help="data/busho* の名前で絞る")
    ap.add_argument("--only", default=None,
                    help="No.を1行ずつ書いたファイル。既に表があっても作り直す")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    A.ONLINE = True
    for d in (A.CACHE_SKILL, A.CACHE_CARD):
        if not os.path.exists(d):
            os.makedirs(d)

    chars = load_chars()
    known = known_values(chars)
    pages = skill_pages()
    consensus = consensus_after(chars)
    print("既存の表から拾えたスキル %d種 / うちページを持つ %d種"
          % (len(known), len(pages)))

    if a.check:
        return cmd_check(chars, known, pages, a.limit, consensus)
    if a.patch:
        return cmd_patch(chars, known, pages, a.apply)

    only = None
    if a.only:
        only = {l.strip() for l in io.open(a.only, encoding="utf-8")
                if l.strip()}
        print("--only: %d体を作り直す(既に表があっても上書きする)" % len(only))
    todo = [(f, d, e) for f, d, e in chars
            if ((str(e.get("no")) in only) if only
                else not e.get("synthesisTable"))
            and e.get("initialSkill")
            and (a.dir is None or d == a.dir)]
    if a.limit:
        todo = todo[:a.limit]
    print("対象 %d体%s" % (len(todo), "" if a.apply else "(下見)"))

    filled = empty = 0
    holes = collections.Counter()
    clash = collections.Counter()
    stat = collections.Counter()
    for f, d, e in todo:
        gens = gens_for(e["initialSkill"])
        rows = (build_rows(gens, known, pages, clash,
                           e.get("initialSkill"), consensus) if gens else [])
        if not rows:
            empty += 1
            holes["表が取れない:" + e["initialSkill"]] += 1
            continue
        for r in rows:
            stat["行"] += 1
            if r.get("effectShort") is None:
                holes["効果が不明:" + r["skill"]] += 1
            else:
                stat["効果あり"] += 1
            if r.get("target"):
                stat["対象あり"] += 1
            if r.get("rate"):
                stat["確率あり"] += 1
            if not any((r.get("target"), r.get("rate"), r.get("effectShort"))):
                stat["3つとも空"] += 1
        filled += 1
        if a.apply:
            e["synthesisTable"] = rows
            with io.open(f, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(e, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
    print("表を作れた %d体 / 作れなかった %d体" % (filled, empty))
    miss = [(k, v) for k, v in holes.items() if k.startswith("効果が不明:")]
    print("効果文が埋まらなかった行 %d件(%d種のスキル)"
          % (sum(v for _, v in miss), len(miss)))
    print("行の内訳: 合計%d / 効果あり%d / 対象あり%d / 確率あり%d / 3つとも空%d"
          % (stat["行"], stat["効果あり"], stat["対象あり"],
             stat["確率あり"], stat["3つとも空"]))
    for k, v in sorted(holes.items(), key=lambda kv: -kv[1])[:15]:
        print("   %-40s %d" % (k, v))
    show_clash(clash)
    if not a.apply:
        print()
        print("書き込むには --apply を付ける。**先に --check を通すこと。**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
