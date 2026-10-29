"""소스미터(SMU) 드라이버: Keithley 2400 계열(SCPI)과, 장비 없이 연습하는 모의 장비.

안전 원칙
- 연결해도 출력은 켜지지 않는다. enable()을 불러야 켜진다.
- with 문으로 쓰면, 정상 종료·오류·Ctrl+C 모두에서 close()가 0 V → 출력 OFF를 '시도'한다.
  각 단계가 실패해도 다음 단계를 계속 시도하고, 실패 내용은 close_errors에 남긴다.
- 한계: USB/GPIB 연결이 끊기면 PC는 장비를 끌 수 없다. 그때는 장비 앞면 OUTPUT 버튼으로 끈다.
- compliance(전류 제한)는 "전류가 이 값을 넘지 않게 전압을 낮추는" 장비 동작이다.
  프로그램을 멈추지 않는다. 그래서 매 측정마다 제한에 걸렸는지(compliance 플래그)를 기록한다.
- v_limit_V는 이 코드가 거부하는 전압 크기다. 소자의 안전 범위가 아니라, 내가 정한 '실험 계획의 상한'이다.

Keithley 2400 이외의 모델(2450, 26xx)은 명령이 다르다. 이 파일을 Claude에게 주고 모델에 맞게 바꿔 달라고 하자.
"""
import math
import time


class SMUError(RuntimeError):
    pass


class Keithley2400:
    # 2400 상태 워드에서 compliance를 뜻하는 비트. ← 2400 사용자 설명서의 'status word' 표에서 확인 (실물 검증 대기)
    COMPLIANCE_BIT = 3

    def __init__(self, addr, *, compliance_A, v_limit_V, nplc=0.1, i_range_A=None, v_range_V=2.0, timeout_ms=10000):
        self.addr, self.compliance_A, self.v_limit_V = addr, compliance_A, v_limit_V
        self.nplc, self.i_range_A, self.v_range_V, self.timeout_ms = nplc, i_range_A, v_range_V, timeout_ms
        self.dev = self.rm = None
        self.enabled = False
        self.close_errors = []
        self.idn = ""

    # ---- 열기·닫기 ----
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False                      # 오류는 숨기지 않고 그대로 올린다

    def open(self):
        import pyvisa
        self.rm = pyvisa.ResourceManager()
        self.dev = self.rm.open_resource(self.addr)
        self.dev.timeout = self.timeout_ms
        self.idn = self.dev.query("*IDN?").strip()
        if "MODEL 24" not in self.idn.upper():
            raise SMUError(f"2400 계열이 아닙니다: {self.idn!r} → 명령을 모델에 맞게 바꿔야 합니다")
        w = self.dev.write
        w("*RST")                          # 초기화 후 출력은 OFF 상태
        w(":SOUR:FUNC VOLT")
        w(":SOUR:VOLT:MODE FIXED")
        w(f":SOUR:VOLT:RANG {self.v_range_V}")
        w(':SENS:FUNC "CURR"')
        w(f":SENS:CURR:PROT {self.compliance_A}")
        if self.i_range_A:
            w(f":SENS:CURR:RANG {self.i_range_A}")   # 고정 범위: 범위 전환 때문에 생기는 끊김·지연이 없음
        else:
            w(":SENS:CURR:RANG:AUTO ON")              # 처음 탐색용
        w(f":SENS:CURR:NPLC {self.nplc}")
        w(":FORM:ELEM VOLT,CURR,TIME,STAT")
        w(":SOUR:VOLT 0")
        err = self.dev.query(":SYST:ERR?").strip()
        if not err.startswith("0"):
            raise SMUError(f"설정 중 장비 오류: {err}")

    def enable(self):
        """출력 켜기. 이 함수를 부르기 전에는 소자에 전압이 걸리지 않는다."""
        self.set_v(0.0)
        self.dev.write(":OUTP ON")
        self.enabled = True

    def close(self):
        steps = [("0 V", lambda: self.dev.write(":SOUR:VOLT 0")),
                 ("출력 OFF", lambda: self.dev.write(":OUTP OFF")),
                 ("연결 닫기", lambda: self.dev.close()),
                 ("VISA 닫기", lambda: self.rm.close())]
        for name, fn in steps:
            try:
                if self.dev is not None:
                    fn()
            except Exception as e:          # 실패해도 다음 단계를 계속 시도
                self.close_errors.append(f"{name}: {e}")
        self.enabled = False
        if self.close_errors:
            print("!! 장비 종료 중 실패:", self.close_errors, "→ 장비 앞면에서 출력이 꺼졌는지 직접 확인하세요")

    # ---- 측정 ----
    def set_v(self, v):
        if not math.isfinite(v) or abs(v) > self.v_limit_V:
            raise SMUError(f"요청 전압 {v} V가 계획 상한 ±{self.v_limit_V} V를 벗어남")
        self.dev.write(f":SOUR:VOLT {v:.5f}")

    def read(self):
        """측정 1회 → dict(t_host, V, I, t_inst, compliance). t_host는 PC가 응답을 받은 시각."""
        if not self.enabled:
            raise SMUError("출력이 꺼져 있습니다. enable()을 먼저 부르세요")
        v, i, t_inst, stat = map(float, self.dev.query(":READ?").split(",")[:4])
        return dict(t_host=time.perf_counter(), V=v, I=i, t_inst=t_inst,
                    compliance=bool(int(stat) >> self.COMPLIANCE_BIT & 1))

    def hold(self, v, dur_s):
        """전압 v를 '대략' dur_s초 유지하며 계속 읽는다. 실제 유지 시간은 기록된 시각으로 확인할 것."""
        t_set = time.perf_counter()
        self.set_v(v)
        out = [self.read()]
        while time.perf_counter() - t_set < dur_s:
            out.append(self.read())
        for r in out:
            r["V_set"], r["t_set"] = v, t_set
        return out


