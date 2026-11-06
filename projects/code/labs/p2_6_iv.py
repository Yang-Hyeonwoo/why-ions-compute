# ============================================================
# P2 실습 6 · I–V sweep: 전압을 조금씩 바꾸며 전류 재기
#
# 전체 과정:
#
#   전압을 0 → +VMAX → 0 → −VMAX → 0 으로 STEP씩 바꾼다
#   한 단계에 DWELL초 머물고, 단계 끝의 전류를 읽는다
#         ↓
#   그래프 ① 전압–전류 (올라갈 때 / 내려올 때 색을 달리)
#          ② 시간에 따른 전류
#         ↓
#   두 선이 겹치면 → 지금 전압만 따르는 소자 (resistor처럼)
#   두 선이 벌어져 고리(hysteresis)가 되면 → 느리게 따라오는 무언가가 있다
#
# 진짜 소자에서는 VMAX를 0.2 V부터 시작해 조금씩 넓히고,
# 넓힐 때마다 0.2 V를 다시 재서 COMPARE로 겹쳐 본다 (소자가 변했나?).
# ============================================================

import json
import sys
import types
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from smu import open_smu                           # 장비(진짜 또는 mock)를 여는 함수
from a1_tests import Recorder, run_iv              # I–V sweep 순서 (python/a1_tests.py)
from common import atomic_save_npz


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

MOCK = True                 # True = 가짜 장비, False = 진짜 소스미터
MOCK_MODEL = "memory"       # mock 안의 가짜 소자: "memory", "series_rc", "resistor"
VMAX = 0.2                  # 가장 큰 전압 (V). 진짜 소자는 0.2부터 조금씩
STEP = 0.02                 # 한 단계에 바꾸는 전압 (V)
DWELL = 0.05                # 한 단계에 머무는 시간 (초). 작을수록 빠른 sweep
NAME = "iv_mock"            # 저장 이름 → runs\iv_mock.npz
COMPARE = []                # ①에 같이 그릴 예전 결과. 예: ["iv_dev01_02"]

# --- 진짜 장비일 때만 쓰는 값 (MOCK = False) ---
ADDR = "GPIB0::24::INSTR"
COMPLIANCE_A = 1e-5         # 전류 제한. 처음 재는 소자는 작게
DEVICE_ID = "dev01"


# ============================================================
# 2. 장비 설정
# ============================================================

cfg = json.loads((CODE / "python" / "config_example.json").read_text(encoding="utf-8"))
inst = cfg["instrument"]
if MOCK:
    inst["mock"]["model"] = MOCK_MODEL
else:
    inst.update(addr=ADDR, compliance_A=COMPLIANCE_A)
    cfg["device"]["id"] = DEVICE_ID
out = CODE / "runs" / NAME
out.parent.mkdir(exist_ok=True)
if not MOCK and out.with_suffix(".npz").exists():
    raise SystemExit(f"runs/{NAME}.npz가 이미 있습니다. 진짜 측정은 덮어쓰지 않도록 NAME을 바꾸세요.")


# ============================================================
# 3. 측정 (python/a1_tests.py의 run_iv)
# ============================================================

a = types.SimpleNamespace(vmax=VMAX, step=STEP, dwell=DWELL)
with open_smu(inst, mock=MOCK) as smu:              # 요청 전압이 상한(1.0 V)을 넘으면 거부
    print(f"instrument : {smu.idn}" + (f" (model: {MOCK_MODEL})" if MOCK else ""))
    smu.enable()
    rec = Recorder(smu)
    summary = run_iv(rec, a)
d = rec.arrays()
atomic_save_npz(str(out) + ".npz", **d, **{"sum_" + k: v for k, v in summary.items()})
V, I = summary["V_steps"], summary["I_end"] * 1e6
print(f"saved      : runs/{NAME}.npz ({len(d['t'])} reads, {int(d['compliance'].sum())} hit compliance)")
print(f"steps      : {len(V)} (0 -> +{VMAX:g} -> 0 -> -{VMAX:g} -> 0 V)")
print(f"current    : min {I.min():+.3f} uA, max {I.max():+.3f} uA")

# 같은 전압에서 '올라갈 때'와 '내려올 때' 전류 차이 = 고리의 벌어짐
up = np.r_[True, np.diff(V) > 0]                     # 전압이 커지는 단계
gap_at = []
for v in np.unique(np.round(V[V > 0], 6)):
    i_up = I[up & np.isclose(V, v)]
    i_dn = I[~up & np.isclose(V, v) & (np.arange(len(V)) < len(V) // 2)]
    if len(i_up) and len(i_dn):
        gap_at.append((v, i_up[0] - i_dn[0]))
v_big, g_big = max(gap_at, key=lambda x: abs(x[1]))
print(f"loop width : largest at +{v_big:g} V, up - down = {round(g_big, 3) + 0.0:+.3f} uA")


# ============================================================
# 4. 그래프 ① 전압–전류   ② 시간에 따른 전류
# ============================================================

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6.4), gridspec_kw={"height_ratios": [1.5, 1]})
ax1.axhline(0, color="0.85", lw=0.8)
ax1.axvline(0, color="0.85", lw=0.8)
ax1.plot(V[up], I[up], "o", color="#2b59c3", ms=5, label="전압을 올릴 때")
ax1.plot(V[~up], I[~up], "s", color="#e08a3c", ms=5, label="전압을 내릴 때")
ax1.plot(V, I, "-", color="0.6", lw=0.8)
colors = ["#2f9e6e", "#8e5bc4", "#7a7f87", "#c0392b"]
for c, other in zip(colors, COMPARE):
    p = CODE / "runs" / f"{other}.npz"
    if not p.exists():
        print(f"(COMPARE: runs/{other}.npz가 없어 건너뜀)")
        continue
    with np.load(p) as o:
        ax1.plot(o["sum_V_steps"], o["sum_I_end"] * 1e6, "--", color=c, lw=1.5, label=other)
ax1.set_xlabel("전압 (V)")
ax1.set_ylabel("단계 끝 전류 (µA)")
ax1.set_title(f"① I–V ({'mock ' + MOCK_MODEL if MOCK else NAME}, 한 단계 {DWELL:g} s)", loc="left")

ax2.plot(d["t"], d["I"] * 1e6, color="0.45", lw=1)
ax2.set_xlabel("시간 (s)")
ax2.set_ylabel("전류 (µA)")
ax2.set_title("② 시간에 따른 전류 (계속 읽은 값)", loc="left")
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.legend(*ax1.get_legend_handles_labels(), loc="lower center", ncol=4, fontsize=9.5)

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
