"""기억 용량(Memory Capacity, MC): 지금의 상태 x(t)로 d걸음 전 입력 u(t−d)를 얼마나 맞히나.

주의할 점 (결과를 읽기 전에)
- washout: 맨 앞 구간은 초기 상태의 영향이 남아 있어 버린다.
- 시간 순서대로 나눈다: 앞부분으로 학습, 뒷부분으로 평가 (섞으면 이웃한 시점끼리 정보가 샌다).
- 유한 표본 편향: 아무 관계 없는 신호여도 r²는 0보다 조금 크게 나온다.
  그래서 '독립 무작위 목표'로 같은 계산을 반복한 null 값과 비교하고, null보다 큰 부분만 의미 있게 본다.
- MC가 크다 = 이 입력 통계·이 인코딩에서 선형으로 꺼낼 수 있는 과거 정보가 많다. 모든 과제에 좋은 레저버라는 뜻은 아니다.

사용: python mc.py runs/mc/checkpoint.npz mc_input.npz --M 8
"""
import argparse

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _r2_for(X, target, ntr):
    model = GridSearchCV(make_pipeline(StandardScaler(), Ridge()), {"ridge__alpha": np.logspace(-6, 2, 9)},
                         cv=TimeSeriesSplit(4))
    model.fit(X[:ntr], target[:ntr])
    p = model.predict(X[ntr:])
    c = np.corrcoef(p, target[ntr:])[0, 1]
    return 0.0 if not np.isfinite(c) else float(c * c)


def memory_capacity(X, u, d_max=10, washout=50, train_frac=0.67, n_null=20, seed=0):
    """X: (K, 특징), u: (K,). 반환: d별 r², null 평균·95% 값, MC(합), MC_excess(null 95%를 넘는 부분 합)"""
    rng = np.random.default_rng(seed)
    K = len(u)
    t = np.arange(washout + d_max, K)
    ntr = int(len(t) * train_frac)
    r2 = [_r2_for(X[t], u[t - d], ntr) for d in range(1, d_max + 1)]
    null = np.array([_r2_for(X[t], rng.random(len(t)), ntr) for _ in range(n_null)])
    q95 = float(np.quantile(null, 0.95))
    return dict(r2=np.round(r2, 4).tolist(), null_mean=float(null.mean()), null_q95=q95,
                MC=float(sum(r2)), MC_excess=float(sum(max(0.0, r - q95) for r in r2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("states")
    ap.add_argument("inputs")
    ap.add_argument("--M", type=int, required=True, help="마스크 수(가상 노드 수)")
    a = ap.parse_args()
    u = np.load(a.inputs)["U"][0]
    X = np.load(a.states)["S"][0].reshape(len(u), a.M)
    print(memory_capacity(X, u))


if __name__ == "__main__":
    main()
