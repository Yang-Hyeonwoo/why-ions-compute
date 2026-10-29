"""학습한 readout과 측정 조건을 마이크로컨트롤러용 헤더 파일로 내보낸다 (손으로 복사하지 않기).

만드는 파일
  config.h       L, M, 마스크, V0, VA, 펄스 폭, 휴지 시간, 전압 상한  ← 측정 manifest에서
  weights.h      표준화 평균·표준편차, 가중치 W[NC][NF], 절편 BIAS[NC], 클래스 이름
  ref_vectors.h  저장된 특징 몇 개와 Python이 계산한 점수 → MCU 계산이 같은지 먼저 확인용

이진 분류는 NC=1 (점수 > 0 이면 두 번째 클래스), 다중 분류는 NC=클래스 수 (점수가 가장 큰 클래스).

사용: python export_mcu.py model.joblib runs/b_collect/manifest.json runs/b_collect/checkpoint.npz out_dir/
"""
import argparse
import os
import re

import numpy as np

from common import load_json


def _arr(a):
    return "{" + ",".join(f"{float(x):.9g}f" for x in np.ravel(a)) + "}"


def export(model, manifest, F_ref, out_dir, v_limit, n_ref=5, cols=None):
    os.makedirs(out_dir, exist_ok=True)
    sc, lr = model.named_steps["sc"], model.named_steps["lr"]
    enc = manifest["encoding"]
    M = len(enc["mask"])
    nf_total = manifest["n_features"]
    if nf_total % M:
        raise ValueError("n_features가 M의 배수가 아닙니다")
    L = nf_total // M
    NF = len(sc.mean_)
    if cols is None and NF != L * M:
        raise ValueError(f"특징 수 {NF} ≠ L×M = {L*M}")
    W, B = np.atleast_2d(lr.coef_), np.atleast_1d(lr.intercept_)
    NC = W.shape[0]
    with open(os.path.join(out_dir, "config.h"), "w", encoding="utf-8") as f:
        f.write("// 자동 생성: export_mcu.py — 손으로 고치지 말 것\n#pragma once\n")
        f.write(f"const int L = {L};\nconst int M = {M};\nconst float MASK[M] = {_arr(enc['mask'])};\n")
        f.write(f"const float V0 = {enc['V0']}f;\nconst float VA = {enc['VA']}f;\n")
        f.write(f"const uint32_t THETA_US = {int(round(enc['theta_s'] * 1e6))};\n")
        f.write(f"const uint32_t REST_MS = {int(round(enc['rest_s'] * 1e3))};\n")
        f.write(f"const float V_LIMIT = {v_limit}f;\n")
        f.write(f"const char RUN_NOTE[] = \"{manifest.get('created', '')} {manifest['device'].get('id', '')}\";\n")
    feat_cols = "ALL" if cols is None else ",".join(map(str, cols))
    with open(os.path.join(out_dir, "weights.h"), "w", encoding="utf-8") as f:
        f.write("// 자동 생성: export_mcu.py\n#pragma once\n")
        f.write(f"const int NF = {NF};\nconst int NC = {NC};  // 1이면 이진(점수>0 → 클래스 1)\n")
        f.write(f"// 사용 특징 열: {feat_cols}\n")
        fcol = range(NF) if cols is None else cols     # 상태 L×M개 중 몇 번째 열을 쓰는지
        f.write(f"const int FCOL[NF] = {{{','.join(map(str, fcol))}}};\n")
        f.write(f"const float MU[NF] = {_arr(sc.mean_)};\nconst float SD[NF] = {_arr(sc.scale_)};\n")
        f.write(f"const float W[NC][NF] = {{{','.join(_arr(w) for w in W)}}};\n")
        f.write(f"const float BIAS[NC] = {_arr(B)};\n")
        f.write(f"const int CLASS_ID[] = {{{','.join(str(int(c)) for c in lr.classes_)}}};\n")
    Fr = np.asarray(F_ref)[:n_ref]
    Sr = np.atleast_2d(model.decision_function(Fr)).reshape(len(Fr), -1)
    with open(os.path.join(out_dir, "ref_vectors.h"), "w", encoding="utf-8") as f:
        f.write("// 자동 생성: MCU 계산 확인용 (같은 특징 → 같은 점수여야 함)\n#pragma once\n")
        f.write(f"const int NREF = {len(Fr)};\n")
        f.write(f"const float XREF[NREF][NF] = {{{','.join(_arr(x) for x in Fr)}}};\n")
        f.write(f"const float SREF[NREF][NC] = {{{','.join(_arr(s) for s in Sr)}}};\n")
    return dict(L=L, M=M, NF=NF, NC=NC)


def export_inputs(U, y, out_dir):
    """B6가 재생할 시험 입력 (0–1)과 정답 → inputs_test.h"""
    U, y = np.asarray(U, float), np.asarray(y, int)
    with open(os.path.join(out_dir, "inputs_test.h"), "w", encoding="utf-8") as f:
        f.write("// 자동 생성: B6가 재생할 시험 입력\n#pragma once\n")
        f.write(f"const int NT = {len(U)};\n")
        f.write(f"const float UT[NT][{U.shape[1]}] = {{{','.join(_arr(u) for u in U)}}};\n")
        f.write(f"const int YT[NT] = {{{','.join(map(str, y))}}};\n")


def read_header_arrays(path):
    """헤더의 배열을 다시 읽는다 (내보내기 확인용)."""
    txt = open(path, encoding="utf-8").read()
    out = {}
    for name, body in re.findall(r"const \w+ (\w+)(?:\[[^\]]*\])+ = (\{.*?\});\n", txt, re.S):
        out[name] = np.array([float(v.rstrip("f")) for v in re.findall(r"-?[\d.]+(?:e[-+]?\d+)?f?", body)])
    return out


def mcu_score(x, h):
    """MCU 코드와 같은 순서로 계산하는 파이썬 판 (float32)"""
    x = np.float32(x)
    z = (x - np.float32(h["MU"])) / np.float32(h["SD"])
    W = np.float32(h["W"]).reshape(-1, len(z))
    return W @ z + np.float32(h["BIAS"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("manifest")
    ap.add_argument("states")
    ap.add_argument("out_dir")
    ap.add_argument("--v-limit", type=float, required=True, help="보드가 거부할 소자 전압 상한(V)")
    ap.add_argument("--inputs", help="시험 입력 npz (U, y, test_idx) → inputs_test.h")
    a = ap.parse_args()
    import joblib
    pack = joblib.load(a.model)
    cols = None if not pack.get("cols") else [int(c) for c in pack["cols"].split(",")]
    d = np.load(a.states)
    F = d["S"][d["done"]]
    if cols is not None:
        F = F[:, cols]
    print(export(pack["model"], load_json(a.manifest), F, a.out_dir, a.v_limit, cols=cols))
    if a.inputs:
        di = np.load(a.inputs)
        te = di["test_idx"] if "test_idx" in di else np.arange(len(di["U"]))
        export_inputs(di["U"][te], di["y"][te], a.out_dir)
        print("inputs_test.h:", len(te), "개")


if __name__ == "__main__":
    main()
