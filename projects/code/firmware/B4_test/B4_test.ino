// B4_test — 저항(가짜 소자)으로 회로 확인 + DAC 보정 + EEPROM 안전 코드 저장
// 시리얼 모니터(115200)에서 명령:  s = 전압 계단 시험(저항 연결),  c = DAC 출력 보정(소자·저항을 뺀 상태),  e = EEPROM에 '소자 0 V' 저장
// 상태: 컴파일·실물 동작 미검증
#include "device_io.h"
const float V_LIMIT = 1.0f;   // 이 시험에서 거부할 전압 상한 (저항 시험용 예시)

void setup() {
  Serial.begin(115200);
  delay(500);
  if (!ioBegin()) {
    Serial.println("E,-1,io_init (I2C 주소·배선·기준 전압 확인). 소자를 구동하지 않습니다.");
    return;
  }
  Serial.printf("READY VREF=%.4f V, ADC 1회 %lu us\n", VREF, (unsigned long)adcReadUs);
}

void stepTest() {
  const float vs[] = {-1.0f, -0.5f, 0.0f, 0.5f, 1.0f};
  for (float v : vs) {
    if (!setDeviceV(v, V_LIMIT)) { Serial.println("거부됨"); continue; }
    delay(300);                               // 저항이면 금방 안정. RC 모의 소자면 이 시간 동안 변화를 볼 것
    bool sat;
    float vd = readDeviceV(), i = readCurrent_nA(&sat);
    Serial.printf("요청 %+.3f V | 실제 %+.4f V | %+.2f nA%s | 기대(100k) %+.1f nA\n",
                  v, vd, i, sat ? " [포화]" : "", vd / 100e3f * 1e9f);
  }
  setDeviceV(0.0f, V_LIMIT);
}

// DAC 출력 보정: 전류가 흐르지 않아야 A0(소자 위쪽 단자) = DAC 출력이 된다.
// → 소자·저항을 빼서 열어 두고(J1은 꽂은 채) 실행한다. 전류가 보이면 거부한다.
void calib() {
  bool sat;
  dac.setVoltage(2048, false);
  delay(50);
  float i0 = readCurrent_nA(&sat);
  if (fabsf(i0) > 5.0f) {
    Serial.printf("전류 %.1f nA가 흐릅니다. 소자/저항을 빼고(열린 상태) 다시 c 하세요.\n", i0);
    setDeviceV(0.0f, V_LIMIT);
    return;
  }
  const int codes[] = {500, 1500, 2500, 3500};
  float sx = 0, sy = 0, sxx = 0, sxy = 0;
  ads.setGain(GAIN_ONE);
  for (int c : codes) {
    dac.setVoltage(c, false);
    delay(50);
    float v = ads.computeVolts(ads.readADC_SingleEnded(0));
    Serial.printf("코드 %d → %.4f V\n", c, v);
    sx += c; sy += v; sxx += (float)c * c; sxy += c * v;
  }
  float n = 4, slope = (n * sxy - sx * sy) / (n * sxx - sx * sx), ofs = (sy - slope * sx) / n;
  Serial.printf("device_io.h에 넣을 값: DAC_SLOPE = %.8ff; DAC_OFS = %.5ff;\n", slope, ofs);
  setDeviceV(0.0f, V_LIMIT);
}

void loop() {
  if (!ioReady || !Serial.available()) return;
  char c = Serial.read();
  if (c == 's') stepTest();
  else if (c == 'c') calib();
  else if (c == 'e') { storeSafePowerOnCode(); Serial.println("EEPROM 저장 완료 (자주 하지 말 것)"); }
}
