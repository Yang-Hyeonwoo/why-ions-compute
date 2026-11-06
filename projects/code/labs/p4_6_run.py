# ============================================================
# P4 실습 6 · 리듬 trial 돌리기: tapper로 누르며 소자 전류를 계속 기록
#
# 전체 과정 (trial 하나마다):
#
#   소자에 read voltage를 걸고 rest_s초 쉬기
#         ↓
#   소스미터로 전류를 쉬지 않고 읽기 시작   +   tapper에 "T,번호,간격,간격,간격"
#         ↓
#   tapper가 X(마지막 onset)를 보내고 1.2초 더 읽은 뒤 멈춤
#         ↓
#   전류·힘·onset 시각을 runs/<RUN_NAME>/raw/trial_xxxxx.npz 로 저장
#   (어디까지 했는지 checkpoint.npz에 적어 두므로, 멈춰도 같은 파일을 다시 ▷하면 이어서 함)
#         ↓
#   그림: 마지막 trial의 힘·전류,  지금까지 trial의 peak force
#
# MOCK = True  : 장비 없이 가짜 소자·가짜 tapper로 (폴더 이름 앞에 mock_)
# MOCK = False : 진짜 소스미터 + tapper (공용 코드 c_run.py와 같은 계산) [실물 미검증]
# 분석은 실습 3·4에서 RUNS = ["c_dev01_day1"]처럼 폴더 이름만 바꿔서 한다.
# ============================================================

import shutil
import sys
import time
from pathlib import Path

# 공용 코드(python 폴더)를 불러오려고 경로를 잡는다.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import numpy as np
import matplotlib.pyplot as plt
from common import load_json                       # 공용 코드: 설정 파일 읽기
from measure_seq import run_trials                 # 공용 코드: trial마다 저장·이어서 하기


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

MOCK = True                       # True: 장비 없이 연습,  False: 진짜 장비
CONFIG = "config_c.json"          # 내 설정 파일 (python 폴더 안). MOCK이면 config_c_mock.json을 씀
PORT = "COM6"                     # tapper board의 COM 번호
RHYTHM_FILE = "rhythm_n60.npz"    # 실습 1을 N_PER_RHYTHM = 60으로 돌려 만든 일정 (runs 안)
RUN_NAME = "c_dev01_day1"         # 기록 폴더 이름: 소자 이름 + 날짜 순번
LIMIT = 8                         # 이번에 몇 trial만 할까. None = 남은 것 전부


# ============================================================
# 2. 준비: 일정·설정 읽기
# ============================================================

d = np.load(CODE / "runs" / RHYTHM_FILE)
gaps, y = d["gaps"], d["y"]
if MOCK:
    RUN_NAME = "mock_" + RUN_NAME                  # 가짜 기록이 진짜 기록과 섞이지 않게
    cfg = load_json(CODE / "python" / "config_c_mock.json")
else:
    cfg = load_json(CODE / "python" / CONFIG)
run_dir = CODE / "runs" / RUN_NAME

# 연습(MOCK)용: trial이 다 끝난 mock 폴더면 지우고 처음부터 다시 (연습을 여러 번 해 볼 수 있게)
if MOCK and (run_dir / "checkpoint.npz").exists():
    with np.load(run_dir / "checkpoint.npz") as ck:
        finished = bool(ck["done"].all())
    if finished:
        shutil.rmtree(run_dir)


# ============================================================
# 3. trial 하나를 재는 방법 (measure_trial)
# ============================================================
#
#   MOCK  : 공용 코드 c_mock.simulate (흔적이 남는 가짜 소자, TAU 0.6초)
#   실물  : 공용 코드 c_run.c_trial_fn — 소스미터를 따로 도는 일꾼(thread)이 쉬지 않고 읽는 동안
#           tapper에 T 명령을 보내고, X 줄이 올 때까지 기다린다.
#           PC와 tapper는 "명령을 보낸 순간"을 각자 0초로 삼는다 (USB 지연 몇 ms만큼 어긋날 수 있음)
# ============================================================

if MOCK:
    from c_mock import simulate
    from c_rhythm import end_features
    sess = dict(force=1.0, base=1.0)

    def measure_trial(n, gaps_row):
        rng = np.random.default_rng(n)
        t, I, onsets, tf, F = simulate(gaps_row, rng, "memory", sess)
        raw = dict(t=t, I=I, compliance=np.zeros(len(t), bool), onsets_ms=onsets * 1000,
                   force_t_ms=tf * 1000, force_N=F)
        return end_features(t, I, onsets[-1]), raw
