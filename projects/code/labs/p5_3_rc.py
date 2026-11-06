# ============================================================
# P5 실습 3 · 정류와 R–C 흔적: 근육이 쉰 뒤에도 흔적이 남을까
#
# 전체 과정:
#
#   실습 1과 같은 가짜 EMG (trial 200개)
#         ↓
#   정류 (rectification): |EMG|  = −도 +로 뒤집기  (빗물통에 물이 들어오기만 하게)
#         ↓
#   R–C 하나 (빗물통 하나):  state가 |EMG|를 천천히 따라 오르고, 쉬면 천천히 식는다
#       state(다음) = a × state(지금) + (1 − a) × |EMG|,   a = e^(−dt/TAU)
#         ↓
#   끝 0.3초(2.2–2.5초)의 state 평균을 채널마다 보기
#   간단한 규칙: "extensor state > flexor state 이면 class 0" 으로 몇 개나 맞나?
#         ↓
#   [그림 1] trial 하나: 정류 확대 · 채널마다 |EMG|와 state
#   [그림 2] trial 200개: class마다 (extensor − flexor) state가 끝에서 갈라지나
#
# 맨 위의 TAU를 0.1 → 0.3 → 1 → 3으로 바꿔 Run 해 보세요.
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

TAU = 0.3            # time constant τ (초). 흔적이 얼마나 오래 남나 (빗물통 구멍 크기). 0.1, 0.3, 1, 3 …
N_TRIALS = 200
SEED = 1


# ============================================================
# 2. 가짜 EMG 만들기 (실습 1·2와 같은 코드)
# ============================================================

FS_MAKE, T, END = 2000, 2.5, 2.2
N = int(FS_MAKE * T)


def band(x, lo, hi):
    F = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / FS_MAKE)
    F[..., (f < lo) | (f > hi)] = 0
    return np.fft.irfft(F, x.shape[-1], axis=-1)


def burst(t, start, dur, ramp=0.05):
    w = np.minimum(np.clip((t - start) / ramp, 0, 1), np.clip((start + dur - t) / ramp, 0, 1))
    return 0.5 - 0.5 * np.cos(np.pi * w)


def make_emg(n, seed, crosstalk=0.15, sensor_noise=0.005):
    """가짜 EMG (trial, 채널 2, 점 5000) mV · 정답 class · envelope."""
    rng = np.random.default_rng(seed)
    y = np.arange(n) % 2
    rng.shuffle(y)
    t = np.arange(N) / FS_MAKE
    s1, d1, gap, d2 = (rng.uniform(lo, hi, (n, 1)) for lo, hi in ((0.2, 0.5), (0.3, 0.6), (0.1, 0.3), (0.3, 0.6)))
    a1, a2 = rng.uniform(0.3, 1.0, (n, 1)), rng.uniform(0.3, 1.0, (n, 1))
    first, second = a1 * burst(t, s1, d1), a2 * burst(t, s1 + d1 + gap, d2)
    flex = np.where(y[:, None] == 0, first, second)
    ext = np.where(y[:, None] == 0, second, first)
    env = np.stack([flex + crosstalk * ext, ext + crosstalk * flex], axis=1) + 0.02
    shake = band(rng.normal(size=(n, 2, N)), 20, 450)
    shake = shake / shake.std(axis=-1, keepdims=True)
    emg = band(env * shake, 20, 450) + rng.normal(0, sensor_noise, (n, 2, N))
    return emg, y, env


emg, y, env = make_emg(N_TRIALS, SEED)
t = np.arange(N) / FS_MAKE


# ============================================================
# 3. 정류 + R–C 하나 (빗물통 하나)
# ============================================================
#
#   u = |EMG|            ← 정류: +와 −로 떨리는 값을 모두 +로
#
#   0.5 ms(dt)마다:
#     state = a × (지난 state) + (1 − a) × u
#     a = e^(−dt/TAU)    ← TAU가 클수록 a가 1에 가까워 천천히 변함
#
#   계산은 0.5 ms마다 하지만, 기록은 5 ms마다(1초에 200번)만 해 둔다.
# ============================================================

