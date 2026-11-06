# ============================================================
# P2 실습 4 · 쓰기–쉬기–읽기: 흔적이 쉬는 동안 얼마나 남나
#
# 전체 과정:
#
#   GAPS의 쉬기 시간마다, + 쓰기와 − 쓰기를 한 번씩:
#
#     0 V로 5초 기다리기 (settle: 처음 상태로 가라앉히기)
#       → 쓰기: ±0.5 V를 1초 (흔적 남기기)
#       → 쉬기: 0 V를 GAP초 (흔적이 사라질 시간 주기)
#       → 읽기: 작은 0.05 V를 0.5초 (전류로 흔적 보기)
#         ↓
#   + 쓰기 뒤와 − 쓰기 뒤의 '읽기 전류'가 다르면 → 흔적이 남아 있다
#   쉬기가 길어질수록 그 차이가 줄어들면 → 흔적이 사라지는 중
#         ↓
#   그래프 ① 전체 전압·전류  ② 쉬기마다 읽기 전류 (+ 쓰기 vs − 쓰기)
#          ③ 흔적의 크기 vs 쉬기 시간
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
from a1_tests import Recorder, run_wrr             # 쓰기–쉬기–읽기 순서 (python/a1_tests.py)
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
MOCK_MODEL = "series_rc"    # mock 안의 가짜 부품: "series_rc" (R과 C를 일렬로), "resistor", "memory"
GAPS = [0.1, 1, 5]          # 쉬기 시간 (초)
VW, TW = 0.5, 1.0           # 쓰기 전압 (V), 쓰기 시간 (초)
VR, TR = 0.05, 0.5          # 읽기 전압 (V), 읽기 시간 (초)
NAME = "wrr_rc_mock"        # 저장 이름 → runs\wrr_rc_mock.npz
COMPARE = []                # ③에 같이 그릴 예전 결과 이름들. 예: ["wrr_rc_real", "wrr_r1M"]

# --- 진짜 장비일 때만 쓰는 값 (MOCK = False) ---
ADDR = "GPIB0::24::INSTR"   # NI MAX에서 찾은 장비 주소
COMPLIANCE_A = 1e-5         # 전류 제한 (A)
DEVICE_ID = "R1M_C1u_test"  # 지금 잰 시료 이름


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
# 3. 측정 (python/a1_tests.py의 run_wrr)
# ============================================================

a = types.SimpleNamespace(gaps=GAPS, vw=VW, tw=TW, vr=VR, tr=TR, settle=5.0)
with open_smu(inst, mock=MOCK) as smu:
    print(f"instrument : {smu.idn}" + (f" (model: {MOCK_MODEL})" if MOCK else ""))
    smu.enable()
    rec = Recorder(smu)                      # 읽은 값을 모두 적어 두는 공책
    summary = run_wrr(rec, a)                # 쓰기–쉬기–읽기를 GAPS × (+, −) 번
d = rec.arrays()
atomic_save_npz(str(out) + ".npz", **d, **{"sum_" + k: v for k, v in summary.items()})
print(f"saved      : runs/{NAME}.npz ({len(d['t'])} reads, {int(d['compliance'].sum())} hit compliance)")


# ============================================================
# 4. 숫자로 보기
# ============================================================
#
# I_read_first = 읽기를 시작한 직후의 전류
# I_read_late  = 읽기 후반(뒤쪽 절반)의 평균 전류
# trace        = (+ 쓰기 뒤 I_read_first) − (− 쓰기 뒤 I_read_first)
#                0이면 쓰기 방향을 구별할 흔적이 없다
# ============================================================

gap, pol = summary["gap"], summary["polarity"]
first, late = summary["I_read_first"] * 1e6, summary["I_read_late"] * 1e6
print()
print("rest (s)  write   I_read_first (uA)   I_read_late (uA)")
for g, p, f, l in zip(gap, pol, first, late):
    print(f"{g:>8g}  {'+' if p > 0 else '-'}{VW:g} V   {f:>12.3f}        {l:>12.3f}")
trace = first[pol > 0] - first[pol < 0]
print()
print("rest (s)   trace = (+write) - (-write)  (uA)")
for g, tr in zip(gap[pol > 0], trace):
    print(f"{g:>8g}   {tr:+.3f}")


# ============================================================
# 5. 그래프 ① 전체 전압·전류
# ============================================================

