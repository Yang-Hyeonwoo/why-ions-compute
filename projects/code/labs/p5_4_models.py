# ============================================================
# P5 실습 4 · 모형별 채점: 끝 0.3초만 읽고 순서를 맞힐까
#
# 전체 과정:
#
#   실습 1과 같은 가짜 EMG (trial 200개) → 정류 |EMG|
#         ↓
#   소자 모형 세 가지에 넣기
#     · R–C 하나      : τ 하나인 빗물통, 채널마다 1개 (τ를 바꿔 가며 따로)
#     · R–C ×4 (선형) : τ가 다른 빗물통 4개, 채널마다
#     · reservoir     : τ가 다른 node 4개 + 포화(거의 차면 덜 오름)
#         ↓
#   끝 0.3초에서 READ_RATE Hz로 state를 읽기 (읽을 때마다 측정 오차 READ_NOISE) → 평균
#         ↓
#   readout (실습 2와 같은 ridge, 5-fold cross-validation) → balanced accuracy
#   비교: no memory (끝 0.3초 EMG 세기만) · digital (2.5초 전체를 1000 Hz로, 참고)
#         ↓
#   [그림 1] trial 하나에서 reservoir node 4개의 state와 읽는 점
#   [그림 2] 모형마다 맞힌 비율 막대그래프
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

READ_RATE = 20             # 끝 0.3초 동안 state를 1초에 몇 번 읽나 (Hz). 200을 나누는 수: 5, 10, 20, 25, 40, 50, 100
READ_NOISE = 0.01          # 읽을 때마다 더해지는 측정 오차의 크기 (state와 같은 단위, mV)
TAUS = [0.1, 0.3, 1, 3]    # node들의 time constant τ (초)
N_TRIALS = 200
SEED = 1


# ============================================================
# 2. 가짜 EMG 만들기 (실습 1–3과 같은 코드)
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


emg, y = make_emg(N_TRIALS, SEED)
t = np.arange(N) / FS_MAKE


# ============================================================
# 3. 소자 모형: 정류한 EMG를 node마다 천천히 따라가기
# ============================================================
#
#   u = |EMG| (정류),  0.5 ms(dt)마다 node 하나하나:
#
#   선형 (R–C):   state = a × state + (1 − a) × u,   a = e^(−dt/τ)
#   포화 (reservoir node):
#                 state += dt/τ × ( 2·u·(1 − state) − state )
#                           ↑ state가 1에 가까울수록 (1 − state)가 작아져 덜 오른다 = 포화
#
#   node끼리는 이어져 있지 않다 (τ가 다른 소자 여러 개를 나란히 둔 셈).
#   실제 이온 소자의 식이 아니라 흉내 낸 수식이다.
#   기록은 5 ms마다 (1초에 GRID = 200번).
# ============================================================

GRID = 200


