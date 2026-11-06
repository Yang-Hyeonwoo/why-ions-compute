"""E: 합성 근전도(EMG) 두 채널로 '손목을 어느 순서로 움직였나'를 맞힌다. 끝 구간(근육이 쉬는 때)만 읽는다.

장비가 필요 없다. 신호는 이 파일이 만드는 '근전도 모양' 합성 신호다(실제 사람 기록 아님).

사용법:
  python e_emg.py runs/e1             # P5.1: raw EMG를 여러 sampling rate로 숫자로 만들고 컴퓨터가 판정
  python e_emg.py runs/e2 --part 2    # P5.2: 소자(모형)가 먼저 흔적으로 바꾸고, 끝 구간 state만 천천히 읽기
  python e_emg.py runs/e2 --part 2 --rate 20 --n 200 --noise 0.01 --seed 1

과제:
  trial 하나 = 2.5초. 채널 0 = 손목 굽힘 근육(flexor), 채널 1 = 손목 폄 근육(extensor).
  class 0 = 굽힘 → 폄, class 1 = 폄 → 굽힘. 힘 크기(0.3–1.0 mV)·길이(0.3–0.6초)·시작 시각·간격은 매번 무작위.
  마지막 0.3초(2.2–2.5초)는 두 class 모두 근육이 쉰다 → 이 구간의 EMG만 보면 구별할 수 없다.

결과 (출력 폴더):
  --part 1  e1_digital.csv   sampling rate마다 data rate, filter를 지난 EMG 비율, 2.5초 전체를 본 balanced accuracy
            e1_emg.png       두 class의 trial 예 (raw EMG 두 채널, readout 구간)
            e1_sampling.png  (a) 같은 0.1초를 1000 Hz와 50 Hz로 숫자로 만든 모습 (b) sampling rate와 정확도
  --part 2  e2_models.csv    모형마다 끝 구간만 읽은 balanced accuracy (readout rate --rate)
            e2_rates.csv     readout rate(또는 sampling rate)마다 data rate와 정확도
            e2_states.png    한 trial에서 정류된 EMG와 소자 state, 끝 구간에서 읽는 점
            e2_compare.png   (a) 모형 비교 (b) data rate와 정확도

모형의 가정 (실제와 다른 점):
  - EMG = (힘 곡선 envelope) × (20–450 Hz 띠의 무작위 잡음)을 다시 20–450 Hz filter에 통과 + 센서 잡음 0.005 mV.
    옆 근육으로 새는 신호(crosstalk) 15 %.
    움직임 잡음(motion artifact), 전원선 잡음(60 Hz), 피로·땀은 넣지 않았다. 신호는 센서 모듈의 아날로그 filter를 지난 뒤라고 친다.
  - 디지털 경로: 숫자로 바꾸기 전 이상적인 anti-aliasing filter(sampling rate의 절반 위를 모두 지움) → 일정 간격으로 집기
    → 0.25초 칸 10개의 RMS(세기) 20개를 컴퓨터가 계산. data rate = 2채널 × sampling rate × 12 bit (bit 오차는 넣지 않음).
  - R–C: 정류된 입력 |EMG| (mV)를 따라가는 leaky integrator. dx/dt = (|EMG| − x)/τ.
  - reservoir: 채널마다 τ = 0.1, 0.3, 1, 3초인 node 4개. 포화가 있는 비선형 node: dx/dt = (2|EMG|(1 − x) − x)/τ.
    node끼리 연결은 없다(τ가 다른 소자 여러 개를 나란히 둔 셈). 실제 이온 소자의 식이 아니라 흉내 낸 수식이다.
  - readout: 끝 구간 0.3초 안에서 readout rate 간격으로 state를 읽고(읽을 때마다 noise --noise 더함) 평균한 값.
    5겹 cross-validation, 겹마다 학습 쪽으로만 표준화, ridge(λ=1) 선형 분류 (s2_memory.py와 같은 함수).
    label shuffle = 정답을 20번 섞어 같은 계산을 한 평균.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from s2_memory import cv_accuracy

FS = 2000                 # 합성 신호를 만드는 촘촘한 rate (Hz)
T = 2.5                   # trial 길이 (초)
N = int(FS * T)
END = 2.2                 # readout 구간 시작 (초). 2.2–2.5초
BITS = 12
GRID = 200                # 소자 state를 기록해 두는 촘촘한 간격 (Hz). readout rate는 이것을 나눌 수 있어야 함
TAUS = (0.1, 0.3, 1.0, 3.0)
CH = ("flexor", "extensor")


def band_noise(rng, shape, lo=20.0, hi=450.0):
    """lo–hi Hz 띠만 남긴 무작위 잡음, 표준편차 1."""
    x = rng.normal(size=shape + (N,))
    F = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(N, 1 / FS)
    F[..., (f < lo) | (f > hi)] = 0
    x = np.fft.irfft(F, N, axis=-1)
    return x / x.std(axis=-1, keepdims=True)


def burst(t, start, dur, ramp=0.05):
    """힘을 주는 구간 하나: 0.05초에 걸쳐 오르고, 유지하고, 0.05초에 걸쳐 내림. t (N,), start·dur (n,1)."""
    w = np.minimum(np.clip((t - start) / ramp, 0, 1), np.clip((start + dur - t) / ramp, 0, 1))
    return 0.5 - 0.5 * np.cos(np.pi * w)


def make_trials(n, seed):
    """합성 EMG (n, 2, N) mV, class y, envelope (n, 2, N), 힘 구간 정보."""
    rng = np.random.default_rng(seed)
    y = np.arange(n) % 2
    rng.shuffle(y)
    t = np.arange(N) / FS
    s1 = rng.uniform(0.2, 0.5, (n, 1))
    d1 = rng.uniform(0.3, 0.6, (n, 1))
    gap = rng.uniform(0.1, 0.3, (n, 1))
    d2 = rng.uniform(0.3, 0.6, (n, 1))
    s2 = s1 + d1 + gap
    a1 = rng.uniform(0.3, 1.0, (n, 1))
    a2 = rng.uniform(0.3, 1.0, (n, 1))
    first = a1 * burst(t, s1, d1)
    second = a2 * burst(t, s2, d2)
    flex = np.where(y[:, None] == 0, first, second)      # class 0: 굽힘이 먼저
    ext = np.where(y[:, None] == 0, second, first)
    env = np.stack([flex + 0.15 * ext, ext + 0.15 * flex], axis=1) + 0.02   # crosstalk 15 %, 쉬는 근육의 작은 활동
    emg = band(env * band_noise(rng, (n, 2)), 20, 450)            # 센서 모듈의 filter: 20–450 Hz만 남김
    emg = emg + rng.normal(0, 0.005, (n, 2, N))                    # 센서·ADC 잡음
    info = dict(s1=s1[:, 0], d1=d1[:, 0], s2=s2[:, 0], d2=d2[:, 0])
    return emg, y, env, info


def band(x, lo, hi):
    """이상적인 filter: lo–hi Hz 밖의 성분을 모두 지운다."""
    F = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / FS)
    F[..., (f < lo) | (f > hi)] = 0
    return np.fft.irfft(F, x.shape[-1], axis=-1)


def lowpass(x, cut):
    """이상적인 anti-aliasing filter: cut Hz 위의 성분을 모두 지운다."""
    return band(x, 0, cut)


def digital(emg, fs):
    """raw EMG를 fs Hz로 숫자로 만든 뒤 0.25초 칸 10개의 RMS → (n, 20). 남은 EMG power 비율도."""
    x = lowpass(emg, fs / 2) if fs < FS else emg
    kept = float((x ** 2).mean() / (emg ** 2).mean())
    x = x[..., FS // fs - 1::FS // fs]                  # fs Hz로 집기
    rms = [np.sqrt((w ** 2).mean(-1)) for w in np.array_split(x, 10, axis=-1)]   # 0.25초 칸 10개
    return np.stack(rms, -1).reshape(len(x), -1), kept


def device(emg, taus, saturate):
    """정류한 EMG를 node마다 leaky integrate. 결과 state (n, 2, len(taus), GRID*T) = GRID Hz 간격 기록."""
    u = np.abs(emg)
    tau = np.array(taus)[None, None, :]
    x = np.zeros(u.shape[:2] + (len(taus),))
    step = FS // GRID
    out = np.zeros(x.shape + (N // step,))
    dt = 1 / FS
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


def read_end(S, rate, noise, seed):
    """끝 구간(2.2–2.5초)에서 rate Hz 간격으로 state를 읽어(읽을 때마다 noise) 평균 → (n, state 수).
    noise는 (seed, rate)로 정해지므로 같은 state를 같은 rate로 읽으면 두 표에서 같은 값이 나온다."""
    rng = np.random.default_rng([seed, rate])
    gap = GRID // rate
    idx = np.arange(S.shape[-1] - 1, int(END * GRID) - 1, -gap)       # 2.5초에서 거꾸로
    R = S[..., idx] + rng.normal(0, noise, S.shape[:-1] + (len(idx),))
    return R.mean(-1).reshape(len(S), -1)


def score(F, y, seed, rng):
    m, s = cv_accuracy(F, y, seed)
    sh = float(np.mean([cv_accuracy(F, rng.permutation(y), seed)[0] for _ in range(20)]))
    return m, s, sh


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def part1(a, out, emg, y, env, plt):
    from common import print_table
    rng = np.random.default_rng(a.seed + 7)
    rows = []
    for fs in a.fs:
        F, kept = digital(emg, fs)
        m, s, sh = score(F, y, a.seed, rng)
        rows.append(dict(sampling_rate_hz=fs, data_rate_bps=2 * fs * BITS, emg_power_kept_pct=round(100 * kept, 1),
                         bacc=round(m, 3), sd=round(s, 3), shuffled_labels=round(sh, 3)))
    write_csv(out / "e1_digital.csv", rows)
    print("digital: sample raw EMG (2 channels, 12 bit), then the computer measures burst strength over all 2.5 s")
    print()
    print_table(["sampling rate|(Hz)", "data rate|(bit/s)", "EMG power|kept (%)", "balanced|accuracy", "+/-",
                 "label|shuffle"],
                [[r["sampling_rate_hz"], r["data_rate_bps"], f"{r['emg_power_kept_pct']:.1f}", f"{r['bacc']:.2f}",
                  f"{r['sd']:.2f}", f"{r['shuffled_labels']:.2f}"] for r in rows])
    print()
    print("table:", out / "e1_digital.csv")
    if plt is None:
        return
    from matplotlib.lines import Line2D
    t = np.arange(N) / FS
    # 그림 1: 두 class의 trial 예
    fig, axs = plt.subplots(2, 1, figsize=(8, 5.6), sharex=True, sharey=True)
    for ax, c, tag in zip(axs, (0, 1), ("(a) class 0: 굽힘(flexor) → 폄(extensor)", "(b) class 1: 폄(extensor) → 굽힘(flexor)")):
        i = int(np.where(y == c)[0][0])
        ax.axvspan(END, T, color="#fff3c4", zorder=0)
        ax.plot(t, emg[i, 0] + 1.6, color="#2b59c3", lw=0.5)
        ax.plot(t, emg[i, 1] - 1.6, color="#c0521c", lw=0.5)
        ax.set_yticks([1.6, -1.6])
        ax.set_yticklabels(["flexor", "extensor"])
        ax.set_ylim(-3.6, 3.9)
        ax.set_title(tag)
    axs[0].text(END + (T - END) / 2, 3.75, "readout 구간", ha="center", va="top", color="#7a5a00", fontsize=10)
    axs[1].set_xlabel("time (s)")
    axs[1].set_xlim(0, T)
    fig.text(0.01, 0.5, "EMG (mV, 두 채널을 위아래로 띄움)", rotation=90, va="center", ha="left")
    fig.tight_layout(rect=(0.03, 0, 1, 1))
    fig.savefig(out / "e1_emg.png")
    plt.close(fig)

    # 그림 2: (a) 같은 0.1초를 1000 Hz와 50 Hz로 (b) sampling rate와 정확도
    i = int(np.where(y == 0)[0][0])
    k0 = int(np.argmax(env[i, 0] > 0.9 * env[i, 0].max()))       # 첫 힘 구간 안
    seg = slice(k0, k0 + int(0.1 * FS))
    fig = plt.figure(figsize=(8, 6.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.1], hspace=0.62)
    ax = fig.add_subplot(gs[0])
    tt = (t[seg] - t[k0]) * 1000
    ax.plot(tt, emg[i, 0, seg], color="0.7", lw=1.2)
    for fs, col, mk in ((1000, "#2b59c3", "o"), (50, "#c0521c", "s")):
        x = lowpass(emg[i:i + 1, 0], fs / 2)[0] if fs < FS else emg[i, 0]
        kk = np.arange(seg.start, seg.stop)
        kk = kk[(kk + 1) % (FS // fs) == 0]
        ax.plot((t[kk] - t[k0]) * 1000, x[kk], color=col, marker=mk, ms=4 if fs == 1000 else 7, lw=1.2 if fs == 50 else 0.8,
                ls="-" if fs == 50 else "none")
    ax.set_xlabel("time (ms, 첫 힘 구간 안의 0.1초)")
    ax.set_ylabel("flexor EMG (mV)")
    ax.set_title("(a) 같은 0.1초를 두 sampling rate로 숫자로 만들면", pad=28)
    ax.legend(handles=[Line2D([], [], color="0.7", lw=1.2, label="원래 EMG (2000 Hz)"),
                       Line2D([], [], color="#2b59c3", marker="o", ms=4, ls="none", label="1000 Hz로 집은 값"),
                       Line2D([], [], color="#c0521c", marker="s", ms=7, lw=1.2, label="50 Hz (filter 뒤)로 집은 값")],
              loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, frameon=False, borderaxespad=0.2)
    ax = fig.add_subplot(gs[1])
    fsx = [r["sampling_rate_hz"] for r in rows]
    ax.axhline(0.5, color="0.6", ls=":", lw=1.3)
    ax.errorbar(fsx, [r["bacc"] for r in rows], yerr=[r["sd"] for r in rows], fmt="o-", color="#2b59c3", lw=2, ms=6,
                capsize=3)
    ax.set_xscale("log")
    ax.set_xticks(fsx)
    ax.set_xticklabels([str(f) for f in fsx])
    ax.minorticks_off()
    ax.set_ylim(0.35, 1.08)
    ax.set_xlabel("sampling rate (Hz, 1초에 몇 번 집나)")
    ax.set_ylabel("balanced accuracy")
    ax.set_title("(b) 2.5초 전체를 숫자로 보고 컴퓨터가 판정했을 때", pad=8)
    ax.text(max(fsx), 0.47, "chance 0.50", color="0.45", fontsize=9.5, va="top", ha="right")
    fig.savefig(out / "e1_sampling.png")
    plt.close(fig)
    print("plots:", out / "e1_emg.png", "|", out / "e1_sampling.png")


def part2(a, out, emg, y, env, plt):
    from common import print_table
    rng = np.random.default_rng(a.seed + 7)
    t_end = slice(int(END * FS), N)
    lin = device(emg, TAUS, saturate=False)
    sat = device(emg, TAUS, saturate=True)
    nm = np.sqrt((emg[..., t_end] ** 2).mean(-1))                       # no memory: 끝 구간 raw EMG의 RMS
    models = [("no memory", "end RMS of raw EMG", nm + rng.normal(0, a.noise, nm.shape))]
    for j, tau in enumerate(TAUS):
        models.append(("R-C", f"tau = {tau:g} s", read_end(lin[:, :, j:j + 1], a.rate, a.noise, a.seed)))
    models.append(("R-C x4 (linear)", "tau = 0.1-3 s", read_end(lin, a.rate, a.noise, a.seed)))
    models.append(("reservoir", "4 saturating nodes", read_end(sat, a.rate, a.noise, a.seed)))
    Fd, _ = digital(emg, 1000)
    models.append(("digital (reference)", "all 2.5 s at 1000 Hz", Fd))
    rows = []
    for name, setting, F in models:
        m, s, sh = score(F, y, a.seed, rng)
        rows.append(dict(model=name, setting=setting, numbers=F.shape[1], bacc=round(m, 3), sd=round(s, 3),
                         shuffled_labels=round(sh, 3)))
    write_csv(out / "e2_models.csv", rows)
    print(f"readout: only the last 0.3 s (muscles at rest), states read at {a.rate} Hz and averaged, "
          f"readout noise {a.noise:g}")
    print()
    print_table(["model", "setting", "numbers|read", "balanced|accuracy", "+/-", "label|shuffle"],
                [[r["model"], r["setting"], r["numbers"], f"{r['bacc']:.2f}", f"{r['sd']:.2f}",
                  f"{r['shuffled_labels']:.2f}"] for r in rows], left=(0, 1))
    print()

    # data rate: 디지털(raw EMG를 2.5초 내내 숫자로) vs 소자 state(끝 0.3초에서만 몇 번 읽음)
    best = max(rows[1:5], key=lambda r: r["bacc"])
    jb = [r["setting"] for r in rows[1:5]].index(best["setting"])
    rr = []
    for fs in (1000, 500, 200, 100, 50):
        F, _ = digital(emg, fs)
        rr.append(dict(path="digital raw EMG", rate_hz=fs, numbers_per_read=2, bps_streaming=2 * fs * BITS,
                       bits_per_decision=int(2 * fs * T * BITS), bacc=round(cv_accuracy(F, y, a.seed)[0], 3)))
    for name, S in (("reservoir states", sat), (f"R-C states ({best['setting'].replace(' ', '')})", lin[:, :, jb:jb + 1])):
        for r_hz in (50, 20, 10, 5):
            F = read_end(S, r_hz, a.noise, a.seed)
            reads = len(np.arange(S.shape[-1] - 1, int(END * GRID) - 1, -(GRID // r_hz)))
            rr.append(dict(path=name, rate_hz=r_hz, numbers_per_read=F.shape[1], bps_streaming=F.shape[1] * r_hz * BITS,
                           bits_per_decision=F.shape[1] * reads * BITS, bacc=round(cv_accuracy(F, y, a.seed)[0], 3)))
    write_csv(out / "e2_rates.csv", rr)
    print("how many bits must leave the sensor (12 bit per number)")
    print("  digital: the whole 2.5 s is needed; device: only the reads in the last 0.3 s")
    print()
    print_table(["path", "rate|(Hz)", "numbers|per read", "bit/s if|streaming", "bits per|decision", "balanced|accuracy"],
                [[r["path"], r["rate_hz"], r["numbers_per_read"], r["bps_streaming"], r["bits_per_decision"],
                  f"{r['bacc']:.2f}"] for r in rr], left=(0,))
    print()
    print("tables:", out / "e2_models.csv", "|", out / "e2_rates.csv")
    if plt is None:
        return
    import matplotlib.ticker
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    tg = np.arange(1, sat.shape[-1] + 1) / GRID
    t = np.arange(N) / FS
    # 그림: 한 trial의 정류된 EMG와 state
    fig, axs = plt.subplots(2, 1, figsize=(8, 6.4), sharex=True)
    i = int(np.where(y == 0)[0][0])
    gap = GRID // a.rate
    idx = np.arange(sat.shape[-1] - 1, int(END * GRID) - 1, -gap)
    cols = ("#9cc0e8", "#5b8fd6", "#2b59c3", "#1a2f6b")
    for ax, c, tag in zip(axs, (0, 1), ("(a) flexor 채널 (이 trial에서는 먼저 힘을 줌)", "(b) extensor 채널 (나중에 힘을 줌)")):
        ax.axvspan(END, T, color="#fff3c4", zorder=0)
        ax.plot(t, np.abs(emg[i, c]), color="0.82", lw=0.4)
        for j, tau in enumerate(TAUS):
            ax.plot(tg, sat[i, c, j], color=cols[j], lw=1.8)
            ax.plot(tg[idx], sat[i, c, j, idx], "o", color="#c0521c", ms=4)
        ax.set_ylim(0, 1.3)
        ax.set_ylabel("|EMG| (mV) · state")
        ax.set_title(tag, pad=6)
    axs[1].set_xlabel("time (s)")
    axs[1].set_xlim(0, T)
    fig.legend(handles=[Line2D([], [], color="0.75", lw=1.2, label="정류된 EMG |EMG|")] +
               [Line2D([], [], color=cols[j], lw=1.8, label=f"node τ = {tau:g} s") for j, tau in enumerate(TAUS)] +
               [Line2D([], [], color="#c0521c", marker="o", ls="none", ms=4, label=f"readout ({a.rate} Hz)"),
                Patch(color="#fff3c4", label="readout 구간")],
               loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4, frameon=False)
    fig.tight_layout()
    fig.savefig(out / "e2_states.png")
    plt.close(fig)

    # 그림: (a) 모형 비교 (b) data rate와 정확도
    fig = plt.figure(figsize=(8, 7.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.1, 1], hspace=0.55)
    ax = fig.add_subplot(gs[0])
    lab = ["no memory", "R–C\nτ 0.1 s", "R–C\nτ 0.3 s", "R–C\nτ 1 s", "R–C\nτ 3 s", "R–C ×4\n(선형)", "reservoir\n(포화)",
           "digital\n(참고)"]
    colr = ["#9a8f86"] + ["#5b8fd6"] * 4 + ["#2b59c3", "#c0521c", "#4f7f5d"]
    xs = np.arange(len(rows))
    ax.bar(xs, [r["bacc"] for r in rows], yerr=[r["sd"] for r in rows], color=colr, width=0.62, capsize=3)
    ax.plot(xs, [r["shuffled_labels"] for r in rows], "_", color="k", ms=18, mew=2)
    ax.axhline(0.5, color="0.6", ls=":", lw=1.3)
    for x_, r in zip(xs, rows):
        ax.text(x_, r["bacc"] + r["sd"] + 0.02, f"{r['bacc']:.2f}", ha="center", va="bottom", fontsize=9.5)
    ax.set_xticks(xs)
    ax.set_xticklabels(lab, fontsize=9.5)
    ax.set_ylim(0, 1.18)
    ax.set_ylabel("balanced accuracy")
    ax.set_title(f"(a) 끝 0.3초만 읽어 맞힌 비율 (state는 {a.rate} Hz로 읽음)", pad=26)
    ax.legend(handles=[Patch(color="#5b8fd6", label="막대 = 맞힌 비율"),
                       Line2D([], [], color="k", marker="_", ms=14, mew=2, ls="none", label="label shuffle (점검)"),
                       Line2D([], [], color="0.6", ls=":", lw=1.3, label="chance 0.50")],
              loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, frameon=False, borderaxespad=0.2)
    ax = fig.add_subplot(gs[1])
    for name, col, mk, ls, dy in (("digital raw EMG", "#4f7f5d", "s", "-", 9), ("reservoir states", "#c0521c", "o", "-", 9),
                                  (rr[-1]["path"], "#2b59c3", "^", "--", -16)):
        sel = [r for r in rr if r["path"] == name]
        ax.plot([r["bits_per_decision"] for r in sel], [r["bacc"] for r in sel], marker=mk, color=col, ls=ls, lw=1.8, ms=6)
        for r in sel:
            ax.annotate(f"{r['rate_hz']}", (r["bits_per_decision"], r["bacc"]), textcoords="offset points", xytext=(0, dy),
                        ha="center", fontsize=8.5, color=col)
    ax.axhline(0.5, color="0.6", ls=":", lw=1.3)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(0.3, 1.14)
    ax.set_xlabel("판정 한 번에 센서 밖으로 보내는 bit 수 (로그 눈금). 점 옆 숫자 = rate (Hz)")
    ax.set_ylabel("balanced accuracy")
    ax.set_title("(b) 판정 한 번에 보내는 양과 맞힌 비율", pad=26)
    ax.legend(handles=[Line2D([], [], color="#4f7f5d", marker="s", lw=1.8, label="digital: raw EMG를 숫자로"),
                       Line2D([], [], color="#c0521c", marker="o", lw=1.8, label="reservoir state (8개)"),
                       Line2D([], [], color="#2b59c3", marker="^", ls="--", lw=1.8, label=f"R–C state (2개)")],
              loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, frameon=False, borderaxespad=0.2)
    fig.savefig(out / "e2_compare.png")
    plt.close(fig)
    print("plots:", out / "e2_states.png", "|", out / "e2_compare.png")


def main():
    # Windows 명령 프롬프트(cp949)에서 못 쓰는 글자는 ?로 바꿔 멈추지 않게
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", help="결과 폴더 (예: runs/e1)")
    ap.add_argument("--part", type=int, choices=(1, 2), default=1, help="1 = 디지털 sampling rate, 2 = 소자 state 읽기")
    ap.add_argument("--fs", default="2000,1000,500,200,100,50,20", help="P5.1의 sampling rate 목록 (2000의 약수)")
    ap.add_argument("--rate", type=int, default=20, help="P5.2에서 state를 읽는 rate (Hz, 200의 약수)")
    ap.add_argument("--n", type=int, default=200, help="trial 수 (짝수)")
    ap.add_argument("--noise", type=float, default=0.01, help="state를 읽을 때 더하는 noise의 표준편차")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    a.fs = [int(v) for v in a.fs.split(",")]
    if any(FS % f for f in a.fs) or GRID % a.rate:
        raise SystemExit("sampling rate must divide 2000, and --rate must divide 200 (e.g. 5, 10, 20, 50, 100)")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    emg, y, env, _ = make_trials(a.n, a.seed)
    print(f"synthetic EMG: {a.n} trials x {T:g} s, 2 channels (flexor, extensor), made at {FS} Hz (seed {a.seed})")
    print("task: class 0 = flex -> extend, class 1 = extend -> flex; chance = 0.50")
    print()
    try:
        from common import korean_plot
        plt = korean_plot()
    except ImportError:
        plt = None
    (part1 if a.part == 1 else part2)(a, out, emg, y, env, plt)
    if plt is None:
        print("matplotlib is not installed: plots skipped (python -m pip install matplotlib)")


if __name__ == "__main__":
    main()
