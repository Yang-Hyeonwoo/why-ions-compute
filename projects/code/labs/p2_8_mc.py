# ============================================================
# P2 실습 8 · memory capacity (MC): 몇 걸음 전 입력까지 기억하나
#
# 전체 과정:
#
#   0–1 사이 무작위 입력 K개를 한 줄로 (python/tasks.py의 mc_sequence)
#         ↓
#   입력 하나 = pulse 4개 (실습 1과 같은 mask) → 소자에 차례로 걸기
#   → 입력마다 state 4개 (pulse 끝 전류)
#         ↓
#   d = 1, 2, … 10 걸음 전 입력을 '지금 state 4개'로 얼마나 맞히나 (r², 0–1)
#   (앞 2/3로 맞히는 법을 배우고, 뒤 1/3로 채점)
#         ↓
#   우연히도 나오는 크기(null)와 비교 → 그보다 큰 부분만 더한 것 = MC_excess
#         ↓
#   그래프: d마다 r² 막대 + 우연 기준선
# ============================================================

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from smu import open_smu
from measure_seq import check_inputs, run_trials, smu_trial_fn   # 실습 2와 같은 측정 순서
from tasks import mc_sequence                      # 무작위 입력 한 줄
from mc import memory_capacity                     # MC 계산 (python/mc.py)


# ============================================================
# 0. 그림 설정 — 건드리지 않아도 됩니다
# ============================================================

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 11,
    "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
})


# ============================================================
# 1. 바꿔 볼 수 있는 설정값  ← 여기를 바꿔 보세요
# ============================================================

MOCK = True                # True = 가짜 장비, False = 진짜 소스미터
MOCK_MODEL = "memory"      # "memory" (기억 있음) 또는 "resistor" (기억 없음)
K = 600                    # 입력 개수. 진짜 장비에서는 600개 × pulse 4개 × 50 ms ≈ 2분 + 통신 시간

# --- 진짜 장비일 때만 쓰는 값 (MOCK = False) ---
ADDR = "GPIB0::24::INSTR"
COMPLIANCE_A = 1e-5
DEVICE_ID = "dev01"
RUN_NAME = "mc_dev01"      # 결과 폴더 → runs\mc_dev01


# ============================================================
# 2. 입력 만들기 + 장비 설정
# ============================================================

U = mc_sequence(K)                     # 모양 (1, K): trial 1개 안에 입력 K개
cfg = json.loads((CODE / "python" / "config_example.json").read_text(encoding="utf-8"))
inst, enc = cfg["instrument"], cfg["encoding"]
M = len(enc["mask"])
if MOCK:
    inst["mock"]["model"] = MOCK_MODEL
    run_dir = CODE / "runs" / f"mc_mock_{MOCK_MODEL}"
    shutil.rmtree(run_dir, ignore_errors=True)     # mock 기록은 매번 새로
else:
    inst.update(addr=ADDR, compliance_A=COMPLIANCE_A)
    cfg["device"]["id"] = DEVICE_ID
    run_dir = CODE / "runs" / RUN_NAME
check_inputs(U, enc, inst["v_limit_V"])


# ============================================================
# 3. 측정: 입력 K개 = pulse K × 4개를 한 번에 (trial 1개)
# ============================================================

print(f"inputs     : {K} random values (0-1) -> {K * M} pulses, nominal {K * M * enc['theta_s'] / 60:.1f} min")
with open_smu(inst, mock=MOCK) as smu:
    print(f"instrument : {smu.idn}" + (f" (model: {MOCK_MODEL})" if MOCK else ""))
    smu.enable()
    S, done = run_trials(cfg, U, str(run_dir), smu_trial_fn(smu, enc), K * M, log=lambda m: None)
print(f"saved      : runs/{run_dir.name}")
X = S[0].reshape(K, M)                 # 입력마다 state 4개


# ============================================================
# 4. MC 계산 (python/mc.py)
# ============================================================
#
# r²(d): d걸음 전 입력을 지금 state로 맞힌 정도. 1 = 완벽, 0 = 전혀
# null_q95: 아무 관계 없는 무작위 목표로 같은 계산을 20번 했을 때 상위 5% 값
#           = "우연히도 이만큼은 나온다"
# MC_excess: r² 중 null_q95를 넘는 부분만 더한 것 = 우연을 뺀 기억
# ============================================================

res = memory_capacity(X, U[0])
print()
print("d (steps back)   r2")
for dd, r in enumerate(res["r2"], start=1):
    print(f"{dd:>14}   {r:.3f}")
print(f"\nnull_q95   : {res['null_q95']:.3f}  (chance level)")
print(f"MC         : {res['MC']:.2f}  (sum of r2)")
print(f"MC_excess  : {res['MC_excess']:.2f}  (only the part above chance)")


# ============================================================
# 5. 그래프: d마다 r²
# ============================================================

dd = np.arange(1, len(res["r2"]) + 1)
fig, ax = plt.subplots(figsize=(8, 4.0))
ax.bar(dd, res["r2"], color=["#2b59c3" if r > res["null_q95"] else "#c9cfd8" for r in res["r2"]], width=0.65)
ax.axhline(res["null_q95"], color="#c0392b", lw=1.2, ls="--", label=f"우연 기준 null_q95 = {res['null_q95']:.3f}")
ax.set_xticks(dd)
ax.set_ylim(0, 1.08)
ax.set_xlabel("몇 걸음 전 입력을 맞히나 (d)")
ax.set_ylabel("r²  (1 = 완벽)")
ax.set_title(f"MC_excess = {res['MC_excess']:.2f} ({'mock ' + MOCK_MODEL if MOCK else RUN_NAME}) · 파랑 = 우연보다 큼", loc="left")
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*ax.get_legend_handles_labels(), loc="lower center")

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
