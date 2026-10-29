"""MIT-BIH 부정맥 DB에서 박동을 잘라 소자 입력(U, 0–1)으로 만든다. (오프라인 경로)

이것은 '오프라인' 준비다: 전체 기록을 미리 갖고 있고, 전문가가 표시한 R파 위치(주석)를 쓰며,
앞뒤를 모두 보는 0위상 필터(filtfilt)를 쓴다. 실시간 장치는 R파를 스스로 찾아야 하고 미래 샘플을 볼 수 없다.

라벨 (AAMI EC57 묶음)
  N 묶음 = N(정상), L(좌각차단), R(우각차단), e(심방 이탈), j(접합부 이탈)  → '비이소성(non-ectopic) 박동'
  V 묶음 = V(심실조기수축), E(심실 이탈)                                → '심실 이소성 박동'
  즉 'N 대 V'는 '정상 대 비정상'이 아니다. 좌각차단 박동도 N 묶음에 들어간다.

분할
  관행적 분할 DS1(학습)/DS2(시험) (de Chazal 2004)을 쓰되, PhysioNet 설명에 따르면 201과 202는
  같은 사람의 기록이다. strict=True(기본)면 202를 시험에서 빼서 사람이 겹치지 않게 한다.
  groups에는 '사람 번호'(202→201)를 넣어 내부 교차검증도 사람 단위로 나뉘게 한다.

리드: 채널 이름이 MLII인 것을 쓴다 (대부분 0번이지만 확인해서 고른다).
샘플링: 360 Hz → fs_out(기본 36 Hz)로 줄일 때 resample_poly(안티앨리어싱 FIR 포함)를 쓴다.
  36 Hz로 줄이면 18 Hz 이상 성분은 사라진다 → QRS의 날카로운 부분이 무뎌진다. 소자 펄스 수와의 맞교환.

필요: pip install wfdb scipy numpy (처음 실행 때 PhysioNet에서 기록을 내려받는다)
사용: python ecg_prep.py ecg_set.npz --train 200 --test 100
"""
import argparse
from fractions import Fraction

import numpy as np

AAMI = {"N": set("NLRej"), "V": set("VE")}
DS1 = [101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230]
DS2 = [100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234]
SUBJECT = {202: 201}                       # 같은 사람의 기록


def subject_of(rec):
    return SUBJECT.get(rec, rec)


def splits(strict=True):
    test = [r for r in DS2 if not (strict and subject_of(r) in {subject_of(x) for x in DS1})]
    return list(DS1), test


def downsample(x, fs, fs_out):
    from scipy.signal import resample_poly
    fr = Fraction(fs_out / fs).limit_denominator(1000)
    return resample_poly(x, fr.numerator, fr.denominator)


def segment(x, fs, samples, symbols, pre_s=0.25, post_s=0.45):
    """x(이미 fs로 줄인 신호), samples(같은 fs 기준 R파 위치) → (박동 배열, 라벨 0=N묶음 1=V묶음)"""
    pre, post = int(round(pre_s * fs)), int(round(post_s * fs))
    X, y = [], []
    for s, sym in zip(samples, symbols):
        lab = 0 if sym in AAMI["N"] else 1 if sym in AAMI["V"] else None
        if lab is None or s - pre < 0 or s + post > len(x):
            continue
        X.append(x[s - pre:s + post])
        y.append(lab)
    return np.array(X).reshape(-1, pre + post), np.array(y, int)


def load_record(rec, fs_out):
    import wfdb
    from scipy.signal import butter, filtfilt
    sig, f = wfdb.rdsamp(str(rec), pn_dir="mitdb")
    if "MLII" not in f["sig_name"]:
        return None
    fs = f["fs"]
    x = sig[:, f["sig_name"].index("MLII")]
    b, a = butter(2, 0.5 / (fs / 2), btype="high")          # 기저선 흔들림 제거 (오프라인 0위상)
    x = downsample(filtfilt(b, a, x), fs, fs_out)
    ann = wfdb.rdann(str(rec), "atr", pn_dir="mitdb")
    samples = np.round(np.asarray(ann.sample) * fs_out / fs).astype(int)
    return x, samples, ann.symbol


def collect(recs, fs_out):
    Xs, ys, gs, rs = [], [], [], []
    for r in recs:
        got = load_record(r, fs_out)
        if got is None:
            print(f"  {r}: MLII 없음 → 제외")
            continue
        X, y = segment(got[0], fs_out, got[1], got[2])
        Xs.append(X), ys.append(y), gs.append(np.full(len(y), subject_of(r))), rs.append(np.full(len(y), r))
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(gs), np.concatenate(rs)


def balanced_pick(y, n_each, rng):
    idx = []
    for c in (0, 1):
        pool = np.where(y == c)[0]
        idx.append(rng.choice(pool, min(n_each, len(pool)), replace=False))
    idx = np.concatenate(idx)
    return idx[rng.permutation(len(idx))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--train", type=int, default=200, help="학습: 클래스당 박동 수")
    ap.add_argument("--test", type=int, default=100, help="시험: 클래스당 박동 수")
    ap.add_argument("--fs", type=float, default=36.0)
    ap.add_argument("--loose", action="store_true", help="202를 시험에 남기는 관행적 분할(사람 겹침 있음)")
    a = ap.parse_args()
    rng = np.random.default_rng(1)
    tr_recs, te_recs = splits(strict=not a.loose)
    Xtr, ytr, gtr, rtr = collect(tr_recs, a.fs)
    Xte, yte, gte, rte = collect(te_recs, a.fs)
    i, j = balanced_pick(ytr, a.train, rng), balanced_pick(yte, a.test, rng)
    lo, hi = np.percentile(Xtr[i], [1, 99])                  # 크기 기준은 학습 데이터에서만
    scale = lambda X: np.clip((X - lo) / (hi - lo), 0, 1)
    U = np.r_[scale(Xtr[i]), scale(Xte[j])]
    n = len(i)
    np.savez(a.out, U=U, y=np.r_[ytr[i], yte[j]], groups=np.r_[gtr[i], gte[j]], record=np.r_[rtr[i], rte[j]],
             train_idx=np.arange(n), test_idx=np.arange(n, len(U)), scale_lo=lo, scale_hi=hi, fs=a.fs,
             class_names=np.array(["0 = N 묶음 (비이소성 박동)", "1 = V 묶음 (심실 이소성 박동)"]))
    print(f"U {U.shape}, 학습 {n} / 시험 {len(U)-n}, 학습·시험 사람 겹침:",
          sorted(set(gtr[i]) & set(gte[j])) or "없음")


if __name__ == "__main__":
    main()
