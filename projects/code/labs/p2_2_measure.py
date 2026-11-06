# ============================================================
# P2 실습 2 · 측정: pulse 48개를 걸고, pulse 끝 전류를 모은다
#
# 전체 과정:
#
#   실습 1이 저장한 시험 문제 (runs\task_p2.npz) 읽기
#         ↓
#   장비 열기: MOCK = True 이면 컴퓨터 속 가짜 장비(mock SMU)
#              MOCK = False 이면 진짜 소스미터 (P2.0R부터)
#         ↓
#   trial 하나마다:
#       0 V로 2초 쉬기 (rest: 앞 trial의 흔적 지우기)
#       → pulse 48개를 차례로 걸며 전류를 계속 읽기
#       → 각 pulse가 끝나기 직전의 전류 1개 = state (숫자 48개)
#         ↓
#   runs\<폴더> 에 저장 (실습 3의 readout이 읽음)
#         ↓
#   그래프 ① trial 하나의 전압·전류   ② class 0 / 1의 평균 state
# ============================================================

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from smu import open_smu                           # 장비(진짜 또는 mock)를 여는 함수
from measure_seq import check_inputs, run_trials, smu_trial_fn   # 측정 순서 (P2 공용)


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

MOCK = True                # True = 가짜 장비 (장비 없이 연습). False = 진짜 소스미터
MOCK_MODEL = "memory"      # mock 안의 가짜 소자: "memory" (기억 있음) 또는 "resistor" (기억 없음)
TASK_NAME = "task_p2"      # 실습 1이 만든 시험 문제 파일 이름
SHOW_TRIAL = 0             # 그래프 ①로 볼 trial 번호

# --- 진짜 장비일 때만 쓰는 값 (MOCK = False) ---
ADDR = "GPIB0::24::INSTR"  # NI MAX에서 찾은 장비 주소
COMPLIANCE_A = 1e-5        # 전류 제한 10 µA: 이보다 큰 전류는 장비가 막음
DEVICE_ID = "R1M_test"     # 지금 잰 시료 이름 (기록에 남음)
RUN_NAME = "r1M"           # 결과 폴더 이름 → runs\r1M  (시료·조건마다 새 이름)
LIMIT = None               # 처음 몇 trial만 잴지. 예: 3. None = 전부


# ============================================================
# 2. 측정 조건 (config_example.json) + 위 설정값 반영
# ============================================================

cfg = json.loads((CODE / "python" / "config_example.json").read_text(encoding="utf-8"))
inst, enc = cfg["instrument"], cfg["encoding"]
if MOCK:
    inst["mock"]["model"] = MOCK_MODEL
    run_dir = CODE / "runs" / f"mock_{MOCK_MODEL}"
    # mock 기록은 몇 초면 다시 만들 수 있으므로 매번 지우고 새로 잰다.
    # (진짜 측정 기록은 절대 지우지 않는다. 아래 run_trials가 이어서 잰다.)
    shutil.rmtree(run_dir, ignore_errors=True)
else:
    inst["addr"] = ADDR
    inst["compliance_A"] = COMPLIANCE_A
    cfg["device"]["id"] = DEVICE_ID
    run_dir = CODE / "runs" / RUN_NAME

task = np.load(CODE / "runs" / f"{TASK_NAME}.npz")
U, y = task["U"], task["y"]
check_inputs(U, enc, inst["v_limit_V"])          # 전압 상한(1.0 V)을 넘는 pulse가 없는지 먼저 확인
M = len(enc["mask"])
n_feat = U.shape[1] * M                           # 12칸 × 4 = 48


# ============================================================
# 3. 측정 (python/measure_seq.py의 run_trials)
# ============================================================
#
# trial 하나가 끝날 때마다 바로 파일로 저장한다.
# 진짜 장비에서 중간에 멈춰도(케이블 빠짐, Ctrl+C) 같은 파일을 다시 ▷ 하면
# 이미 잰 trial은 건너뛰고 이어서 잰다 (설정이 바뀌었으면 섞이지 않게 거부).
# ============================================================

def log(msg):
    """trial 10개마다 한 줄만 찍기 (40줄이 다 찍히면 읽기 어려워서)"""
    if msg.startswith("trial"):
        k = int(msg.split("(")[1].split("/")[0])
        if k % 10 and k != len(U):
            return
    print(" ", msg)

nominal = len(U) * (enc["rest_s"] + n_feat * enc["theta_s"])
print("=" * 56)
print(f"{len(U)} trials x {n_feat} pulses, nominal time {nominal / 60:.1f} min")
with open_smu(inst, mock=MOCK) as smu:
    print(f"instrument : {smu.idn}" + (f" (model: {MOCK_MODEL})" if MOCK else ""))
    smu.enable()                                  # 이때부터 전압이 걸린다
    S, done = run_trials(cfg, U, str(run_dir), smu_trial_fn(smu, enc), n_feat,
                         limit=LIMIT, log=log, extra={"y": y, "groups": task["groups"]})
print(f"saved      : runs/{run_dir.name}  ({done.sum()}/{len(done)} trials)")
print("=" * 56)


