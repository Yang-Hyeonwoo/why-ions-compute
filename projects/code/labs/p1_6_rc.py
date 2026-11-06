# ============================================================
# P1 실습 6 · R–C 하나에 넣어 보기: 흔적이 남을까
#
# 전체 과정:
#
#   실습 5와 같은 trial 200개
#         ↓
#   R–C 하나에 한 칸씩 차례로 넣기
#       state(다음) = a × state(지금) + (1 − a) × 입력
#       a = e^(−1/TAU)   ← TAU가 클수록 a가 1에 가까워 천천히 변함
#         ↓
#   그래프: 입력 막대 위에 state 곡선
#           pattern 0과 1의 평균 state가 readout 구간(8–11)에서 벌어지나?
#
# 맨 위의 TAU를 0.3 → 3 → 100으로 바꿔 Run 해 보세요.
# ============================================================

import numpy as np
import matplotlib.pyplot as plt


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

TAU = 3.0           # time constant τ (칸). 흔적이 얼마나 오래 남나. 0.3, 1, 3, 10, 100 …
N_TRIALS = 200
SEED = 1


# ============================================================
# 2. trial 만들기 (실습 5와 같은 코드)
# ============================================================

def make_task(n, seed, n_steps=12, noise=0.03):
    rng = np.random.default_rng(seed)
    U = np.full((n, n_steps), 0.1)
    y = np.arange(n) % 2
    rng.shuffle(y)
    for i in range(n):
        start = 0 if y[i] == 0 else 4
        U[i, start + rng.choice(4, 3, replace=False)] = 1.0
    U += rng.normal(0, noise, U.shape)
    return U, y

U, y = make_task(N_TRIALS, SEED)


# ============================================================
# 3. R–C 하나 (머그컵 하나)
# ============================================================
#
#   매 칸마다:
#     state = a × (지난 state) + (1 − a) × (지금 입력)
#
#   a가 1에 가까우면 (TAU 큼): 지난 state를 거의 그대로 들고 감 → 천천히 변함
#   a가 0에 가까우면 (TAU 작음): 지난 state를 거의 버림 → 지금 입력만 따라감
#
#   TAU = 3이면 a = e^(−1/3) ≈ 0.72 : 한 칸 지날 때마다 흔적의 72%가 남음
# ============================================================

def run_rc(U, tau):
    a = np.exp(-1.0 / tau)
    X = np.zeros_like(U)                  # 칸마다의 state를 모아 둘 곳
    state = np.zeros(len(U))              # 처음 state = 0 (모든 trial 동시에 계산)
    for k in range(U.shape[1]):           # 0칸, 1칸, … 11칸 차례로
        state = a * state + (1 - a) * U[:, k]
        X[:, k] = state
    return X

X = run_rc(U, TAU)


# ============================================================
# 4. 숫자로 확인: readout 구간에서 두 pattern의 state 차이
# ============================================================

end = slice(8, 12)
s0 = X[y == 0][:, end].mean()
s1 = X[y == 1][:, end].mean()

print("=" * 50)
print(f"R-C, tau = {TAU:g} steps   (a = {np.exp(-1 / TAU):.3f})")
print("=" * 50)
print("mean state in the readout steps (8-11):")
print(f"   pattern 0          : {s0:.4f}")
print(f"   pattern 1          : {s1:.4f}")
print(f"   difference (1 - 0) : {s1 - s0:+.4f}")
print(f"   difference / size  : {(s1 - s0) / max(abs(s0), abs(s1)):.0%}")


# ============================================================
# 5. 그래프: 위 = trial 하나씩 (입력 막대 + state 선), 아래 = 평균 state
# ============================================================

fig = plt.figure(figsize=(8, 6.0))
gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.15], hspace=0.6, wspace=0.25)

for col, c in enumerate((0, 1)):
    i = np.where(y == c)[0][0]
    ax = fig.add_subplot(gs[0, col])
    ax.axvspan(7.5, 11.5, color="#fff1d3", zorder=0)
    ax.bar(range(12), U[i], color="#c9d3ea", width=0.75, label="입력")
    ax.plot(range(12), X[i], "o-", color="#c0521c", lw=2, ms=4, label="state")
    ax.set_ylim(0, 1.15)
    ax.set_xticks([0, 4, 8, 11])
    ax.set_title(f"pattern {c}의 trial 하나", loc="left", fontsize=10.5)
    if col == 0:
        ax.legend(loc="upper right")

ax = fig.add_subplot(gs[1, :])
ax.axvspan(7.5, 11.5, color="#fff1d3", zorder=0, label="readout 구간")
m0, m1 = X[y == 0].mean(0), X[y == 1].mean(0)
ax.plot(range(12), m0, "o-", color="#2b59c3", label="pattern 0 평균 state")
ax.plot(range(12), m1, "s--", color="#c0521c", label="pattern 1 평균 state")
ax.set_ylim(0, max(m0.max(), m1.max()) * 1.15)
ax.set_xticks(range(12))
ax.set_xlabel("time step (칸)")
ax.set_ylabel("state")
ax.set_title(f"τ = {TAU:g}칸: 노란 구간에서 두 선이 얼마나 벌어졌나", loc="left")
ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.32))

plt.show()
