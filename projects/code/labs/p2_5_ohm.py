# ============================================================
# P2 실습 5 · 진짜 소스미터와 첫 대화: 1 MΩ resistor로 옴의 법칙 확인
#
# 전체 과정:
#
#   (MOCK = False일 때) PC에 연결된 장비 주소 목록 보기 (NI-VISA)
#         ↓
#   장비 열기 → "너는 누구니?" (*IDN?) 답 보기
#         ↓
#   전압을 0, 0.1, … 0.5 V로 하나씩 HOLD_MS 동안 걸고, 끝 전류 읽기
#         ↓
#   답을 아는 부품(1 MΩ)이므로 전류 = 전압 ÷ 1,000,000 이어야 한다
#   맞으면 장비·케이블·설정을 믿고 다음 단계로
#         ↓
#   그래프 ① 전압–전류 (재 본 점 vs 예상 선)
#          ② 전압 하나를 걸 때 PC가 전류를 읽은 시각 (실제 pulse 길이)
# ============================================================

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from smu import open_smu                           # 장비(진짜 또는 mock)를 여는 함수


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

MOCK = True                       # True = 가짜 장비 (안의 부품은 resistor), False = 진짜 소스미터
ADDR = "GPIB0::24::INSTR"         # NI MAX에서 찾은 장비 주소 (MOCK = False일 때)
COMPLIANCE_A = 1e-5               # 전류 제한 10 µA (1 MΩ에 1 V여도 1 µA라 충분한 여유)
R_OHM = 1e6                       # 물린 resistor 값 (Ω). 1 MΩ = 1,000,000 Ω
VOLTS = [0, 0.1, 0.2, 0.3, 0.4, 0.5]   # 걸어 볼 전압 (V)
HOLD_MS = 50                      # 전압 하나를 걸고 있는 시간 (ms). P2의 pulse 길이와 같게


# ============================================================
# 2. (진짜 장비일 때) PC가 보는 장비 주소 목록
# ============================================================

if not MOCK:
    import pyvisa
    print("VISA resources :", pyvisa.ResourceManager().list_resources())
    # 예: ('ASRL1::INSTR', 'GPIB0::24::INSTR') → 'GPIB0::…'가 소스미터. ASRL1은 PC의 직렬 단자

cfg = json.loads((CODE / "python" / "config_example.json").read_text(encoding="utf-8"))
inst = cfg["instrument"]
inst.update(addr=ADDR, compliance_A=COMPLIANCE_A)
inst["mock"].update(model="resistor", R=R_OHM)    # mock일 때 안에 넣을 가짜 부품


# ============================================================
# 3. 전압을 하나씩 걸고 끝 전류 읽기
# ============================================================
#
# smu.hold(v, 초): 전압 v를 걸고, 시간이 다 될 때까지 전류를 계속 읽는다.
# 돌려받는 것: 읽을 때마다 {시각, 전압, 전류, compliance 걸림?}의 목록.
# ============================================================

rows, first_hold = [], None
with open_smu(inst, mock=MOCK) as smu:            # with 문이 끝나면 0 V → 출력 OFF (자동)
    print(f"instrument     : {smu.idn}")
    smu.enable()                                  # 이때부터 전압이 걸린다
    for v in VOLTS:
        recs = smu.hold(v, HOLD_MS / 1000)
        rows.append((v, recs[-1]["I"], any(r["compliance"] for r in recs)))
        if first_hold is None and v > 0:
            first_hold = recs                     # 그래프 ②에 쓸, 0이 아닌 첫 전압의 읽기 기록

V = np.array([r[0] for r in rows])
I = np.array([r[1] for r in rows])


# ============================================================
# 4. 숫자로 확인: 잰 전류 vs 예상 전류 (= 전압 ÷ R)
# ============================================================

print()
print("V set (V)   I measured (uA)   I expected V/R (uA)   compliance")
for v, i, c in rows:
    print(f"{v:>9.2f}   {i * 1e6:>15.3f}   {v / R_OHM * 1e6:>19.3f}   {'HIT' if c else '-':>10}")
slope = np.polyfit(V, I, 1)[0]                     # 전류–전압 직선의 기울기 = 1/R
print(f"\nR from slope   : {1 / slope / 1e6:.3f} MOhm  (expected {R_OHM / 1e6:g} MOhm)")

t_set = first_hold[0]["t_set"]
t_reads = np.array([r["t_host"] for r in first_hold]) - t_set
print(f"reads in one {HOLD_MS} ms hold : {len(t_reads)}  at {np.round(t_reads * 1000).astype(int).tolist()} ms")
print(f"actual hold    : {t_reads[-1] * 1000:.0f} ms (set {HOLD_MS} ms)")


# ============================================================
# 5. 그래프 ① 전압–전류   ② 전류를 읽은 시각
# ============================================================

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.9), gridspec_kw={"width_ratios": [1.15, 1]})
vv = np.linspace(0, max(VOLTS), 50)
ax1.plot(vv, vv / R_OHM * 1e6, "-", color="0.65", lw=2, label=f"예상: V ÷ {R_OHM / 1e6:g} MΩ")
ax1.plot(V, I * 1e6, "o", color="#2b59c3", ms=8, label="재 본 값")
ax1.set_xlabel("건 전압 (V)")
ax1.set_ylabel("전류 (µA)")
ax1.set_title("① 전압–전류: 점이 회색 선 위에", loc="left")

ax2.axvspan(0, HOLD_MS, color="#eef3fb", zorder=0)
ax2.axvline(HOLD_MS, color="#e08a3c", lw=1.5, ls="--")
ax2.plot(t_reads * 1000, np.zeros_like(t_reads), "o", color="#c0392b", ms=9)
ax2.set_xlim(-5, max(HOLD_MS, t_reads[-1] * 1000) * 1.3)
ax2.set_ylim(-1, 1)
ax2.set_yticks([])
ax2.spines["left"].set_visible(False)
ax2.set_xlabel("전압을 건 뒤 시간 (ms)")
ax2.set_title(f"② 읽은 시각 {len(t_reads)}번 → 실제 {t_reads[-1] * 1000:.0f} ms", loc="left")
fig.tight_layout(rect=(0, 0.1, 1, 1))
h, l = ax1.get_legend_handles_labels()
h2 = [plt.Line2D([], [], color="#c0392b", marker="o", ls="none"),
      plt.Line2D([], [], color="#e08a3c", ls="--")]
fig.legend(h + h2, l + ["전류를 읽은 순간", f"설정 길이 {HOLD_MS} ms"], loc="lower center", ncol=4, fontsize=9.5)

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
