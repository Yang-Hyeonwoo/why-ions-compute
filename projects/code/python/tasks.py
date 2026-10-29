"""작은 합성 입력 과제 (A2). ECG 전에 '시간 패턴을 기억하는가'만 따로 묻는다.

timing_task: 높은 입력 3개가 '앞쪽(0–3번 칸)'에 있는지 '뒤쪽(4–7번 칸)'에 있는지 맞히기.
  8–11번 칸은 모든 시행에서 똑같이 낮은 값 → 마지막 4칸만 읽으면 입력 자체로는 구별 불가(찍기 0.5).
  소자의 출력이 마지막 4칸에서도 두 클래스를 가른다면, 그 정보는 '앞에서 받은 입력의 흔적'에서 온 것이다.
  (어떤 물리 기작인지는 이것만으로 알 수 없다 — 이온 이동, 충·방전, 계면 분극 모두 흔적을 남길 수 있다.)

mc_sequence: 기억 용량(MC) 측정용 무작위 입력 한 줄.
"""
import argparse

import numpy as np


def timing_task(n_per_class=40, L=12, n_high=3, lo=0.2, hi=1.0, seed=0):
    rng = np.random.default_rng(seed)
    U, y = [], []
    for cls, (a, b) in enumerate([(0, 4), (4, 8)]):
        for _ in range(n_per_class):
            u = np.full(L, lo)
            u[rng.choice(np.arange(a, b), n_high, replace=False)] = hi
            U.append(u)
            y.append(cls)
    idx = rng.permutation(len(y))          # 클래스를 섞은 순서로 측정 (시간에 따른 drift가 한쪽에 몰리지 않게)
    U, y = np.array(U)[idx], np.array(y)[idx]
    readout_steps = np.arange(8, L)        # '끝만 읽기'에 쓰는 칸
    return U, y, np.arange(len(y)), readout_steps


def feature_columns(steps, M):
    """칸 번호 목록 → 상태 행렬(L×M 펼침)의 열 번호"""
    return np.array([s * M + j for s in steps for j in range(M)])


def mc_sequence(K=600, seed=0):
    return np.random.default_rng(seed).random((1, K))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["timing", "mc"])
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=40, help="timing: 클래스당 시행 수 / mc: 길이")
    ap.add_argument("--M", type=int, default=4, help="마스크 수 (config의 mask 개수와 같게)")
    a = ap.parse_args()
    if a.kind == "timing":
        U, y, g, steps = timing_task(a.n)
        ntr = int(len(y) * 0.7)                          # 앞 70% 학습, 뒤 30% 시험 (이미 섞인 순서)
        np.savez(a.out, U=U, y=y, groups=g, readout_steps=steps, end_cols=feature_columns(steps, a.M),
                 train_idx=np.arange(ntr), test_idx=np.arange(ntr, len(y)))
        print(f"시행 {len(y)}개 (클래스 0: 앞쪽, 1: 뒤쪽), 학습 {ntr} / 시험 {len(y) - ntr}, 끝만 읽기 칸 {steps.tolist()}")
    else:
        np.savez(a.out, U=mc_sequence(a.n))
    print("저장:", a.out)


if __name__ == "__main__":
    main()
