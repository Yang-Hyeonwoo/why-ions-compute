# ============================================================
# P2 실습 7 · paired-pulse: 같은 pulse를 두 번, 간격을 바꿔 가며
#
# 전체 과정:
#
#   GAPS의 간격마다:
#     0 V로 5초 기다리기 (흔적 지우기)
#       → pulse 1: VP를 TP초 → 끝 전류 I1
#       → 0 V로 GAP초
#       → pulse 2: 같은 VP를 TP초 → 끝 전류 I2
#         ↓
#   ratio = I2 / I1
#     1이면 첫 pulse의 흔적이 없다 (두 번째가 첫 번째와 똑같다)
#     1보다 크거나 작으면 간격 동안 흔적이 남아 있었다
#         ↓
#   그래프 ① 간격에 따른 ratio   ② 가장 짧은 간격의 전류 기록
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
from a1_tests import Recorder, run_ppf             # paired-pulse 순서 (python/a1_tests.py)
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
VP, TP = 0.5, 0.2           # pulse 높이 (V), 길이 (초)
GAPS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5]   # 두 pulse 사이 간격 (초)
NAME = "ppf_mock"           # 저장 이름 → runs\ppf_mock.npz
COMPARE = []                # ①에 같이 그릴 예전 결과. 예: ["ppf_rc"]

# --- 진짜 장비일 때만 쓰는 값 (MOCK = False) ---
ADDR = "GPIB0::24::INSTR"
COMPLIANCE_A = 1e-5
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
# 3. 측정 (python/a1_tests.py의 run_ppf)
# ============================================================

a = types.SimpleNamespace(vp=VP, tp=TP, gaps=GAPS, settle=5.0)
with open_smu(inst, mock=MOCK) as smu:
    print(f"instrument : {smu.idn}" + (f" (model: {MOCK_MODEL})" if MOCK else ""))
    smu.enable()
    rec = Recorder(smu)
    summary = run_ppf(rec, a)
d = rec.arrays()
atomic_save_npz(str(out) + ".npz", **d, **{"sum_" + k: v for k, v in summary.items()})
print(f"saved      : runs/{NAME}.npz ({len(d['t'])} reads, {int(d['compliance'].sum())} hit compliance)")
print()
print("gap (s)   I1 (uA)   I2 (uA)   ratio I2/I1")
for g, i1, i2, r in zip(summary["gap"], summary["I1"], summary["I2"], summary["ratio"]):
    print(f"{g:>7g}   {i1 * 1e6:7.3f}   {i2 * 1e6:7.3f}   {r:8.3f}")


# ============================================================
# 4. 그래프 ① 간격에 따른 ratio   ② 가장 짧은 간격의 전류
# ============================================================

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6.2), gridspec_kw={"height_ratios": [1.3, 1]})
ax1.axhline(1, color="0.6", lw=1, ls=":")
ax1.plot(GAPS, summary["ratio"], "o-", color="#2b59c3", lw=2, ms=7, label=NAME)
colors = ["#e08a3c", "#2f9e6e", "#8e5bc4", "#7a7f87"]
for c, other in zip(colors, COMPARE):
    p = CODE / "runs" / f"{other}.npz"
    if not p.exists():
        print(f"(COMPARE: runs/{other}.npz가 없어 건너뜀)")
        continue
    with np.load(p) as o:
        ax1.plot(o["sum_gap"], o["sum_ratio"], "s--", color=c, lw=1.6, ms=6, label=other)
ax1.set_xscale("log")
ax1.set_xticks(GAPS, [f"{g:g}" for g in GAPS])
ax1.minorticks_off()
ax1.set_xlabel("두 pulse 사이 간격 (s, 로그 눈금)")
ax1.set_ylabel("ratio = I2 / I1")
ax1.set_title("① 간격이 짧을수록 1에서 멀어지면, 흔적이 남아 있던 것 (점선 = 1)", loc="left")

# 가장 짧은 간격의 묶음만 잘라 보기: seg 이름이 pulse1 → gap → pulse2 인 첫 덩어리
names = list(d["seg_names"])
k1, k2 = names.index("pulse1"), names.index("pulse2")
s = np.where(d["seg"] == k1)[0][0]
e = np.where(d["seg"] == k2)[0]
e = e[e > s]
e_end = e[np.r_[np.diff(e) > 1, True]][0]          # 첫 pulse2 덩어리의 끝
sl = slice(max(0, s - 5), e_end + 6)
t0 = d["t"][s]
ax2.plot((d["t"][sl] - t0) * 1000, d["I"][sl] * 1e6, color="0.45", lw=1.2)
i1_idx = np.where(d["seg"] == k1)[0]
i1_end = i1_idx[np.r_[np.diff(i1_idx) > 1, True]][0]
ax2.plot([(d["t"][i1_end] - t0) * 1000, (d["t"][e_end] - t0) * 1000],
         [d["I"][i1_end] * 1e6, d["I"][e_end] * 1e6], "o", color="#c0392b", ms=8)
ax2.set_xlabel(f"시간 (ms, pulse 1의 첫 읽기 = 0) · 간격 {GAPS[0]:g} s")
ax2.set_ylabel("전류 (µA)")
ax2.set_title("② 가장 짧은 간격: 빨간 점 = I1, I2 (pulse 끝 전류)", loc="left")
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.legend(*ax1.get_legend_handles_labels(), loc="lower center", ncol=4, fontsize=9.5)

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
