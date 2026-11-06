# ============================================================
# P2 실습 1 · 시험 문제(입력) 만들기: 12칸 입력이 pulse 48개가 되기까지
#
# 전체 과정:
#
#   12칸 입력 한 줄 = trial 하나 (P1 실습 5와 같은 과제)
#     class 0: 큰 입력(1.0) 3개가 앞쪽 4칸(0–3) 안에
#     class 1: 큰 입력(1.0) 3개가 가운데 4칸(4–7) 안에
#     나머지 칸은 작은 입력(0.2). 마지막 4칸(8–11)은 두 class가 똑같다
#         ↓
#   trial을 class마다 N_PER_CLASS개 → 파일로 저장 (다음 실습들이 읽음)
#         ↓
#   입력 한 칸 u → mask 4개를 곱해 높이가 다른 pulse 4개
#       pulse 높이(V) = 0.8 × u × mask
#   그래서 12칸 → pulse 12 × 4 = 48개
#         ↓
#   그래프: 입력 12칸 · mask · 소자에 걸 전압(pulse 48개)
#
# 이 실습은 장비가 필요 없습니다. 소자에 "무엇을" 걸지 눈으로 봅니다.
# ============================================================

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

# 공용 코드(python 폴더)를 쓸 수 있게 경로를 잡는다.
# 이 파일은 ion-projects-code\mylabs 안에 있으므로, 두 단계 위가 ion-projects-code 폴더.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from tasks import timing_task, feature_columns     # python/tasks.py의 과제 만드는 함수


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

N_PER_CLASS = 20        # class마다 trial 몇 개 (모두 2배). P2.2의 진짜 소자 측정에서는 40
SHOW_TRIAL = 0          # 그래프로 볼 trial 번호 (0부터)
TASK_NAME = "task_p2"   # 저장할 파일 이름 → ion-projects-code\runs\task_p2.npz


# ============================================================
# 2. 측정 조건 읽기 (설정 파일 config_example.json)
# ============================================================
#
# pulse 높이·길이는 실험 조건이라 설정 파일에 한 번만 적어 둔다.
# 다음 실습의 측정도 같은 파일을 읽으므로, 여기서 보는 pulse가 그대로 소자에 걸린다.
# ============================================================

cfg = json.loads((CODE / "python" / "config_example.json").read_text(encoding="utf-8"))
enc = cfg["encoding"]
MASK = np.array(enc["mask"])     # [0.84, 0.43, 0.97, 0.61]
VA = enc["VA"]                   # 0.8 V: 입력 1.0 × mask 1.0일 때의 높이
THETA = enc["theta_s"]           # pulse 하나의 길이 0.05초
M = len(MASK)                    # mask 개수 4


# ============================================================
# 3. trial 만들기 (python/tasks.py의 timing_task)
# ============================================================

U, y, groups, steps = timing_task(N_PER_CLASS)   # U: trial × 12칸, y: 정답 class
n = len(y)
n_train = int(n * 0.7)            # 앞 70%로 readout을 가르치고, 뒤 30%로 시험 (이미 섞인 순서)

out = CODE / "runs" / f"{TASK_NAME}.npz"
out.parent.mkdir(exist_ok=True)
np.savez(out, U=U, y=y, groups=groups, readout_steps=steps,
         end_cols=feature_columns(steps, M),            # 마지막 4칸의 pulse 16개 번호
         train_idx=np.arange(n_train), test_idx=np.arange(n_train, n))


# ============================================================
# 4. 글자로 확인: 앞 6개 trial을 # (큰 입력) 과 . (작은 입력) 으로
# ============================================================

print("=" * 56)
print(f"task: {n} trials (class 0: {np.sum(y == 0)}, class 1: {np.sum(y == 1)})")
print(f"train {n_train} / test {n - n_train}, readout steps {steps.tolist()}")
print("=" * 56)
print("trial  class  step" + "".join(f"{s:>3}" for s in range(12)))
for i in range(6):
    marks = "".join(f"{'#' if u > 0.5 else '.':>3}" for u in U[i])
    print(f"{i:>5}  {y[i]:>5}      {marks}")
print("(# = big input 1.0, . = small input 0.2)")
print()

