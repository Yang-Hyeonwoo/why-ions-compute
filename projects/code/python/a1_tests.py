"""A1 소자 특성 측정 3종. 소스미터 또는 모의 장비(--mock)로 실행한다.

  python a1_tests.py iv  config.json runs/iv_r1M  --vmax 0.2 --step 0.02 --dwell 0.05
  python a1_tests.py wrr config.json runs/wrr_rc  --vw 0.5 --tw 1 --vr 0.05 --tr 0.5 --gaps 0.1,0.3,1,3
  python a1_tests.py ppf config.json runs/ppf_rc  --vp 0.5 --tp 0.2 --gaps 0.05,0.1,0.2,0.5,1,2
  공통 선택: --mock --mock-model resistor|series_rc|memory   (장비 없이 연습)

결과: <이름>.npz (모든 읽기: t, V_set, V, I, compliance, seg) + <이름>.json(조건) + <이름>.png(그래프, matplotlib 있을 때)
  seg는 구간 번호이고 seg_names에 이름이 있다 (예: "settle", "write+", "rest", "read").
전압 순서 (그림 ②와 같음)
  wrr: 0 V로 settle → 쓰기 ±vw (tw초) → 0 V로 쉬기 (gap초) → 읽기 vr (tr초)   [gap마다, 극성 +/− 둘 다]
  ppf: 0 V로 settle → 펄스 vp (tp초) → 0 V (gap초) → 펄스 vp (tp초)
이 파일은 짧은 시험용이라 '이어서 하기'가 없다. 중간에 멈추면 처음부터 다시 한다.
"""
import argparse
import copy
import json
import os
import time

import numpy as np

from common import atomic_save_npz, load_json
from smu import open_smu


class Recorder:
    def __init__(self, smu):
        self.smu, self.rows, self.names = smu, [], []

    def seg(self, name, v, dur):
        if name not in self.names:
            self.names.append(name)
        k = self.names.index(name)
        recs = self.smu.hold(v, dur)
        for r in recs:
            self.rows.append((r["t_host"], v, r["V"], r["I"], r["compliance"], k))
        return recs

    def arrays(self):
        a = np.array(self.rows, dtype=float)
        return dict(t=a[:, 0] - a[0, 0], V_set=a[:, 1], V=a[:, 2], I=a[:, 3],
                    compliance=a[:, 4].astype(bool), seg=a[:, 5].astype(int), seg_names=np.array(self.names))


def tri(vmax, step):
    up = np.arange(0, vmax + step / 2, step)
    return np.r_[up, up[::-1][1:], -up[1:], -up[::-1][1:]]


def run_iv(rec, a):
    vs = tri(a.vmax, a.step)
    last = [rec.seg("sweep", float(v), a.dwell)[-1]["I"] for v in vs]
    return dict(V_steps=vs, I_end=np.array(last))


