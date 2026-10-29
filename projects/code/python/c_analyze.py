"""C 분석: 원시 기록(전류·힘·onset) → 쉬운 단서 점검 → 특징 → 분류 결과 표.

  python c_analyze.py runs/c_day1                 # 세션 하나: 같은 세션 안 무작위 분할만
  python c_analyze.py runs/c_day1 runs/c_day2     # 세션 둘 이상: + '새 세션' 평가 (한 세션으로 학습, 다른 세션으로 시험)
결과: 화면 표 + c_report.md (--out으로 이름 변경)

특징 세 가지 (모두 기록에서 '나중에' 뽑은 것. 실제로 끝에서만 읽는 장치를 만든 것은 아니다)
  end1 : 마지막 누름 시작 + 0.3 s 전류 1개
  end3 : + 0.3 / 0.6 / 1.0 s 전류 3개
  full : 첫 누름 시작부터 (총 길이 + 1 s)까지 50 Hz로 다시 샘플링한 전류 전체
기준선
  force_end3 / force_full : 로드셀 힘을 같은 방식으로 뽑은 것 = '이상적 무기억 센서'
쉬운 단서 점검
  리듬별 누름 최대 힘, 누름 시간(힘 > 최대의 50%), 총 길이(o1→o4)의 평균±표준편차
"""
import argparse
import glob
import os

import numpy as np
from sklearn.model_selection import StratifiedKFold

from c_rhythm import end_features, full_features
from readout import evaluate, fit_select

DELAYS = (0.3, 0.6, 1.0)
SPAN = 1.8
NORMALIZE = False   # True: 전류를 그 시행의 '누르기 전 기준 전류'로 나눔 (날마다 기준이 달라지는 drift 대응)


def load_session(run_dir):
    with np.load(os.path.join(run_dir, "checkpoint.npz")) as ck:
        done, y = ck["done"].copy(), ck["y"].copy()
    rows = []
    for n in np.where(done)[0]:
        with np.load(os.path.join(run_dir, "raw", f"trial_{n:05d}.npz")) as r:
            t, I = r["t"], r["I"]
            on = r["onsets_ms"] / 1000
            tf, F = r["force_t_ms"] / 1000, r["force_N"]
        peaks, holds = [], []
        for o in on:
            m = (tf >= o - 0.02) & (tf < o + 0.2)
            pk = F[m].max() if m.any() else np.nan
            peaks.append(pk)
            above = tf[m][F[m] > 0.5 * pk] if m.any() else []
            holds.append(above[-1] - above[0] if len(above) > 1 else np.nan)
        span = on[-1] - on[0]
        if NORMALIZE:
            base = I[(t > on[0] - 0.4) & (t < on[0] - 0.05)].mean()
            I = I / base
        rows.append(dict(y=int(y[n]),
                         end1=end_features(t, I, on[-1], DELAYS[:1]), end3=end_features(t, I, on[-1], DELAYS),
                         full=full_features(t, I, on[0], SPAN),
                         force_end3=end_features(tf, F, on[-1], DELAYS), force_full=full_features(tf, F, on[0], SPAN),
                         peak=np.nanmean(peaks), hold=np.nanmean(holds), span=span))
    return rows


def stack(rows, key):
    return np.array([r[key] for r in rows], float).reshape(len(rows), -1)


def within_cv(F, y, k=5):
    accs = []
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=0).split(F, y):
        m, _ = fit_select(F[tr], y[tr], n_splits=3)
        accs.append(evaluate(m, F[te], y[te])["balanced_accuracy"])
    return np.mean(accs), np.std(accs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default="c_report.md")
    ap.add_argument("--span", type=float, default=1.8, help="리듬 총 길이 [s] (c_rhythm.py --span과 같게)")
    ap.add_argument("--normalize", action="store_true", help="전류를 시행마다 누르기 전 기준 전류로 나누기")
    a = ap.parse_args()
    ap_norm = a.normalize
    global SPAN, NORMALIZE
    SPAN, NORMALIZE = a.span, ap_norm
    sessions = {os.path.basename(os.path.normpath(r)): load_session(r) for r in a.runs}
    lines = ["# C 분석 결과", "", f"세션: {', '.join(f'{k}({len(v)}시행)' for k, v in sessions.items())}",
             f"전류 정규화(누르기 전 기준으로 나눔): {'예' if NORMALIZE else '아니오'}", ""]
    lines += ["## 쉬운 단서 점검 (리듬별 평균 ± 표준편차)", "", "| 세션 | 리듬 | 최대 힘 [N] | 누름 시간 [ms] | 총 길이 [s] |", "|---|---|---|---|---|"]
    for name, rows in sessions.items():
        y = stack(rows, "y").ravel()
        for c in np.unique(y):
            sel = [r for r in rows if r["y"] == c]
            f = lambda k, s=1: f"{np.nanmean([r[k] for r in sel])*s:.3g} ± {np.nanstd([r[k] for r in sel])*s:.2g}"
            lines.append(f"| {name} | {int(c)} | {f('peak')} | {f('hold', 1000)} | {f('span')} |")
    lines += ["", "리듬마다 힘·누름 시간이 뚜렷이 다르면 아래 결과는 소자가 아니라 그 차이로 구별했을 수 있습니다.", ""]
    keys = ["end1", "end3", "full", "force_end3", "force_full"]
    lines += ["## 같은 세션 안 무작위 분할 (5겹 교차검증, 균형 정확도, 찍기 0.25)", "",
              "| 세션 | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
    for name, rows in sessions.items():
        y = stack(rows, "y").ravel().astype(int)
        cells = [f"{m:.2f} ± {s:.2f}" for m, s in (within_cv(stack(rows, k), y) for k in keys)]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "이 값은 같은 날·같은 소자 안에서의 성능입니다. 새 날·새 소자에 대한 성능이 아닙니다.", ""]
    if len(sessions) >= 2:
        lines += ["## 새 세션 평가 (한 세션으로 학습 → 다른 세션으로 시험)", "",
                  "| 학습 → 시험 | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
        names = list(sessions)
        for tr_name in names:
            for te_name in names:
                if tr_name == te_name:
                    continue
                cells = []
                for k in keys:
                    Ftr, ytr = stack(sessions[tr_name], k), stack(sessions[tr_name], "y").ravel().astype(int)
                    Fte, yte = stack(sessions[te_name], k), stack(sessions[te_name], "y").ravel().astype(int)
                    m, _ = fit_select(Ftr, ytr, n_splits=3)
                    cells.append(f"{evaluate(m, Fte, yte)['balanced_accuracy']:.2f}")
                lines.append(f"| {tr_name} → {te_name} | " + " | ".join(cells) + " |")
    txt = "\n".join(lines) + "\n"
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    print("저장:", a.out)


if __name__ == "__main__":
    main()