u_big, u_small = 1.0, 0.2
print("one input step -> 4 pulses: height = 0.8 V x u x mask")
print(f"  mask              : {MASK.tolist()}")
print(f"  u = 1.0 (big)   -> {np.round(VA * u_big * MASK, 2).tolist()} V")
print(f"  u = 0.2 (small) -> {np.round(VA * u_small * MASK, 2).tolist()} V")
print(f"pulses per trial    : {U.shape[1]} steps x {M} masks = {U.shape[1] * M}")
print(f"saved: runs/{TASK_NAME}.npz")


# ============================================================
# 5. 그래프: 입력 12칸 → mask → pulse 48개
# ============================================================

k = SHOW_TRIAL
u_row = U[k]
heights = np.array([VA * u * m for u in u_row for m in MASK])   # pulse 48개의 높이
t0 = np.arange(len(heights)) * THETA                            # 각 pulse가 시작하는 시각

BIG, SMALL, ZONE = "#2b59c3", "#a9bde8", "#fdf0c2"
fig = plt.figure(figsize=(8, 7.4))
gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.25], width_ratios=[1, 1.5], hspace=0.75, wspace=0.35)

# (위) 입력 12칸
ax1 = fig.add_subplot(gs[0, :])
ax1.axvspan(7.5, 11.5, color=ZONE, zorder=0)
ax1.bar(range(12), u_row, color=[BIG if u > 0.5 else SMALL for u in u_row], width=0.7)
ax1.set_xticks(range(12))
ax1.set_xlim(-0.6, 11.6)
ax1.set_ylim(0, 1.25)
ax1.set_ylabel("입력 u")
ax1.set_xlabel("칸 (time step)")
ax1.set_title(f"① trial {k}의 입력 12칸 (class {y[k]}). 노란 칸 = 마지막 4칸 (두 class가 같음)", loc="left")

# (가운데 왼쪽) mask 4개
ax2 = fig.add_subplot(gs[1, 0])
ax2.bar(range(M), MASK, color="#e08a3c", width=0.6)
ax2.set_xticks(range(M), [f"mask {j}" for j in range(M)], fontsize=9)
ax2.set_ylim(0, 1.15)
ax2.set_title("② mask 4개 (늘 같은 숫자)", loc="left")

# (가운데 오른쪽) 큰 입력 한 칸 → pulse 4개 (확대)
big_step = int(np.argmax(u_row > 0.5))
ax3 = fig.add_subplot(gs[1, 1])
hb = VA * u_row[big_step] * MASK
ax3.bar(np.arange(M) * THETA * 1000 + THETA * 500, hb, width=THETA * 1000 * 0.92, color=BIG)
for j, h in enumerate(hb):
    ax3.text(j * THETA * 1000 + THETA * 500, h + 0.03, f"{h:.2f}", ha="center", va="bottom", fontsize=9)
ax3.set_ylim(0, 1.0)
ax3.set_xlim(0, M * THETA * 1000)
ax3.set_xlabel("시간 (ms)")
ax3.set_ylabel("전압 (V)")
ax3.set_title(f"③ {big_step}번 칸(u = 1.0) → pulse 4개 = 0.8 × 1.0 × mask", loc="left")

# (아래) trial 전체: pulse 48개
ax4 = fig.add_subplot(gs[2, :])
ax4.axvspan(8 * M * THETA, 12 * M * THETA, color=ZONE, zorder=0)
ax4.bar(t0 + THETA / 2, heights, width=THETA * 0.92,
        color=[BIG if u_row[i // M] > 0.5 else SMALL for i in range(len(heights))])
for s in range(1, 12):
    ax4.axvline(s * M * THETA, color="0.85", lw=0.8, zorder=0)
ax4.set_xlim(0, 12 * M * THETA)
ax4.set_ylim(0, 1.0)
ax4.set_xlabel("시간 (s)  ·  회색 세로줄 = 칸의 경계 (칸 하나 = pulse 4개 = 0.2초)")
ax4.set_ylabel("전압 (V)")
ax4.set_title("④ 소자에 걸 전압: pulse 48개 (진한 파랑 = 큰 입력의 pulse)", loc="left")

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
