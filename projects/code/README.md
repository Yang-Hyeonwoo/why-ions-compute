# 프로젝트 코드 묶음

사이트의 프로젝트 A·B·C 페이지와 같이 쓰는 실행 파일입니다. 명령은 모두 `python` 폴더에서 입력합니다.

## 검증 상태 (2026-10-29)

| 대상 | 한 것 | 하지 않은 것 |
|---|---|---|
| Python | 문법 확인. 모의 장비로 `run_tests.py` 12개 통과. 이 zip을 새 폴더에 풀어 A0 명령·A1 모의·C 모의 분석·헤더 내보내기를 순서대로 실행해 결과와 그래프가 나오는 것 확인 | 실제 Keithley·보드·tapper 연결, MIT-BIH 내려받기(`ecg_prep.py`), `c_run.py`·`board_collect.py`의 실제 장비 실행 |
| 펌웨어 (`firmware/`) | 사람이 코드를 읽어 확인 | **컴파일, 보드 업로드, 실물 동작 모두 미검증** |
| 회로 | 설계안 | 저항·RC 모의 소자로의 실측 |

모의 장비는 코드 흐름을 확인하는 장난감 모델입니다. 모의 결과는 실제 소자 성능에 대해 아무것도 말해 주지 않습니다.

## 설치

```bash
cd python
python -m pip install -r requirements.txt
```

## 장비 없이 처음 해 보기 (A0)

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
| `config_board_example.json` | B5 보드 측정 | 복사해 `config_board.json`으로: `device`, `R_meas_ohm`, `R_lim_ohm`, `v_limit_V` |
| `config_c_mock.json` | C 모의 연습 (`c_mock.py`) | 고칠 것 없음 |
| `config_c_example.json` | C 실제 장비 (`c_run.py`) | 복사해 `config_c.json`으로: `addr`, `compliance_A`, `v_limit_V`, `device`, `read_V` |

## 파일

| 파일 | 하는 일 |
|---|---|
| `python/smu.py` | Keithley 2400 드라이버(안전 종료) + 모의 장비(resistor, series_rc, memory) |
| `python/common.py` | manifest, 원자적 저장, 재개 조건 비교, 그래프 한글 글꼴 |
| `python/measure_seq.py` | 입력 → 마스킹 펄스 → 상태 저장 (이어서 하기 지원) |
| `python/plot_run.py` | 시행 하나의 시간별 전압·전류 그래프 |
| `python/a1_tests.py` | A1: I–V(`iv`), 쓰기–쉬기–읽기(`wrr`), 짝펄스(`ppf`) + 그래프 |
| `python/tasks.py` | A2 합성 시간 패턴 과제, MC 입력 |
| `python/mc.py` | 기억 용량 + null 비교 |
| `python/readout.py` | fold 안 표준화 + 그룹 교차검증 readout (`--end-only`) |
| `python/ecg_prep.py` | MIT-BIH 박동 준비 (오프라인 경로) |
| `python/make_config_h.py` | B5: 설정 파일 → 보드용 `config.h` |
| `python/board_collect.py` | B5: 보드로 입력 보내고 상태·실제 소자 전압·시간 받기 |
| `python/export_mcu.py` | readout·측정 조건 → B6용 `config.h`·`weights.h`·`ref_vectors.h`·`inputs_test.h` |
| `python/c_rhythm.py` | C 리듬 일정(`rhythm.npz`) 만들기, 끝 판독 특징 |
| `python/c_mock.py` | C 모의 기록 (장비 없이 분석 연습) |
| `python/c_run.py` | C 실제 실험 실행 (소스미터 + tapper) |
| `python/c_analyze.py` | C 분석: 쉬운 단서 점검 → 특징 → 같은 세션 / 새 세션 결과 표 |
| `python/sync_firmware.py` | `firmware/common/device_io.h`를 각 스케치로 복사 |
| `firmware/B4_test` | 저항 시험, DAC 출력 보정(소자를 뺀 상태), EEPROM 안전 코드 |
| `firmware/B5_collect` | 엄격한 입력 검사 후 펄스열 실행, 펄스 끝 전류·전압·시간 보고 |
| `firmware/B6_standalone` | 점수 일치 자체 점검 → 저장 입력 재생·판단·알림 |
| `firmware/C_tapper` | onset 간격 리듬 누르기 + 힘–시간 기록 |

`firmware/*/config.h` 등 헤더 예시는 모의 장비로 만든 값입니다. 실제 측정 뒤 `make_config_h.py`(B5)·`export_mcu.py`(B6)로 다시 만드세요.

기준 플랫폼: ESP32 DevKitC (ESP32-WROOM-32E), Arduino-ESP32 core 3.x, Adafruit MCP4725 / ADS1X15 / SSD1306 / GFX, ESP32Servo, HX711(bogde).
