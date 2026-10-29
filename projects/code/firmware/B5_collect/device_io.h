// device_io.h — B 단계 공통: DAC로 소자 전압 걸기, ADS1115로 전압·전류 읽기, 펄스열 실행.
// 기준 플랫폼: ESP32 DevKitC (ESP32-WROOM-32E) · Arduino-ESP32 core 3.x
// 라이브러리: Adafruit MCP4725, Adafruit ADS1X15 (라이브러리 관리자)
// 상태: 컴파일·실물 동작 미검증. 저항(가짜 소자)으로 먼저 시험할 것.
// 이 파일은 각 스케치 폴더에 복사해 둔다 (아두이노는 다른 폴더의 파일을 바로 포함하지 못함).
#pragma once
#include <Wire.h>
#include <math.h>
#include <Adafruit_MCP4725.h>
#include <Adafruit_ADS1X15.h>

// ---------- 내 배선에 맞게 고칠 값 ----------
#define PIN_SDA 21
#define PIN_SCL 22
#define DAC_ADDR 0x60          // I2C 스캐너로 확인 (호환품 0x60, Adafruit 0x62 등)
#define ADC_ADDR 0x48          // ADS1115 ADDR → GND
// #define MEAS_SHUNT          // 션트 저항 방식이면 이 줄의 // 를 지운다 (기본: TIA)
const float R_MEAS = 150e3f;   // TIA 피드백 저항 R_f 또는 션트 저항 R_s [Ω] — 멀티미터로 잰 실제 값
float DAC_SLOPE = 3.30f / 4095.0f;   // B4 보정 결과 [V/코드] — DAC 출력 핀 전압 = DAC_SLOPE × 코드 + DAC_OFS
float DAC_OFS = 0.0f;                // B4 보정 결과 [V]

// ADS1115 입력 배치 (그림 ④·B4 표와 같음)
//   TIA : A0 = 소자 ① 위쪽 단자 (R_lim·J1 뒤), A1 = V_ref, A2 = TIA 출력(핀 7), A3 = V_ref
//   션트: A0 = 소자 ① 위쪽 단자, A1 = 소자 ② 아래쪽(= 션트 위쪽), A2 = 션트 위쪽(A1과 같은 점), A3 = V_ref(= 션트 아래쪽)
Adafruit_MCP4725 dac;
Adafruit_ADS1115 ads;
float VREF = 1.65f;          // 시작할 때 A3에서 실제로 잰다
uint32_t adcReadUs = 1500;   // 시작할 때 실제로 잰다 (ADC 1회 변환 + I2C)
bool ioReady = false;

// DAC 보정의 뜻: "DAC 출력 핀 전압 = DAC_SLOPE × 코드 + DAC_OFS" (전류가 흐르지 않을 때 잰 값).
// 이것은 소자 전압을 맞추는 되먹임 제어가 아니다. 전류 I가 흐르면
//   소자 전압 = DAC 출력 − V_ref − I × R_lim  (션트 방식이면 − I × R_s 도)
// 이므로 실제 소자 전압은 매 펄스 끝에 A0−A1로 따로 재서 기록한다 (PulseLog.vDev).
int dacCodeForOutput(float vOut) {
  long c = lroundf((vOut - DAC_OFS) / DAC_SLOPE);
  return (int)constrain(c, 0L, 4095L);
}
int dacCodeFor(float vdev) { return dacCodeForOutput(VREF + vdev); }   // 전류가 없을 때 소자 전압이 vdev가 되는 코드

// 범위를 벗어나면 자르지 않고 거부한다. I²C 쓰기가 실패해도 false.
bool setDeviceV(float v, float vLimit) {
  if (!isfinite(v) || fabsf(v) > vLimit) return false;
  return dac.setVoltage(dacCodeFor(v), false);
}

float readDeviceV() {                       // 소자 양끝 실제 전압 [V] = A0 − A1
  ads.setGain(GAIN_TWO);                    // ±2.048 V (각 핀의 절대 전압은 여전히 0–3.3 V 안이어야 함)
  return ads.computeVolts(ads.readADC_Differential_0_1());
}

float readCurrent_nA(bool *sat) {           // 소자 전류 [nA], sat: 측정 범위를 벗어났는지
#ifdef MEAS_SHUNT
  ads.setGain(GAIN_SIXTEEN);                // ±0.256 V, 한 칸 7.8 µV
  int16_t raw = ads.readADC_Differential_2_3();
  float i = ads.computeVolts(raw) / R_MEAS;          // V_s = +I·R_s (전류가 위→아래로 흐를 때 +)
  if (sat) *sat = (raw >= 32700 || raw <= -32700);   // ADC 범위 끝
#else
  ads.setGain(GAIN_TWO);
  int16_t raw = ads.readADC_Differential_2_3();
  float i = -ads.computeVolts(raw) / R_MEAS;         // TIA: V_out − V_ref = −I·R_f
  // op-amp 출력이 전원 끝(0 V·3.3 V) 근처면 포화 → 가상 기준점이 깨져 소자 전압도 틀어진다.
  // 이때 ADC는 범위 안이라 raw만으로는 모른다 → 출력 크기로 판단 (여유 0.15 V)
  if (sat) *sat = fabsf(ads.computeVolts(raw)) > VREF - 0.15f;
#endif
  return i * 1e9f;
}

