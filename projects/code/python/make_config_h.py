"""설정 파일(config_board.json)과 입력 파일(task.npz)로 보드용 config.h를 만든다 (B5용, 손으로 옮기지 않기).

  python make_config_h.py config_board.json task.npz ../firmware/B5_collect
  → ../firmware/B5_collect/config.h  (L, M, MASK, V0, VA, THETA_US, REST_MS, V_LIMIT)
B6용 config.h는 export_mcu.py가 측정 manifest로 만든다 (그때는 실제 측정 조건이 기준).
"""
import argparse
import os

import numpy as np

from common import load_json
from export_mcu import _arr


def write_config_h(enc, L, v_limit, note, out_dir):
    M = len(enc["mask"])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "config.h")
    with open(path, "w", encoding="utf-8") as f:
        f.write("// 자동 생성: make_config_h.py — 손으로 고치지 말 것\n#pragma once\n")
        f.write(f"const int L = {L};\nconst int M = {M};\nconst float MASK[M] = {_arr(enc['mask'])};\n")
        f.write(f"const float V0 = {enc['V0']}f;\nconst float VA = {enc['VA']}f;\n")
        f.write(f"const uint32_t THETA_US = {int(round(enc['theta_s'] * 1e6))};\n")
        f.write(f"const uint32_t REST_MS = {int(round(enc['rest_s'] * 1e3))};\n")
        f.write(f"const float V_LIMIT = {v_limit}f;\n")
        f.write(f"const char RUN_NOTE[] = \"{note}\";\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("inputs")
    ap.add_argument("out_dir")
    a = ap.parse_args()
    cfg = load_json(a.config)
    L = np.load(a.inputs)["U"].shape[1]
    p = write_config_h(cfg["encoding"], L, cfg["instrument"]["v_limit_V"], cfg["device"].get("id", ""), a.out_dir)
    print(f"저장: {p} (L={L}, M={len(cfg['encoding']['mask'])})")


if __name__ == "__main__":
    main()
