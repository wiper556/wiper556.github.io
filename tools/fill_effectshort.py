# -*- coding: utf-8 -*-
"""合成表(synthesisTable)の effectShort が空の行に、効果文を入れる。

**なぜ機械でやるか。** 2026-09-11 の `fill_synthesis.py` は、スキル名・ランク・
スロットは ixanary から入れたが、**数値はうちの既存データからしか取らない**方針
だったので、どの武将にも前例が無いスキルは効果文が空のまま残った。
2026-09-20 時点で 355行 / 188種。1体ずつ外部サイトを引くと 188回の調査になる。

**どこから取るか。外部は引かない。** うちの正本 `data/skill/{名前}.json` の
trTable LV10 の効果文が、既に F-03 の書式

    対象　確率 X% / 効果…

で書かれている。**先頭のヘッダーを落とした残りが effectShort。** それだけ。
新しい数値はどこからも作らない(I-06: 自サイトの既存データは参照ソースの1つ)。

■ この導き方が正しいことの確かめ方

既に effectShort が入っている 3,945行で逆向きに検算すると、**60.0% が文字まで
完全一致**する。残りは「+ で繋ぐか読点で繋ぐか」程度の言い回し差で、意味が
食い違うものは無い。`--verify` でこの検算を再実行できる。

■ 機械に任せない分

ヘッダーに確率が2つ以上並ぶ LV10(「確率 36%/100% /」)は、切り出すと2つ目が
本文に残る。効果ごとの確率を () に付ける既存の書き方に合わせて **手で書いた**。
OVERRIDES がそれで、1件ずつ根拠をコメントに残してある。

書き込む前に関門を通す。ヘッダーの残り・TRなしの残り・効果語で始まらない文は
**書かずに報告する**(黙って通さない)。

■ 使い方

    python tools/fill_effectshort.py            # 下見(書き込まない)
    python tools/fill_effectshort.py --write    # 書き込む
    python tools/fill_effectshort.py --verify   # 導き方の検算だけ
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 先頭の「対象　確率 X% /」。対象は兵科名+スコープ語で 40字に収まる。
# 確率が「-」(城スキルなど、確率の概念が無いもの)の形もある。
HEAD = re.compile(r'^.{0,40}?確率\s*(?:[+＋]?[\d.]+%|[-−–])\s*(?:/|／)?\s*')
# LV10 の効果文の末尾に付く鍛錬の有無(D-17)。合成表には書かない。
TRNASHI = re.compile(r'\s*(?:・TRなし|\(TRなし\)|（TRなし）)')

# --- 手で書いたぶん -------------------------------------------------------
# いずれも正本の LV10 から機械では切り出せないもの。根拠を1件ずつ書く。
OVERRIDES = {
    # 確率が2つ以上並ぶ LV10。effectSummary の①②③に合わせ、効果ごとの確率を () に付けた。
    # LV10: 馬・砲・器　攻撃 確率 18% / 60%上昇+防御 確率 18% / 60%上昇+速度 確率 100% / 24%上昇
    '覇竜十架砲': '攻撃 60%上昇(確率18%)+防御 60%上昇(確率18%)+速度 24%上昇(確率100%)',
    # LV10: 槍・鉄　確率 36%/100% / …
    '天攻狂刃': '攻撃 72%上昇(確率36%)+速度 45%上昇(確率100%)(4部隊以下の攻撃で攻撃効果2倍)',
    # LV10: 槍・弓・焙　確率 24%/100% / …
    '躑躅ノ花ノ如': '攻撃 82%上昇(確率24%)+速度 45%上昇(確率100%)(4部隊以下の攻撃で攻撃効果2倍)',
    # LV10: 弓・馬・器　確率 40%/40%/100% / …
    '北斗征軍': '攻撃 50%上昇(確率40%)+防御 50%上昇(確率40%)+速度 60%上昇(確率100%)',
    # LV10: 弓・馬・器・焙　確率 60%/60%/100% / …
    '四海無双ノ兵': '攻撃 94%上昇(確率60%)+防御 94%上昇(確率60%)+速度 60%上昇(確率100%)',
    # LV10: 全　確率 32%/32%/100% / …
    '覇龍千架砲': '攻撃 127%上昇(確率32%)+防御 127%上昇(確率32%)+速度 40%上昇(確率100%)',
    # LV10: 馬騎　確率 45%/100% / …
    '勝軍神撃': '攻撃 66%上昇(確率45%)+速度 40%上昇(確率100%)(4部隊以下の攻撃で攻撃効果2倍)',
    # LV10: 弓馬焙騎　確率 36%/100% / …
    '天謀ノ星約': '攻撃 86%上昇(確率36%)+速度 50%上昇(確率100%)(4部隊以下の攻撃で攻撃効果2倍)',

    # 3つの確率と3つの効果が組み合わせ選択制。どれか1つを選ぶので「+」では繋がない。
    '日本号 神哭': '攻撃 124%/170%/240%上昇(確率 70%/30%/5%・組み合わせ選択制・移動時は選択不可)',
    '夢幻城回廊': '防御 124%/170%/240%上昇(確率 70%/30%/5%・組み合わせ選択制・移動時は選択不可)',

    # 通常確率では発動しない。対象欄が「全」だけで卓越を持たないので、
    # スコープ語の「卓越」を効果文の側に残す(F-05)。
    '夏炎雷祭': '攻撃 420%上昇+飛翔15(卓越:追加確率30%で発動・攻撃戦闘時のみ・'
                '飛翔獲得部分は模倣不可・二重卓越不可)',

    # この2件は**正本の LV10 が壊れている**(「7%×自軍「姫」武将数=上昇」と、= の右が空)。
    # 母数の決まらない人数なので計算はできず、symbolic のままが正しい(F-04 の既知の母数は
    # 部隊内=4人 と 防御参加武将数=280人 の2つだけ)。同じ正本の effectSummary
    # (勢王秘剣は TR1 も)に正しい形があるので、そこから取った。正本側の LV10 は別途直す。
    '神勅烈母': '防御 (7×自軍「姫」武将数)%上昇(効果上限1000%)',
    '勢王秘剣': '攻撃 (12×飛翔を持たない防御参加武将数)%上昇(模倣不可)',

    # --- 2回目(2026-09-22)。rate か target も空で、1回目は触らなかった行のぶん ---
    # いずれも確率が2つ以上並ぶ LV10。上と同じ扱いにした。
    # LV10: 槍弓馬器　攻撃 確率 40% / 70%上昇+防御 確率 40% / 70%上昇+速度 確率 100% / 60%上昇
    '天神凱武': '攻撃 70%上昇(確率40%)+防御 70%上昇(確率40%)+速度 60%上昇(確率100%)',
    # LV10: 全　攻撃 確率 40% / 40%上昇+速度 確率 100% / 25%低下
    '懸乱龍 雷霆': '攻撃 40%上昇(確率40%)+速度 25%低下(確率100%)',
    # LV10: 弓・砲　攻撃 確率 30% / 45%上昇+速度 確率 100% / 25%低下
    '螺旋生死掘': '攻撃 45%上昇(確率30%)+速度 25%低下(確率100%)',
    # LV10 の本文が対象「全」を繰り返してから始まる。区切りの読点は既存の書き方に合わせ・にした。
    '団右衛門見参': '防御 0%上昇(所持名声×3%・最大2500%)+防御戦闘で減少したHPと同数の名声を消費'
                    '(複数発動時は各部隊につき消費量が最も大きい一件分のみ消費)',
}

# --- 書き込む前の関門 -----------------------------------------------------
LEFTOVER = re.compile(r'^\s*[\d.]+%\s*(?:/|／)')                 # 「100% / 」が残った
HEADER_LEFT = re.compile(r'^\s*\S*\s*確率\s*[\d.]+%\s*(?:/|／)')  # ヘッダーごと残った
START_OK = re.compile(
    r'^(攻撃|防御|速度|破壊|全防|全攻|全速|兵士|自軍|自部隊|敵|戦闘|拠点|待機|合流|'
    r'所属|部隊|城|本丸|コスト|対象|模倣|卓越|不屈|無尽|兵站|覇道|撤退|飛翔|\(|（|[\d.]+%)')


def body_of(effect):
    """LV10 の効果文から、先頭のヘッダーと末尾の (TRなし) を落とす。"""
    s = HEAD.sub('', effect or '').strip()
    s = TRNASHI.sub('', s).strip()
    s = re.sub(r'\(\s*\)|（\s*）', '', s).strip()
    return s


def load_lv10():
    """正本のスキル名 -> trTable LV10 の効果文。"""
    out = {}
    for p in glob.glob(os.path.join(ROOT, 'data/skill/*.json')):
        j = json.load(open(p, encoding='utf-8'))
        for r in (j.get('trTable') or []):
            if r.get('level') == 'LV10' and r.get('effect'):
                out[j['name']] = r['effect']
                break
    return out


def busho_files():
    return sorted(glob.glob(os.path.join(ROOT, 'data/busho*/*.json')))


def norm(s):
    """言い回しの差を無視して比べるための正規化(検算専用)。"""
    s = (s or '').replace('　', ' ')
    s = TRNASHI.sub('', s)
    s = re.sub(r'\s+', '', s)
    s = s.replace('()', '').replace('（）', '')
    s = s.replace('（', '(').replace('）', ')').replace('：', ':')
    s = s.replace('ｘ', 'x').replace('×', 'x').replace('X', 'x')
    return s


def verify(lv10):
    """既に埋まっている行で、導き方が再現するかを測る。"""
    same = diff = 0
    for f in busho_files():
        d = json.load(open(f, encoding='utf-8'))
        for r in (d.get('synthesisTable') or []):
            s, es = r.get('skill'), r.get('effectShort')
            if not s or not es or s not in lv10:
                continue
            cand = body_of(lv10[s])
            if not cand:
                continue
            if norm(cand) == norm(es):
                same += 1
            else:
                diff += 1
    total = same + diff
    print('検算: 既に埋まっている %d行のうち %d行が完全一致 (%.1f%%)'
          % (total, same, 100.0 * same / max(1, total)))
    return same, diff


def main():
    write = '--write' in sys.argv
    lv10 = load_lv10()

    if '--verify' in sys.argv:
        verify(lv10)
        return 0

    # 空の行を集める
    targets = {}   # スキル -> [(file, index)]
    for f in busho_files():
        d = json.load(open(f, encoding='utf-8'))
        for i, r in enumerate(d.get('synthesisTable') or []):
            s = r.get('skill')
            if not s or r.get('effectShort'):
                continue
            # effectShort の出どころはスキル名 -> 正本 なので、同じ行の target や
            # rate が空でも関係なく取れる。rate が正本にも無い行(城スキルなど)は
            # rate を空のまま残し、効果文だけ入れる。
            targets.setdefault(s, []).append((f, i))

    texts, blocked, nosrc = {}, [], []
    for s in targets:
        t = OVERRIDES.get(s)
        if t is None:
            if s not in lv10:
                nosrc.append(s)
                continue
            t = body_of(lv10[s])
        why = None
        if not t:
            why = '効果文が空'
        elif LEFTOVER.match(t) or HEADER_LEFT.match(t):
            why = 'ヘッダーの残り'
        elif 'TRなし' in t:
            why = 'TRなしが残っている'
        elif not START_OK.match(t):
            why = '効果語で始まっていない'
        if why:
            blocked.append((s, why, t))
        else:
            texts[s] = t

    if nosrc:
        rows_nosrc = sum(len(targets[s]) for s in nosrc)
        print('■ 正本が無い %d種 / %d行 は触らない(外部調査が要る)'
              % (len(nosrc), rows_nosrc))
    if blocked:
        print('■ 関門で止めた %d種(OVERRIDES に手で書く)' % len(blocked))
        for s, why, t in blocked:
            print('   [%s] %s: %s' % (s, why, t))

    # 正本の target も、空いている行へ入れる。'-' や None は中身が無いのと同じ。
    hon_target = {}
    for p in glob.glob(os.path.join(ROOT, 'data/skill/*.json')):
        j = json.load(open(p, encoding='utf-8'))
        t = j.get('target')
        if t and t != '-':
            hon_target[j['name']] = t

    # ファイルごとに (行番号, 項目, 値) を集める
    jobs = {}
    for s in texts:
        for f, i in targets[s]:
            jobs.setdefault(f, []).append((i, s, 'effectShort', texts[s]))
    for f in busho_files():
        d = json.load(open(f, encoding='utf-8'))
        for i, r in enumerate(d.get('synthesisTable') or []):
            s = r.get('skill')
            if s and not r.get('target') and s in hon_target:
                jobs.setdefault(f, []).append((i, s, 'target', hon_target[s]))

    count = {'effectShort': 0, 'target': 0}
    for f, todo in sorted(jobs.items()):
        d = json.load(open(f, encoding='utf-8'))
        st = d.get('synthesisTable') or []
        changed = False
        for i, s, field, value in todo:
            r = st[i]
            if r.get('skill') != s or r.get(field):
                continue
            r[field] = value
            changed = True
            count[field] += 1
        if changed and write:
            # newline='\n' を外すと Windows で CRLF になり、差分が全行になる
            with open(f, 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1)
                fh.write('\n')

    print('effectShort %d行(%d種) / target %d行 を%s'
          % (count['effectShort'], len(texts), count['target'],
             '書き込んだ' if write else '書き込む(下見)'))
    if not write:
        print('(--write で書き込む)')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
