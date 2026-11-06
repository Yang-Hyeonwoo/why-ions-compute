# 프로젝트 코드 묶음

사이트의 프로젝트 P2·P3·P4 페이지와 같이 쓰는 실행 파일입니다. 명령은 모두 `python` 폴더에서 입력합니다.

## 검증 상태 (2026-11-03)

| 대상 | 한 것 | 하지 않은 것 |
|---|---|---|
| Python | 문법 확인. 모의 장비·합성 데이터로 `run_tests.py` 13개 통과. 이 zip을 새 폴더에 풀어 P2.0 명령·P2.1 모의·C 모의 분석·헤더 내보내기를 순서대로 실행해 결과와 그래프가 나오는 것 확인 | 실제 Keithley·보드·tapper 연결, MIT-BIH 내려받기(`ecg_prep.py`), `c_run.py`·`board_collect.py`의 실제 장비 실행 |
| 펌웨어 (`firmware/`) | NU40 DK용 컴파일 (아래 기록) | **보드 업로드, 실물 동작 미검증** |
| 회로 | 설계안 | 저항·RC 모의 소자로의 실측 |

모의 장비는 코드 흐름을 확인하는 장난감 모델입니다. 모의 결과는 실제 소자 성능에 대해 아무것도 말해 주지 않습니다.

## 설치

```bash
cd python
python -m pip install -r requirements.txt
```

## 장비 없이 처음 해 보기 (P2.0)

```bash
python run_tests.py
python tasks.py timing task.npz --n 20
python measure_seq.py config_example.json task.npz runs/practice_mem --mock --limit 5
python measure_seq.py config_example.json task.npz runs/practice_mem --mock
python plot_run.py runs/practice_mem --trial 0
python measure_seq.py config_example.json task.npz runs/practice_res --mock --mock-model resistor
python readout.py runs/practice_mem/checkpoint.npz task.npz --out practice_mem.joblib --end-only
python readout.py runs/practice_res/checkpoint.npz task.npz --out practice_res.joblib --end-only
python a1_tests.py wrr config_example.json runs/wrr_rc_mock --mock --mock-model series_rc --gaps 0.1,1,5
```

## 설정 파일

| 파일 | 용도 | 고칠 것 |
|---|---|---|
| `config_example.json` | A 모의 연습 (`addr: MOCK`) | 실제 장비용은 복사해 `config_real.json`으로: `addr`, `compliance_A`, `v_limit_V`, `device` |
| `config_board_example.json` | P3.5 보드 측정 | 복사해 `config_board.json`으로: `device`, `R_meas_ohm`, `R_lim_ohm`, `v_limit_V` |
| `config_c_mock.json` | C 모의 연습 (`c_mock.py`) | 고칠 것 없음 |
| `config_c_example.json` | C 실제 장비 (`c_run.py`) | 복사해 `config_c.json`으로: `addr`, `compliance_A`, `v_limit_V`, `device`, `read_V` |

## 파일

