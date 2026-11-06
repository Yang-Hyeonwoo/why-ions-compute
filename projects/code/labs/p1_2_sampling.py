# ============================================================
# P1 실습 2 · sampling rate: 1초에 몇 번 값을 집을까
#
# 전체 과정:
#
#   실습 1과 같은 가짜 심전도 (원래 신호, 1초에 2000점)
#         ↓
#   FS Hz로 값 집기  = 1/FS 초마다 점 하나만 남기기
#         ↓
#   R 봉우리(박동)마다 "0.5 mV 선 위에 점이 찍혔나?" 세기
#         ↓
#   그래프: 매끈한 원래 신호 vs 컴퓨터가 가진 점들
#
# 맨 위의 FS 숫자를 바꿔 다시 Run 해 보는 것이 이 실습의 핵심입니다.
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

FS = 25            # sampling rate (Hz): 1초에 값을 몇 번 집나. 25, 50, 100, 250, 500 …
THRESHOLD = 0.5    # 박동 판정 선 (mV). 실습 4에서 자세히
SECONDS = 60       # 신호 길이 (초)
SEED = 1


# ============================================================
# 2. 가짜 심전도 만들기 (실습 1과 같은 코드)
# ============================================================

REF_FS = 2000      # 원래 신호의 촘촘함: 1초에 2000점

def make_ecg(seconds, seed):
    """가짜 심전도(mV)와 정답 박동 시각(초)을 돌려준다."""
    rng = np.random.default_rng(seed)
    beats, now = [], 0.4
    while now < seconds - 0.6:
        beats.append(now)
        now += 60 / rng.uniform(62, 88)
    t = np.arange(int(seconds * REF_FS)) / REF_FS
    x = np.zeros_like(t)
    for b in beats:
        for shift, height, width in [(-0.18, 0.12, 0.025), (-0.025, -0.12, 0.008), (0, 1.0, 0.009),
                                     (0.025, -0.25, 0.009), (0.28, 0.3, 0.045)]:
            x += height * np.exp(-0.5 * ((t - b - shift) / width) ** 2)
    x += 0.15 * np.sin(2 * np.pi * 0.3 * t) + rng.normal(0, 0.02, t.size)
    return t, x, np.array(beats)

t, ecg, beats = make_ecg(SECONDS, SEED)


# ============================================================
# 3. FS Hz로 값 집기 (sampling)
# ============================================================
#
# 원래 신호는 0.5 ms마다 점이 있다 (2000 Hz).
# FS = 25 Hz면 2000 / 25 = 80칸마다 하나만 남긴다
#   → 40 ms마다 점 하나.
# ============================================================

if REF_FS % FS != 0:
    raise SystemExit(f"FS = {FS}: 2000을 나누어떨어지게 하는 수만 됩니다 (25, 40, 50, 80, 100, 125, 200, 250, 400, 500 …)")

step = REF_FS // FS
ts = t[::step]          # 집은 순간의 시각
xs = ecg[::step]        # 집은 값

interval_ms = 1000 / FS


# ============================================================
# 4. 박동마다: R 봉우리 근처(±30 ms)에 0.5 mV 선을 넘는 점이 있나?
# ============================================================
#
# 기준선이 흔들리므로, 봉우리 바로 앞 0.2초의 평균을 빼고 본다.
# (실습 4의 박동 찾기와 같은 방식)
# ============================================================

caught = 0
caught_flag = []                                          # 박동마다 잡았나(True) 놓쳤나(False)
for b in beats:
    near = np.abs(ts - b) <= 0.03                        # 봉우리 ±30 ms 안의 점들
    base = xs[(ts > b - 0.25) & (ts < b - 0.05)]          # 봉우리 앞 기준선
    base = base.mean() if len(base) else 0
    ok = bool(near.any() and (xs[near] - base).max() > THRESHOLD)
    caught_flag.append(ok)
    caught += ok

print("=" * 50)
print(f"sampling rate {FS} Hz")
print("=" * 50)
print(f"interval between samples : {interval_ms:.0f} ms")
print(f"samples in {SECONDS} s           : {len(xs)}")
print(f"true beats               : {len(beats)}")
print(f"beats with a sample above {THRESHOLD} mV : {caught} / {len(beats)}")
print(f"beats missed by sampling : {len(beats) - caught}")


# ============================================================
# 5. 그래프: "잡은 박동" 하나와 "놓친 박동" 하나를 크게
# ============================================================
#
# 놓친 박동이 없으면(FS가 충분히 높으면) 처음 두 박동을 보여 준다.
# ============================================================

caught_flag = np.array(caught_flag)
pick = []
if caught_flag.any():
    pick.append((beats[caught_flag][0], "잡은 박동 (예)"))
if (~caught_flag).any():
    pick.append((beats[~caught_flag][0], "놓친 박동 (예)"))
while len(pick) < 2:
    pick.append((beats[len(pick)], "잡은 박동 (예)"))

fig, axs = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)

for ax, (b, title) in zip(axs, pick):
    lo, hi = b - 0.15, b + 0.15                 # 봉우리 앞뒤 0.15초
    m = (t >= lo) & (t <= hi)
    ms = (ts >= lo) & (ts <= hi)

    # 판정 선: 봉우리 앞 기준선 + THRESHOLD. 파란 점이 이 선을 넘어야 '박동'으로 잡힌다
    base_b = ecg[(t > b - 0.25) & (t < b - 0.05)].mean()
    ax.axhline(base_b + THRESHOLD, color="#d9962a", ls="--", lw=1.3, label=f"판정 선 (+{THRESHOLD} mV)")
    ax.plot((t[m] - b) * 1000, ecg[m], color="0.75", lw=2, label="원래 신호")
    ax.vlines((ts[ms] - b) * 1000, -0.4, xs[ms], color="#2b59c3", lw=1)
    ax.plot((ts[ms] - b) * 1000, xs[ms], "o", color="#2b59c3", ms=5, label=f"집은 값 ({FS} Hz)")
    ax.set_xlabel("R 봉우리 기준 시간 (ms)")
    ax.set_ylim(-0.4, 1.3)
    ax.set_title(title, loc="left")

axs[0].set_ylabel("mV")
fig.suptitle(f"{FS} Hz = {interval_ms:.0f} ms마다 점 하나: 봉우리를 집었나?", x=0.02, ha="left", fontsize=12)
fig.tight_layout(rect=(0, 0.08, 1, 1))
# 범례는 그래프 아래 한 줄에 (그래프·제목과 겹치지 않게)
fig.legend(*axs[0].get_legend_handles_labels(), loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0))

plt.show()
