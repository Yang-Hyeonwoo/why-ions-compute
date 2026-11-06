"""B5: PC가 입력을 하나씩 보드(NU40 DK + B5_collect 펌웨어)로 보내고, 상태와 실제 펄스 시간을 받아 저장한다.
measure_seq.py와 같은 폴더 구조·manifest·이어서 하기 규칙을 쓴다.

통신 약속 (한 줄 = 한 메시지, 끝은 \\n)
  PC → 보드  : B,<시행번호>,<L>,u1,...,uL
  보드 → PC  : S,<시행번호>,i1,...,iNF        전류 [nA], 펄스 끝 읽기
               V,<시행번호>,v1,...,vNF        펄스 끝에 잰 실제 소자 전압 [V] (A0−A1)
               P,<시행번호>,p1,...,pNF        DAC 명령 시작 → 다음 명령 시작 [µs] (= 그 전압 '명령'이 유지된 시간)
               R,<시행번호>,r1,...,rNF        DAC 명령 시작 → 읽기 끝 [µs]
               Q,<시행번호>,<포화 횟수>       측정 범위를 벗어난 읽기 수
               E,<시행번호>,<이유>            입력 거부 (보드는 소자를 구동하지 않음)
사용: python board_collect.py config_board_example.json task.npz runs/b_pilot --port COM5 --limit 10
"""
import argparse

import numpy as np

from common import load_json
from measure_seq import check_inputs, run_trials


def board_trial_fn(ser, L, NF, timeout_s):
    def read_line(prefix, n):
        line = ser.readline().decode(errors="replace").strip()
        if not line:
            raise TimeoutError(f"trial {n}: no answer from board (timeout)")
        parts = line.split(",")
        if parts[0] == "E":
            raise RuntimeError(f"trial {n}: board rejected the input -> {line}")
        if parts[0] != prefix or len(parts) < 2 or parts[1] != str(n):
            raise RuntimeError(f"trial {n}: expected {prefix},{n},... but got: {line[:80]!r}")
        return np.array([float(v) for v in parts[2:]])

    def measure_trial(n, u_row):
        ser.reset_input_buffer()
        ser.write(("B,%d,%d," % (n, L) + ",".join(f"{x:.5f}" for x in u_row) + "\n").encode())
        got = {k: read_line(k, n) for k in ("S", "V", "P", "R", "Q")}
        bad = {k: len(got[k]) for k in "SVPR" if len(got[k]) != NF}
        if bad or len(got["Q"]) != 1:
            raise RuntimeError(f"trial {n}: got {bad} values, expected {NF}")
        if got["Q"][0] > 0:
            print(f"  ! trial {n}: {int(got['Q'][0])} reads out of range -> check R_f and voltage range")
        return got["S"], dict(I_nA=got["S"], V_dev=got["V"], period_us=got["P"], read_end_us=got["R"],
                              saturated=got["Q"])
    return measure_trial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("inputs")
    ap.add_argument("run_dir")
    ap.add_argument("--port", required=True)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    import serial
    cfg = load_json(a.config)
    enc = cfg["encoding"]
    d = np.load(a.inputs)
    U = d["U"]
    check_inputs(U, enc, cfg["instrument"]["v_limit_V"])
    L, NF = U.shape[1], U.shape[1] * len(enc["mask"])
    per_trial = enc["rest_s"] + NF * enc["theta_s"]
    extra = {k: d[k] for k in ("y", "groups") if k in d}
    with serial.Serial(a.port, 115200, timeout=per_trial * 2 + 5) as ser:
        ser.reset_input_buffer()
        run_trials(cfg, U, a.run_dir, board_trial_fn(ser, L, NF, per_trial), NF, limit=a.limit, extra=extra)


if __name__ == "__main__":
    main()
