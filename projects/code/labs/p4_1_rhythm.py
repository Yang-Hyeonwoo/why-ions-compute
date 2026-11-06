# ============================================================
# P4 실습 1 · 리듬 일정 만들기: 네 가지 리듬, 언제 누를까
#
# 전체 과정:
#
#   리듬 4가지 정하기 (누름 4번 → onset 사이 간격 3개)
#         ↓
#   리듬마다 N_PER_RHYTHM번씩, 간격에 ±10 % jitter(흔들림)
#         ↓
#   모든 trial의 총 길이(첫 onset → 마지막 onset)를 SPAN_S로 같게
#         ↓
#   trial 순서 섞기  →  runs/rhythm_n15.npz 로 저장 (실습 2가 읽음)
#         ↓
#   그림: 리듬마다 trial을 한 줄씩, 누른 순간을 막대로
#
# 이 실습은 장비가 필요 없습니다. 실물 실험(c_run)도 이 파일을 그대로 씁니다.
# ============================================================

import sys
from pathlib import Path

# 공용 코드(python 폴더)를 불러오려고 경로를 잡는다.
# 이 파일은 ion-projects-code/mylabs/ 안에 있으므로, 두 단계 위가 ion-projects-code 폴더.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import numpy as np
import matplotlib.pyplot as plt
from c_rhythm import make_schedule                 # 공용 코드: 리듬 일정 만들기


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

N_PER_RHYTHM = 15    # 리듬마다 몇 번 (연습 15, 실물 실험 60)
SPAN_S = 1.8         # 첫 onset → 마지막 onset (초). 모든 리듬에서 같다
JITTER = 0.10        # 간격을 흔드는 정도 (0.10 = ±10 %)
SEED = 0             # 무작위 씨앗. 같은 SEED면 언제 돌려도 같은 일정


# ============================================================
# 2. 리듬 4가지 (공용 코드 c_rhythm.py의 RHYTHMS와 같은 순서)
# ============================================================
#
#   간격 3개의 비율 (합 = 1). SPAN_S = 1.8초면
#     1/3 = 0.6초,  1/9 = 0.2초,  7/9 = 1.4초
#
#   번호  이름              간격 (초)          느낌
#   0     R1 고르게         0.6  0.6  0.6      탁 — 탁 — 탁 — 탁
#   1     R2 앞에 몰림      0.2  0.2  1.4      탁·탁·탁 ……… 탁
#   2     R3 뒤에 몰림      1.4  0.2  0.2      탁 ……… 탁·탁·탁
#   3     R4 가운데 쉼      0.2  1.4  0.2      탁·탁 ……… 탁·탁
# ============================================================

NAMES_EN = ["R1 even", "R2 early", "R3 late", "R4 middle"]     # TERMINAL용 (영어)
NAMES_KO = ["R1 고르게", "R2 앞에 몰림", "R3 뒤에 몰림", "R4 가운데 쉼"]   # 그림용
COLORS = ["#2b59c3", "#d9822b", "#2a9d8f", "#9b59b6"]


# ============================================================
# 3. 일정 만들기 (공용 코드 한 줄)
# ============================================================
#
#   gaps: trial마다 간격 3개 (초)   → 모양 (trial 수, 3)
#   y   : trial마다 리듬 번호 0–3  → 정답
#   순서는 섞여 있다 (R1만 몰아서 누르면 그 사이 소자 변화가 리듬처럼 보일 수 있어서)
# ============================================================

gaps, y = make_schedule(N_PER_RHYTHM, SPAN_S, jitter=JITTER, seed=SEED)

out = CODE / "runs" / f"rhythm_n{N_PER_RHYTHM}.npz"
out.parent.mkdir(exist_ok=True)
np.savez(out, gaps=gaps, y=y, names=np.array(NAMES_EN), span_s=SPAN_S)


# ============================================================
# 4. 숫자로 확인
# ============================================================

print("=" * 52)
print("rhythm schedule")
print("=" * 52)
print(f"trials      : {len(y)} ({len(NAMES_EN)} rhythms x {N_PER_RHYTHM}), order shuffled")
print(f"span        : {SPAN_S} s (first onset -> last onset, same for all)")
print(f"jitter      : +/-{JITTER * 100:.0f} %")
print()
print("rhythm      gap1 (s)  gap2 (s)  gap3 (s)   mean of trials")
print("---------   --------  --------  --------")
for c, name in enumerate(NAMES_EN):
    g = gaps[y == c].mean(0)
    print(f"{name:<10}    {g[0]:.2f}      {g[1]:.2f}      {g[2]:.2f}")
print()
print(f"gap range   : {gaps.min():.2f} - {gaps.max():.2f} s")
print(f"first 8 rhythms in order: {y[:8].tolist()}")
print(f"saved       : runs/{out.name}")


# ============================================================
# 5. 그림: 리듬마다 trial을 한 줄씩. 막대 = 누르는 80 ms
# ============================================================

HOLD = 0.08            # 누르는 시간 (초). firmware C_tapper와 같은 값
READ = [0.3, 0.6, 1.0]  # 마지막 onset 뒤 전류를 읽을 시점 (초)

fig, ax = plt.subplots(figsize=(8, 5.2))
row = 0
centers = []
for c in range(4):
    trials = gaps[y == c]
    start = row
    for g in trials:
        onsets = np.r_[0, np.cumsum(g)]                  # 첫 onset = 0초
        ax.broken_barh([(o, HOLD) for o in onsets], (row, 0.8), color=COLORS[c])
        row += 1
    centers.append((start + row) / 2)
    row += 2                                             # 리듬 사이 빈 줄

# 마지막 onset(모든 리듬에서 SPAN_S)과 읽기 시점 (그림 맨 위)
ax.axvline(SPAN_S, color="0.4", ls="--", lw=1)
ax.text(SPAN_S - 0.03, -0.07 * row, "마지막 onset", ha="right", va="bottom", color="0.3", fontsize=10)
for d in READ:
    ax.plot(SPAN_S + d, -0.035 * row, "o", color="#7a3db8", ms=7)
ax.text(SPAN_S + 0.65, -0.07 * row, "여기서 읽기 (+0.3·0.6·1.0초)", ha="center", va="bottom",
        color="#7a3db8", fontsize=10)

ax.set_yticks(centers, NAMES_KO)
ax.set_ylim(row - 1.5, -0.15 * row)                         # 위쪽이 첫 줄 (아래로 갈수록 줄 번호가 커짐)
ax.set_xlim(-0.1, SPAN_S + 1.15)
ax.set_xlabel("첫 onset부터의 시간 (s)")
ax.set_title(f"리듬 4가지 × {N_PER_RHYTHM}번: 막대 = 누르는 순간 (80 ms)", loc="left")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.tight_layout()

plt.show()   # 그림 창이 뜹니다. 창을 닫으면 프로그램이 끝납니다.
