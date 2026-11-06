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
    # 표는 (제목, 열 이름, 줄들, 아래 설명)으로 모아 두고, 명령 창에는 열을 맞춘 표로, c_report.md에는 markdown 표로 쓴다
    tables = []
    rows_easy = []
    for name, rows in sessions.items():
        y = stack(rows, "y").ravel()
        for c in np.unique(y):
            sel = [r for r in rows if r["y"] == c]
            f = lambda k, s=1: f"{np.nanmean([r[k] for r in sel])*s:.3g} +/- {np.nanstd([r[k] for r in sel])*s:.2g}"
            rows_easy.append([name, int(c), f("peak"), f("hold", 1000), f("span")])
    tables.append(("Easy-cue check (mean +/- SD per rhythm)", ["session", "rhythm", "peak force (N)", "hold (ms)", "span (s)"],
                   rows_easy, "If force or hold time differs clearly between rhythms, the results below may come from that "
                   "difference, not from the device."))
    keys = ["end1", "end3", "full", "force_end3", "force_full"]
    rows_in = []
    for name, rows in sessions.items():
        y = stack(rows, "y").ravel().astype(int)
        rows_in.append([name] + [f"{m:.2f} +/- {s:.2f}" for m, s in (within_cv(stack(rows, k), y) for k in keys)])
    tables.append(("Same session, random split (5-fold cross-validation, balanced accuracy, chance 0.25)",
                   ["session"] + keys, rows_in, "Same day, same device only. This is not performance on a new day or device."))
    if len(sessions) >= 2:
        rows_new = []
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
                rows_new.append([f"{tr_name} -> {te_name}"] + cells)
        tables.append(("New session (train on one session -> test on another), balanced accuracy",
                       ["train -> test"] + keys, rows_new, ""))

    head = [f"sessions: {', '.join(f'{k} ({len(v)} trials)' for k, v in sessions.items())}",
            f"current normalized by pre-press baseline: {'yes' if NORMALIZE else 'no'}"]
    lines = ["# P4 analysis result", ""] + [h + "  " for h in head] + [""]
    for title, cols, rows_t, note in tables:
        lines += [f"## {title}", "", "| " + " | ".join(cols) + " |", "|---" * len(cols) + "|"]
        lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in rows_t]
        lines += ["", note, ""] if note else [""]
    txt = "\n".join(lines) + "\n"
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(txt)
    from common import print_table
    for h in head:
        print(h)
    for title, cols, rows_t, note in tables:
        print()
        print(title)
        print_table(cols, rows_t, left=(0,))
        if note:
            print(note)
    print()
    print("saved:", a.out)


if __name__ == "__main__":
    main()
