# ============================================================
# P4 실습 2 · mock 기록: 가짜 소자를 리듬대로 누른 척하기
#
# 전체 과정:
#
#   실습 1의 리듬 일정 (runs/rhythm_n15.npz) 읽기
#         ↓
#   trial마다: 누른 힘(force) 곡선 만들기 → 가짜 소자의 전류 계산
#     흔적이 남는 소자: 누를 때마다 state가 올라가고, TAU초 정도에 걸쳐 천천히 빠진다
#     기억 없는 소자:   전류가 '지금 힘'에만 비례 (떼면 바로 원래대로)
#         ↓
#   첫째 날(session 1)·둘째 날(session 2)을 따로 저장
#     → runs/c_mock_memory_day1, runs/c_mock_memory_day2
#     (실물 실험 c_run과 똑같은 모양의 폴더 → 실습 3·4가 그대로 분석)
#         ↓
#   그림 1: 한 trial의 힘과 전류   그림 2: 리듬 4개의 전류를 겹쳐 보기
#
# mock 결과는 진짜 소자에 대해 아무것도 말해 주지 않습니다. 분석을 익히는 연습장입니다.
# ============================================================

import shutil
import sys
from pathlib import Path

# 공용 코드(python 폴더)를 불러오려고 경로를 잡는다.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import numpy as np
import matplotlib.pyplot as plt
from c_mock import simulate, HOLD, LEAD            # 공용 코드: 가짜 소자 계산
from c_rhythm import end_features                  # 공용 코드: 마지막 onset 뒤 전류 읽기
from common import load_json                       # 공용 코드: 설정 파일 읽기
from measure_seq import run_trials                 # 공용 코드: trial마다 기록 저장 (실물과 같음)


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

MEMORY = True        # True: 흔적이 남는 가짜 소자,  False: 기억 없는 가짜 소자
TAU = 0.6            # 흔적이 빠지는 시간 (초). 0.6초 뒤 처음의 약 1/3이 남음
SESSIONS = [1, 2]    # 만들 날(session) 번호. 날마다 baseline·힘이 조금 다르다
RHYTHM_FILE = "rhythm_n15.npz"   # 실습 1이 만든 일정 (runs 폴더 안)


# ============================================================
# 2. 준비: 일정 읽기, 저장할 폴더 이름
# ============================================================

MODEL = "memory" if MEMORY else "memoryless"
FOLDER = "c_mock_memory" if MEMORY else "c_mock_nomem"     # → c_mock_memory_day1 …

d = np.load(CODE / "runs" / RHYTHM_FILE)
gaps, y = d["gaps"], d["y"]
NAMES_KO = ["R1 고르게", "R2 앞에 몰림", "R3 뒤에 몰림", "R4 가운데 쉼"]
COLORS = ["#2b59c3", "#d9822b", "#2a9d8f", "#9b59b6"]

cfg = load_json(CODE / "python" / "config_c_mock.json")   # 연습용 설정 (고치지 않음)


# ============================================================
# 3. 가짜 소자 (공용 코드 c_mock.simulate가 하는 일)
# ============================================================
#
#   힘 F: 누를 때마다 80 ms 동안 반달 모양으로 솟는다 (약 2 N, 누를 때마다 ±5 %)
#
#   흔적이 남는 소자 (구멍 난 양동이):
#     state x  ←  x × exp(−0.02/TAU)   +   (지금 힘에 비례한 양)
#                 └ 20 ms마다 조금씩 빠짐   └ 누르는 동안 물이 참
#     전류 I = baseline × (1 + x)
#
#   기억 없는 소자:  전류 I = baseline × (1 + 0.4 × 지금 힘)
#
#   session(날)마다 baseline이 약 20 %, 힘이 약 10 % 다르다 (실제 날마다 조건이 다른 것을 흉내)
#   전류는 20 ms마다, 힘은 12.5 ms마다(load cell 80 SPS) 기록
# ============================================================

examples = {}                                      # 그림에 쓸 trial (첫째 날, 리듬마다 첫 trial)
summary = []

