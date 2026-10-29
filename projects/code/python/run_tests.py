"""장비 없이 코드 흐름을 확인하는 시험. 실제 소자·장비 동작을 검증하는 것이 아니다.
사용: python run_tests.py   (numpy, scipy, scikit-learn 필요)
"""
import copy
import json
import os
import shutil
import tempfile

import numpy as np

from common import load_json
from measure_seq import check_inputs, run_trials, smu_trial_fn
from smu import MockSMU, SMUError
import ecg_prep
import export_mcu
import mc
import readout
import tasks
import c_rhythm

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = load_json(os.path.join(HERE, "config_example.json"))
passed = []


def ok(name):
    passed.append(name)
    print("통과:", name)


def mock(cfg, **kw):
    m = cfg["instrument"]["mock"]
    s = MockSMU(**m, compliance_A=cfg["instrument"]["compliance_A"], v_limit_V=cfg["instrument"]["v_limit_V"], **kw)
    s.enable()
    return s


def measure(cfg, U, run, limit=None, **kw):
    s = mock(cfg, **kw)
    nf = U.shape[1] * len(cfg["encoding"]["mask"])
    return run_trials(cfg, U, run, smu_trial_fn(s, cfg["encoding"]), nf, limit=limit, log=lambda *_: None)


def main():
    tmp = tempfile.mkdtemp()
    try:
        # 1) 안전: 출력 OFF 상태 읽기 거부, 상한 밖 전압 거부, 인코딩이 상한을 넘으면 거부
        s = MockSMU(v_limit_V=1.0)
        try:
            s.read(); raise AssertionError
        except SMUError:
            pass
        s.enable()
        try:
            s.set_v(1.5); raise AssertionError
        except SMUError:
            pass
        bad = copy.deepcopy(CFG); bad["encoding"]["VA"] = 2.0
        try:
            check_inputs(np.zeros((2, 3)), bad["encoding"], 1.0); raise AssertionError
        except ValueError:
            pass
        for U in (np.full((2, 3), 1.2), np.array([[0.1, np.nan]]), np.zeros(3)):
            try:
                check_inputs(U, CFG["encoding"], 1.0); raise AssertionError
            except ValueError:
                pass
        ok("출력 OFF 읽기·상한 초과·잘못된 입력 거부")

        # 2) 작은 시험(10시행) → 중단(통신 오류) → 이어서 → 완료, 앞 결과는 그대로
        U, y, g, steps = tasks.timing_task(n_per_class=12)
        run = os.path.join(tmp, "pilot")
        S1, done = measure(CFG, U, run, limit=10)
        assert done.sum() == 10
        first = S1[done].copy()
        try:
            measure(CFG, U, run, fail_after=200)
            raise AssertionError
        except IOError:
            pass
        with np.load(os.path.join(run, "checkpoint.npz")) as ck:
            assert 10 <= ck["done"].sum() < len(U)
        S2, done2 = measure(CFG, U, run)
        assert done2.all() and np.allclose(S2[:len(first)][done[:len(first)]], first)
        assert len(os.listdir(os.path.join(run, "raw"))) == len(U)
        with np.load(os.path.join(run, "raw", "trial_00000.npz")) as r:
            assert {"t_host", "V_set", "V", "I", "compliance", "pulse_dur_s"} <= set(r.files)
        ok("10시행 시험·중단 후 이어서·원시 기록 저장")

        # 3) 조건이 다르면 이어서 하기 거부
        other = copy.deepcopy(CFG); other["encoding"]["theta_s"] = 0.1
        try:
            measure(other, U, run); raise AssertionError
        except SystemExit:
            pass
        try:
            measure(CFG, U[:-1], run); raise AssertionError
        except SystemExit:
            pass
        ok("조건·입력이 다른 재개 거부")

        # 4) 끝만 읽기: 입력 그대로는 찍기, 기억 있는 모의 소자는 구별, 기억 없는 모의 저항은 찍기
        M = len(CFG["encoding"]["mask"])
        U, y, g, steps = tasks.timing_task(n_per_class=40)
        cols = tasks.feature_columns(steps, M)
        tr, te = np.arange(0, 60), np.arange(60, 80)

        def score(F):
            m, _ = readout.fit_select(F[tr], y[tr])
            return readout.evaluate(m, F[te], y[te])["balanced_accuracy"]
        S_mem, _ = measure(CFG, U, os.path.join(tmp, "mem"))
        res = copy.deepcopy(CFG); res["instrument"]["mock"]["model"] = "resistor"
        S_res, _ = measure(res, U, os.path.join(tmp, "res"))
        a_in, a_mem, a_res = score(U[:, steps]), score(S_mem[:, cols]), score(S_res[:, cols])
        print(f"   끝만 읽기 균형정확도: 입력 {a_in:.2f}, 모의 기억소자 {a_mem:.2f}, 모의 저항 {a_res:.2f}")
        assert a_in <= 0.65 and a_res <= 0.7 and a_mem >= 0.8
        ok("합성 과제: 기억 유무에 따른 차이 (모의 장비)")

        # 5) 그룹 분할·누출 방지: 사람 겹침 0, scaler가 Pipeline 안에 있음
        tr_r, te_r = ecg_prep.splits(strict=True)
        assert not ({ecg_prep.subject_of(r) for r in tr_r} & {ecg_prep.subject_of(r) for r in te_r})
        assert 202 in ecg_prep.splits(strict=False)[1]
        m, gs = readout.fit_select(S_mem[tr][:, cols], y[tr], np.repeat(np.arange(12), 5))
        assert list(m.named_steps) == ["sc", "lr"] and type(gs.cv).__name__ == "GroupKFold"
        ok("ECG 사람 단위 분할(201/202) · 그룹 내부 CV")

        # 6) ECG 자르기·다운샘플: 합성 신호, 라벨 묶음, 길이 25
        fs = 360.0
        x = np.zeros(3600); x[[500, 1500, 2500]] = 1.0
        xd = ecg_prep.downsample(x, fs, 36.0)
        assert len(xd) == 360
        X, lab = ecg_prep.segment(xd, 36.0, [50, 150, 250, 2], ["N", "V", "A", "N"])
        assert X.shape == (2, 25) and lab.tolist() == [0, 1]
        ok("ECG 박동 자르기·안티앨리어싱 다운샘플")

        # 7) MC: null 비교 포함, 기억 소자 > 저항
        Umc = tasks.mc_sequence(300)
        enc = dict(CFG["encoding"], rest_s=0.5, mask=[0.9, 0.5, 0.7, 0.3, 1.0, 0.6, 0.4, 0.8])
        cm = dict(CFG, encoding=enc)
        S, _ = measure(cm, Umc, os.path.join(tmp, "mc_mem"))
        mm = mc.memory_capacity(S[0].reshape(300, 8), Umc[0], d_max=5, n_null=5)
        cr = copy.deepcopy(cm); cr["instrument"]["mock"]["model"] = "resistor"
        S, _ = measure(cr, Umc, os.path.join(tmp, "mc_res"))
        mr = mc.memory_capacity(S[0].reshape(300, 8), Umc[0], d_max=5, n_null=5)
        print(f"   MC 초과분: 모의 기억소자 {mm['MC_excess']:.2f}, 모의 저항 {mr['MC_excess']:.2f}")
        assert mm["MC_excess"] > mr["MC_excess"]
        ok("MC 계산과 null 비교")

        # 8) 내보내기: 이진·4클래스 모두, 헤더를 다시 읽어 계산한 점수 = Python 점수
        man = load_json(os.path.join(tmp, "mem", "manifest.json"))
        for name, yy in (("bin", y), ("multi", np.arange(len(y)) % 4)):
            mdl, _ = readout.fit_select(S_mem, yy)
            out = os.path.join(tmp, "hdr_" + name)
            info = export_mcu.export(mdl, man, S_mem, out, v_limit=1.0)
            h = export_mcu.read_header_arrays(os.path.join(out, "weights.h"))
            ref = export_mcu.read_header_arrays(os.path.join(out, "ref_vectors.h"))
            for x, sref in zip(ref["XREF"].reshape(-1, info["NF"]), ref["SREF"].reshape(-1, info["NC"])):
                assert np.allclose(export_mcu.mcu_score(x, h), sref, rtol=1e-3, atol=1e-3)
            assert info["NF"] == info["L"] * info["M"] and info["NC"] == (1 if name == "bin" else 4)
        ok("MCU 헤더 내보내기 (이진·4클래스) 수치 일치")

        # 9) C 리듬 일정: 총 길이 같음, 최소 간격 지킴, 판독 특징
        gaps, yc = c_rhythm.make_schedule(10)
        assert np.allclose(gaps.sum(1), 1.8) and gaps.min() >= 0.15 - 1e-9 and len(set(yc)) == 4
        t = np.linspace(0, 5, 501)
        assert np.allclose(c_rhythm.end_features(t, t * 2, 2.0), [4.6, 5.2, 6.0])
        ok("C 리듬 일정·끝 판독 특징")

        # 10) A1 쓰기–쉬기–읽기: 직렬 RC는 '기억처럼 보이는' 차이가 쉬는 시간에 따라 줄고, 저항은 차이가 없음
        import argparse
        import a1_tests
        args = argparse.Namespace(vw=0.5, tw=1.0, vr=0.05, tr=0.5, settle=5.0, gaps=[0.1, 1.0, 5.0])

        def wrr(model):
            s = MockSMU(model=model, R=1e6, C=1e-6, v_limit_V=1.0, read_dt=0.02)
            s.enable()
            rec = a1_tests.Recorder(s)
            r = a1_tests.run_wrr(rec, args)
            names = list(rec.arrays()["seg_names"])
            assert names == ["settle", "write+", "rest", "read", "write-"], names   # 그림 ②와 같은 순서
            diff = r["I_read_first"][r["polarity"] > 0] - r["I_read_first"][r["polarity"] < 0]
            return diff
        d_rc, d_r = wrr("series_rc"), wrr("resistor")
        print(f"   읽기 첫 전류 차이(+쓰기 − −쓰기) [nA], 쉬기 0.1/1/5 s: RC {np.round(d_rc*1e9, 1)}, 저항 {np.round(d_r*1e9, 2)}")
        assert abs(d_rc[0]) > abs(d_rc[1]) > abs(d_rc[2]) and np.all(np.abs(d_r) < 2e-9)
        ok("A1 쓰기–쉬기–읽기 순서·모의 RC와 저항의 차이")

        # 11) C: 모의 기록 → 분석 경로 (기억 모델은 끝 판독으로 구별, 무기억 모델·힘만으로는 찍기 수준, 단서 균등)
        import c_analyze
        import c_mock
        gaps, yc = c_rhythm.make_schedule(15)
        res = {}
        for model in ("memory", "memoryless"):
            run = os.path.join(tmp, "c_" + model)
            sess = dict(force=1.0, base=1.0)

            def mt(n, g, model=model):
                rng = np.random.default_rng(n)
                t, I, on, tf, F = c_mock.simulate(g, rng, model, sess)
                return c_rhythm.end_features(t, I, on[-1]), dict(t=t, I=I, compliance=np.zeros(len(t), bool),
                                                                    onsets_ms=on * 1000, force_t_ms=tf * 1000, force_N=F)
            cfgc = load_json(os.path.join(HERE, "config_c_mock.json"))
            run_trials(cfgc, gaps, run, mt, 3, extra={"y": yc}, log=lambda *_: None)
            rows = c_analyze.load_session(run)
            yy = c_analyze.stack(rows, "y").ravel().astype(int)
            res[model] = {k: c_analyze.within_cv(c_analyze.stack(rows, k), yy)[0] for k in ("end3", "force_end3")}
            peaks = [np.mean([r["peak"] for r in rows if r["y"] == c]) for c in range(4)]
            assert max(peaks) / min(peaks) < 1.1
        print(f"   C 끝 3개 균형정확도: 모의 기억 {res['memory']['end3']:.2f}, 모의 무기억 {res['memoryless']['end3']:.2f}, 힘만 {res['memory']['force_end3']:.2f}")
        assert res["memory"]["end3"] > 0.6 and res["memoryless"]["end3"] < 0.45 and res["memory"]["force_end3"] < 0.45
        ok("C 모의 기록 → 단서 점검 → 분류 경로")

        # 12) 보드 통신: 정상 응답 수락, 개수 틀림·거부(E) 줄은 오류
        from board_collect import board_trial_fn

        class FakeSerial:
            def __init__(self, lines):
                self.lines = [l.encode() + b"\n" for l in lines]
            def reset_input_buffer(self):
                pass
            def write(self, b):
                self.sent = b
            def readline(self):
                return self.lines.pop(0) if self.lines else b""
        nf = 4
        good = ["S,7," + ",".join(["1.5"] * nf), "V,7," + ",".join(["0.3"] * nf), "P,7," + ",".join(["50100"] * nf),
                "R,7," + ",".join(["49900"] * nf), "Q,7,0"]
        st, raw = board_trial_fn(FakeSerial(good), 1, nf, 1)(7, np.array([0.5]))
        assert len(st) == nf and raw["period_us"][0] == 50100
        for lines in (good[:1] + ["V,7,0.3"] + good[2:], ["E,7,bad_value"], []):
            try:
                board_trial_fn(FakeSerial(lines), 1, nf, 1)(7, np.array([0.5])); raise AssertionError
            except (RuntimeError, TimeoutError):
                pass
        ok("보드 통신 형식 검사 (모의 직렬 포트)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n모두 통과 ({len(passed)}개). 이것은 코드 흐름 시험이며 실제 장비·소자 검증이 아닙니다.")


if __name__ == "__main__":
    main()
