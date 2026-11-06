"""S1: 같은 심전도 모양 신호를 샘플링률·bit 수만 바꿔 숫자로 만들고, 데이터량과 박동 판정이 어떻게 달라지는지 본다.

장비가 필요 없다. 신호는 이 파일이 만드는 '심전도 모양' 합성 신호다(실제 환자 기록 아님).

사용법:
  python s1_bits.py runs/s1
  python s1_bits.py runs/s1 --fs 25,50,100,250,500 --bits 3,4,6,8,12 --seed 1

결과 (출력 폴더):
  s1_table.csv   설정마다 데이터량(bit/s)·양자화 한 눈금·박동 판정(맞힘·놓침·오검출(없는데 있다고 판단))·시각 오차
  s1_waves.png   같은 2초 구간을 세 설정으로 숫자로 만든 모양 (회색 = 원래 신호)

모형의 가정 (실제 장치와 다른 점):
  - ADC 입력 범위 ±2 mV (앞단 증폭을 거친 셈 치고 신호 단위로 적음). 한 눈금 = 4 mV ÷ 2^bit.
  - 샘플링은 원래 신호에서 일정 간격으로 값을 집는 것뿐이다(앞단 저역 통과 필터 없음).
  - 데이터량은 샘플 값만 센 payload다. 무선의 헤더·재전송·수신 대기 같은 비용은 넣지 않았다.
  - 박동 판정은 단순 문턱 검출기다(0.2초 이동평균을 빼고 0.5 mV를 넘는 첫 봉우리, 0.25초 불응기).
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

REF_FS = 2000  # '원래 신호'를 만드는 촘촘한 시간 간격 (Hz)


def make_signal(seconds, seed):
    """심전도 모양 합성 신호(mV)와 실제 R파 시각(초)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * REF_FS)) / REF_FS
    x = np.zeros_like(t)
    beats = []
    now = 0.4
    while now < seconds - 0.6:
        beats.append(now)
        rr = 60 / rng.uniform(62, 88)  # 박동 간격: 분당 62–88회
        now += rr
    for b in beats:
        for dt, amp, w in ((-0.18, 0.12, 0.025), (-0.025, -0.12, 0.008), (0.0, 1.0, 0.009),
                           (0.025, -0.25, 0.009), (0.28, 0.3, 0.045)):  # P, Q, R, S, T
            x += amp * np.exp(-0.5 * ((t - b - dt) / w) ** 2)
    x += 0.15 * np.sin(2 * np.pi * 0.3 * t)  # 호흡 등으로 기준선이 천천히 흔들림
    x += rng.normal(0, 0.02, t.size)  # 잡음
    return t, x, np.array(beats)


def digitize(t, x, fs, bits, vrange=2.0):
    step = REF_FS // fs
    ts, xs = t[::step], x[::step]
    lsb = 2 * vrange / 2 ** bits
    q = np.clip(np.round(xs / lsb), -(2 ** (bits - 1)), 2 ** (bits - 1) - 1) * lsb
    return ts, q, lsb


def detect(ts, q, fs, thr=0.5, refractory=0.25):
    """0.2초 이동평균을 빼고(기준선 제거) 문턱을 넘은 뒤의 봉우리 시각."""
    k = max(1, int(round(0.2 * fs)))
    base = np.convolve(q, np.ones(k) / k, mode="same")
    y = q - base
    out, i, n = [], 0, len(y)
    while i < n:
        if y[i] > thr:
            j = i
            while j + 1 < n and y[j + 1] >= y[j]:
                j += 1
            out.append(ts[j])
            i = j + max(1, int(refractory * fs))
        else:
            i += 1
    return np.array(out)


def score(found, truth, tol=0.05):
    used = np.zeros(len(found), bool)
    hit, err = 0, []
    for b in truth:
        d = np.abs(found - b) if len(found) else np.array([])
        cand = np.where((d <= tol) & ~used)[0] if len(d) else []
        if len(cand):
            j = cand[np.argmin(d[cand])]
            used[j] = True
            hit += 1
            err.append(abs(found[j] - b))
    return hit, len(truth) - hit, int((~used).sum()), (1000 * np.mean(err) if err else float("nan"))