class MockSMU:
    """장비 없이 연습·시험용 모의 소스미터. 실제 시간을 기다리지 않고 가상 시계로 진행한다.

    model="resistor": 옴의 법칙만 (기억 없음)
    model="series_rc": 저항 R과 커패시터 C를 직렬로 (A0-5 실험). 전압을 바꾸면 전류가 τ=RC로 0을 향해 줄어든다
    model="rc":       저항 + 병렬 커패시터 충전 전류 (전압을 바꾼 직후 잠깐 큰 전류, 저항 상태는 변하지 않음)
    model="memory":   위 RC에 더해, 전압 이력에 따라 천천히 변하고 τ로 돌아오는 전도도 상태 x
    이것은 실제 소자 모델이 아니라 코드 흐름을 확인하기 위한 장난감이다.
    """

    def __init__(self, *, model="memory", R=1e6, C=2e-7, tau=0.5, gain=0.8, compliance_A=1e-4, v_limit_V=2.0,
                 read_dt=0.02, noise=2e-10, seed=0, fail_after=None, **_):
        import numpy as np
        self.np = np
        self.model, self.R, self.C, self.tau, self.gain = model, R, C, tau, gain
        self.compliance_A, self.v_limit_V, self.read_dt, self.noise = compliance_A, v_limit_V, read_dt, noise
        self.rng = np.random.default_rng(seed)
        self.fail_after, self.n_reads = fail_after, 0
        self.t, self.v, self.v_prev, self.t_change, self.x, self.vc = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        self.enabled, self.close_errors, self.idn = False, [], "MOCK SMU"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def open(self):
        pass

    def reseed(self, seed):
        self.rng = self.np.random.default_rng(seed)

    def enable(self):
        self.set_v(0.0)
        self.enabled = True

    def close(self):
        self.v, self.enabled = 0.0, False

    def set_v(self, v):
        if not math.isfinite(v) or abs(v) > self.v_limit_V:
            raise SMUError(f"요청 전압 {v} V가 계획 상한 ±{self.v_limit_V} V를 벗어남")
        self.v_prev, self.v, self.t_change = self.v, v, self.t

    def _advance(self, dt):
        if self.model == "memory":     # dx/dt = (gain·V − x)/τ  (V>0이면 x가 늘고, 0 V에서 τ로 회복)
            target = self.gain * self.v
            self.x = target + (self.x - target) * math.exp(-dt / self.tau)
        if self.model == "series_rc":  # 커패시터 전압 vc가 걸어 준 전압 v를 향해 τ=RC로 따라감
            self.vc = self.v + (self.vc - self.v) * math.exp(-dt / (self.R * self.C))
        self.t += dt

    def read(self):
        if not self.enabled:
            raise SMUError("출력이 꺼져 있습니다. enable()을 먼저 부르세요")
        self.n_reads += 1
        if self.fail_after is not None and self.n_reads > self.fail_after:
            raise IOError("모의 통신 오류")
        self._advance(self.read_dt)
        if self.model == "series_rc":
            i = (self.v - self.vc) / self.R
        else:
            g = (1.0 / self.R) * (1.0 + (self.x if self.model == "memory" else 0.0))
            i = g * self.v * (1 + (0.3 * self.v * self.v if self.model == "memory" else 0.0))                     # 약한 비선형
        if self.model in ("rc", "memory"):
            tc = self.R * self.C / 10
            i += self.C * (self.v - self.v_prev) / tc * math.exp(-(self.t - self.t_change) / tc)
        i += self.noise * self.rng.standard_normal()
        comp = abs(i) > self.compliance_A
        if comp:
            i = math.copysign(self.compliance_A, i)
        return dict(t_host=self.t, V=self.v, I=i, t_inst=self.t, compliance=comp)

    def hold(self, v, dur_s):
        t_set = self.t
        self.set_v(v)
        out = [self.read()]
        while self.t - t_set < dur_s - 1e-12:
            out.append(self.read())
        for r in out:
            r["V_set"], r["t_set"] = v, t_set
        return out


def open_smu(inst_cfg, mock=False, **override):
    """설정(dict)으로 장비를 만든다. mock=True면 모의 장비."""
    kw = dict(inst_cfg)
    kw.update(override)
    if mock or kw.get("addr") == "MOCK":
        return MockSMU(**kw.get("mock", {}), compliance_A=kw["compliance_A"], v_limit_V=kw["v_limit_V"],
                       fail_after=kw.get("fail_after"))
    return Keithley2400(kw["addr"], compliance_A=kw["compliance_A"], v_limit_V=kw["v_limit_V"],
                        nplc=kw.get("nplc", 0.1), i_range_A=kw.get("i_range_A"), v_range_V=kw.get("v_range_V", 2.0))
