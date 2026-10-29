"""C 연습용 모의 실험: 장비 없이 c_run.py와 같은 형식의 기록(runs/<이름>/)을 만든다.
실제 소자·센서에 대해서는 아무것도 말해 주지 않는다. 분석 경로(c_analyze.py)를 익히기 위한 것.

  python c_mock.py config_c_mock.json rhythm.npz runs/c_mock_mem --model memory  --session 1
  python c_mock.py config_c_mock.json rhythm.npz runs/c_mock_fsr --model memoryless --session 1
모델
  memory     : 누름이 상태 x를 올리고 x가 τ로 천천히 돌아온다. 전류 = 기준 × (1 + x)
  memoryless : 전류가 지금 힘에만 비례 (이상적 무기억 센서)
session: 다른 날을 흉내 내는 번호. 날마다 기준 전류와 힘이 조금 다르다.
"""
import argparse

import numpy as np

from c_rhythm import end_features
from common import load_json
from measure_seq import run_trials

HOLD, LEAD, POST = 0.08, 0.5, 1.5        # 펌웨어 C_tapper와 같은 값 [s]


def simulate(gaps, rng, model, sess_rng, tau=0.6, read_dt=0.02, force_dt=0.0125):
    onsets = LEAD + np.r_[0, np.cumsum(gaps)]
    t_end = onsets[-1] + HOLD + POST
    tf = np.arange(0, t_end, force_dt)
    peak = 2.0 * sess_rng["force"] * (1 + 0.05 * rng.standard_normal(4))
    F = np.zeros_like(tf)
    for o, pk in zip(onsets, peak):
        m = (tf >= o) & (tf < o + HOLD)
        F[m] = pk * np.sin(np.pi * (tf[m] - o) / HOLD)
    t = np.arange(0, t_end, read_dt)
    Ft = np.interp(t, tf, F)
    x = np.zeros_like(t)
    for k in range(1, len(t)):
        x[k] = x[k - 1] * np.exp(-read_dt / tau) + 0.15 * Ft[k] * read_dt / 0.08
    base = 1e-7 * sess_rng["base"]
    I = base * (1 + (x if model == "memory" else 0.4 * Ft)) + 2e-10 * rng.standard_normal(len(t))
    return t, I, onsets, tf, F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("rhythm")
    ap.add_argument("run_dir")
    ap.add_argument("--model", choices=["memory", "memoryless"], default="memory")
    ap.add_argument("--session", type=int, default=1)
    a = ap.parse_args()
    cfg = load_json(a.config)
    cfg["device"] = dict(cfg["device"], mock_model=a.model, session=a.session)
    d = np.load(a.rhythm)
    srng = np.random.default_rng(1000 + a.session)
    sess = dict(force=1 + 0.1 * srng.standard_normal(), base=1 + 0.2 * srng.standard_normal())

    def measure_trial(n, gaps_row):
        rng = np.random.default_rng(a.session * 100000 + n)
        t, I, onsets, tf, F = simulate(gaps_row, rng, a.model, sess)
        state = end_features(t, I, onsets[-1])
        raw = dict(t=t, I=I, compliance=np.zeros(len(t), bool), onsets_ms=onsets * 1000,
                   force_t_ms=tf * 1000, force_N=F)
        return state, raw
    run_trials(cfg, d["gaps"], a.run_dir, measure_trial, 3, extra={"y": d["y"]}, log=lambda *_: None)
    print(f"저장: {a.run_dir} (모의 {a.model}, 세션 {a.session}, 시행 {len(d['y'])}개)")


if __name__ == "__main__":
    main()