def main():
    # Windows 명령 프롬프트(cp949)에서 못 쓰는 글자는 ?로 바꿔 멈추지 않게
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", help="결과 폴더 (예: runs/s1)")
    ap.add_argument("--fs", default="25,50,100,250,500", help="샘플링률 목록 (Hz, 2000의 약수)")
    ap.add_argument("--bits", default="3,4,6,8,12", help="bit 수 목록")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    fss = [int(v) for v in a.fs.split(",")]
    bitss = [int(v) for v in a.bits.split(",")]
    for fs in fss:
        if REF_FS % fs:
            raise SystemExit(f"--fs {fs}: use a number that divides 2000 (e.g. 25, 40, 50, 80, 100, 125, 200, 250, 500)")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t, x, truth = make_signal(a.seconds, a.seed)

    rows = []
    for fs in fss:
        for bits in bitss:
            ts, q, lsb = digitize(t, x, fs, bits)
            hit, miss, false, err = score(detect(ts, q, fs), truth)
            rows.append({"fs_Hz": fs, "bits": bits, "data_bit_s": fs * bits, "lsb_uV": round(lsb * 1000, 1),
                         "beats": len(truth), "hit": hit, "miss": miss, "false": false,
                         "time_err_ms": round(err, 1)})
    with open(out / "s1_table.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"synthetic ECG: {a.seconds:.0f} s, {len(truth)} true beats (seed {a.seed})")
    print()
    from common import print_table
    print_table(["sampling rate|(Hz)", "bit", "data rate|(bit/s)", "LSB|(uV)", "hit", "miss", "false+",
                 "timing error|(ms)"],
                [[r["fs_Hz"], r["bits"], r["data_bit_s"], f"{r['lsb_uV']:.1f}", r["hit"], r["miss"], r["false"],
                  f"{r['time_err_ms']:.1f}"] for r in rows])
    print()
    print("table:", out / "s1_table.csv")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from common import korean_plot
        korean_plot()
    except ImportError:
        print("matplotlib is not installed: plot skipped (python -m pip install matplotlib)")
        return
    show = [(max(fss), max(bitss)), (100 if 100 in fss else fss[len(fss) // 2], 6 if 6 in bitss else bitss[len(bitss) // 2]),
            (min(fss), min(bitss))]
    w0, w1 = truth[2] - 0.5, truth[2] + 1.5
    fig, axs = plt.subplots(len(show), 1, figsize=(8, 6.6), sharex=True)
    m = (t >= w0) & (t <= w1)
    for ax, (fs, bits) in zip(axs, show):
        ts, q, lsb = digitize(t, x, fs, bits)
        mm = (ts >= w0) & (ts <= w1)
        found = detect(ts, q, fs)
        ax.plot(t[m], x[m], color="0.75", lw=1.2, label="원래 신호 (analog)")
        ax.step(ts[mm], q[mm], where="mid", color="#2b59c3", lw=1.3, label="digitized (숫자로 만든 값)")
        ax.plot(ts[mm], q[mm], "o", ms=2.5, color="#2b59c3")
        ff = found[(found >= w0) & (found <= w1)]
        ax.plot(ff, np.full(len(ff), 1.25), "v", color="#c0392b", ms=7, label="detected beat")
        ax.set_ylim(-0.7, 1.45)
        ax.set_ylabel("mV")
        ax.set_title(f"sampling rate {fs} Hz × {bits} bit = {fs * bits:,} bit/s · LSB {lsb * 1000:.0f} µV", loc="left")
    # 범례는 그림 맨 위 한 줄에 따로 둔다 (2026-11-06: 첫 그래프 제목과 겹쳤음)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False)
    axs[-1].set_xlabel("time (s)")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out / "s1_waves.png")
    print("plot: ", out / "s1_waves.png")


if __name__ == "__main__":
    main()