# ============================================================
# 4. 숫자로 보기: 마지막 4칸에서 class 0과 1의 state가 다른가?
# ============================================================
#
# state = pulse 끝 전류. 마지막 4칸(8–11)의 입력은 두 class가 똑같다.
# 그런데도 전류가 다르면, 그 차이는 '앞에서 받은 입력의 흔적'에서 온 것.
# 실습 3의 readout은 바로 이 차이를 써서 답을 맞힌다.
# ============================================================

ok = done
mean0 = S[ok & (y == 0)].mean(0) * 1e6           # class 0 평균 (µA)
mean1 = S[ok & (y == 1)].mean(0) * 1e6
step0 = mean0.reshape(-1, M).mean(1)             # 칸마다 pulse 4개 평균
step1 = mean1.reshape(-1, M).mean(1)
print()
print("mean state in the last 4 steps (uA, average of 4 pulses)")
print("step   class 0   class 1   1 minus 0")
for s in range(8, 12):
    diff = round(step1[s] - step0[s], 3) + 0.0       # + 0.0: -0.000이 0.000으로 찍히게
    print(f"{s:>4}   {step0[s]:7.3f}   {step1[s]:7.3f}   {diff:+8.3f}")


# ============================================================
# 5. 그래프 ① trial 하나: 건 전압과 흐른 전류
# ============================================================

k = SHOW_TRIAL
with np.load(run_dir / "raw" / f"trial_{k:05d}.npz") as d:
    t, v, cur, p = d["t_host"] - d["t_host"][0], d["V_set"], d["I"] * 1e6, d["pulse"]
ends = [np.where(p == j)[0][-1] for j in range(n_feat)]          # pulse마다 마지막 읽기
t_start = t[np.where(p == 0)[0][0]]                              # 첫 pulse 시작 = 쉬기 끝
zone = (t[np.where(p == 8 * M)[0][0]], t[-1])                   # 마지막 4칸 = pulse 32–47

fig, ax = plt.subplots(2, 1, figsize=(8, 5.6), sharex=True)
for a in ax:
    a.axvspan(*zone, color="#fdf0c2", zorder=0)
    a.axvspan(0, t_start, color="0.93", zorder=0)
ax[0].step(t, v, where="post", color="#2b59c3", lw=1.2)
ax[0].set_ylabel("건 전압 (V)")
ax[0].set_ylim(-0.05, 1.0)
ax[0].set_title(f"① trial {k} (class {y[k]}) · 회색 = 0 V 쉬기, 노랑 = 마지막 4칸", loc="left")
ax[1].plot(t, cur, color="0.45", lw=1, label="전류 (계속 읽은 값)")
ax[1].plot(t[ends], cur[ends], ".", color="#c0392b", ms=6, label="pulse 끝 전류 = state (48개)")
ax[1].set_ylabel("전류 (µA)")
ax[1].set_xlabel("시간 (s)")
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.legend(*ax[1].get_legend_handles_labels(), loc="lower center", ncol=2)


# ============================================================
# 6. 그래프 ② class 0 / class 1의 평균 state (칸마다) + ③ 마지막 4칸의 차이
# ============================================================

fig2, (ax2, ax3) = plt.subplots(1, 2, figsize=(8, 4.0), gridspec_kw={"width_ratios": [1.6, 1]})
ax2.axvspan(7.5, 11.5, color="#fdf0c2", zorder=0)
ax2.plot(range(12), step0, "o-", color="#2b59c3", lw=2, label="class 0 (큰 입력이 앞쪽 0–3칸)")
ax2.plot(range(12), step1, "s--", color="#e08a3c", lw=2, label="class 1 (큰 입력이 가운데 4–7칸)")
ax2.set_xticks(range(12))
ax2.set_xlabel("칸 (time step)")
ax2.set_ylabel("평균 state (µA)")
ax2.set_title(f"② 칸마다 평균 state ({'mock ' + MOCK_MODEL if MOCK else RUN_NAME})", loc="left")

# 오른쪽: 마지막 4칸의 pulse 16개에서 "class 1 평균 − class 0 평균"
# 막대가 0이면 두 class의 state가 같다 = 마지막 4칸만 봐서는 구별할 단서가 없다
xs = np.arange(8 * M, 12 * M)
diff16 = mean1[xs] - mean0[xs]
lim = max(0.05, 1.15 * np.abs(diff16).max())        # 차이가 아주 작으면 ±0.05 µA로 고정 (작은 흔들림을 부풀리지 않게)
ax3.set_facecolor("#fdf0c2")
ax3.bar(xs, diff16, width=0.75, color=["#e08a3c" if d > 0 else "#2b59c3" for d in diff16])
ax3.axhline(0, color="0.3", lw=0.8)
ax3.set_ylim(-lim, lim)
ax3.set_ylabel("class 1 - class 0 (µA)")
ax3.set_xticks([8 * M + 1.5 + M * j for j in range(4)], [str(8 + j) for j in range(4)])
ax3.set_xlabel("칸 (pulse 16개)")
ax3.set_title("③ 마지막 4칸의 차이", loc="left")
fig2.tight_layout(rect=(0, 0.1, 1, 1))
fig2.legend(*ax2.get_legend_handles_labels(), loc="lower center", ncol=2)

plt.show()   # 그림 창 두 개를 모두 닫으면 프로그램이 끝납니다.
