# -*- coding: utf-8 -*-
"""武将カードのスクリーンショットから TYPE1/TYPE2 を切り抜く。

切り抜きの絶対ルール(2026-07-29確定):
  TYPE2(カードのみ)          = 224 x 315
  TYPE1(カード+スキルパネル) = 466 x 315
元スクリーンショットの解像度がバッチごとに違っても出力サイズは必ずこれに揃える
(拡大縮小はしない。カード左下の赤いハートを基準に絶対位置合わせするだけ)。

ハート基準の位置合わせ:
  承認済み画像(224x315)ではハートの左上が (x=6, y=267)。
  検出したハートが同じ位置に来るよう cropLeft = minX - 6 / cropTop = minY - 267 とする。

誤検出対策:
  ・x探索範囲は割合ではなく絶対55px(ダメなら40px)に固定する
  ・候補ピクセルの中央値から15px以上離れた孤立点は除外する
  ・正常なハートは概ね 19x19 / 94px。大きく外れたら誤検出として再試行する

使い方:
  python tools/crop_card.py <No> [<No> ...]      # 元スクリーンショット/スクリーンショット_<No>.png を処理
  python tools/crop_card.py --all                # アーカイブ内の全No.を処理(既存ファイルは上書きしない)
"""
import sys, pathlib
from PIL import Image, ImageChops, ImageFilter, ImageStat

ARCH = pathlib.Path(r"C:\Users\uesug\ixa-simulator-char-screenshots\元スクリーンショット")
CROPTEST = pathlib.Path(r"C:\Users\uesug\ixa-simulator-char-screenshots\crop_test")
DEST = pathlib.Path(__file__).resolve().parent.parent / "assets" / "img" / "characters"

HEART = (206, 18, 38)
TOL = 20
ANCHOR_X, ANCHOR_Y = 6, 267
TYPE2 = (224, 315)
TYPE1 = (466, 315)


def find_heart(im, xlimit):
    """ハート(概ね19x19・約94px)の左上を返す。

    2026-08-16: **中央値で絞る方法は特カードで通用しない。** 特の枠は赤で、
    ハートと同じ色域に入る。枠は縦に長いので候補の中央値がそちらへ引っ張られ、
    7x31 という縦棒が「ハート」として返っていた(今日の119枚が全滅)。
    赤い塊を連結成分に分け、**形がハートに一番近い塊**を選ぶ。
    """
    px = im.convert("RGB").load()
    W, H = im.size
    red = set()
    for y in range(int(H * 0.55), H):
        for x in range(0, min(xlimit, W)):
            r, g, b = px[x, y]
            if abs(r - HEART[0]) <= TOL and abs(g - HEART[1]) <= TOL and abs(b - HEART[2]) <= TOL:
                red.add((x, y))
    if not red:
        return None, "ハートが見つからない"

    # 連結成分に分ける(8近傍)
    best = None
    seen = set()
    for s in red:
        if s in seen:
            continue
        stack, comp = [s], []
        seen.add(s)
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (cx + dx, cy + dy)
                    if n in red and n not in seen:
                        seen.add(n)
                        stack.append(n)
        minX = min(p[0] for p in comp); minY = min(p[1] for p in comp)
        w = max(p[0] for p in comp) - minX + 1
        h = max(p[1] for p in comp) - minY + 1
        # ハートらしさ: 19x19・94px からの離れ具合。縦棒(w<<h)は大きく外れる
        score = abs(w - 19) + abs(h - 19) + abs(len(comp) - 94) / 10.0
        if best is None or score < best[0]:
            best = (score, minX, minY, w, h, len(comp))
    if best is None:
        return None, "赤い塊が1つも無い"
    return (best[1], best[2], best[3], best[4], best[5]), None


def find_heart_bottom(im, xlimit):
    """上の検出が駄目だったときだけ使う予備。

    2026-09-02 に2枚で詰まったので足した。**上の検出には触っていない**
    (抜き取り120枚で基点が1枚も変わらないことを確かめてある)。

      ・No.2640 真田幸村 … 絵柄の赤い炎が大量に候補へ上がり、画面の上の方の
        塊が選ばれて基点が負になった。→ **カード下部の帯だけを見る。**
      ・No.32640 真田幸村(パラレル) … **パラレルはハートがピンク**で、
        赤(206,18,38)の色域に入らず1つも候補が出なかった。→ **ピンクも拾う。**

    ハートの大きさは元画像の解像度で変わる(19x19/94px の回もあれば
    13x9/34px の回もある)ので、大きさではなく **形の比** で選ぶ。
    """
    px = im.convert("RGB").load()
    W, H = im.size
    cand = set()
    for y in range(int(H * 0.66), int(H * 0.95)):
        for x in range(0, min(xlimit, W)):
            r, g, b = px[x, y]
            if abs(r - HEART[0]) <= TOL and abs(g - HEART[1]) <= TOL and abs(b - HEART[2]) <= TOL:
                cand.add((x, y))
            elif r > 170 and g < r - 70 and 90 < b < 210:   # パラレルのピンク
                cand.add((x, y))
    if not cand:
        return None, "下の帯に赤もピンクも無い"
    best, seen = None, set()
    for s in cand:
        if s in seen:
            continue
        stack, comp = [s], []
        seen.add(s)
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (cx + dx, cy + dy)
                    if p in cand and p not in seen:
                        seen.add(p)
                        stack.append(p)
        minX = min(p[0] for p in comp)
        minY = min(p[1] for p in comp)
        w = max(p[0] for p in comp) - minX + 1
        h = max(p[1] for p in comp) - minY + 1
        if len(comp) < 15 or not (1.1 <= w / float(h) <= 2.4):
            continue
        # 横長すぎず縦長すぎず、面積の割に詰まっているものを選ぶ
        score = abs(w / float(h) - 1.45) * 10 + abs(len(comp) / float(w * h) - 0.55) * 10
        if best is None or score < best[0]:
            best = (score, minX, minY, w, h, len(comp))
    if best is None:
        return None, "ハートらしい形の塊が無い"
    return (best[1], best[2], best[3], best[4], best[5]), None



