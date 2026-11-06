# ============================================================
# P5 실습 1 · 가짜 근육 신호(synthetic EMG) 만들고 보기
#
# 전체 과정:
#
#   trial 200개 정하기 (class 0 = 굽힘 → 폄, class 1 = 폄 → 굽힘)
#         ↓
#   trial마다 '힘을 주는 모양'(envelope) 두 개를 그리기
#   (세기 0.3–1.0 mV, 길이 0.3–0.6초, 시작 시각은 매번 무작위)
#         ↓
#   envelope × 빠른 떨림(20–450 Hz)  = EMG
#   + 옆 근육으로 새는 신호(crosstalk) + 작은 센서 잡음
#         ↓
#   표: 앞쪽 · 뒤쪽 · 끝 0.3초에서 채널마다 세기(RMS)
#   그래프: class 0과 class 1의 trial 하나씩
#
# 이 신호는 진짜 사람 기록이 아니라 수식으로 만든 것입니다.
# 그래서 정답(class)을 우리가 정확히 압니다.
# ============================================================

import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# 0. 그림 설정 (한글 글꼴 · 글씨 크기) — 건드리지 않아도 됩니다
# ============================================================

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 11,
    "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
})


# ============================================================
# 1. 바꿔 볼 수 있는 설정값  ← 여기를 바꿔 보세요
# ============================================================

CROSSTALK = 0.15     # 옆 근육의 신호가 몇 배로 새어 드나 (0 = 전혀 안 샘, 0.15 = 15 %)
SENSOR_NOISE = 0.005 # 센서 잡음의 크기 (mV)
N_TRIALS = 200       # 시험 문제(trial) 수 (짝수)
SEED = 1             # 무작위 '씨앗'. 같은 SEED면 언제 돌려도 같은 신호


# 가짜 EMG를 만드는 촘촘함과 길이 (바꾸지 않습니다)
FS_MAKE = 2000       # 1초에 2000점 = 0.5 ms마다 점 하나
T = 2.5              # trial 하나의 길이 (초)
N = int(FS_MAKE * T) # 점 5000개
END = 2.2            # 끝 0.3초(2.2–2.5초) = readout 구간. 여기서는 두 근육 모두 쉰다


# ============================================================
# 2. 도구 두 개: filter와 '힘 주는 구간' 모양
# ============================================================

def band(x, lo, hi):
    """lo–hi Hz 사이의 떨림만 남기고 나머지는 모두 지운다 (이상적인 filter).
    신호를 '몇 Hz 떨림이 얼마나 들어 있나'로 바꾼 뒤(FFT), 범위 밖을 0으로 만들고 되돌린다."""
    F = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / FS_MAKE)
    F[..., (f < lo) | (f > hi)] = 0
    return np.fft.irfft(F, x.shape[-1], axis=-1)


def burst(t, start, dur, ramp=0.05):
    """힘을 주는 구간 하나: 0.05초에 걸쳐 오르고 → 유지 → 0.05초에 걸쳐 내린다 (높이 1)."""
    w = np.minimum(np.clip((t - start) / ramp, 0, 1), np.clip((start + dur - t) / ramp, 0, 1))
    return 0.5 - 0.5 * np.cos(np.pi * w)


# ============================================================
# 3. trial 만들기
# ============================================================

rng = np.random.default_rng(SEED)
y = np.arange(N_TRIALS) % 2          # 정답 class: 0, 1, 0, 1, … (반반)
rng.shuffle(y)                       # 순서를 섞는다
t = np.arange(N) / FS_MAKE           # 시간 축 (초)

# 첫 번째 힘: 0.2–0.5초에 시작, 0.3–0.6초 동안
s1 = rng.uniform(0.2, 0.5, (N_TRIALS, 1))
d1 = rng.uniform(0.3, 0.6, (N_TRIALS, 1))
# 두 번째 힘: 0.1–0.3초 쉬었다가 시작, 0.3–0.6초 동안
gap = rng.uniform(0.1, 0.3, (N_TRIALS, 1))
d2 = rng.uniform(0.3, 0.6, (N_TRIALS, 1))
s2 = s1 + d1 + gap
# 힘의 세기: 0.3–1.0 mV (세 배까지 다름)
a1 = rng.uniform(0.3, 1.0, (N_TRIALS, 1))
a2 = rng.uniform(0.3, 1.0, (N_TRIALS, 1))

first = a1 * burst(t, s1, d1)
second = a2 * burst(t, s2, d2)

# class 0이면 굽힘 근육(flexor)이 첫 번째 힘, 폄 근육(extensor)이 두 번째 힘. class 1은 반대.
flex = np.where(y[:, None] == 0, first, second)
ext = np.where(y[:, None] == 0, second, first)

