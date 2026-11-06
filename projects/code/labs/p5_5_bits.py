# ============================================================
# P5 실습 5 · 판정 한 번에 센서 밖으로 보내는 bit 비교
#
# 전체 과정:
#
#   실습 4와 같은 가짜 EMG · 소자 모형 (reservoir node 4개, R–C 하나)
#         ↓
#   길 1. digital : raw EMG를 2.5초 내내 숫자로 바꿔 모두 보냄
#                   bit = 채널 2 × sampling rate × 2.5초 × BITS
#   길 2. 소자    : 소자가 흔적을 들고 있고, 끝 0.3초에서 state만 몇 번 읽어 보냄
#                   bit = state 개수 × 읽는 횟수 × BITS
#         ↓
#   rate를 바꿔 가며 '판정 한 번에 보내는 bit'와 맞힌 비율을 표로
#         ↓
#   [그림] (a) 언제 숫자를 보내나 (시간 막대)  (b) 보내는 bit와 맞힌 비율
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

DIGITAL_RATES = [1000, 500, 200, 100, 50]   # digital: raw EMG를 집는 sampling rate들 (2000을 나누는 수)
READ_RATES = [50, 20, 10, 5]                # 소자: 끝 0.3초에서 state를 읽는 rate들 (200을 나누는 수)
RC_TAU = 0.3                                # 비교할 R–C 하나의 τ (초)
READ_NOISE = 0.01                           # state를 읽을 때마다 더해지는 측정 오차
BITS = 12                                   # 숫자 하나 = 12 bit (bit 수 계산에만 씀, 반올림 오차는 넣지 않음)
N_TRIALS = 200
SEED = 1


# ============================================================
# 2. 가짜 EMG · 소자 모형 · 읽기 · 채점 (실습 1–4와 같은 코드)
# ============================================================

FS_MAKE, T, END, GRID = 2000, 2.5, 2.2, 200
N = int(FS_MAKE * T)
TAUS = [0.1, 0.3, 1, 3]                     # reservoir node 4개


def band(x, lo, hi):
    F = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / FS_MAKE)
    F[..., (f < lo) | (f > hi)] = 0
    return np.fft.irfft(F, x.shape[-1], axis=-1)


def burst(t, start, dur, ramp=0.05):
    w = np.minimum(np.clip((t - start) / ramp, 0, 1), np.clip((start + dur - t) / ramp, 0, 1))
    return 0.5 - 0.5 * np.cos(np.pi * w)


def make_emg(n, seed, crosstalk=0.15, sensor_noise=0.005):
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
    return emg, y


