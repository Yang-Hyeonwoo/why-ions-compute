"""measure_seq.py로 잰 시행 하나의 시간별 전압·전류를 그림으로 저장한다.

  python plot_run.py runs/practice --trial 0
  → runs/practice/trial_00000.png  (위: 설정 전압, 아래: 전류. 빨간 점 = 상태로 쓴 '펄스 끝 읽기')
"""
import argparse
import os

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--trial", type=int, default=0)
    a = ap.parse_args()
    path = os.path.join(a.run_dir, "raw", f"trial_{a.trial:05d}.npz")
    if not os.path.exists(path):
        raise SystemExit(f"{path}가 없습니다. 그 시행이 아직 측정되지 않았을 수 있습니다.")
    from common import korean_plot
    plt = korean_plot()
    with np.load(path) as d:
        t, v, i, p = d["t_host"] - d["t_host"][0], d["V_set"], d["I"], d["pulse"]
        dur = d["pulse_dur_s"]
    ends = [np.where(p == k)[0][-1] for k in range(p.max() + 1)]
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True)
    ax[0].step(t, v, where="post", lw=1)
    ax[0].set_ylabel(r"설정 전압 $V_{\mathrm{set}}$ (V)")
    ax[1].plot(t, i * 1e6, lw=1)
    ax[1].plot(t[ends], i[ends] * 1e6, "r.", ms=5, label="펄스 끝 읽기 (상태)")
    ax[1].set_ylabel(r"전류 $I$ (µA)")
    ax[1].set_xlabel(r"시간 $t$ (s, 쉬기 구간 포함)")
    ax[1].legend(loc="upper right", frameon=False)
    ax[0].set_title(f"trial {a.trial}: actual pulse width mean {dur.mean()*1000:.1f} ms (min {dur.min()*1000:.1f}, max {dur.max()*1000:.1f})")
    fig.tight_layout()
    out = os.path.join(a.run_dir, f"trial_{a.trial:05d}.png")
    fig.savefig(out)
    print("plot:", out)


if __name__ == "__main__":
    main()
