# ============================================================
# P5 실습 2 · sampling rate: EMG를 1초에 몇 번 집어야 하나
#
# 전체 과정:
#
#   실습 1과 같은 가짜 EMG (trial 200개, 1초에 2000점)
#         ↓
#   anti-aliasing filter: sampling rate의 절반보다 빠른 떨림을 지운다
#         ↓
#   일정 간격으로 값 집기 (FS Hz)
#         ↓
#   컴퓨터가 2.5초를 0.25초 칸 10개로 나눠 칸마다 · 채널마다 세기(RMS) = 숫자 20개
#         ↓
#   이 숫자 20개로 class 맞히기 (readout, 5-fold cross-validation)
#         ↓
#   표: sampling rate마다 data rate · 남은 EMG 비율 · 맞힌 비율
#   그래프: (a) 같은 0.1초를 FS Hz로 집은 모습  (b) sampling rate와 맞힌 비율
#
# 맨 위의 FS를 바꿔 (a) 그림이 어떻게 변하는지 보는 것이 이 실습의 핵심입니다.
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

FS = 50              # (a) 그림에서 볼 sampling rate (Hz). 2000을 나누어떨어지게 하는 수: 1000, 500, 200, 100, 50, 40, 25, 20 …
FS_LIST = [2000, 1000, 500, 200, 100, 50, 20]   # 표와 (b) 그림에서 비교할 sampling rate 목록
BITS = 12            # 숫자 하나를 몇 bit로 적나 (data rate 계산에만 씀)
N_TRIALS = 200
SEED = 1


# ============================================================
# 2. 가짜 EMG 만들기 (실습 1과 같은 코드를 함수 하나로 묶음)
# ============================================================

FS_MAKE, T, END = 2000, 2.5, 2.2
N = int(FS_MAKE * T)


def band(x, lo, hi):
    """lo–hi Hz 사이의 떨림만 남기는 이상적인 filter."""
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
# 3. 숫자로 바꾸기 (ADC 흉내)
# ============================================================
#
#   ① anti-aliasing filter: fs의 절반보다 빠른 떨림을 지운다
#      (지우지 않으면 빠른 떨림이 느린 떨림처럼 둔갑해 섞인다 = aliasing)
#   ② 2000 ÷ fs 칸마다 하나씩만 남긴다 = fs Hz로 집기
#   ③ 0.25초 칸 10개 × 채널 2개 = 세기(RMS) 숫자 20개 (컴퓨터가 계산)
# ============================================================

def digitize(emg, fs):
    """raw EMG를 fs Hz로 집은 값, 남은 EMG 비율, 세기 숫자 20개를 돌려준다."""
    x = band(emg, 0, fs / 2) if fs < FS_MAKE else emg            # ①
    kept = float((x ** 2).mean() / (emg ** 2).mean())            # filter 뒤에 남은 EMG power 비율
    step = FS_MAKE // fs
    xs = x[..., step - 1::step]                                  # ②
    rms = [np.sqrt((w ** 2).mean(-1)) for w in np.array_split(xs, 10, axis=-1)]   # ③
    return x, kept, np.stack(rms, -1).reshape(len(xs), -1)


# ============================================================
# 4. readout과 채점 (P1 실습 7과 같은 방법)
# ============================================================
#
#   readout = "숫자 20개에 무게를 곱해 더한 값이 0보다 크면 class 1"
#   무게는 연습 문제로 정한다 (ridge). 5-fold cross-validation으로 시험.
#   balanced accuracy = class 0 문제와 class 1 문제를 따로 채점해서 평균. 찍으면 0.50.
# ============================================================

def cross_validate(F, y, seed, folds=5, lam=1.0):
    rng = np.random.default_rng(seed)
    i0, i1 = rng.permutation(np.where(y == 0)[0]), rng.permutation(np.where(y == 1)[0])
    parts = [np.concatenate([i0[f::folds], i1[f::folds]]) for f in range(folds)]
    scores = []
    for f in range(folds):
        test = parts[f]
        train = np.concatenate([parts[g] for g in range(folds) if g != f])
        mu, sd = F[train].mean(0), F[train].std(0) + 1e-12       # 연습 문제 기준으로 크기 맞춤
        A = np.hstack([(F[train] - mu) / sd, np.ones((len(train), 1))])
        w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ (2.0 * y[train] - 1))
        B = np.hstack([(F[test] - mu) / sd, np.ones((len(test), 1))])
        pred = (B @ w > 0).astype(int)
        scores.append(np.mean([np.mean(pred[y[test] == c] == c) for c in (0, 1)]))
    return np.mean(scores), np.std(scores)


