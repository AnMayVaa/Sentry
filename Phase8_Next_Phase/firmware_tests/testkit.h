#pragma once
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int g_fail = 0, g_pass = 0;
#define CHECK(cond) do { if (cond) g_pass++; else { g_fail++; printf("  FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define TEST(name) static void name(); struct name##_reg { name##_reg() { reg(#name, name); } } name##_inst; static void name()
#include <vector>
#include <utility>
static std::vector<std::pair<const char*, void (*)()>>& tests() { static std::vector<std::pair<const char*, void (*)()>> t; return t; }
static void reg(const char* n, void (*f)()) { tests().push_back({n, f}); }
static int run_all(const char* suite) {
  const char* only = getenv("ONLY");
  for (auto& t : tests()) { if (only && strcmp(only, t.first) != 0) continue; int before = g_fail; t.second(); printf("%s %s::%s\n", g_fail == before ? "ok  " : "FAIL", suite, t.first); }
  printf("%s: %d checks passed, %d failed\n", suite, g_pass, g_fail);
  return g_fail ? 1 : 0;
}
