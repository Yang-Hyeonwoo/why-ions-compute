# ============================================================
# P4 실습 4 · 리듬 맞히기: 끝의 전류 몇 개만 보고 맞히나
#
# 전체 과정:
#
#   실습 2의 기록 폴더 읽기
#         ↓
#   trial마다 feature(readout에 넣는 숫자) 다섯 종류 뽑기
#     end1       마지막 onset + 0.3초의 전류 1개        ← 끝에서 한 번만 읽기
#     end3       + 0.3 / 0.6 / 1.0초의 전류 3개         ← 끝에서 세 번 읽기
#     full       처음부터 끝까지 50 Hz로 읽은 전류 전부  ← 계속 읽는 보통 방식
#     force_end3 같은 세 시점의 '힘'                    ← 기억이 전혀 없는 센서를 끝에서 읽기
#     force_full 힘 전부                                ← 기억이 전혀 없는 센서를 계속 읽기
#         ↓
#   ① Same session : 같은 날 trial을 연습 4/5 · 시험 1/5로 나눠 다섯 번 (5-fold)
#   ② New session  : 첫째 날 전부로 연습 → 둘째 날로 시험 (그 반대도)
#         ↓
#   balanced accuracy 표 (찍기 = 0.25)  +  runs/c_report.md
#         ↓
#   그림 1: readout이 보는 숫자 (end1)   그림 2: 점수 막대
# ============================================================

import sys
from pathlib import Path

# 공용 코드(python 폴더)를 불러오려고 경로를 잡는다.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import numpy as np
import matplotlib.pyplot as plt
import c_analyze                                   # 공용 코드: 실물 분석(c_analyze.py)과 같은 계산
from readout import fit_select, evaluate           # 공용 코드: readout 연습·채점
from common import print_table                     # 공용 코드: TERMINAL에 표 찍기


# ============================================================
# 0. 그림 설정 — 건드리지 않아도 됩니다
# ============================================================

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 11,
    "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
})


# ============================================================
# 1. 바꿔 볼 수 있는 설정값  ← 여기를 바꿔 보세요
# ============================================================

MEMORY = True        # 실습 2의 어느 기록을 쓸까. True: 흔적이 남는 소자, False: 기억 없는 소자
NORMALIZE = False    # True: 전류를 trial마다 '누르기 전 baseline'으로 나눈 뒤 분석

# 분석할 기록 폴더 (runs 안). 실물 기록이면 이 줄을 예: RUNS = ["c_dev01_day1", "c_dev01_day2"]
DEVICE = "memory" if MEMORY else "nomem"
RUNS = ["c_mock_" + DEVICE + "_day1", "c_mock_" + DEVICE + "_day2"]


# ============================================================
# 2. 기록 읽기 + feature 뽑기 (공용 코드 c_analyze.load_session)
# ============================================================

c_analyze.NORMALIZE = NORMALIZE                    # 공용 코드에 normalize 여부 알려 주기
sessions = {name: c_analyze.load_session(str(CODE / "runs" / name)) for name in RUNS}
KEYS = ["end1", "end3", "full", "force_end3", "force_full"]


def table(rows, key):
    """trial마다 feature 숫자를 한 줄로 → (trial 수, 숫자 개수) 표"""
    return np.array([r[key] for r in rows], float).reshape(len(rows), -1)


def answers(rows):
    return np.array([r["y"] for r in rows])


# ============================================================
# 3. readout (공용 코드 readout.py)
# ============================================================
#
#   readout = 숫자 몇 개 → "어느 리듬인가"를 답하는 작은 계산 (logistic regression)
#   fit_select : 연습 trial의 정답을 보고 규칙(무게)을 정한다
#   evaluate   : 시험 trial에 규칙을 적용해 채점 → balanced accuracy
#   balanced accuracy = 리듬 4개를 따로 채점해 평균. 찍기 = 0.25, 다 맞힘 = 1.00
# ============================================================

# ① Same session: 같은 날 안에서 5-fold cross-validation
same = {}
for name, rows in sessions.items():
    same[name] = [c_analyze.within_cv(table(rows, k), answers(rows)) for k in KEYS]   # (평균, SD)

# ② New session: 한 날 전부로 연습 → 다른 날로 시험
new = {}
for tr in RUNS:
    for te in RUNS:
        if tr != te:
            scores = []
            for k in KEYS:
                model, _ = fit_select(table(sessions[tr], k), answers(sessions[tr]), n_splits=3)
                scores.append(evaluate(model, table(sessions[te], k), answers(sessions[te]))["balanced_accuracy"])
            new[f"{tr} -> {te}"] = scores


