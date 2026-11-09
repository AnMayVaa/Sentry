// ============================================================
// sentry_common.h  -  Sentry Phase 8 shared logic (no hardware calls)
//
// The SAME file is copied into Phase8_RX_Node/ and Phase8_Alert_Station/
// because Arduino only compiles files inside the sketch folder.
// firmware_tests/run_tests.sh checks the two copies are identical and
// unit-tests everything in here on a PC.
//
// Nothing here touches pins or Wi-Fi, so it is safe to test anywhere.
// ============================================================
#pragma once
#include <stdint.h>
#include <string.h>

namespace sentry {

// ---------------- Button (debounce + short / long press) ----------------
//
// Feed it the raw "is pressed" level every loop. It reports:
//   DOWN         once, as soon as a press is confirmed (after debounce)
//   SHORT_PRESS  once, on release, if the press was shorter than longMs
//   LONG_PRESS   once, as soon as the button has been held for longMs
//                (fires while still held so the user gets instant feedback;
//                 no SHORT_PRESS follows on release)
enum ButtonEvent : uint8_t { BTN_NONE = 0, BTN_DOWN, BTN_SHORT_PRESS, BTN_LONG_PRESS };

class Button {
 public:
  explicit Button(uint32_t debounceMs = 30, uint32_t longMs = 2000)
      : debounceMs_(debounceMs), longMs_(longMs) {}

  ButtonEvent update(bool rawPressed, uint32_t now) {
    if (rawPressed != raw_) {
      raw_ = rawPressed;
      rawSince_ = now;
    }
    ButtonEvent ev = BTN_NONE;
    if (raw_ != stable_ && (uint32_t)(now - rawSince_) >= debounceMs_) {
      stable_ = raw_;
      if (stable_) {
        pressStart_ = now;
        longFired_ = false;
        ev = BTN_DOWN;
      } else if (!longFired_) {
        ev = BTN_SHORT_PRESS;
      }
    }
    if (stable_ && !longFired_ && (uint32_t)(now - pressStart_) >= longMs_) {
      longFired_ = true;
      ev = BTN_LONG_PRESS;
    }
    return ev;
  }

  bool isHeld() const { return stable_; }
  // True while held but before the long press fired (used for "keep holding" feedback).
  bool isCharging() const { return stable_ && !longFired_; }
  uint32_t heldFor(uint32_t now) const { return stable_ ? (uint32_t)(now - pressStart_) : 0; }

 private:
  uint32_t debounceMs_, longMs_;
  bool raw_ = false, stable_ = false, longFired_ = false;
  uint32_t rawSince_ = 0, pressStart_ = 0;
};

// ---------------- On/off patterns for an ACTIVE buzzer and the LED ----------------
//
// A pattern is a list of durations in ms: ON, OFF, ON, OFF, ...
// An active buzzer only does on/off (it has its own oscillator), so every
// sound is a rhythm. Each alert has its own rhythm so people can tell them apart.
struct Pattern {
  const uint16_t* steps;
  uint8_t count;
  bool loop;
};

// Fall: fast urgent beeping, forever until silenced.
static const uint16_t FALL_STEPS[] = {150, 100};
// SOS: Morse "... --- ..." (dot 150 ms, dash 450 ms), forever until silenced.
static const uint16_t SOS_STEPS[] = {150, 150, 150, 150, 150, 450,
                                     450, 150, 450, 150, 450, 450,
                                     150, 150, 150, 150, 150, 1050};
// SOS sent: 3 quick chirps (tells the person "your SOS went out").
static const uint16_t CONFIRM_STEPS[] = {80, 80, 80, 80, 80, 300};
// Boot / Wi-Fi connected: 2 short beeps.
static const uint16_t BOOT_STEPS[] = {100, 100, 100, 100};
// Self-test: one long beep.
static const uint16_t TEST_STEPS[] = {1000, 200};
// Status chirp: one tiny beep.
static const uint16_t CHIRP_STEPS[] = {40, 60};

#define SENTRY_COUNT(a) (uint8_t)(sizeof(a) / sizeof((a)[0]))
static const Pattern PATTERN_FALL = {FALL_STEPS, SENTRY_COUNT(FALL_STEPS), true};
static const Pattern PATTERN_SOS = {SOS_STEPS, SENTRY_COUNT(SOS_STEPS), true};
static const Pattern PATTERN_CONFIRM = {CONFIRM_STEPS, SENTRY_COUNT(CONFIRM_STEPS), false};
static const Pattern PATTERN_BOOT = {BOOT_STEPS, SENTRY_COUNT(BOOT_STEPS), false};
static const Pattern PATTERN_TEST = {TEST_STEPS, SENTRY_COUNT(TEST_STEPS), false};
static const Pattern PATTERN_CHIRP = {CHIRP_STEPS, SENTRY_COUNT(CHIRP_STEPS), false};

class PatternPlayer {
 public:
  void start(const Pattern* p, uint32_t now) {
    p_ = p;
    idx_ = 0;
    stepStart_ = now;
  }
  void stop() { p_ = 0; }
  bool active() const { return p_ != 0; }
  const Pattern* current() const { return p_; }

