# ============================================================
# P3 실습 3 · 다섯 가지 방법으로 리듬 X·Y 맞히기
#
# 전체 과정:
#
#   버튼 기록 (처음엔 synthetic data: session 3개 × 리듬 2개 × 20번)
#         ↓
#   쉼이 1.6초보다 길면 끊어서 trial(리듬 한 번)로 나누기, bounce 버리기
#         ↓
#   session s1·s2로 연습(train), 마지막 session s3로 시험(test)
#         ↓
#   다섯 방법으로 채점:
#     last value only · count & length · first-gap rule
#     leaky node (τ 세 가지) · reservoir 40 (slow / fast)
#         ↓
#   [그림 1] 방법별 정확도
#   [그림 2] 시험 리듬만 빠르게·느리게, 손 떨림을 크게 하면?
#
# 내 버튼 기록이 session 2개 이상 쌓이면 DATA를 내 CSV로 바꿔 Run 합니다.
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import b1_memory as bm                # 리듬 나누기·다섯 방법 채점 (P3.1b 공용 코드)
from common import print_table        # TERMINAL에 표를 줄 맞춰 찍기


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

DATA = "synthetic"          # 내 기록으로: "runs/p3/b1_taps.csv"
TAUS = (0.1, 0.5, 2.0)      # 비교할 leaky node의 τ (초) 세 개


# ============================================================
# 2. 기록 읽기 → trial로 나누기
# ============================================================
#
# synthetic data = 사람이 X·Y를 20번씩 친 것처럼 컴퓨터가 만든 가짜 기록.
#   박자를 8 %쯤 흔들고, bounce를 10 %쯤 섞고, 가끔 한 번을 빼먹게 만든다.
#   SEED가 고정이라 언제 돌려도 같은 결과 (실측 아님).
# ============================================================

if DATA == "synthetic":
    rng = np.random.default_rng(7)
    streams = {}
    for session in ("s1", "s2", "s3"):
        for label in ("X", "Y"):
            t, btn, _ = bm.synth_stream(label, 20, rng)
            streams[(session, label)] = (np.round(t, 3), btn)
else:
    streams = bm.load(str(CODE / DATA))          # 내 CSV: session·label별로 읽기

all_trials, info = bm.trials(streams)             # (session, label, 누름 시각 5개) 목록
sessions = sorted({s for s, _, _ in all_trials})
if len(sessions) < 2:
    raise SystemExit("session이 2개 이상 필요합니다 (연습·시험을 session으로 나눔). 실습 1을 SESSION = 's2'로 더 기록하세요.")

test_session = sessions[-1]                        # 마지막 session은 시험에만
train = [x for x in all_trials if x[0] != test_session]
test = [x for x in all_trials if x[0] == test_session]

print(f"{'synthetic' if DATA == 'synthetic' else 'measured'} data: {len(all_trials)} trials "
      f"(train {len(train)}: {', '.join(sessions[:-1])} / test {len(test)}: {test_session})")
for k, v in info.items():
    print(f"  {k}: {v}")


# ============================================================
# 3. 다섯 방법으로 채점 (b1_memory.evaluate)
# ============================================================
#
#   last value only : 마지막 누름 순간의 입력 (X든 Y든 1)
#   count & length  : 누른 횟수(5)와 처음→마지막 길이(2.0 s)
#   first-gap rule  : 첫 간격 하나를 문턱과 비교 (X 0.25 s, Y 1.0 s)
#   leaky node      : 실습 2의 물컵. 마지막 누름 직후 물 높이 하나
#   reservoir 40    : 물컵 40개를 무작위로 이어 둔 것 + 학습한 readout
#                     slow = 흔적이 약 0.4초, fast = 약 0.07초
# 모든 방법이 train 기록만 보고 문턱·weight를 정하고, test 기록으로 채점한다.
# ============================================================

bm.TAUS = tuple(TAUS)                              # 공용 코드가 이 τ 목록을 쓰게
names = {"last": "last value only", "count": "count & length", "rule": "first-gap rule",
         **{f"tau{t}": f"leaky node tau={t} s" for t in TAUS},
         "esn": "reservoir 40 (slow)", "esn_fast": "reservoir 40 (fast)"}