else:
    import serial                                  # tapper와 USB로 글자 주고받기
    from smu import open_smu                       # 공용 코드: 소스미터 열기
    from c_run import c_trial_fn                   # 공용 코드: 실물 trial 하나 재기
    ser = serial.Serial(PORT, 115200, timeout=15)  # Arduino IDE(Serial Monitor)가 열려 있으면 여기서 오류
    smu = open_smu(cfg["instrument"])
    smu.open()                                     # 소스미터 연결 (출력은 아직 꺼져 있음)
    time.sleep(2)
    ser.reset_input_buffer()
    smu.enable()                                   # 출력 켜기 (끝나면 아래에서 끔)
    rd = cfg["encoding"]                           # read_V(읽기 전압), rest_s(trial 사이 쉬기)
    measure_trial = c_trial_fn(smu, ser, rd["read_V"], rd["rest_s"])


# ============================================================
# 4. 돌리기 (공용 코드 run_trials: 실물·MOCK 똑같음)
# ============================================================
#
#   이미 끝난 trial은 건너뛰고, LIMIT개만 더 한다.
#   TERMINAL에는 처음 3개와 끝 1개, 그 사이 50개마다 한 줄만 찍는다.
# ============================================================

lines, shown = [], []

def log(msg):
    lines.append(msg)
    n = sum(not m.startswith("resume") for m in lines)     # 이번에 저장한 trial 수
    if msg.startswith("resume") or n <= 3 or n % 50 == 0:
        print(msg)
        shown.append(msg)

print(f"run: runs/{RUN_NAME}   ({'MOCK, no instruments' if MOCK else 'SMU ' + cfg['instrument']['addr'] + ', tapper ' + PORT})")
try:
    S, done = run_trials(cfg, gaps, str(run_dir), measure_trial, 3, limit=LIMIT, extra={"y": y}, log=log)
finally:
    if not MOCK:
        smu.close()                                # 0 V → 출력 OFF → 연결 닫기
        ser.close()
if lines and lines[-1] not in shown:               # 마지막 줄은 늘 보여 준다
    print("...")
    print(lines[-1])
print()
print(f"done: {done.sum()}/{len(done)} trials")
print(f"left: {len(done) - done.sum()}   -> run again with LIMIT = None to finish" if not done.all()
      else "all trials done -> analyze with labs 3 and 4 (RUNS = [\"" + RUN_NAME + "\"])")


# ============================================================
# 5. 그림: 마지막으로 잰 trial 하나 + 지금까지의 peak force
# ============================================================

last = int(np.where(done)[0][-1])
with np.load(run_dir / "raw" / f"trial_{last:05d}.npz") as r:
    t, I, on = r["t"], r["I"], r["onsets_ms"] / 1000
    tf, F = r["force_t_ms"] / 1000, r["force_N"]

fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.8), sharex=True)
a1.plot(tf, F, color="#c0392b", lw=1.4)
a1.set_ylabel("force (N)")
a1.set_title(f"trial {last} (리듬 R{int(y[last]) + 1}): 위 = 힘, 아래 = 소자 전류", loc="left")
a2.plot(t, I * 1e9, color="#2b59c3", lw=1.4)
reads = on[-1] + np.array([0.3, 0.6, 1.0])
a2.plot(reads, np.interp(reads, t, I) * 1e9, "o", color="#7a3db8", ms=6)
a2.set_ylabel("current (nA)")
a2.set_xlabel("time (s)")
fig.tight_layout()

peaks, ys = [], []
for n in np.where(done)[0]:
    with np.load(run_dir / "raw" / f"trial_{n:05d}.npz") as r:
        peaks.append(r["force_N"].max())
        ys.append(int(y[n]))
fig2, ax = plt.subplots(figsize=(8, 3.4))
for c in range(4):
    idx = [i for i, v in enumerate(ys) if v == c]
    ax.plot([np.where(done)[0][i] for i in idx], [peaks[i] for i in idx], "o", ms=4, color=f"C{c}", label=f"R{c + 1}")
ax.set_xlabel("trial 번호")
ax.set_ylabel("가장 큰 힘 (N)")
ax.set_title("지금까지 잰 trial의 가장 큰 힘 (리듬마다 색이 섞여 있으면 좋음)", loc="left")
fig2.tight_layout(rect=(0, 0.1, 1, 1))
fig2.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=4)

plt.show()   # 그림 창 두 개가 뜹니다. 둘 다 닫아야 프로그램이 끝납니다.
