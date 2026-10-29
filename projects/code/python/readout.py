"""레저버 출력(상태 행렬)으로 선형 분류기(readout)를 학습·평가한다.

데이터 누출을 막는 규칙
- 표준화(StandardScaler)는 분류기와 한 Pipeline 안에 넣어, 내부 교차검증의 각 fold 학습 부분에서만 맞춘다.
- 내부 교차검증은 같은 사람/세션이 학습·검증에 동시에 들어가지 않게 그룹 단위(GroupKFold)로 나눈다.
- 시험(test) 데이터는 마지막 평가에 딱 한 번만 쓴다. 정규화 강도 선택에 쓰지 않는다.

사용:
  python readout.py runs/pilot/checkpoint.npz split.npz --out model.joblib [--cols 0,1,2]
split.npz: train_idx, test_idx (정수 배열). groups는 checkpoint.npz 또는 split.npz에서 읽는다.
"""
import argparse

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, recall_score
from sklearn.model_selection import GridSearchCV, GroupKFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def make_model():
    return Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(max_iter=5000))])


def fit_select(Ftr, ytr, gtr=None, Cs=np.logspace(-3, 3, 13), n_splits=5):
    """그룹이 충분하면 GroupKFold, 아니면(모든 시행이 독립) StratifiedKFold로 C를 고른다."""
    if gtr is not None and len(np.unique(gtr)) >= n_splits and len(np.unique(gtr)) < len(gtr):
        cv = GroupKFold(n_splits)
    else:
        cv = StratifiedKFold(n_splits, shuffle=True, random_state=0)
    gs = GridSearchCV(make_model(), {"lr__C": Cs}, cv=cv, scoring="balanced_accuracy")
    gs.fit(Ftr, ytr, groups=gtr if isinstance(cv, GroupKFold) else None)
    return gs.best_estimator_, gs


def evaluate(model, Fte, yte):
    p = model.predict(Fte)
    labels = np.unique(np.r_[yte, p])
    return dict(balanced_accuracy=float(balanced_accuracy_score(yte, p)),
                recall_per_class={int(c): float(r) for c, r in
                                  zip(labels, recall_score(yte, p, labels=labels, average=None, zero_division=0))},
                confusion=confusion_matrix(yte, p, labels=labels).tolist(), labels=labels.tolist())


def label_shuffle_check(Ftr, ytr, gtr, Fte, yte, seed=0):
    """정답을 섞어 학습 → 찍기 수준이 나와야 정상 (높게 나오면 어딘가 누출이 있다는 신호)"""
    rng = np.random.default_rng(seed)
    m, _ = fit_select(Ftr, rng.permutation(ytr), gtr)
    return evaluate(m, Fte, yte)["balanced_accuracy"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("states")
    ap.add_argument("split")
    ap.add_argument("--out", default="model.joblib")
    ap.add_argument("--cols", help="쓸 특징 열 번호 (쉼표). 생략하면 전부")
    ap.add_argument("--end-only", action="store_true", help="split 파일의 end_cols(끝만 읽기 열)만 사용")
    a = ap.parse_args()
    import joblib
    d, s = np.load(a.states), np.load(a.split)
    F, y = d["S"], (d["y"] if "y" in d else s["y"])
    g = d["groups"] if "groups" in d else (s["groups"] if "groups" in s else None)
    if a.end_only:
        a.cols = ",".join(map(str, s["end_cols"]))
    if a.cols:
        F = F[:, [int(c) for c in a.cols.split(",")]]
    ok = d["done"] if "done" in d else np.ones(len(F), bool)          # 아직 안 잰 시행은 빼고
    tr, te = [i for i in s["train_idx"] if ok[i]], [i for i in s["test_idx"] if ok[i]]
    print(f"학습 {len(tr)}개, 시험 {len(te)}개 사용 (측정 안 된 시행 {int((~ok).sum())}개 제외)")
    if g is not None and set(g[tr]) & set(g[te]):
        raise SystemExit("학습과 시험에 같은 그룹(사람/세션)이 있습니다. 분할을 다시 만드세요.")
    model, gs = fit_select(F[tr], y[tr], None if g is None else g[tr])
    res = evaluate(model, F[te], y[te])
    res["chosen_C"] = float(gs.best_params_["lr__C"])
    res["label_shuffle_bal_acc"] = label_shuffle_check(F[tr], y[tr], None if g is None else g[tr], F[te], y[te])
    print(f"균형 정확도 {res['balanced_accuracy']:.2f}  (찍기 = {1/len(res['labels']):.2f})")
    print(f"클래스별 맞힌 비율 {res['recall_per_class']}")
    print(f"혼동 행렬 (행 = 정답, 열 = 예측) {res['confusion']}")
    print(f"라벨 섞기 확인 {res['label_shuffle_bal_acc']:.2f}  (찍기 근처여야 정상)  ·  고른 C = {res['chosen_C']:.3g}")
    joblib.dump(dict(model=model, cols=a.cols, result=res), a.out)
    print("저장:", a.out, "(학습된 표준화·가중치·결과. B의 export_mcu.py가 읽는 파일)")


if __name__ == "__main__":
    main()