for s in SESSIONS:
    srng = np.random.default_rng(1000 + s)         # 날마다 정해진 차이 (c_mock.py와 같은 규칙)
    sess = dict(force=1 + 0.1 * srng.standard_normal(), base=1 + 0.2 * srng.standard_normal())

    def measure_trial(n, gaps_row):
        rng = np.random.default_rng(s * 100000 + n)            # trial마다 같은 잡음 (다시 돌려도 같음)
        t, I, onsets, tf, F = simulate(gaps_row, rng, MODEL, sess, tau=TAU)
        state = end_features(t, I, onsets[-1])                 # 마지막 onset + 0.3/0.6/1.0초 전류
        raw = dict(t=t, I=I, compliance=np.zeros(len(t), bool), onsets_ms=onsets * 1000,
                   force_t_ms=tf * 1000, force_N=F)
        if s == SESSIONS[0] and int(y[n]) not in examples:
            examples[int(y[n])] = (t, I, onsets, tf, F)
        return state, raw

    run_dir = CODE / "runs" / f"{FOLDER}_day{s}"
    if run_dir.exists():
        shutil.rmtree(run_dir)                     # mock은 몇 초면 다시 만드니, 매번 새로 만든다
    run_cfg = dict(cfg, device=dict(cfg["device"], mock_model=MODEL, session=s, tau=TAU))
    S, done = run_trials(run_cfg, gaps, str(run_dir), measure_trial, 3,
                         extra={"y": y}, log=lambda *_: None)
    summary.append((run_dir.name, sess, S[:, 0]))


# ============================================================
# 4. 숫자로 확인
# ============================================================

print("=" * 60)
print(f"mock records: {MODEL} device, TAU = {TAU} s, {len(y)} trials per session")
print("=" * 60)
for name, sess, _ in summary:
    print(f"saved: runs/{name}   (baseline x{sess['base']:.2f}, force x{sess['force']:.2f})")
print()
print("current at last onset + 0.3 s (nA), mean of trials per rhythm")
print("rhythm     " + "".join(f"{name:>22}" for name, _, _ in summary))
for c in range(4):
    print(f"R{c + 1}         " + "".join(f"{e1[y == c].mean() * 1e9:>22.1f}" for _, _, e1 in summary))


# ============================================================
# 5. 그림 1: 한 trial (R2 앞에 몰림) 의 힘과 전류
# ============================================================

t, I, onsets, tf, F = examples[1]
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True, height_ratios=[1, 1.4])
a1.plot(tf, F, color="#c0392b", lw=1.6)
a1.set_ylabel("force (N)")
a1.set_title("한 trial (R2 앞에 몰림, 첫째 날): 위 = 누른 힘, 아래 = 가짜 소자의 전류", loc="left")
a2.plot(t, I * 1e9, color="#2b59c3", lw=1.6)
reads = onsets[-1] + np.array([0.3, 0.6, 1.0])
a2.plot(reads, np.interp(reads, t, I) * 1e9, "o", color="#7a3db8", ms=7, label="끝에서 읽는 점 (+0.3·0.6·1.0초)")
for o in onsets:
    for ax in (a1, a2):
        ax.axvspan(o, o + HOLD, color="#c0392b", alpha=0.12, lw=0)
a2.set_ylabel("current (nA)")
a2.set_xlabel("time (s)")
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.legend(*a2.get_legend_handles_labels(), loc="lower center")


# ============================================================
# 6. 그림 2: 리듬 4개의 전류를 마지막 onset에 맞춰 겹치기
# ============================================================
#
#   모든 리듬의 마지막 onset은 같은 시각(LEAD + SPAN)에 온다.
#   끝에서 읽는 점(보라 세로선)에서 네 곡선의 높이가 다르면 → 한 번만 읽어도 리듬을 알 수 있다.
# ============================================================

fig2, ax = plt.subplots(figsize=(8, 4.2))
for c in range(4):
    t, I, onsets, tf, F = examples[c]
    ax.plot(t, I * 1e9, color=COLORS[c], lw=1.6, label=NAMES_KO[c])
last = examples[0][2][-1]
for dly in (0.3, 0.6, 1.0):
    ax.axvline(last + dly, color="#7a3db8", ls=":", lw=1.3)
ax.set_xlabel("time (s)")
ax.set_ylabel("current (nA)")
ax.set_title(f"리듬 4개의 전류 ({'흔적이 남는' if MEMORY else '기억 없는'} 가짜 소자, TAU = {TAU} s)"
             "  ·  보라 점선 = 끝에서 읽는 시점", loc="left", fontsize=10.5)
fig2.tight_layout(rect=(0, 0.08, 1, 1))
fig2.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=4)

plt.show()   # 그림 창 두 개가 뜹니다. 둘 다 닫아야 프로그램이 끝납니다.
