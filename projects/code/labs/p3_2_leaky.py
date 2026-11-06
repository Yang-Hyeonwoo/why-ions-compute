# ============================================================
# P3 실습 2 · leaky node 하나에 리듬 X·Y를 넣어 보기
#
# 전체 과정:
#
#   리듬 X, Y: 둘 다 5번 누르고, 마지막 두 번(1.5 s, 2.0 s)은 똑같다
#         ↓
#   leaky node(구멍 난 물컵)에 넣기
#     누를 때마다 물을 붓고, 쉬는 동안 τ에 따라 물이 샌다
#         ↓
#   마지막 누름 직후의 물 높이(state) 하나만 읽기
#         ↓
#   [그림 왼쪽] X와 Y의 물 높이가 시간에 따라 어떻게 변하나
#   [그림 오른쪽] 손 떨림이 있는 리듬 N번씩: 마지막 물 높이로 X·Y가 갈리나?
#
# 맨 위의 TAU를 0.1 → 0.5 → 2.0으로 바꿔 Run 해 보는 것이 이 실습의 핵심입니다.
# board는 필요 없습니다.
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import b1_memory      # 리듬 X·Y의 정의, leaky node 계산 (P3.1b 공용 코드)


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

TAU = 0.5          # time constant τ (초): 흔적이 얼마나 오래 남나. 0.1, 0.5, 2.0 …
G = 0.5            # 한 번 누를 때 붓는 양 (빈 컵의 절반만큼)
N_TRIALS = 40      # 리듬마다 몇 번 쳤다고 칠까 (앞 절반은 연습, 뒤 절반은 시험)
JITTER = 0.08      # 손 떨림: 간격이 평균 몇 %씩 흔들리나 (0.08 = 8 %)
SEED = 1


# ============================================================
# 2. 두 리듬 (공용 코드 b1_memory.PAT에 적혀 있다)
# ============================================================

PAT = b1_memory.PAT       # {"X": [0, 0.25, 0.5, 1.5, 2.0], "Y": [0, 1.0, 1.25, 1.5, 2.0]}
for name in ("X", "Y"):
    print(f"rhythm {name}: press times {PAT[name]} s,  gaps {np.round(np.diff(PAT[name]), 2).tolist()} s")


# ============================================================
# 3. leaky node: 물 높이 x (0 = 빈 컵, 1 = 가득)
# ============================================================
#
#   누를 때       x ← x + G × (1 − x)          (남은 빈 공간의 G만큼 붓기)
#   쉬는 Δt 동안  x ← x × exp(−Δt / τ)         (τ초가 지나면 약 1/3로 줄어듦)
#
# b1_memory.leaky_state(누름 시각들, τ, G)가 이 계산을 하고
# "마지막 누름 직후의 x"를 돌려준다. 그림을 그리려고 아래에서 시간마다 x도 계산한다.
# ============================================================

def leaky_curve(times, tau, g, t_end=2.6, dt=0.005):
    """0초부터 t_end초까지 5 ms마다의 물 높이"""
    ts = np.arange(0, t_end, dt)
    xs = np.zeros_like(ts)
    x, last_t, k = 0.0, 0.0, 0
    for i, now in enumerate(ts):
        x *= np.exp(-(now - last_t) / tau)          # 새는 동안
        last_t = now
        while k < len(times) and times[k] <= now:   # 이 순간에 누름이 있으면 붓기
            x += g * (1 - x)
            k += 1
        xs[i] = x
    return ts, xs


# ============================================================
# 4. 손 떨림이 있는 리듬을 여러 번: 마지막 물 높이 모으기
# ============================================================

rng = np.random.default_rng(SEED)

def jittered(name):
    gaps = np.diff(PAT[name]) * rng.normal(1, JITTER, 4)      # 간격마다 조금씩 흔들기
    return np.concatenate([[0], np.cumsum(gaps)])

final = {name: np.array([b1_memory.leaky_state(jittered(name), TAU, G) for _ in range(N_TRIALS)])
         for name in ("X", "Y")}


# ============================================================
# 5. 문턱(threshold) 하나로 나누기: 연습 절반으로 문턱, 시험 절반으로 채점
# ============================================================

half = N_TRIALS // 2
v_train = np.r_[final["X"][:half], final["Y"][:half]]
y_train = np.r_[np.ones(half), np.zeros(half)]              # X = 1, Y = 0
th, sign = b1_memory.fit_threshold(v_train, y_train)          # 연습 문제를 가장 잘 나누는 문턱

v_test = np.r_[final["X"][half:], final["Y"][half:]]
y_test = np.r_[np.ones(N_TRIALS - half), np.zeros(N_TRIALS - half)]
acc = np.mean((sign * (v_test - th) > 0) == y_test)

print()
print(f"leaky node, tau = {TAU} s")
print(f"final state X : {final['X'].mean():.3f}  (min {final['X'].min():.3f}, max {final['X'].max():.3f})")
print(f"final state Y : {final['Y'].mean():.3f}  (min {final['Y'].min():.3f}, max {final['Y'].max():.3f})")
print(f"threshold     : {th:.3f}")
print(f"test accuracy : {acc:.0%}   (chance = 50%)")


# ============================================================
# 6. 그림
# ============================================================

fig, ax = plt.subplots(1, 2, figsize=(8, 3.9), gridspec_kw={"width_ratios": [1.6, 1]})
color = {"X": "#2b59c3", "Y": "#d9962a"}

for name in ("X", "Y"):
    ts, xs = leaky_curve(PAT[name], TAU, G)
    ax[0].plot(ts, xs, color=color[name], lw=1.8, label=f"리듬 {name}")
    ax[0].plot(PAT[name], np.full(5, -0.05 if name == "X" else -0.11), "|", color=color[name], ms=8, mew=2)  # 누른 시각
    end = b1_memory.leaky_state(PAT[name], TAU, G)
    ax[0].plot(2.0, end, "o", color=color[name], ms=7)
ax[0].axvline(2.0, color="0.6", ls=":", lw=1)
ax[0].text(2.03, 0.98, "여기서 한 번\n읽는다", va="top", fontsize=9.5, color="0.35")
ax[0].set_ylim(-0.15, 1.02)
ax[0].set_xlabel("time (s)   | = 누른 시각")
ax[0].set_ylabel("물 높이 (state)")
ax[0].set_title(f"τ = {TAU} s일 때 물 높이", loc="left")

for row, name in enumerate(("X", "Y")):
    ax[1].plot(final[name], np.full(N_TRIALS, row) + rng.uniform(-0.15, 0.15, N_TRIALS), "o",
               color=color[name], ms=4, alpha=0.7)
ax[1].axvline(th, color="#c0392b", ls="--", lw=1.3, label="문턱")
ax[1].set_yticks([0, 1], ["X", "Y"])
ax[1].set_ylim(-0.6, 1.6)
ax[1].set_xlabel("마지막 물 높이")
ax[1].set_title(f"{N_TRIALS}번씩: 시험 {acc:.0%}", loc="left")

fig.tight_layout(rect=(0, 0.08, 1, 1))
h0, l0 = ax[0].get_legend_handles_labels()
h1, l1 = ax[1].get_legend_handles_labels()
fig.legend(h0 + h1, l0 + l1, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0))

plt.show()