def run_wrr(rec, a):
    out = []
    for gap in a.gaps:
        for pol in (+1, -1):
            rec.seg("settle", 0.0, a.settle)
            rec.seg("write+" if pol > 0 else "write-", pol * a.vw, a.tw)
            rec.seg("rest", 0.0, gap)
            r = rec.seg("read", a.vr, a.tr)
            I = np.array([x["I"] for x in r])
            out.append((gap, pol, I[0], I[len(I) // 2:].mean()))
    o = np.array(out)
    return dict(gap=o[:, 0], polarity=o[:, 1], I_read_first=o[:, 2], I_read_late=o[:, 3])


def run_ppf(rec, a):
    out = []
    for gap in a.gaps:
        rec.seg("settle", 0.0, a.settle)
        i1 = rec.seg("pulse1", a.vp, a.tp)[-1]["I"]
        rec.seg("gap", 0.0, gap)
        i2 = rec.seg("pulse2", a.vp, a.tp)[-1]["I"]
        out.append((gap, i1, i2))
    o = np.array(out)
    return dict(gap=o[:, 0], I1=o[:, 1], I2=o[:, 2], ratio=o[:, 2] / o[:, 1])


def plot(path, kind, d, s):
    try:
        from common import korean_plot
        plt = korean_plot()
    except ImportError:
        print("matplotlib이 없어 그래프는 건너뜀 (pip install matplotlib)")
        return
    fig, ax = plt.subplots(2, 1, figsize=(8, 6), sharex=(kind != "ppf"))
    ax[0].plot(d["t"], d["V_set"], lw=1)
    ax[0].set_ylabel("V_set [V]")
    ax[1].plot(d["t"], d["I"] * 1e6, lw=1)
    ax[1].set_ylabel("I [µA]")
    ax[1].set_xlabel("t [s]")
    if kind == "iv":
        ax[0].cla(); ax[0].plot(s["V_steps"], s["I_end"] * 1e6, "o-", ms=3)
        ax[0].set_xlabel("V [V]"); ax[0].set_ylabel("I [µA] (각 단계 끝)")
    if kind == "ppf":
        from matplotlib.ticker import ScalarFormatter
        ax[0].cla(); ax[0].semilogx(s["gap"], s["ratio"], "o-")
        ax[0].xaxis.set_major_formatter(ScalarFormatter())   # 10^-1 대신 0.1처럼 표시
        ax[0].set_xlabel("간격 [s]"); ax[0].set_ylabel("I2 / I1"); ax[0].axhline(1, color="gray", lw=0.5)
    if kind == "wrr":
        ax[0].set_title("wrr: settle → write ± → rest(gap) → read")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print("그래프:", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["iv", "wrr", "ppf"])
    ap.add_argument("config")
    ap.add_argument("out", help="저장 이름 (확장자 없이), 예: runs/iv_r1M")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--mock-model", choices=["resistor", "series_rc", "memory"])
    ap.add_argument("--vmax", type=float, default=0.2)
    ap.add_argument("--step", type=float, default=0.02)
    ap.add_argument("--dwell", type=float, default=0.05)
    ap.add_argument("--vw", type=float, default=0.5)
    ap.add_argument("--tw", type=float, default=1.0)
    ap.add_argument("--vr", type=float, default=0.05)
    ap.add_argument("--tr", type=float, default=0.5)
    ap.add_argument("--vp", type=float, default=0.5)
    ap.add_argument("--tp", type=float, default=0.2)
    ap.add_argument("--settle", type=float, default=5.0, help="각 시험 전 0 V로 쉬는 시간 [s]")
    ap.add_argument("--gaps", default="0.1,0.3,1,3")
    a = ap.parse_args()
    a.gaps = [float(g) for g in a.gaps.split(",")]
    cfg = copy.deepcopy(load_json(a.config))
    if a.mock_model:
        cfg["instrument"].setdefault("mock", {})["model"] = a.mock_model
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open_smu(cfg["instrument"], mock=a.mock) as smu:
        print("장비:", smu.idn)
        smu.enable()
        rec = Recorder(smu)
        summary = {"iv": run_iv, "wrr": run_wrr, "ppf": run_ppf}[a.kind](rec, a)
    d = rec.arrays()
    atomic_save_npz(a.out + ".npz", **d, **{"sum_" + k: v for k, v in summary.items()})
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(dict(kind=a.kind, args=vars(a), instrument=cfg["instrument"], device=cfg["device"],
                       saved=time.strftime("%Y-%m-%d %H:%M:%S")), f, ensure_ascii=False, indent=1)
    print(f"저장: {a.out}.npz ({len(d['t'])}개 읽기, compliance {int(d['compliance'].sum())}개)")
    for k, v in summary.items():
        print(f"  {k}: {np.array2string(np.asarray(v), precision=3, max_line_width=110)}")
    plot(a.out + ".png", a.kind, d, summary)


if __name__ == "__main__":
    main()
