# ============================================================
# P3 실습 5 · board로 소자 데이터 모으기 (처음엔 mock board)
#
# 전체 과정:
#
#   실습 4의 입력 80줄(task.npz)과 설정 파일 읽기
#         ↓
#   입력 한 줄씩 board에 보내기:  "B,번호,12,u1,…,u12"
#         ↓
#   board(B5_collect)가 2초 쉬고 → pulse 48개를 걸고 → pulse 끝마다 전류·전압을 읽어
#   S·V·P·R·Q 다섯 줄로 돌려준다
#   (MOCK = True면 컴퓨터 속 'mock board'가 같은 다섯 줄을 만든다)
#         ↓
#   trial 하나 끝날 때마다 runs/…/b_dev01 폴더에 저장 (끊겨도 이어서)
#         ↓
#   [그림 1] trial 하나: 건 전압과 읽은 전류   [그림 2] class별 평균 전류
#
# 진짜 측정: board에 B5_collect를 올리고 Serial Monitor를 닫은 뒤
#            MOCK = False, PORT = 내 COM 번호, 처음엔 LIMIT = 10.
# ============================================================

import shutil
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

from common import load_json                        # 설정 파일 읽기
from measure_seq import check_inputs, pulse_plan, run_trials   # 범위 검사, pulse 높이, trial마다 저장
from smu import MockSMU                             # 가짜 소자 (mock board 안에서 씀)


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

MOCK = True          # True: mock board / False: 진짜 board (B5_collect)
PORT = "COM5"        # 진짜 board의 COM 번호
LIMIT = None         # None = 남은 trial 전부, 10 = 이번에는 10개만
SHOW_TRIAL = 0       # 그림 1에서 볼 trial 번호

# MOCK에 따라 정해지는 파일 위치 (실습 4와 같은 규칙)
CONFIG = "config_board_example.json" if MOCK else "config_board.json"
BASE = CODE / "runs" / ("p3_mock" if MOCK else "p3")
RUN_DIR = BASE / "b_dev01"


# ============================================================
# 2. 설정·입력 읽기
# ============================================================

cfg = load_json(CODE / "python" / CONFIG)
enc = cfg["encoding"]
task = np.load(BASE / "task.npz")                  # 실습 4가 만든 파일
U, y = task["U"], task["y"]
check_inputs(U, enc, cfg["instrument"]["v_limit_V"])

L, M = U.shape[1], len(enc["mask"])
NF = L * M                                         # trial 하나의 state 수 = 48
per_trial_s = enc["rest_s"] + NF * enc["theta_s"]   # 2 + 48 × 0.05 = 4.4초
theta_us = int(round(enc["theta_s"] * 1e6))


# ============================================================
# 3. mock board: B5_collect firmware가 하는 일을 컴퓨터 안에서 흉내
# ============================================================
#
#   진짜 board                          mock board
#   DAC로 전압 걸기                     MockSMU(가짜 소자)에 전압 걸기
#   pulse 끝에 TIA·ADC로 전류 읽기      가짜 소자의 전류를 nA로
#   A0−A1로 실제 소자 전압 읽기         건 전압 − 전류 × R_lim (R_lim에서 떨어지는 만큼)
#   micros()로 pulse 시간 재기          가상 시계라 정확히 50 ms
#
#   가짜 소자(model "memory")는 전압을 받으면 전도도가 천천히 오르고 0 V에서
#   τ = 0.5초로 돌아오는 '장난감'이다. 진짜 소자의 성능과는 상관없다.
# ============================================================

class MockBoard:
    def __init__(self):
        self.dev = MockSMU(model="memory", R=1e6, tau=0.5, compliance_A=1.0,
                           v_limit_V=cfg["instrument"]["v_limit_V"], read_dt=0.005)
        self.dev.enable()
        self.R_lim = cfg["instrument"]["R_lim_ohm"]
        self.R_meas = cfg["instrument"]["R_meas_ohm"]

    def measure_trial(self, n, u_row):
        self.dev.reseed(n)                              # 같은 trial은 같은 잡음
        self.dev.hold(0.0, enc["rest_s"])               # 0 V로 쉬기 (rest)
        S, V, sat = [], [], 0
        for v in pulse_plan(u_row, enc):                # pulse 48개
            last = self.dev.hold(v, enc["theta_s"])[-1]  # pulse 끝의 읽기
            i_A = last["I"]
            S.append(i_A * 1e9)                         # 전류 (nA) = state
            V.append(v - i_A * self.R_lim)              # 실제 소자 전압
            sat += abs(i_A * self.R_meas) > 1.5         # TIA 출력이 1.5 V를 넘으면 포화로 셈
        P = np.full(NF, theta_us)                       # 명령 유지 시간 (µs)
        return np.array(S), dict(I_nA=np.array(S), V_dev=np.array(V), period_us=P,
                                 read_end_us=P.copy(), saturated=np.array([sat]))


# ============================================================
# 4. trial마다 보내고 받고 저장 (measure_seq.run_trials)
# ============================================================
#
#   run_trials는 trial 하나가 끝날 때마다 checkpoint.npz를 새로 쓴다.
#   중간에 끊겨도 같은 파일을 다시 Run 하면 남은 trial부터 이어서 한다 (책갈피).
#   mock은 매번 처음부터 (폴더를 지우고 시작).
# ============================================================

def short_log(msg):
    """trial 80줄을 다 찍지 않고 10개마다 한 줄"""
    if msg.startswith("trial"):
        k = int(msg.split("(")[1].split("/")[0])
        if k % 10 and k != len(U):
            return
    print(msg)