def device(emg, taus, saturate):
    """정류 |EMG| → node마다 천천히 따라가기 (실습 4와 같음). 결과 (trial, 채널, node, 기록 500개)"""
    u = np.abs(emg)
    tau = np.array(taus, float)[None, None, :]
    x = np.zeros(u.shape[:2] + (len(taus),))
    step = FS_MAKE // GRID
    out = np.zeros(x.shape + (N // step,))
    dt = 1 / FS_MAKE
    a = np.exp(-dt / tau)
    for k in range(N):
        uk = u[:, :, k:k + 1]
        x = x + dt / tau * (2.0 * uk * (1 - x) - x) if saturate else a * x + (1 - a) * uk
        if (k + 1) % step == 0:
            out[..., (k + 1) // step - 1] = x
    return out


def read_times(rate):
    """끝 0.3초 안에서 state를 읽는 기록 번호들 (2.5초에서 거꾸로 1/rate초 간격)"""
    return np.arange(int(T * GRID) - 1, int(END * GRID) - 1, -(GRID // rate))


def read_end(S, rate, noise, seed):
    rng = np.random.default_rng([seed, rate])
    idx = read_times(rate)
    R = S[..., idx] + rng.normal(0, noise, S.shape[:-1] + (len(idx),))
    return R.mean(-1).reshape(len(S), -1)


def digital_features(emg, fs):
    x = band(emg, 0, fs / 2) if fs < FS_MAKE else emg
    x = x[..., FS_MAKE // fs - 1::FS_MAKE // fs]
    return np.stack([np.sqrt((w ** 2).mean(-1)) for w in np.array_split(x, 10, axis=-1)], -1).reshape(len(x), -1)


def cross_validate(F, y, seed, folds=5, lam=1.0):
    rng = np.random.default_rng(seed)
    i0, i1 = rng.permutation(np.where(y == 0)[0]), rng.permutation(np.where(y == 1)[0])
    parts = [np.concatenate([i0[f::folds], i1[f::folds]]) for f in range(folds)]
    scores = []
    for f in range(folds):
        test = parts[f]
        train = np.concatenate([parts[g] for g in range(folds) if g != f])
        mu, sd = F[train].mean(0), F[train].std(0) + 1e-12
        A = np.hstack([(F[train] - mu) / sd, np.ones((len(train), 1))])
        w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ (2.0 * y[train] - 1))
        B = np.hstack([(F[test] - mu) / sd, np.ones((len(test), 1))])
        pred = (B @ w > 0).astype(int)
        scores.append(np.mean([np.mean(pred[y[test] == c] == c) for c in (0, 1)]))
    return np.mean(scores), np.std(scores)


for fs in DIGITAL_RATES:
    if FS_MAKE % fs:
        raise SystemExit(f"DIGITAL_RATES의 {fs}: 2000을 나누는 수만 됩니다")
for r in READ_RATES:
    if GRID % r:
        raise SystemExit(f"READ_RATES의 {r}: 200을 나누는 수만 됩니다 (5, 10, 20, 25, 40, 50, 100)")

emg, y = make_emg(N_TRIALS, SEED)
sat = device(emg, TAUS, saturate=True)       # reservoir: state 4개 × 채널 2 = 8개
rc = device(emg, [RC_TAU], saturate=False)   # R–C 하나: state 1개 × 채널 2 = 2개


# ============================================================
# 3. 길마다 '판정 한 번에 보내는 bit'와 맞힌 비율
# ============================================================
#
#   bit/s if streaming : 쉬지 않고 계속 보낼 때 1초에 보내는 bit
#   bits per decision  : 답 하나를 내려고 보내야 하는 bit
#                        digital = 2.5초 전체가 필요 → 2 × rate × 2.5 × BITS
#                        소자    = 끝 0.3초에 읽은 것만 → 숫자 개수 × 읽는 횟수 × BITS
# ============================================================

rows = []
for fs in DIGITAL_RATES:
    acc, _ = cross_validate(digital_features(emg, fs), y, SEED)
    rows.append(("digital raw EMG", fs, 2, 2 * fs * BITS, int(2 * fs * T * BITS), acc))
for name, S in (("reservoir states", sat), (f"R-C states (tau={RC_TAU:g}s)", rc)):
    for r in READ_RATES:
        F = read_end(S, r, READ_NOISE, SEED)
        reads = len(read_times(r))
        rows.append((name, r, F.shape[1], F.shape[1] * r * BITS, F.shape[1] * reads * BITS, cross_validate(F, y, SEED)[0]))

print("=" * 72)
print(f"how many bits must leave the sensor ({BITS} bit per number)")
print("  digital: the whole 2.5 s is needed;  device: only the reads in the last 0.3 s")
print("=" * 72)
print("                       rate  numbers    bit/s if  bits per  balanced")
print("path                   (Hz)  per read  streaming  decision  accuracy")
print("---------------------  ----  --------  ---------  --------  --------")
for path, rate, num, bps, bpd, acc in rows:
    print(f"{path:<21}  {rate:>4}     {num:>2}     {bps:>7}    {bpd:>6}      {acc:.2f}")


# ============================================================
# 4. 그래프 (a): 한 trial 동안 언제 숫자를 보내나
# ============================================================
#
#   세로 막대 하나 = 숫자를 한 번 보내는 순간.
#   digital은 2.5초 내내, 소자는 끝 0.3초(노란 띠)에서만.
# ============================================================

fig = plt.figure(figsize=(8, 7.4))
gs = fig.add_gridspec(2, 1, height_ratios=[0.75, 1.25], hspace=0.6)
ax = fig.add_subplot(gs[0])
ax.axvspan(END, T, color="#fff3c4", zorder=0)
show = [(f"digital {max(DIGITAL_RATES)} Hz", np.arange(1, int(max(DIGITAL_RATES) * T) + 1) / max(DIGITAL_RATES),
         "#4f7f5d", int(2 * max(DIGITAL_RATES) * T * BITS)),
        (f"digital {min(DIGITAL_RATES)} Hz", np.arange(1, int(min(DIGITAL_RATES) * T) + 1) / min(DIGITAL_RATES),
         "#4f7f5d", int(2 * min(DIGITAL_RATES) * T * BITS))]
r_show = 20 if 20 in READ_RATES else READ_RATES[0]
show.append((f"reservoir {r_show} Hz", (read_times(r_show) + 1) / GRID, "#c0521c", 2 * len(TAUS) * len(read_times(r_show)) * BITS))
for row, (label, times, col, bits) in enumerate(show):
    yy = len(show) - 1 - row
    ax.vlines(times, yy - 0.32, yy + 0.32, color=col, lw=0.6 if len(times) > 200 else 1.6)
    ax.text(T + 0.04, yy, f"{bits:,} bit", va="center", ha="left", fontsize=10, color=col)
ax.set_yticks(range(len(show)), [s[0] for s in show][::-1])
ax.set_xlim(0, T)
ax.set_ylim(-0.6, len(show) - 0.4)
ax.set_xlabel("time (s) in one trial   ·   노란 띠 = readout 구간")
ax.set_title("(a) 판정 한 번을 위해 숫자를 보내는 순간들 (오른쪽 = 보내는 bit)", loc="left")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)


# ============================================================
# 5. 그래프 (b): 판정 한 번에 보내는 bit와 맞힌 비율
#
#   점 옆 숫자 = rate (Hz). dy = 숫자를 점에서 얼마나 띄울지 (가로, 세로)
# ============================================================

ax = fig.add_subplot(gs[1])
for name, label, col, mk, ls, dy in (("digital raw EMG", "digital: raw EMG를 숫자로", "#4f7f5d", "s", "-", (0, 9)),
                                     ("reservoir states", f"reservoir state {2 * len(TAUS)}개", "#c0521c", "o", "-", (0, 9)),
                                     (rows[-1][0], f"R–C state 2개 (τ {RC_TAU:g} s)", "#2b59c3", "^", "--", (6, -12))):
    sel = [r for r in rows if r[0] == name]
    ax.plot([r[4] for r in sel], [r[5] for r in sel], marker=mk, color=col, ls=ls, lw=1.8, ms=6, label=label)
    for r in sel:
        ax.annotate(f"{r[1]}", (r[4], r[5]), textcoords="offset points", xytext=dy, ha="center" if dy[0] == 0 else "left",
                    fontsize=8.5, color=col)
ax.axhline(0.5, color="0.6", ls=":", lw=1.3)
ax.set_xscale("log")
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.set_ylim(0.3, 1.12)
ax.set_xlabel("판정 한 번에 보내는 bit (로그 눈금). 점 옆 숫자 = rate (Hz)")
ax.set_ylabel("balanced accuracy")
ax.set_title("(b) 왼쪽 위일수록 '적게 보내고 잘 맞힘'", loc="left", pad=26)
ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, borderaxespad=0.2, fontsize=9.5)

plt.show()
