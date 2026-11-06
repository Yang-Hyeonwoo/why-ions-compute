# ============================================================
# P1 실습 5 · 기억 과제 만들기: pattern 0과 pattern 1
#
# 전체 과정:
#
#   12칸짜리 입력 한 줄 = trial 하나
#         ↓
#   pattern 0: 큰 입력(1) 3번이 앞쪽 4칸(0–3) 안에
#   pattern 1: 큰 입력(1) 3번이 가운데 4칸(4–7) 안에
#   나머지 칸: 작은 입력(0.1) + 모든 칸에 작은 흔들림(noise)
#         ↓
#   trial 200개 (pattern마다 100개)
#         ↓
#   그래프: 예시 몇 개 + 칸마다 평균
#
# 핵심: 마지막 4칸(8–11, readout 구간)은 두 pattern의 입력이 똑같다.
#       그래서 '마지막 4칸의 입력'만 보면 어느 pattern인지 모른다.
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
# 1. 설정값
# ============================================================

N_TRIALS = 200      # 시험 문제 수 (짝수)
N_STEPS = 12        # 한 trial의 칸 수 (time step)
NOISE = 0.03        # 모든 칸에 더하는 작은 흔들림의 크기
SEED = 1


# ============================================================
# 2. trial 만들기
# ============================================================

def make_task(n, seed):
    """입력 U (n × 12)와 정답 y (0 또는 1)를 돌려준다."""
    rng = np.random.default_rng(seed)

    U = np.full((n, N_STEPS), 0.1)       # 처음엔 모든 칸이 작은 입력 0.1
    y = np.arange(n) % 2                 # 정답: 0, 1, 0, 1, … (반반)
    rng.shuffle(y)                       # 순서를 섞는다

    for i in range(n):
        start = 0 if y[i] == 0 else 4    # pattern 0 → 0–3칸, pattern 1 → 4–7칸
        three = rng.choice(4, 3, replace=False)   # 그 4칸 중 무작위 3칸
        U[i, start + three] = 1.0        # 큰 입력

    U += rng.normal(0, NOISE, U.shape)   # 흔들림
    return U, y

U, y = make_task(N_TRIALS, SEED)


# ============================================================
# 3. 숫자로 확인
# ============================================================

end = slice(8, 12)      # readout 구간: 8, 9, 10, 11칸

print("=" * 50)
print("memory task")
print("=" * 50)
print(f"U shape            : {U.shape}  (trial {N_TRIALS}개 × 칸 {N_STEPS}개)")
print(f"pattern 0 / 1      : {(y == 0).sum()} / {(y == 1).sum()}")
print(f"first trial        : pattern {y[0]}")
print(f"   input           : {np.round(U[0], 2)}")
print()
print("mean input in the readout steps (8-11):")
print(f"   pattern 0       : {U[y == 0][:, end].mean():.3f}")
print(f"   pattern 1       : {U[y == 1][:, end].mean():.3f}")
print("   → 거의 같다. 입력만으로는 구별할 수 없다.")


# ============================================================
# 4. 그래프: 위 = pattern별 예시 3개, 아래 = 칸마다 평균
# ============================================================

fig = plt.figure(figsize=(8, 6.2))
gs = fig.add_gridspec(3, 3, height_ratios=[1, 1, 1.25], hspace=0.75, wspace=0.25)

for row, c in enumerate((0, 1)):
    idx = np.where(y == c)[0][:3]
    for col, i in enumerate(idx):
        ax = fig.add_subplot(gs[row, col])
        ax.axvspan(7.5, 11.5, color="#fff1d3", zorder=0)          # readout 구간
        ax.bar(range(N_STEPS), U[i], color=np.where(U[i] > 0.5, "#2b59c3", "#c9d3ea"), width=0.75)
        ax.set_ylim(0, 1.2)
        ax.set_xticks([0, 4, 8, 11])
        ax.set_yticks([0, 1] if col == 0 else [])
        ax.set_title(f"pattern {c} · 예 {col + 1}", loc="left", fontsize=10.5)

ax = fig.add_subplot(gs[2, :])
ax.axvspan(7.5, 11.5, color="#fff1d3", zorder=0, label="readout 구간 (8–11)")
ax.plot(range(N_STEPS), U[y == 0].mean(0), "o-", color="#2b59c3", label="pattern 0 평균")
ax.plot(range(N_STEPS), U[y == 1].mean(0), "s--", color="#c0521c", label="pattern 1 평균")
ax.set_xticks(range(N_STEPS))
ax.set_xlabel("time step (칸)")
ax.set_ylabel("평균 입력")
ax.set_ylim(0, 1)
ax.set_title("칸마다 평균: 노란 구간에서는 두 선이 겹친다", loc="left")
ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.38))   # 범례는 그래프 아래

plt.show()