// 시작 점검. 하나라도 이상하면 false → 소자를 구동하지 않는다.
bool ioBegin() {
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  if (!dac.begin(DAC_ADDR)) return false;
  if (!ads.begin(ADC_ADDR)) return false;
  ads.setDataRate(RATE_ADS1115_860SPS);
  ads.setGain(GAIN_ONE);
  VREF = ads.computeVolts(ads.readADC_SingleEnded(3));
  if (VREF < 1.4f || VREF > 1.9f) return false;      // 기준 전압 회로 이상
  if (!dac.setVoltage(dacCodeFor(0.0f), false)) return false;
  uint32_t t = micros();
  bool s;
  readCurrent_nA(&s);
  readDeviceV();
  adcReadUs = (micros() - t) / 2;                    // 변환 1회(+I²C) 평균. 펄스 끝에 2회 읽는다
  ioReady = true;
  return true;
}

// MCP4725는 전원이 켜질 때 EEPROM에 저장된 코드를 출력한다 (펌웨어가 돌기 전).
// '소자 0 V' 코드를 EEPROM에 한 번 저장해 두면 켜지는 순간의 위험이 줄지만,
// V_ref가 아직 0 V인 순간·ESP32 리셋 중의 과도 상태까지 막지는 못한다 → 소자는 점퍼(J1)로 나중에 연결.
void storeSafePowerOnCode() { dac.setVoltage(dacCodeFor(0.0f), true); }

// 펄스 하나의 기록. 시간은 모두 '그 펄스의 DAC 명령을 보내기 시작한 순간 = 0' 기준 [µs].
//   cmdUs     : DAC 명령(I²C 쓰기)이 끝난 시각. 이때부터 DAC 출력이 바뀌기 시작
//   readEndUs : 전류 → 전압 순서로 두 번 변환한 읽기가 끝난 시각 (펄스 끝 부근)
//   periodUs  : 다음 펄스 명령 시작까지 = 이 전압 '명령'이 유지된 시간
// 소자에 '실제로 목표 전압이 걸린 시간'은 이 값들로 알 수 없다. DAC 출력 정착 시간(데이터시트)과
// R_lim × 소자 정전용량의 충전 시간이 더해지기 때문. 펄스 끝 실제 소자 전압 vDev로 도달 여부를 확인한다.
struct PulseLog {
  float iNa, vDev;
  uint32_t cmdUs, readEndUs, periodUs;
  bool sat;
};

// 실패 시 err에 이유: not_ready, theta_too_short, out_of_range, dac_i2c, dac_i2c_end
// 한계: ADC 통신이 끊기면 라이브러리가 변환 완료를 기다리며 멈출 수 있다 (라이브러리 버전에 따라 확인 필요).
//       그동안 DAC는 마지막 전압을 유지한다 → J1을 빼서 끊는다.
template <int LL, int MM>
bool runSequence(const float *u, const float (&mask)[MM], float v0, float va, uint32_t thetaUs, uint32_t restMs,
                 float vLimit, PulseLog *log, int *nsat, const char **err) {
  *err = "";
  uint32_t readBudget = 2 * adcReadUs;
  if (!ioReady) { *err = "not_ready"; return false; }
  if (thetaUs < readBudget + 1000) { *err = "theta_too_short"; return false; }
  for (int i = 0; i < LL; i++)                       // 먼저 모든 전압을 검사 → 하나라도 밖이면 시작 안 함
    for (int j = 0; j < MM; j++) {
      float v = v0 + va * u[i] * mask[j];
      if (!isfinite(v) || fabsf(v) > vLimit) { *err = "out_of_range"; return false; }
    }
  if (!setDeviceV(0.0f, vLimit)) { *err = "dac_i2c"; return false; }
  delay(restMs);
  *nsat = 0;
  int k = 0;
  uint32_t tPrev = 0;
  for (int i = 0; i < LL; i++)
    for (int j = 0; j < MM; j++, k++) {
      uint32_t t0 = micros();
      if (k > 0) log[k - 1].periodUs = t0 - tPrev;
      bool ok = setDeviceV(v0 + va * u[i] * mask[j], vLimit);
      log[k].cmdUs = micros() - t0;
      if (!ok) {                                     // DAC 쓰기 실패: 0 V를 한 번 더 시도하고 멈춤
        setDeviceV(0.0f, vLimit);
        *err = "dac_i2c";
        return false;
      }
      uint32_t readAt = thetaUs - readBudget;        // 두 번의 읽기가 펄스 끝에 끝나도록
      while (micros() - t0 + 2000 < readAt) delay(1);
      while (micros() - t0 < readAt) {}
      bool s;
      log[k].iNa = readCurrent_nA(&s);
      log[k].vDev = readDeviceV();
      log[k].readEndUs = micros() - t0;
      log[k].sat = s;
      if (s) (*nsat)++;
      tPrev = t0;
    }
  log[k - 1].periodUs = micros() - tPrev;
  if (!setDeviceV(0.0f, vLimit)) { *err = "dac_i2c_end"; return false; }
  return true;
}