def device(emg, taus, saturate):
    """결과 state: (trial, 채널 2, node 수, 기록 500개)"""
    u = np.abs(emg)
    tau = np.array(taus, float)[None, None, :]
    x = np.zeros(u.shape[:2] + (len(taus),))
    step = FS_MAKE // GRID
    out = np.zeros(x.shape + (N // step,))
    dt = 1 / FS_MAKE
    a = np.exp(-dt / tau)
    for k in range(N):
        uk = u[:, :, k:k + 1]
        if saturate:
            x = x + dt / tau * (2.0 * uk * (1 - x) - x)
        else:
            x = a * x + (1 - a) * uk
        if (k + 1) % step == 0:
            out[..., (k + 1) // step - 1] = x
    return out


lin = device(emg, TAUS, saturate=False)     # R–C들
sat = device(emg, TAUS, saturate=True)      # reservoir


# ============================================================
# 4. 끝 0.3초에서 state 읽기
# ============================================================
#
#   2.5초에서 거꾸로 1/READ_RATE초 간격으로 읽는다. 20 Hz면 50 ms 간격 → 6번.
#   읽을 때마다 측정 오차를 더하고, 6번을 평균한 값을 readout에 넘긴다.
# ============================================================

if GRID % READ_RATE:
    raise SystemExit(f"READ_RATE = {READ_RATE}: 200을 나누는 수만 됩니다 (5, 10, 20, 25, 40, 50, 100)")


def read_end(S, rate, noise, seed):
    """(trial, …, 기록) → 끝 구간에서 읽어 평균한 값 (trial, 숫자 개수)"""
    rng = np.random.default_rng([seed, rate])
    idx = np.arange(S.shape[-1] - 1, int(END * GRID) - 1, -(GRID // rate))
    R = S[..., idx] + rng.normal(0, noise, S.shape[:-1] + (len(idx),))
    return R.mean(-1).reshape(len(S), -1)


def digital_features(emg, fs=1000):
    """참고용: raw EMG를 fs Hz로 집어(filter 포함) 0.25초 칸 10개 × 채널 2 = 세기 20개 (실습 2와 같음)"""
    x = band(emg, 0, fs / 2)
    x = x[..., FS_MAKE // fs - 1::FS_MAKE // fs]
    return np.stack([np.sqrt((w ** 2).mean(-1)) for w in np.array_split(x, 10, axis=-1)], -1).reshape(len(x), -1)


# ============================================================
# 5. readout과 채점 (실습 2와 같은 코드)
# ============================================================

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


rng = np.random.default_rng(SEED + 7)

# no memory: 끝 0.3초 raw EMG의 세기(RMS)를 채널마다 1개. 읽을 때 같은 크기의 측정 오차.
nm = np.sqrt((emg[..., int(END * FS_MAKE):] ** 2).mean(-1))
models = [("no memory", "end RMS of raw EMG", nm + rng.normal(0, READ_NOISE, nm.shape))]
for j, tau in enumerate(TAUS):
    models.append(("R-C", f"tau = {tau:g} s", read_end(lin[:, :, j:j + 1], READ_RATE, READ_NOISE, SEED)))
models.append(("R-C x4 (linear)", f"tau = {min(TAUS):g}-{max(TAUS):g} s", read_end(lin, READ_RATE, READ_NOISE, SEED)))
models.append(("reservoir", f"{len(TAUS)} saturating nodes", read_end(sat, READ_RATE, READ_NOISE, SEED)))
models.append(("digital (reference)", "all 2.5 s at 1000 Hz", digital_features(emg)))

print("=" * 76)
print(f"readout: only the last 0.3 s, states read at {READ_RATE} Hz and averaged, readout noise {READ_NOISE:g}")
print("=" * 76)
print("model                setting                numbers  balanced         label")
print("                                              read   accuracy  +/-   shuffle")
print("-------------------  --------------------  -------  --------  ----  -------")
results = []
for name, setting, F in models:
    acc, sd = cross_validate(F, y, SEED)
    shuffled = np.mean([cross_validate(F, rng.permutation(y), SEED)[0] for _ in range(20)])
    results.append((name, setting, F.shape[1], acc, sd, shuffled))
    print(f"{name:<19}  {setting:<20}  {F.shape[1]:>5}      {acc:.2f}    {sd:.2f}   {shuffled:.2f}")


# ============================================================
# 6. [그림 1] class 0 trial 하나: reservoir node 4개의 state와 읽는 점
# ============================================================

i = int(np.where(y == 0)[0][0])
tg = np.arange(1, sat.shape[-1] + 1) / GRID
idx = np.arange(sat.shape[-1] - 1, int(END * GRID) - 1, -(GRID // READ_RATE))
blues = plt.cm.Blues(np.linspace(0.4, 0.95, len(TAUS)))        # 연한 파랑 = 빠른 node, 남색 = 느린 node

fig, axs = plt.subplots(2, 1, figsize=(8, 6.4), sharex=True)
for ax, c, tag in zip(axs, (0, 1), ("(a) flexor 채널 (이 trial에서는 먼저 힘을 줌)", "(b) extensor 채널 (나중에 힘을 줌)")):
    ax.axvspan(END, T, color="#fff3c4", zorder=0)
    ax.plot(t, np.abs(emg[i, c]), color="0.85", lw=0.4)
    for j, tau in enumerate(TAUS):
        ax.plot(tg, sat[i, c, j], color=blues[j], lw=1.8, label=f"node τ = {tau:g} s")
        ax.plot(tg[idx], sat[i, c, j, idx], "o", color="#c0521c", ms=4)
    ax.set_ylim(0, 1.3)
    ax.set_ylabel("|EMG| (mV) · state")
    ax.set_title(tag, loc="left", pad=6)
axs[1].set_xlabel("time (s)")
axs[1].set_xlim(0, T)
handles = [plt.Line2D([], [], color="0.75", lw=1.2, label="정류된 EMG |EMG|")] + axs[0].get_legend_handles_labels()[0] + \
          [plt.Line2D([], [], color="#c0521c", marker="o", ls="none", ms=4, label=f"읽는 점 ({READ_RATE} Hz)")]
fig.tight_layout(rect=(0, 0.1, 1, 1))
fig.legend(handles=handles, loc="lower center", ncol=3)


# ============================================================
# 7. [그림 2] 모형마다 맞힌 비율
# ============================================================
#
#   막대 = balanced accuracy, 막대 끝 세로선 = +/-,
#   검은 짧은 가로선 = label shuffle (0.50 근처면 정상), 점선 = chance 0.50
# ============================================================

labels = ["no memory"] + [f"R–C\nτ {tau:g} s" for tau in TAUS] + ["R–C ×4\n(선형)", "reservoir\n(포화)", "digital\n(참고)"]
colors = ["#9a8f86"] + ["#5b8fd6"] * len(TAUS) + ["#2b59c3", "#c0521c", "#4f7f5d"]
xs = np.arange(len(results))
acc = np.array([r[3] for r in results])
sd = np.array([r[4] for r in results])

fig2, ax2 = plt.subplots(figsize=(8, 4.4))
ax2.bar(xs, acc, yerr=sd, color=colors, width=0.62, capsize=3)
ax2.plot(xs, [r[5] for r in results], "_", color="k", ms=18, mew=2)
ax2.axhline(0.5, color="0.6", ls=":", lw=1.3)
for x_, a_, s_ in zip(xs, acc, sd):
    ax2.text(x_, a_ + s_ + 0.02, f"{a_:.2f}", ha="center", va="bottom", fontsize=9.5)
ax2.set_xticks(xs, labels, fontsize=9.5)
ax2.set_ylim(0, 1.18)
ax2.set_ylabel("balanced accuracy")
ax2.set_title(f"끝 0.3초만 읽어 맞힌 비율 (state는 {READ_RATE} Hz로 읽음, 측정 오차 {READ_NOISE:g})", loc="left")
fig2.tight_layout(rect=(0, 0.08, 1, 1))
fig2.legend(handles=[plt.Line2D([], [], color="k", marker="_", ms=14, mew=2, ls="none", label="label shuffle (점검)"),
                     plt.Line2D([], [], color="0.6", ls=":", lw=1.3, label="chance 0.50")],
            loc="lower center", ncol=2)

plt.show()   # 그림 창 두 개가 뜹니다. 둘 다 닫으면 끝납니다.