read_k = list(d["seg_names"]).index("read")
is_read = d["seg"] == read_k
fig, ax = plt.subplots(2, 1, figsize=(8, 5.0), sharex=True)
ax[0].plot(d["t"], d["V_set"], color="#2b59c3", lw=1)
ax[0].set_ylabel("건 전압 (V)")
ax[0].set_title(f"① 전체 기록 ({'mock ' + MOCK_MODEL if MOCK else NAME}) · 빨강 = 읽기 구간", loc="left")
ax[1].plot(d["t"], d["I"] * 1e6, color="0.45", lw=1)
ax[1].plot(d["t"][is_read], d["I"][is_read] * 1e6, ".", color="#c0392b", ms=3)
ax[1].set_ylabel("전류 (µA)")
ax[1].set_xlabel("시간 (s)")
fig.tight_layout()


# ============================================================
# 6. 그래프 ② 쉬기마다 읽기 전류  ③ 흔적 vs 쉬기 시간
# ============================================================

# 읽기 구간을 하나씩 잘라 낸다 (seg 번호가 'read'인 줄이 이어지는 덩어리)
starts = np.where(is_read & ~np.r_[False, is_read[:-1]])[0]
pieces = []
for s in starts:
    e = s
    while e + 1 < len(is_read) and is_read[e + 1]:
        e += 1
    pieces.append((d["t"][s:e + 1] - d["t"][s], d["I"][s:e + 1] * 1e6))

n = len(GAPS)
fig2 = plt.figure(figsize=(8, 6.4))
gs = fig2.add_gridspec(2, n, height_ratios=[1, 1.1], hspace=0.75, wspace=0.2)
ylo = min(p[1].min() for p in pieces)
yhi = max(p[1].max() for p in pieces)
pad = 0.1 * (yhi - ylo + 1e-12)
for j, g in enumerate(GAPS):
    axj = fig2.add_subplot(gs[0, j])
    tp, ip = pieces[2 * j]          # + 쓰기 뒤 (run_wrr 순서: 쉬기마다 +, −)
    tm, im = pieces[2 * j + 1]      # − 쓰기 뒤
    axj.plot(tp, ip, "-", color="#2b59c3", lw=2, label=f"+{VW:g} V 쓰기 뒤")
    axj.plot(tm, im, "--", color="#e08a3c", lw=2, label=f"-{VW:g} V 쓰기 뒤")
    axj.axhline(0, color="0.8", lw=0.8)
    axj.set_ylim(ylo - pad, yhi + pad)
    axj.set_title(f"쉬기 {g:g} s", loc="left", fontsize=10.5)
    axj.set_xticks([0, TR / 2], ["0", f"{TR / 2:g}"])
    axj.set_xlabel("읽기 시작 뒤 (s)", fontsize=9.5)
    if j == 0:
        axj.set_ylabel("읽기 전류 (µA)")
    else:
        axj.set_yticklabels([])
fig2.text(0.02, 0.975, "② 쉬기 시간마다 읽기 전류: 두 선이 갈라져 있으면 흔적이 남은 것", fontsize=11.5, va="top")

ax3 = fig2.add_subplot(gs[1, :])
ax3.axhline(0, color="0.75", lw=1)
ax3.plot(gap[pol > 0], trace, "o-", color="#2b59c3", lw=2, ms=7, label=NAME)
colors = ["#e08a3c", "#2f9e6e", "#8e5bc4", "#7a7f87"]
for c, other in zip(colors, COMPARE):
    p = CODE / "runs" / f"{other}.npz"
    if not p.exists():
        print(f"(COMPARE: runs/{other}.npz가 없어 건너뜀)")
        continue
    with np.load(p) as o:
        og, op, of = o["sum_gap"], o["sum_polarity"], o["sum_I_read_first"] * 1e6
    ax3.plot(og[op > 0], of[op > 0] - of[op < 0], "s--", color=c, lw=1.6, ms=6, label=other)
ax3.set_xscale("log")
ax3.set_xticks(GAPS, [f"{g:g}" for g in GAPS])
ax3.minorticks_off()
ax3.set_xlabel("쉬기 시간 (s, 로그 눈금)")
ax3.set_ylabel("흔적 (µA)\n(+쓰기) - (-쓰기)")
ax3.set_title("③ 흔적의 크기: 0에 가까워지면 흔적이 사라진 것", loc="left")
fig2.subplots_adjust(left=0.13, right=0.98, top=0.88, bottom=0.2)
h1, l1 = fig2.axes[0].get_legend_handles_labels()
h3, l3 = ax3.get_legend_handles_labels()
fig2.legend(h1 + h3, l1 + l3, loc="lower center", ncol=4, fontsize=9.5)

plt.show()   # 그림 창 두 개를 모두 닫으면 프로그램이 끝납니다.
