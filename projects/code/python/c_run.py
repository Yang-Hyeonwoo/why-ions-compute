"""C: 리듬 시행을 돌리며 소스미터로 소자 전류를 계속 읽고, tapper의 힘 기록과 함께 저장한다.

시각 맞추기: PC가 'T' 명령을 보낸 시각을 tapper의 0 ms로 본다. 직렬 지연(수 ms)만큼 오차가 있으므로
SMU 읽기 간격(보통 15–40 ms)보다 작은지 확인하고 보고서에 적는다.
상태(state) = 마지막 onset 뒤 0.3/0.6/1.0 s 전류 3개. 계속 읽기 특징은 raw에서 나중에 만든다.

사용: python c_run.py config_c_example.json rhythm.npz runs/c_dev01 --tapper COM6 [--limit 8]
rhythm.npz 만들기: python c_rhythm.py rhythm.npz --n 60
분석: python c_analyze.py runs/c_dev01
'끝 3개'는 계속 읽은 기록에서 나중에 뽑는다 → 실제로 끝에서만 읽는 장치의 전력·ADC 횟수를 잰 것이 아니다.
상태: 장비 없이 시험하지 못함 (실물 검증 대기)
"""
import argparse
import threading
import time

import numpy as np

from c_rhythm import end_features
from common import load_json
from measure_seq import run_trials
from smu import open_smu


def c_trial_fn(smu, ser, read_v, rest_s, delays=(0.3, 0.6, 1.0)):
    def lines_until_x(n):
        got = {}
        while "X" not in got:
            line = ser.readline().decode(errors="replace").strip()
            if not line:
                raise TimeoutError(f"시행 {n}: tapper 응답 없음")
            p = line.split(",")
            if p[0] == "E":
                raise RuntimeError(f"시행 {n}: tapper 거부 {line}")
            if len(p) > 1 and p[1] == str(n):
                got[p[0]] = np.array([float(v) for v in p[2:]])
        return got

    def measure_trial(n, gaps_row):
        smu.hold(read_v, rest_s)                       # 읽기 전압에서 쉬며 안정
        recs, stop = [], threading.Event()

        def reader():
            while not stop.is_set():
                recs.append(smu.read())
        th = threading.Thread(target=reader)
        th.start()
        t_cmd = time.perf_counter()
        try:
            ser.write(("T,%d," % n + ",".join(str(int(round(g * 1000))) for g in gaps_row) + "\n").encode())
            got = lines_until_x(n)
            time.sleep(max(delays) + 0.2)
        finally:
            stop.set()
            th.join()
        t = np.array([r["t_host"] for r in recs]) - t_cmd
        I = np.array([r["I"] for r in recs])
        t_last = got["X"][0] / 1000
        state = end_features(t, I, t_last, delays)
        raw = dict(t=t, I=I, compliance=np.array([r["compliance"] for r in recs]),
                   onsets_ms=got["O"], force_t_ms=got["FT"], force_N=got["FV"])
        return state, raw
    return measure_trial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("rhythm")
    ap.add_argument("run_dir")
    ap.add_argument("--tapper", required=True)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    import serial
    cfg = load_json(a.config)
    d = np.load(a.rhythm)
    gaps = d["gaps"]
    rd = cfg["encoding"]                 # C에서는 encoding = 읽기 조건 (read_V, rest_s)
    with serial.Serial(a.tapper, 115200, timeout=15) as ser, open_smu(cfg["instrument"]) as smu:
        time.sleep(2)
        ser.reset_input_buffer()
        smu.enable()
        run_trials(cfg, gaps, a.run_dir, c_trial_fn(smu, ser, rd["read_V"], rd["rest_s"]), 3,
                   limit=a.limit, extra={"y": d["y"]})


if __name__ == "__main__":
    main()