GRID = 200                                   # state를 기록해 두는 간격: 1초에 200번
u = np.abs(emg)                              # 정류
dt = 1 / FS_MAKE
a = np.exp(-dt / TAU)
state = np.zeros(u.shape[:2])                # (trial, 채널) 모두 동시에 계산. 처음 state = 0
S = np.zeros(u.shape[:2] + (N // (FS_MAKE // GRID),))
for k in range(N):
    state = a * state + (1 - a) * u[:, :, k]
    if (k + 1) % (FS_MAKE // GRID) == 0:
        S[:, :, (k + 1) // (FS_MAKE // GRID) - 1] = state
tg = np.arange(1, S.shape[-1] + 1) / GRID    # 기록한 시각 (초)


# ============================================================
# 4. 숫자로 확인: 끝 0.3초의 state
# ============================================================

end = tg > END
s_end = S[:, :, end].mean(-1)                # (trial, 채널): 끝 구간 평균 state

print("=" * 58)
print(f"R-C, tau = {TAU:g} s")
print("=" * 58)
print(f"after 0.5 s of rest, the trace keeps : {np.exp(-0.5 / TAU):.0%}")
print(f"after 1.0 s of rest, the trace keeps : {np.exp(-1.0 / TAU):.0%}")
print()
print("mean state in the readout window (2.2-2.5 s), mV")
print("           flexor   extensor   extensor - flexor")
for c in (0, 1):
    f_, e_ = s_end[y == c].mean(0)
    print(f"class {c}    {f_:.3f}    {e_:.3f}       {e_ - f_:+.3f}")

# 간단한 규칙: 나중에 쓴 근육의 흔적이 더 남아 있을 것 → extensor가 더 크면 class 0 (굽힘 → 폄)
guess = (s_end[:, 1] <= s_end[:, 0]).astype(int)
acc = np.mean([np.mean(guess[y == c] == c) for c in (0, 1)])
print()
print(f"simple rule 'extensor > flexor -> class 0' : balanced accuracy {acc:.2f}  (chance 0.50)")


# ============================================================
# 5. [그림 1] trial 하나: 정류 확대 · 채널마다 |EMG|와 state
# ============================================================

i = int(np.where(y == 0)[0][0])                          # class 0의 첫 trial
k0 = int(np.argmax(env[i, 0] > 0.9 * env[i, 0].max()))   # 굽힘 근육이 힘을 주는 구간 안
seg = slice(k0, k0 + int(0.05 * FS_MAKE))                # 0.05초만 확대

fig = plt.figure(figsize=(8, 7.4))
gs = fig.add_gridspec(3, 1, height_ratios=[0.8, 1, 1], hspace=0.75)

ax = fig.add_subplot(gs[0])
ms_ = (t[seg] - t[k0]) * 1000
ax.axhline(0, color="0.8", lw=0.8)
ax.plot(ms_, emg[i, 0, seg], color="0.7", lw=1.2, label="raw EMG (+와 -)")
ax.plot(ms_, u[i, 0, seg], color="#2b59c3", lw=1.4, label="정류 |EMG| (모두 +)")
ax.set_xlabel("time (ms, 0.05초 확대)")
ax.set_ylabel("mV")
ax.set_title("(a) 정류: -쪽 떨림을 +로 뒤집는다", loc="left", pad=26)
ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, borderaxespad=0.2, fontsize=9.5)

for row, c, col, tag in ((1, 0, "#2b59c3", "(b) flexor 채널 (이 trial에서는 먼저 힘을 줌)"),
                         (2, 1, "#c0521c", "(c) extensor 채널 (나중에 힘을 줌)")):
    ax = fig.add_subplot(gs[row])
    ax.axvspan(END, T, color="#fff3c4", zorder=0)
    ax.plot(t, u[i, c], color="0.82", lw=0.4)
    ax.plot(tg, S[i, c], color=col, lw=2.2)
    ax.set_ylim(0, 1.3)
    ax.set_xlim(0, T)
    ax.set_ylabel("mV")
    ax.set_title(tag, loc="left", pad=6)
    ax.text(T - 0.02, 1.25, f"끝 state {s_end[i, c]:.3f}", ha="right", va="top", fontsize=9.5, color=col)
ax.set_xlabel("time (s)   ·   연한 회색 = |EMG|, 진한 선 = R–C state, 노란 띠 = readout 구간")


# ============================================================
# 6. [그림 2] trial 200개: (extensor - flexor) state, class마다
# ============================================================
#
#   선 = class의 가운데 값, 옅은 띠 = trial의 가운데 절반(25–75 %)이 들어오는 범위.
#   왼쪽 = 2.5초 전체, 오른쪽 = 끝 0.3초만 크게 (세로 눈금이 다름).
#   끝 구간에서 두 띠가 안 겹칠수록 "끝만 보고도" 순서를 가려낼 수 있다.
# ============================================================

d = S[:, 1] - S[:, 0]                                    # (trial, 시각)
fig2, (ax2, ax3) = plt.subplots(1, 2, figsize=(8, 4.0), gridspec_kw={"width_ratios": [2.6, 1]})
for ax, m in ((ax2, tg > 0), (ax3, end)):
    ax.axvspan(END, T, color="#fff3c4", zorder=0)
    ax.axhline(0, color="0.6", lw=0.8)
    for c, col, name in ((0, "#2b59c3", "class 0 (굽힘 → 폄)"), (1, "#c0521c", "class 1 (폄 → 굽힘)")):
        lo, mid, hi = np.percentile(d[y == c][:, m], [25, 50, 75], axis=0)
        ax.fill_between(tg[m], lo, hi, color=col, alpha=0.18, lw=0)
        ax.plot(tg[m], mid, color=col, lw=2, label=name)
ax2.set_xlim(0, T)
ax3.set_xlim(END, T)
ax3.set_xticks([2.2, 2.35, 2.5])
ax2.set_xlabel("time (s)")
ax3.set_xlabel("time (s)")
ax2.set_ylabel("extensor - flexor state (mV)")
ax2.set_title(f"τ = {TAU:g} s: 2.5초 전체", loc="left")
ax3.set_title("끝 0.3초 확대", loc="left")
fig2.tight_layout(rect=(0, 0.08, 1, 1))
fig2.legend(*ax2.get_legend_handles_labels(), loc="lower center", ncol=2)

plt.show()   # 그림 창 두 개가 뜹니다. 둘 다 닫으면 끝납니다.