# ============================================================
# 5. sampling rate마다 채점
# ============================================================

for fs in FS_LIST + [FS]:
    if FS_MAKE % fs:
        raise SystemExit(f"{fs} Hz: 2000을 나누어떨어지게 하는 수만 됩니다 (1000, 500, 200, 100, 50, 40, 25, 20 …)")

rng = np.random.default_rng(SEED + 7)          # label shuffle용
rows = []
for fs in FS_LIST:
    _, kept, F = digitize(emg, fs)
    acc, sd = cross_validate(F, y, SEED)
    # label shuffle: 정답지를 섞고 똑같이 → 0.50 근처가 정상 (20번 평균)
    shuffled = np.mean([cross_validate(F, rng.permutation(y), SEED)[0] for _ in range(20)])
    rows.append((fs, 2 * fs * BITS, kept, acc, sd, shuffled))

print("=" * 66)
print(f"digital: sample raw EMG (2 channels, {BITS} bit), strength over all 2.5 s")
print("=" * 66)
print("sampling rate  data rate  EMG power  balanced         label")
print("     (Hz)       (bit/s)    kept (%)  accuracy  +/-   shuffle")
print("-------------  ---------  ---------  --------  ----  -------")
for fs, bps, kept, acc, sd, sh in rows:
    print(f"    {fs:>4}        {bps:>6}      {100 * kept:>5.1f}      {acc:.2f}    {sd:.2f}   {sh:.2f}")


# ============================================================
# 6. 그래프 (a): 첫 힘 구간 안의 0.1초를 FS Hz로 집은 모습
# ============================================================

i = int(np.where(y == 0)[0][0])                                  # class 0의 첫 trial
k0 = int(np.argmax(env[i, 0] > 0.9 * env[i, 0].max()))           # 굽힘 근육이 힘을 주는 구간 안
seg = slice(k0, k0 + int(0.1 * FS_MAKE))
x_fs, _, _ = digitize(emg[i:i + 1], FS)                         # 이 trial 하나만 FS Hz로
kk = np.arange(seg.start, seg.stop)
kk = kk[(kk + 1) % (FS_MAKE // FS) == 0]                         # FS Hz로 집는 순간들

fig = plt.figure(figsize=(8, 6.6))
gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.1], hspace=0.62)
ax = fig.add_subplot(gs[0])
ms_ = (t[seg] - t[k0]) * 1000
ax.plot(ms_, emg[i, 0, seg], color="0.75", lw=1.2, label="원래 EMG (2000 Hz)")
if FS < FS_MAKE:
    ax.plot(ms_, x_fs[0, 0, seg], color="#e6a57e", lw=1.2, label=f"filter 뒤 ({FS / 2:g} Hz보다 빠른 떨림 지움)")
ax.plot((t[kk] - t[k0]) * 1000, x_fs[0, 0, kk], "o", color="#c0521c", ms=6 if FS <= 200 else 3,
        label=f"{FS} Hz로 집은 값")
ax.set_xlabel("time (ms, 첫 힘 구간 안의 0.1초)")
ax.set_ylabel("flexor EMG (mV)")
ax.set_title(f"(a) {FS} Hz = {1000 / FS:g} ms마다 한 번 집기", loc="left", pad=28)
ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, borderaxespad=0.2, fontsize=9.5)


# ============================================================
# 7. 그래프 (b): sampling rate와 맞힌 비율
# ============================================================

ax = fig.add_subplot(gs[1])
fsx = [r[0] for r in rows]
ax.axhline(0.5, color="0.6", ls=":", lw=1.3)
ax.errorbar(fsx, [r[3] for r in rows], yerr=[r[4] for r in rows], fmt="o-", color="#2b59c3", lw=2, ms=6, capsize=3)
if FS in fsx:                                                    # 지금 FS를 주황 동그라미로 표시
    r = rows[fsx.index(FS)]
    ax.plot(FS, r[3], "o", ms=13, mfc="none", mec="#c0521c", mew=2)
ax.set_xscale("log")
ax.set_xticks(fsx, [str(f) for f in fsx])
ax.minorticks_off()
ax.set_ylim(0.35, 1.08)
ax.set_xlabel("sampling rate (Hz, 1초에 몇 번 집나, 로그 눈금)")
ax.set_ylabel("balanced accuracy")
ax.set_title("(b) 2.5초 전체를 숫자로 보고 컴퓨터가 판정했을 때", loc="left", pad=8)
ax.text(max(fsx), 0.47, "chance 0.50", color="0.45", fontsize=9.5, va="top", ha="right")

plt.show()