extra = {"y": y, "groups": task["groups"]}

if MOCK:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    print(f"(MOCK) {len(U)} trials, each {per_trial_s:.1f} s on a real board (mock: no waiting)")
    run_trials(cfg, U, str(RUN_DIR), MockBoard().measure_trial, NF, limit=LIMIT, log=short_log, extra=extra)
else:
    import serial                                   # pyserial
    from board_collect import board_trial_fn        # 진짜 board와 주고받는 규칙
    todo = len(U) if LIMIT is None else LIMIT
    print(f"{PORT}: up to {todo} trials x {per_trial_s:.1f} s = about {todo * per_trial_s / 60:.0f} min")
    with serial.Serial(PORT, 115200, timeout=per_trial_s * 2 + 5) as ser:
        ser.reset_input_buffer()
        run_trials(cfg, U, str(RUN_DIR), board_trial_fn(ser, L, NF, per_trial_s), NF,
                   limit=LIMIT, log=short_log, extra=extra)


# ============================================================
# 5. 저장된 것 읽어 보기
# ============================================================

ck = np.load(RUN_DIR / "checkpoint.npz")
S, done = ck["S"], ck["done"]
if not done[SHOW_TRIAL]:
    raise SystemExit(f"trial {SHOW_TRIAL}은 아직 안 쟀습니다.")
raw = np.load(RUN_DIR / "raw" / f"trial_{SHOW_TRIAL:05d}.npz")
cmd = np.array(pulse_plan(U[SHOW_TRIAL], enc))
end = slice(8 * M, L * M)                          # readout 칸 8–11 = pulse 32–47

print()
print(f"saved in        : {RUN_DIR.relative_to(CODE).as_posix()}  ({int(done.sum())}/{len(done)} trials)")
print(f"state range     : {np.nanmin(S):.0f} to {np.nanmax(S):.0f} nA")
print(f"V row (trial {SHOW_TRIAL}) : largest gap command - device = {np.max(cmd - raw['V_dev']) * 1000:.1f} mV (R_lim drop)")
print(f"saturated reads : {int(sum(np.load(f)['saturated'][0] for f in (RUN_DIR / 'raw').glob('*.npz')))}")
for c in (0, 1):
    rows = done & (y == c)
    print(f"class {c}: mean state in readout steps 8-11 = {S[rows][:, end].mean():.1f} nA  ({rows.sum()} trials)")


# ============================================================
# 6. 그림 1: trial 하나 — 건 전압과 읽은 전류
# ============================================================

k = np.arange(NF)
fig1, ax = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True)
ax[0].step(k, cmd, where="mid", color="0.6", lw=1.5, label="명령 전압")
ax[0].plot(k, raw["V_dev"], ".", color="#2b59c3", ms=6, label="pulse 끝 실제 소자 전압 (V 줄)")
ax[0].set_ylabel("V")
ax[0].set_title(f"trial {SHOW_TRIAL} (class {y[SHOW_TRIAL]}): pulse 48개", loc="left")
ax[1].plot(k, raw["I_nA"], "o-", color="#0e8a83", ms=4, lw=1, label="pulse 끝 전류 = state (S 줄)")
for a in ax:
    a.axvspan(8 * M - 0.5, L * M - 0.5, color="#d9962a", alpha=0.15, lw=0)
ax[1].text(8 * M, ax[1].get_ylim()[1], " readout 칸 8–11", va="top", fontsize=9.5, color="#a0661a")
ax[1].set_ylabel("nA")
ax[1].set_xlabel("pulse 번호 (칸 번호 × 4 + mask 번호)")
fig1.tight_layout(rect=(0, 0.08, 1, 1))
h0, l0 = ax[0].get_legend_handles_labels()
h1, l1 = ax[1].get_legend_handles_labels()
fig1.legend(h0 + h1, l0 + l1, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0), fontsize=9.5)


# ============================================================
# 7. 그림 2: class별 평균 state — 마지막 4칸에서도 벌어져 있나?
# ============================================================

fig2, ax2 = plt.subplots(1, 2, figsize=(8, 3.8), gridspec_kw={"width_ratios": [1.7, 1]})
colors = {0: "#2b59c3", 1: "#d9962a"}
for c in (0, 1):
    rows = done & (y == c)
    m, sd = S[rows].mean(0), S[rows].std(0)
    for a in ax2:                                   # 왼쪽 = 전체, 오른쪽 = readout 칸 크게
        a.plot(k, m, color=colors[c], lw=1.6, marker="o" if a is ax2[1] else None, ms=4,
               label=f"class {c} ({'early' if c == 0 else 'late'}) 평균")
        a.fill_between(k, m - sd, m + sd, color=colors[c], alpha=0.2, lw=0)
ax2[0].axvspan(8 * M - 0.5, L * M - 0.5, color="#d9962a", alpha=0.12, lw=0)
ax2[0].set_xlabel("pulse 번호")
ax2[0].set_ylabel("state (nA)")
ax2[0].set_title("class별 평균 state (띠 = 흩어진 정도)", loc="left")
ax2[1].set_xlim(8 * M - 0.5, L * M - 0.5)
ax2[1].set_ylim(np.nanmin(S[:, end]) - 30, np.nanmax(S[:, end]) + 30)
ax2[1].set_xlabel("pulse 번호 (readout 칸만)")
ax2[1].set_title("readout 칸 크게", loc="left")
fig2.tight_layout(rect=(0, 0.08, 1, 1))
fig2.legend(*ax2[0].get_legend_handles_labels(), loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.0))

plt.show()