# ============ 形で位置を合わせる(2026-09-09) ============
#
# なぜ要るか: うぐさんが持っていない札はゲーム内で**白黒**表示になる。
# これまでの位置合わせはカード左下の**赤いハート**を探していたので、
# 白黒だと赤が消えて一切効かない。**色に頼らない目印が要る。**
#
# やり方: **同じレアリティの承認済み画像の左上をそのまま型にして、元画像から探す。**
# 左上には飾り帯とレアリティのバッジがあり、同じレアリティなら1ドットまで同じ。
# 当たった位置がそのまま切り抜きの基点になる。
#
# **平均した型は使わない。** 一度、承認済み1013枚の輪郭を足し合わせた型を作って
# 試したが、飾り帯が10pxおきの繰り返し柄なので横に10pxずれても点数が同じになり、
# 一致は56%しかなかった。繰り返さない部分に絞っても97%止まりで、白黒の No.2005 では
# 実際に(20,23)と外した(正解は(17,19))。**承認済みの実物を型にすると8枚中8枚が
# (17,19)で一致した。** レアリティごとに飾りの形が違うので、同じレアリティで比べる。
REF_MAX = 6          # 型に使う承認済み画像の枚数(多数決)
REF_BOX = (0, 0, 60, 60)
REF_SPAN = 60        # 元画像のこの範囲から探す
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def _same_rarity_refs(no):
    """同じレアリティで、画像が登録済みの No. を集める。"""
    here = None
    for d in sorted(DATA.glob("busho*")):
        if (d / ("%s.json" % no)).exists():
            here = d
            break
    if here is None:
        return []
    out = []
    for p in sorted(here.glob("*.json")):
        n = p.stem
        if n == str(no):
            continue
        if (DEST / ("no%s_full.png" % n)).exists():
            out.append(n)
        if len(out) >= REF_MAX:
            break
    return out


def _score(tpl, edge, ox, oy, w, h):
    if ox < 0 or oy < 0 or ox + w > edge.size[0] or oy + h > edge.size[1]:
        return -1
    return ImageStat.Stat(ImageChops.multiply(
        tpl, edge.crop((ox, oy, ox + w, oy + h)))).sum[0]


def find_frame(im, no):
    """同じレアリティの承認済み画像を型にして基点を求める。色は一切見ない。

    戻り値は ((left, top), None) か (None, 理由)。
    """
    refs = _same_rarity_refs(no)
    if not refs:
        return None, "同じレアリティの承認済み画像が無いので型を作れない"
    edge = im.convert("L").filter(ImageFilter.FIND_EDGES)
    x0, y0, x1, y1 = REF_BOX
    w, h = x1 - x0, y1 - y0
    votes = {}
    for r in refs:
        tpl = (Image.open(DEST / ("no%s_full.png" % r)).convert("L")
               .filter(ImageFilter.FIND_EDGES).crop(REF_BOX))
        best = None
        # 粗く探してから、その周りを1pxずつ詰める
        for oy in range(0, REF_SPAN + 1, 3):
            for ox in range(0, REF_SPAN + 1, 3):
                s = _score(tpl, edge, ox, oy, w, h)
                if best is None or s > best[0]:
                    best = (s, ox, oy)
        c = best
        for oy in range(c[2] - 3, c[2] + 4):
            for ox in range(c[1] - 3, c[1] + 4):
                s = _score(tpl, edge, ox, oy, w, h)
                if s > best[0]:
                    best = (s, ox, oy)
        votes[(best[1], best[2])] = votes.get((best[1], best[2]), 0) + 1
    top = max(votes.items(), key=lambda kv: kv[1])
    # **割れたら止める。** 揃わないまま切ると、ずれたまま登録される。
    if top[1] * 2 <= len(refs):
        return None, ("型%d枚の答えが割れた(%s)" % (len(refs), votes))
    return top[0], None