esn = (bm.ESN(leak=0.05), bm.ESN(leak=0.3))        # 느린 reservoir, 빠른 reservoir
base = bm.evaluate(train, test, esn)
chance = max(np.mean([lab == "X" for _, lab, _ in test]), np.mean([lab == "Y" for _, lab, _ in test]))

print(f"chance (always guess the larger class): {chance:.0%}")
print()
print_table(["model", "test accuracy"], [[names[k], f"{v:.0%}"] for k, v in base.items()], left=(0,))


# ============================================================
# 4. 시험 리듬만 바꿔 보기 (연습은 그대로)
# ============================================================
#
#   tempo : 시험 리듬의 간격을 모두 ×0.5(두 배 빠르게) ~ ×2(두 배 느리게)
#   jitter: 간격마다 손 떨림을 0–30 % 더하기
#   새로 친 것이 아니라 기록된 시각을 계산으로 늘이고 흔든 것이다.
# ============================================================

mid_tau = f"tau{TAUS[1]}"
show = ("rule", mid_tau, "esn")                    # 세 방법만 비교
scales = [0.5, 0.7, 1.0, 1.4, 2.0]
jitters = [0.0, 0.1, 0.2, 0.3]
by_scale = {k: [bm.evaluate(train, bm.vary(test, scale=s), esn)[k] for s in scales] for k in show}
by_jit = {k: [bm.evaluate(train, bm.vary(test, jitter=j), esn)[k] for j in jitters] for k in show}

print()
print("test tempo changed (x interval; training stays at 1.0)")
print_table(["model"] + [f"x{s:g}" for s in scales],
            [[names[k]] + [f"{v:.0%}" for v in by_scale[k]] for k in show], left=(0,))
print()
print("hand jitter added (relative SD of intervals)")
print_table(["model"] + [f"{j:g}" for j in jitters],
            [[names[k]] + [f"{v:.0%}" for v in by_jit[k]] for k in show], left=(0,))


# ============================================================
# 5. 그림 1: 방법별 정확도
# ============================================================

keys = list(base)
fig1, ax = plt.subplots(figsize=(8, 3.8))
bars = ax.barh([names[k] for k in keys][::-1], [base[k] for k in keys][::-1], color="#2b59c3", height=0.6)
for b, k in zip(bars, keys[::-1]):
    ax.text(base[k] + 0.01, b.get_y() + b.get_height() / 2, f"{base[k]:.0%}", va="center", fontsize=10)
ax.axvline(chance, color="0.5", ls="--", lw=1)
ax.text(chance, len(keys) - 0.35, " chance", color="0.4", fontsize=9.5)
ax.set_xlim(0, 1.1)
ax.set_xlabel("test accuracy (1.0 = 다 맞힘)")
ax.set_title("같은 빠르기로 친 시험 session", loc="left")
fig1.tight_layout()


# ============================================================
# 6. 그림 2: 빠르기·손 떨림을 바꾼 시험
# ============================================================

fig2, ax2 = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)
colors = {"rule": "#0f1b33", mid_tau: "#0e8a83", "esn": "#2b59c3"}
for k in show:
    ax2[0].plot(scales, by_scale[k], "o-", color=colors[k], label=names[k])
    ax2[1].plot(jitters, by_jit[k], "o-", color=colors[k])
ax2[1].set_xticks(jitters)
ax2[0].set_xscale("log", base=2)
ax2[0].set_xticks(scales, [str(s) for s in scales])
ax2[0].set_xlabel("간격 배율 (1 = 연습 때와 같음)")
ax2[0].set_title("빠르기를 바꾸면", loc="left")
ax2[1].set_xlabel("손 떨림 (0.3 = 간격마다 약 30 %)")
ax2[1].set_title("손 떨림을 키우면", loc="left")
for a in ax2:
    a.axhline(chance, color="0.5", ls="--", lw=1)
    a.set_ylim(0.3, 1.05)
ax2[0].set_ylabel("test accuracy")
fig2.tight_layout(rect=(0, 0.1, 1, 1))
fig2.legend(*ax2[0].get_legend_handles_labels(), loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0))

plt.show()
