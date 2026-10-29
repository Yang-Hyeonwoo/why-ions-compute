"""입력 U(시행 × L, 값 0–1)를 마스킹 펄스로 소자에 걸고, 각 펄스 끝의 전류를 '상태'로 모은다.

펄스 규칙 (config의 encoding):
  입력 하나 u → 펄스 M개, 높이 V = V0 + VA·u·mask[j], 폭 theta_s
  시행 시작 전 0 V로 rest_s 동안 쉼
  상태 = 각 펄스의 마지막 읽기 전류 → 시행 하나에 L×M개

사용:
  python measure_seq.py config.json inputs.npz runs/pilot --limit 10      # 처음 10시행만 (시험)
  python measure_seq.py config.json inputs.npz runs/pilot                 # 같은 명령 → 남은 시행 이어서
  python measure_seq.py config.json inputs.npz runs/pilot --mock          # 장비 없이 모의 장비로
inputs.npz에는 U가 꼭 있어야 하고, y(정답)·groups(환자/세션 번호)는 있으면 같이 보관된다.
"""
import argparse
import os

import numpy as np

from common import (array_sha, atomic_save_npz, atomic_write_json, load_json, make_manifest,
                    manifest_mismatch)


def pulse_plan(u_row, enc):
    mask = np.asarray(enc["mask"], float)
    return [enc["V0"] + enc["VA"] * u * m for u in u_row for m in mask]


def check_inputs(U, enc, v_limit):
    if U.ndim != 2 or U.shape[0] == 0 or U.shape[1] == 0:
        raise ValueError(f"U는 (시행 수, L) 2차원이어야 합니다: {U.shape}")
    if not np.all(np.isfinite(U)) or U.min() < 0 or U.max() > 1:
        raise ValueError("U 값은 모두 0–1 사이의 유한한 숫자여야 합니다")
    mask = np.asarray(enc["mask"], float)
    extremes = [enc["V0"]] + list(enc["V0"] + enc["VA"] * mask)
    if max(abs(v) for v in extremes) > v_limit + 1e-12:
        raise ValueError(f"인코딩이 만들 수 있는 전압 {extremes}가 계획 상한 ±{v_limit} V를 넘습니다")


def run_trials(cfg, U, run_dir, measure_trial, n_features, limit=None, log=print, extra=None):
    """시행을 하나씩 측정하며, 끝날 때마다 원시 기록과 체크포인트를 원자적으로 저장한다.
    measure_trial(n, u_row) → (state 길이 n_features, raw dict of arrays)"""
    raw_dir = os.path.join(run_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    mpath, cpath = os.path.join(run_dir, "manifest.json"), os.path.join(run_dir, "checkpoint.npz")
    new = make_manifest(cfg, array_sha(U), len(U), n_features)
    if os.path.exists(mpath):
        bad = manifest_mismatch(load_json(mpath), new)
        if bad:
            raise SystemExit(f"기존 측정({run_dir})과 조건이 다릅니다: {bad}\n"
                             "섞지 않도록 멈춥니다. 조건을 바꾼 측정은 새 폴더 이름으로 하세요.")
        with np.load(cpath) as ck:              # with: 읽은 뒤 파일을 닫아야 Windows에서 덮어쓸 수 있음
            S, done = ck["S"].copy(), ck["done"].copy()
        log(f"이어서 측정: {done.sum()}/{len(done)} 시행이 이미 끝남")
    else:
        atomic_write_json(mpath, new)
        S, done = np.full((len(U), n_features), np.nan), np.zeros(len(U), bool)
        atomic_save_npz(cpath, S=S, done=done, **(extra or {}))
    todo = np.where(~done)[0]
    if limit is not None:
        todo = todo[:limit]
    for n in todo:
        state, raw = measure_trial(int(n), U[n])
        state = np.asarray(state, float)
        if state.shape != (n_features,) or not np.all(np.isfinite(state)):
            raise RuntimeError(f"시행 {n}: 상태 차원/값 이상 {state.shape}")
        atomic_save_npz(os.path.join(raw_dir, f"trial_{n:05d}.npz"), **raw)
        S[n], done[n] = state, True
        atomic_save_npz(cpath, S=S, done=done, **(extra or {}))
        log(f"시행 {n} 저장 ({done.sum()}/{len(done)})")
    return S, done


def smu_trial_fn(smu, enc):
    def measure_trial(n, u_row):
        if hasattr(smu, "reseed"):
            smu.reseed(n)                       # 모의 장비: 같은 시행은 같은 잡음
        recs = smu.hold(0.0, enc["rest_s"])
        for r in recs:
            r["pulse"] = -1                     # -1 = 쉬는 구간
        state = []
        for k, v in enumerate(pulse_plan(u_row, enc)):
            r = smu.hold(v, enc["theta_s"])
            state.append(r[-1]["I"])
            for x in r:
                x["pulse"] = k
            recs += r
        keys = ("t_host", "t_set", "V_set", "V", "I", "compliance", "pulse")
        raw = {k: np.array([x[k] for x in recs]) for k in keys}
        p = raw["pulse"]
        # 실제 펄스 길이 = 그 펄스 마지막 읽기 시각 − 전압 설정 시각 (PC 기준)
        dur = np.array([raw["t_host"][p == k].max() - raw["t_set"][p == k][0] for k in range(len(state))])
        raw["pulse_dur_s"] = dur
        if raw["compliance"].any():
            print(f"  ! 시행 {n}: 전류 제한(compliance)에 걸린 읽기 {int(raw['compliance'].sum())}개")
        return state, raw
    return measure_trial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("inputs")
    ap.add_argument("run_dir")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--mock-model", choices=["resistor", "series_rc", "memory"], help="모의 장비 모델 바꾸기")
    a = ap.parse_args()
    from smu import open_smu
    cfg = load_json(a.config)
    if a.mock_model:                     # 모델이 바뀌면 manifest도 달라져 다른 폴더를 써야 함
        cfg["instrument"].setdefault("mock", {})["model"] = a.mock_model
    d = np.load(a.inputs)
    U = d["U"]
    enc = cfg["encoding"]
    check_inputs(U, enc, cfg["instrument"]["v_limit_V"])
    extra = {k: d[k] for k in ("y", "groups") if k in d}
    nf = U.shape[1] * len(enc["mask"])
    est = len(U) * (enc["rest_s"] + nf * enc["theta_s"])
    print(f"시행 {len(U)}개 × 특징 {nf}개, 명목 시간 ≈ {est/60:.1f}분 (통신·읽기 시간은 별도)")
    with open_smu(cfg["instrument"], mock=a.mock) as smu:
        print("장비:", smu.idn)
        smu.enable()
        run_trials(cfg, U, a.run_dir, smu_trial_fn(smu, enc), nf, limit=a.limit, extra=extra)


if __name__ == "__main__":
    main()