def crop_one(no, verbose=True, origin=None):
    src = ARCH / ("スクリーンショット_%s.png" % no)
    if not src.exists():
        return "元スクリーンショットが無い: %s" % src.name
    im = Image.open(src)
    if origin is not None:
        left, top = origin
        minX, minY, hw, hh, n = left + ANCHOR_X, top + ANCHOR_Y, 0, 0, 0
        way = "手で指定"
    else:
        res = err = None
        for xlimit in (55, 40):
            res, err = find_heart(im, xlimit)
            if res and not (res[2] > 25 or res[3] > 25 or res[4] > 110):
                break
        way = "通常"
        ok = res and not (res[2] > 25 or res[3] > 25 or res[4] > 110)
        if ok:
            l0, t0 = res[0] - ANCHOR_X, res[1] - ANCHOR_Y
            ok = l0 >= 0 and t0 >= 0 and l0 + TYPE1[0] <= im.size[0] and t0 + TYPE1[1] <= im.size[1]
        if not ok:
            res2, err2 = find_heart_bottom(im, 60)
            if res2:
                l0, t0 = res2[0] - ANCHOR_X, res2[1] - ANCHOR_Y
                if l0 >= 0 and t0 >= 0 and l0 + TYPE1[0] <= im.size[0] and t0 + TYPE1[1] <= im.size[1]:
                    res, way = res2, "予備(下の帯・ピンクも拾う)"
                else:
                    return ("No.%s 予備の検出でも収まらない(基点 %d,%d / 画像 %dx%d)。"
                            "--origin 左,上 で手で指定できる" % (no, l0, t0, im.size[0], im.size[1]))
            else:
                # 白黒のスクリーンショットではハートの赤が消えるので、
                # ここに落ちる。**色ではなく形**で合わせ直す(find_frame)。
                fr, ferr = find_frame(im, no)
                if fr:
                    left, top = fr
                    if (left >= 0 and top >= 0
                            and left + TYPE1[0] <= im.size[0]
                            and top + TYPE1[1] <= im.size[1]):
                        minX, minY, hw, hh, n = (left + ANCHOR_X,
                                                 top + ANCHOR_Y, 0, 0, 0)
                        res, way = (minX, minY, 0, 0, 0), "形(枠)で合わせた"
                    else:
                        return ("No.%s 形で合わせた基点が収まらない(%d,%d / 画像 %dx%d)"
                                % (no, left, top, im.size[0], im.size[1]))
                else:
                    return ("No.%s ハート検出失敗(通常=%s / 予備=%s) / 形でも失敗(%s)。"
                            "--origin 左,上 で手で指定できる"
                            % (no, err, err2, ferr))
        minX, minY, hw, hh, n = res
        left, top = minX - ANCHOR_X, minY - ANCHOR_Y
    if left < 0 or top < 0:
        return "No.%s 切り抜き基点が負 (left=%d top=%d)" % (no, left, top)
    DEST.mkdir(parents=True, exist_ok=True)
    for label, (w, h) in (("char", TYPE2), ("full", TYPE1)):
        box = (left, top, left + w, top + h)
        if box[2] > im.size[0] or box[3] > im.size[1]:
            return "No.%s 元画像より切り抜き範囲が大きい %s > %s" % (no, box, im.size)
        out = im.crop(box)
        out.save(DEST / ("no%s_%s.png" % (no, label)))
        sub = CROPTEST / ("TYPE2" if label == "char" else "TYPE1")
        sub.mkdir(parents=True, exist_ok=True)
        out.save(sub / ("%s_%s.png" % (no, "type2" if label == "char" else "type1")))
    if verbose:
        print("No.%-6s %-22s ハート(%d,%d) %dx%d/%dpx → 基点(%d,%d) 出力OK"
              % (no, way, minX, minY, hw, hh, n, left, top))
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    # --origin 左,上 … 検出に失敗したとき、位置を手で指定して切り抜く
    manual = None
    if "--origin" in args:
        i = args.index("--origin")
        manual = tuple(int(v) for v in args[i + 1].split(","))
        del args[i:i + 2]
        if not args:
            raise SystemExit("--origin は No. を1つ以上指定して使う")
        # 2026-09-09: 白黒のスクリーンショットではハートの赤が消えるので自動検出が
        # 効かない(うぐさんが持っていない札はゲーム内で白黒になる)。
        # **同じ画面から撮った束は配置も大きさも同じ**なので、1枚で基点を決めれば
        # 残りは同じ基点で通る。No.を1つに限っていると1枚ずつ叩くことになるので、
        # まとめて指定できるようにする。
        # crop_one はエラー文なら文字列、成功なら None を返す。
        errs = [x for x in (crop_one(no, origin=manual) for no in args) if x]
        for x in errs:
            print("★" + x)
        print("完了: %d件中 %d件失敗" % (len(args), len(errs)))
        raise SystemExit(1 if errs else 0)
    if args and args[0] == "--all":
        nos = sorted((p.stem.split("_")[-1] for p in ARCH.glob("*.png")), key=int)
    else:
        nos = args
    errs = [e for e in (crop_one(n) for n in nos) if e]
    for e in errs:
        print("★" + e)
    print("完了: %d件中 %d件失敗" % (len(nos), len(errs)))