  // Returns true when the output (buzzer / LED) should be ON right now.
  bool output(uint32_t now) {
    if (!p_) return false;
    // After a long stall (e.g. a slow network call) jump whole cycles at once
    // so a looping pattern stays in rhythm without spinning.
    if (p_->loop) {
      uint32_t period = 0, intoCycle = 0;
      for (uint8_t i = 0; i < p_->count; i++) {
        if (i < idx_) intoCycle += p_->steps[i];
        period += p_->steps[i];
      }
      uint32_t cycleStart = stepStart_ - intoCycle;
      uint32_t lag = (uint32_t)(now - cycleStart);
      if (period && lag >= 2 * period) {
        idx_ = 0;
        stepStart_ = cycleStart + (lag - (lag % period));
      }
    }
    for (int guard = 0; guard < 2 * 255 && (uint32_t)(now - stepStart_) >= p_->steps[idx_]; guard++) {
      stepStart_ += p_->steps[idx_];
      idx_++;
      if (idx_ >= p_->count) {
        if (!p_->loop) {
          p_ = 0;
          return false;
        }
        idx_ = 0;
      }
    }
    return (idx_ % 2) == 0;  // even steps are ON
  }

 private:
  const Pattern* p_ = 0;
  uint8_t idx_ = 0;
  uint32_t stepStart_ = 0;
};

// ---------------- Alarm messages on UDP 5005 ----------------
enum AlarmKind : uint8_t { MSG_NONE = 0, MSG_FALL, MSG_SOS, MSG_SILENCE };

static inline bool startsWith(const char* s, const char* prefix) {
  return strncmp(s, prefix, strlen(prefix)) == 0;
}

// Parses "FALL_ALERT:<loc>", "ALARM_TRIGGER", "SOS_ALERT:<loc>" / "SOS_ALERT,<loc>",
// "FALL_SILENCE", "ALARM_STOP", "SILENCE". Writes the location (may be empty)
// into loc (always NUL-terminated). Leading/trailing whitespace is ignored.
static inline AlarmKind parseAlarm(const char* msgIn, char* loc, size_t locSize) {
  if (locSize) loc[0] = 0;
  if (!msgIn) return MSG_NONE;
  while (*msgIn == ' ' || *msgIn == '\t' || *msgIn == '\r' || *msgIn == '\n') msgIn++;
  AlarmKind kind = MSG_NONE;
  const char* rest = 0;
  if (startsWith(msgIn, "FALL_ALERT")) { kind = MSG_FALL; rest = msgIn + 10; }
  else if (startsWith(msgIn, "ALARM_TRIGGER")) { kind = MSG_FALL; rest = msgIn + 13; }
  else if (startsWith(msgIn, "SOS_ALERT")) { kind = MSG_SOS; rest = msgIn + 9; }
  else if (startsWith(msgIn, "FALL_SILENCE") || startsWith(msgIn, "ALARM_STOP") ||
           startsWith(msgIn, "SILENCE")) { return MSG_SILENCE; }
  else return MSG_NONE;

  if (*rest == ':' || *rest == ',') rest++;
  while (*rest == ' ') rest++;
  // The Pi prefixes node names with the sender IP ("[192.168.1.20] Bath Room").
  // Drop that so the RX node's own copy and the Pi's copy count as the same alert.
  if (*rest == '[') {
    const char* close = strchr(rest, ']');
    if (close) {
      rest = close + 1;
      while (*rest == ' ') rest++;
    }
  }
  if (locSize) {
    size_t n = 0;
    while (rest[n] && rest[n] != '\n' && rest[n] != '\r' && n + 1 < locSize) {
      loc[n] = rest[n];
      n++;
    }
    while (n > 0 && (loc[n - 1] == ' ' || loc[n - 1] == '\t')) n--;
    loc[n] = 0;
  }
  return kind;
}

// ---------------- Repeat filter ----------------
//
// The same alert can arrive more than once (the RX node sends its SOS 3 times
// and also the Pi re-broadcasts it). After someone silences an alert, copies of
// that SAME alert that arrive within holdoffMs must not restart the siren.
// A different alert (other kind or other room) always gets through.
static inline uint32_t fnv1a(const char* s) {
  uint32_t h = 2166136261u;
  while (*s) { h ^= (uint8_t)*s++; h *= 16777619u; }
  return h;
}

class RepeatFilter {
 public:
  explicit RepeatFilter(uint32_t holdoffMs = 8000) : holdoffMs_(holdoffMs) {}
  void silenced(AlarmKind kind, const char* loc, uint32_t now) {
    key_ = fnv1a(loc) ^ ((uint32_t)kind * 0x9E3779B9u);
    at_ = now;
    armed_ = true;
  }
  bool allow(AlarmKind kind, const char* loc, uint32_t now) const {
    if (!armed_) return true;
    if ((uint32_t)(now - at_) >= holdoffMs_) return true;
    return key_ != (fnv1a(loc) ^ ((uint32_t)kind * 0x9E3779B9u));
  }

 private:
  uint32_t holdoffMs_;
  uint32_t key_ = 0, at_ = 0;
  bool armed_ = false;
};

// ---------------- Retry sender ----------------
// Schedules N sends spaced gapMs apart without blocking loop().
class Retry {
 public:
  void start(uint8_t times, uint16_t gapMs, uint32_t now) {
    left_ = times;
    gap_ = gapMs;
    next_ = now;
  }
  // True when it is time to send one copy now.
  bool due(uint32_t now) {
    if (left_ == 0 || (int32_t)(now - next_) < 0) return false;
    left_--;
    next_ = now + gap_;
    return true;
  }
  bool pending() const { return left_ > 0; }

 private:
  uint8_t left_ = 0;
  uint16_t gap_ = 0;
  uint32_t next_ = 0;
};

}  // namespace sentry
