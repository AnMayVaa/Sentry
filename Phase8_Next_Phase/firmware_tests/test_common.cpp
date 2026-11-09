#include "../Phase8_RX_Node/sentry_common.h"
#include "testkit.h"
#include <string.h>
using namespace sentry;

TEST(button_short_press_fires_on_release) {
  Button b(30, 2000);
  uint32_t t = 0;
  int shorts = 0, longs = 0;
  for (; t < 300; t++) { auto e = b.update(t >= 10, t); shorts += e == BTN_SHORT_PRESS; longs += e == BTN_LONG_PRESS; }
  CHECK(shorts == 0);
  for (; t < 400; t++) { auto e = b.update(false, t); shorts += e == BTN_SHORT_PRESS; longs += e == BTN_LONG_PRESS; }
  CHECK(shorts == 1); CHECK(longs == 0);
}
TEST(button_long_press_fires_once_while_held_and_no_short_after) {
  Button b(30, 2000);
  int shorts = 0, longs = 0; uint32_t fired_at = 0;
  for (uint32_t t = 0; t < 5000; t++) {
    auto e = b.update(t < 4000, t);
    if (e == BTN_LONG_PRESS) { longs++; fired_at = t; }
    shorts += e == BTN_SHORT_PRESS;
  }
  CHECK(longs == 1); CHECK(shorts == 0);
  CHECK(fired_at >= 2000 && fired_at <= 2040);
}
TEST(button_down_event_on_confirmed_press) {
  Button b(30, 2000);
  int downs = 0; uint32_t at = 0;
  for (uint32_t t = 0; t < 3000; t++) { auto e = b.update(t >= 100, t); if (e == BTN_DOWN) { downs++; at = t; } }
  CHECK(downs == 1); CHECK(at == 130);
}
TEST(button_ignores_contact_bounce) {
  Button b(30, 2000);
  int events = 0;
  for (uint32_t t = 0; t < 1000; t++) events += b.update((t / 5) % 2 == 0 && t < 200, t) != BTN_NONE;  // chatter every 5 ms
  CHECK(events == 0);
}
TEST(button_survives_millis_wraparound) {
  Button b(30, 2000);
  uint32_t start = 0xFFFFFFFFu - 1000; int longs = 0;
  for (uint32_t i = 0; i < 3000; i++) longs += b.update(true, start + i) == BTN_LONG_PRESS;
  CHECK(longs == 1);
}
TEST(pattern_fall_rhythm) {
  PatternPlayer p; p.start(&PATTERN_FALL, 1000);
  CHECK(p.output(1000)); CHECK(p.output(1149)); CHECK(!p.output(1150)); CHECK(!p.output(1249)); CHECK(p.output(1250));
  for (uint32_t t : {100000u, 100123u, 100180u, 777777u})
    CHECK(p.output(t) == (((t - 1000) % 250) < 150)); // stays in rhythm, even after long gaps
}
TEST(pattern_non_loop_ends) {
  PatternPlayer p; p.start(&PATTERN_CHIRP, 0);
  CHECK(p.output(10)); CHECK(!p.output(50)); CHECK(!p.output(200)); CHECK(!p.active());
}
TEST(pattern_sos_is_morse) {
  // dots 150, dashes 450: count on-times
  int dots = 0, dashes = 0;
  for (int i = 0; i < PATTERN_SOS.count; i += 2) { dots += PATTERN_SOS.steps[i] == 150; dashes += PATTERN_SOS.steps[i] == 450; }
  CHECK(dots == 6); CHECK(dashes == 3); CHECK(PATTERN_SOS.count % 2 == 0);
}
TEST(parse_messages) {
  char loc[64];
  CHECK(parseAlarm("FALL_ALERT:Bath Room", loc, sizeof loc) == MSG_FALL); CHECK(strcmp(loc, "Bath Room") == 0);
  CHECK(parseAlarm("SOS_ALERT,Bed Room\n", loc, sizeof loc) == MSG_SOS); CHECK(strcmp(loc, "Bed Room") == 0);
  CHECK(parseAlarm("SOS_ALERT:[192.168.1.20] Bath Room", loc, sizeof loc) == MSG_SOS); CHECK(strcmp(loc, "Bath Room") == 0);
  CHECK(parseAlarm("  ALARM_TRIGGER", loc, sizeof loc) == MSG_FALL); CHECK(loc[0] == 0);
  CHECK(parseAlarm("FALL_SILENCE", loc, sizeof loc) == MSG_SILENCE);
  CHECK(parseAlarm("ALARM_STOP", loc, sizeof loc) == MSG_SILENCE);
  CHECK(parseAlarm("SILENCE\r\n", loc, sizeof loc) == MSG_SILENCE);
  CHECK(parseAlarm("ROUTER_STIMULUS", loc, sizeof loc) == MSG_NONE);
  CHECK(parseAlarm("ALARM_READY:1.2.3.4", loc, sizeof loc) == MSG_NONE);
  CHECK(parseAlarm("", loc, sizeof loc) == MSG_NONE);
  CHECK(parseAlarm(nullptr, loc, sizeof loc) == MSG_NONE);
  char tiny[5];
  CHECK(parseAlarm("FALL_ALERT:Very Long Room Name", tiny, sizeof tiny) == MSG_FALL); CHECK(strcmp(tiny, "Very") == 0);
  CHECK(parseAlarm("FALL_ALERT:[unterminated", loc, sizeof loc) == MSG_FALL); CHECK(strcmp(loc, "[unterminated") == 0);
}
TEST(repeat_filter) {
  RepeatFilter f(8000);
  CHECK(f.allow(MSG_SOS, "Bath Room", 0));
  f.silenced(MSG_SOS, "Bath Room", 1000);
  CHECK(!f.allow(MSG_SOS, "Bath Room", 1500));
  CHECK(f.allow(MSG_FALL, "Bath Room", 1500));   // other kind
  CHECK(f.allow(MSG_SOS, "Bed Room", 1500));     // other room
  CHECK(f.allow(MSG_SOS, "Bath Room", 9000));    // after holdoff
}
TEST(retry_sends_n_spaced) {
  Retry r; r.start(3, 250, 100);
  std::vector<uint32_t> at;
  for (uint32_t t = 100; t < 2000; t++) if (r.due(t)) at.push_back(t);
  CHECK(at.size() == 3); CHECK(at[0] == 100); CHECK(at[1] == 350); CHECK(at[2] == 600); CHECK(!r.pending());
}
int main() { return run_all("sentry_common"); }