| 파일 | 하는 일 |
|---|---|
| `python/smu.py` | Keithley 2400 드라이버(안전 종료) + 모의 장비(resistor, series_rc, memory) |
| `python/common.py` | manifest, 원자적 저장, 재개 조건 비교, 그래프 한글 글꼴 |
| `python/measure_seq.py` | 입력 → 마스킹 펄스 → 상태 저장 (이어서 하기 지원) |
| `python/plot_run.py` | 시행 하나의 시간별 전압·전류 그래프 |
| `python/a1_tests.py` | P2.1: I–V(`iv`), 쓰기–쉬기–읽기(`wrr`), 짝펄스(`ppf`) + 그래프 |
| `python/tasks.py` | P2.2 합성 시간 패턴 과제, MC 입력 |
| `python/mc.py` | 기억 용량 + null 비교 |
| `python/readout.py` | fold 안 표준화 + 그룹 교차검증 readout (`--end-only`) |
| `python/ecg_prep.py` | MIT-BIH 박동 준비 (오프라인 경로) |
| `python/make_config_h.py` | P3.5: 설정 파일 → 보드용 `config.h` |
| `python/board_collect.py` | P3.5: 보드로 입력 보내고 상태·실제 소자 전압·시간 받기 |
| `python/export_mcu.py` | readout·측정 조건 → P3.6용 `config.h`·`weights.h`·`ref_vectors.h`·`inputs_test.h` |
| `python/c_rhythm.py` | C 리듬 일정(`rhythm.npz`) 만들기, 끝 판독 특징 |
| `python/c_mock.py` | C 모의 기록 (장비 없이 분석 연습) |
| `python/c_run.py` | C 실제 실험 실행 (소스미터 + tapper) |
| `python/c_analyze.py` | C 분석: 쉬운 단서 점검 → 특징 → 같은 세션 / 새 세션 결과 표 |
| `python/sync_firmware.py` | `firmware/common/device_io.h`를 각 스케치로 복사 |
| `python/b1_record.py` | P3.1a: 보드 버튼·조도 값을 CSV(`data/b1_taps.csv`)에 이어 붙이고 파형 그림, 누락·접점 튐·포화 개수 |
| `python/b1_memory.py` | P3.1b: 리듬 X/Y를 마지막 값·횟수·간격 규칙·누설 노드·작은 reservoir로 비교 (`--synthetic`, `--failures`) |
| `python/examples/b1_taps_example.csv` | P3.1 CSV 형식 예시 (합성, `source = synthetic`) |
| `firmware/B1a_rhythm` | 버튼1을 200 Hz로 읽어 `n,t_ms,btn,a0` 전송, 버튼2로 따라 칠 리듬 보여 주기 |
| `firmware/B4_test` | 저항 시험, DAC 출력 보정(소자를 뺀 상태), EEPROM 안전 코드 |
| `firmware/B5_collect` | 엄격한 입력 검사 후 펄스열 실행, 펄스 끝 전류·전압·시간 보고 |
| `firmware/B6_standalone` | 점수 일치 자체 점검 → 저장 입력 재생·판단·알림 |
| `firmware/C_tapper` | onset 간격 리듬 누르기 + 힘–시간 기록 |

`firmware/*/config.h` 등 헤더 예시는 모의 장비로 만든 값입니다. 실제 측정 뒤 `make_config_h.py`(P3.5)·`export_mcu.py`(P3.6)로 다시 만드세요.

기준 플랫폼: NUCODE NU40 DK (nRF52840), 보드 패키지 NUBoards nRF52 1.0.2 (보드 'NU40DK nRF52840'), Adafruit MCP4725 / ADS1X15 / SSD1306 / GFX, HX711(bogde). BLE·Servo는 보드 패키지에 들어 있음.
같은 펌웨어가 ESP32 DevKitC(Arduino-ESP32 core 3.x, ESP32Servo)에서도 컴파일되도록 보드별 부분을 `#if defined(ARDUINO_ARCH_ESP32)`로 나눴다(ESP32 컴파일은 미확인).
NU40 핀 번호: P0.xx → xx, P1.xx → 32 + xx. I²C = P0.26(SDA)·P0.27(SCL).
컴파일 확인(2026-11-02): arduino-cli 1.5.2, 보드 nucode:nrf52:nu40dk (NUBoards nRF52 1.0.2), Adafruit MCP4725 2.0.2 · ADS1X15 2.6.2 · SSD1306 2.5.17 · GFX 1.13.0 · BusIO 1.17.4, HX711 Arduino Library 0.7.5 → 펌웨어 4개 모두 오류 없음. 업로드·실물 동작은 미검증.
NU40에서 Serial을 쓰는 스케치는 `#include <Adafruit_TinyUSB.h>`가 있어야 링크된다(펌웨어에는 넣어 둠).

컴파일 확인(2026-11-03): arduino-cli 1.1.1, 같은 보드 패키지 → `B1a_rhythm` 오류 없음. 업로드·실물 동작은 미검증.

`data/` 폴더(내 기록)는 공개 코드 묶음(zip)과 저장소에 넣지 않습니다.