# ============================================================
# 4. 표 (TERMINAL) + c_report.md 저장
# ============================================================

print(f"sessions: {', '.join(f'{n} ({len(r)} trials)' for n, r in sessions.items())}")
print(f"current normalized by pre-press baseline: {'yes' if NORMALIZE else 'no'}")
print()
print("Same session, random split (5-fold cross-validation, balanced accuracy, chance 0.25)")
rows_same = [[n] + [f"{m:.2f} +/- {s:.2f}" for m, s in v] for n, v in same.items()]
print_table(["session"] + KEYS, rows_same, left=(0,))
rows_new = [[n] + [f"{a:.2f}" for a in v] for n, v in new.items()]
if rows_new:
    print()
    print("New session (train on one session -> test on another), balanced accuracy")
    print_table(["train -> test"] + KEYS, rows_new, left=(0,))

md = ["# P4 analysis result", "", f"sessions: {', '.join(RUNS)}  ",
      f"current normalized by pre-press baseline: {'yes' if NORMALIZE else 'no'}", ""]
for title, cols, body in (("Same session (5-fold, balanced accuracy, chance 0.25)", ["session"] + KEYS, rows_same),
                          ("New session (train -> test, balanced accuracy)", ["train -> test"] + KEYS, rows_new)):
    if body:
        md += [f"## {title}", "", "| " + " | ".join(cols) + " |", "|---" * len(cols) + "|"]
        md += ["| " + " | ".join(r) + " |" for r in body] + [""]
(CODE / "runs" / "c_report.md").write_text("\n".join(md), encoding="utf-8")
print()
print("saved: runs/c_report.md")


# ============================================================
# 5. 그림 1: readout이 보는 숫자 — end1 (마지막 onset + 0.3초 전류)
# ============================================================
#
#   점 하나 = trial 하나. 리듬마다 점 무리가 따로 떨어져 있으면 → end1 하나로 맞힐 수 있다.
#   첫째 날과 둘째 날의 점 무리가 위아래로 통째로 어긋나 있으면 → 날을 바꾸면 규칙이 안 맞는다.
# ============================================================

fig, ax = plt.subplots(figsize=(8, 4.0))
unit, scale = ("baseline의 몇 배", 1) if NORMALIZE else ("current (nA)", 1e9)
for k, (name, rows) in enumerate(sessions.items()):
    e1 = table(rows, "end1").ravel() * scale
    yy = answers(rows)
    for c in range(4):
        xc = c + (k - (len(sessions) - 1) / 2) * 0.3
        x = xc + np.random.default_rng(c).uniform(-0.07, 0.07, (yy == c).sum())
        ax.plot(x, e1[yy == c], "os"[k % 2], ms=5, alpha=0.6, color=f"C{k}", label=name if c == 0 else None)
ax.set_xticks(range(4), ["R1 고르게", "R2 앞에 몰림", "R3 뒤에 몰림", "R4 가운데 쉼"])
ax.set_ylabel(f"end1: {unit}")
ax.set_title("readout이 보는 숫자: 마지막 onset + 0.3초의 전류 (점 하나 = trial 하나)", loc="left")
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=len(sessions))


# ============================================================
# 6. 그림 2: 점수 막대 — 같은 날(①) vs 다른 날(②)
# ============================================================

fig2, ax = plt.subplots(figsize=(8, 4.0))
x = np.arange(len(KEYS))
first = RUNS[0]
ax.bar(x - 0.2, [m for m, s in same[first]], 0.38, yerr=[s for m, s in same[first]], capsize=3,
       color="#2b59c3", label=f"① Same session ({first} 안에서)")
if new:
    pair = next(iter(new))
    ax.bar(x + 0.2, new[pair], 0.38, color="#e0a458", label=f"② New session ({pair.replace(' -> ', ' → ')})")
ax.axhline(0.25, color="0.4", ls=":", lw=1.3, label="찍기(chance) 0.25")
ax.set_xticks(x, ["end1\n끝 1개", "end3\n끝 3개", "full\n계속 읽기", "force_end3\n힘 끝 3개", "force_full\n힘 전부"])
ax.set_ylim(0, 1.1)
ax.set_ylabel("balanced accuracy")
ax.set_title("리듬을 맞힌 점수 (1.00 = 다 맞힘)", loc="left")
fig2.tight_layout(rect=(0, 0.22, 1, 1))
fig2.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=1)

plt.show()   # 그림 창 두 개가 뜹니다. 둘 다 닫아야 프로그램이 끝납니다.