# envelope = 떨림의 크기 곡선. 옆 근육 신호가 CROSSTALK만큼 섞이고, 쉬는 근육도 0.02 mV쯤 활동
env = np.stack([flex + CROSSTALK * ext, ext + CROSSTALK * flex], axis=1) + 0.02   # (trial, 채널 2, 점 5000)

# 빠른 떨림: 무작위 수를 20–450 Hz만 남기고 크기 1로 맞춤
shake = band(rng.normal(size=(N_TRIALS, 2, N)), 20, 450)
shake = shake / shake.std(axis=-1, keepdims=True)

# EMG = envelope × 떨림 → 센서 모듈의 filter(20–450 Hz) → 센서 잡음 더하기
emg = band(env * shake, 20, 450)
emg = emg + rng.normal(0, SENSOR_NOISE, emg.shape)


# ============================================================
# 4. 숫자로 확인: 구간마다 세기(RMS)
# ============================================================
#
#   RMS = 값마다 제곱 → 평균 → 제곱근.  +와 −로 떨리는 신호의 '평균 크기'.
#   class마다 평균을 내서, 앞쪽(0–1.1초) · 뒤쪽(1.1–2.2초) · 끝(2.2–2.5초)을 비교한다.
# ============================================================

def rms(x):
    return np.sqrt((x ** 2).mean(-1))

parts = [("early 0-1.1 s", 0.0, 1.1), ("late 1.1-2.2 s", 1.1, END), ("end 2.2-2.5 s", END, T)]

print("=" * 58)
print("synthetic EMG")
print("=" * 58)
print(f"trials       : {N_TRIALS}  (class 0: {(y == 0).sum()}, class 1: {(y == 1).sum()})")
print(f"one trial    : {T} s x 2 channels, {N} points each ({FS_MAKE} per second)")
print(f"crosstalk    : {CROSSTALK:.0%}")
print()
print(f"{'mean RMS (mV)':<25}flexor  extensor")
for c in (0, 1):
    for name, lo, hi in parts:
        k = (t >= lo) & (t < hi)
        r = rms(emg[y == c][:, :, k]).mean(0)
        print(f"class {c}  {name:<14}  {r[0]:.3f}   {r[1]:.3f}")
    print()
print("→ 끝 2.2-2.5 s 줄은 두 class가 거의 같다. 끝만 보면 순서를 알 수 없다.")


# ============================================================
# 5. 그래프: class 0과 class 1의 trial 하나씩
# ============================================================
#
#   두 채널이 겹치지 않게 flexor는 +1.6, extensor는 −1.6 위치로 띄워 그린다.
#   진한 선 = envelope (떨림의 평균 크기). 떨림 하나하나는 이보다 2–3배 높이 튀기도 한다.
# ============================================================

fig, axs = plt.subplots(2, 1, figsize=(8, 5.6), sharex=True, sharey=True)
titles = ("(a) class 0: 굽힘(flexor) → 폄(extensor)", "(b) class 1: 폄(extensor) → 굽힘(flexor)")

for ax, c, title in zip(axs, (0, 1), titles):
    i = int(np.where(y == c)[0][0])                         # 그 class의 첫 trial
    ax.axvspan(END, T, color="#fff3c4", zorder=0)            # 노란 띠 = readout 구간
    ax.plot(t, emg[i, 0] + 1.6, color="#2b59c3", lw=0.5)
    ax.plot(t, emg[i, 1] - 1.6, color="#c0521c", lw=0.5)
    ax.plot(t, env[i, 0] + 1.6, color="#1a2f6b", lw=1.4)     # envelope
    ax.plot(t, env[i, 1] - 1.6, color="#7a2e0e", lw=1.4)
    ax.set_yticks([1.6, -1.6], ["flexor", "extensor"])
    ax.set_ylim(-3.6, 3.9)
    ax.set_title(title, loc="left")

axs[0].text(END + (T - END) / 2, 3.75, "readout 구간", ha="center", va="top", color="#7a5a00", fontsize=10)
axs[1].set_xlabel("time (s)")
axs[1].set_xlim(0, T)
fig.text(0.01, 0.55, "EMG (mV, 두 채널을 위아래로 띄움)", rotation=90, va="center", ha="left")
fig.tight_layout(rect=(0.03, 0.07, 1, 1))
# 범례는 그래프 아래 한 줄에
fig.legend(handles=[plt.Line2D([], [], color="0.55", lw=0.8, label="EMG (빠른 떨림)"),
                    plt.Line2D([], [], color="0.15", lw=1.6, label="envelope (떨림의 평균 크기)")],
           loc="lower center", ncol=2)

plt.show()   # 그림 창이 뜹니다. 창을 닫으면 프로그램이 끝납니다.
