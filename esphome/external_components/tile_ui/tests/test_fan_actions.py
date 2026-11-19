import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tile_ui.data_collection import collect_available_scripts
from tile_ui.tile_generation import generate_tile_cpp
from tile_ui.validation import validate_tiles_config


ROOT = Path(__file__).resolve().parents[4]


def compile_and_run(code):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / "test.cpp").write_text(code)
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        str(path / "test.cpp"), "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test")], check=True)


class FanActionsTest(unittest.TestCase):
    def test_documented_fan_configuration(self):
        documentation = (ROOT / "TILE_CONFIGURATION.md").read_text()
        example = documentation.split("#### Fan controls", 1)[1].split("```yaml\n", 1)[1].split("```", 1)[0]
        config = yaml.safe_load(example)
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_multi_constructor("!", lambda loader, tag, node: loader.construct_scalar(node))
        library = yaml.load((ROOT / "esphome/lib/lib_common.yaml").read_text(), Loader=Loader)
        scripts = collect_available_scripts(library)
        validate_tiles_config(config["screens"], scripts, declared_dynamic_entities=config["dynamic_entities"])
        for screen in config["screens"]:
            for tile in screen["tiles"]:
                self.assertIn("new ", generate_tile_cpp(tile, scripts))

    def test_fan_speed_and_direction(self):
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_multi_constructor("!", lambda loader, tag, node: loader.construct_scalar(node))
        library = yaml.load((ROOT / "esphome/lib/lib_common.yaml").read_text(), Loader=Loader)
        scripts = {script["id"]: script for script in library["script"]}
        glyphs = yaml.safe_load((ROOT / "esphome/lib/mdi_glyphs.yaml").read_text())
        for glyph in ("\uf168", "\uec17", "\uf4b5", "\uf4b6"):
            self.assertIn(glyph, glyphs)
        source = (ROOT / "esphome/lib/utils.h").read_text()
        pending = source.split("struct PendingFanAttribute {", 1)[1].split(
            "\nstd::map<std::string, PendingClimateMode>", 1
        )[0]
        actions = source.split("std::string GetFanAttribute(", 1)[1].split(
            "\nvoid AdjustClimateTemperature", 1
        )[0]
        code = r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>
#define id(x) x
template<class... Args> void log_warning(Args...) {}
#define ESP_LOGW(...) log_warning(__VA_ARGS__)
namespace esphome {
template<class T> std::optional<T> parse_number(const std::string& value) {
  try { size_t n; auto v = std::stof(value, &n); if (n == value.size()) return static_cast<T>(v); }
  catch (...) {}
  return {};
}
struct Scheduler {
  std::vector<std::function<void()>> callbacks;
  void set_timeout(void*, const char*, int, std::function<void()> cb) { callbacks.push_back(cb); }
};
struct Application { Scheduler scheduler; } App;
}
struct Display { void update() {} } disp;
std::map<std::string, std::string> values;
std::string GetTextSensorValue(const std::string& key) { return values[key]; }
std::string GetSensor(const std::string& key) { return key.substr(0, key.find('|')); }
std::vector<std::string> calls;
void PerformHaAction(const std::string& entity, const std::string& action,
                     std::vector<std::pair<std::string, std::string>> data = {}) {
  calls.push_back(entity + ":" + action + (data.empty() ? "" : ":" + data[0].second));
}
struct PendingFanAttribute {
""" + pending + r"""
std::string GetFanAttribute(
""" + actions + r"""
enum TextAlign { CENTER, TOP_LEFT };
enum Font { big, medium, small, tiny, text_small, text_bold, text_big_bold };
enum Color { yellow, gray, white, blue, red };
struct Draw { int x, y; Font font; Color color; TextAlign align; std::string text; };
std::vector<Draw> draws;
void print(int x, int y, Font font, Color color, TextAlign align, const char* text) {
  draws.push_back({x, y, font, color, align, text});
}
std::pair<int, int> measure(Font font, const char*) {
  switch (font) {
    case big: return {80, 80};
    case medium: return {60, 60};
    case small: return {40, 40};
    case tiny: return {24, 24};
    case text_big_bold: return {30, 30};
    case text_bold: return {20, 20};
    case text_small: return {12, 12};
  }
  return {20, 20};
}
"""
        extra_params = {
            "tile_fan": ", Font size",
            "tile_fan_speed": ", Font icon_size, Font text_size",
            "tile_fan_direction": ", Font size",
        }
        for name, extra in extra_params.items():
            code += (
                f"\nvoid {name}(int x_start, int x_end, int y_start, int y_end, "
                f"std::vector<std::string> entities{extra}) {{\n"
                + scripts[name]["then"][0]["lambda"] + "\n}\n"
            )
        code += r"""
int main() {
  const std::string fan = "fan.test";
  const std::string second = "fan.second";
  values[fan] = "on";
  values[fan + "|supported_features"] = "5";
  values[fan + "|percentage_step"] = "33.333333";
  values[fan + "|percentage"] = "33";
  values[fan + "|direction"] = "forward";
  values[second] = "off";
  values[second + "|supported_features"] = "5";
  values[second + "|percentage_step"] = "25";
  values[second + "|percentage"] = "50";
  values[second + "|direction"] = "reverse";
  std::vector<std::string> fans = {fan, second, "fan.missing", fan + "|percentage"};
  tile_fan(10, 110, 20, 120, fans, small);
  assert(draws.size() == 1 && draws[0].color == gray && draws[0].font == small && draws[0].text == "\U0000ec17");
  ToggleFanPower(fans);
  assert((calls == std::vector<std::string>{fan + ":turn_on", second + ":turn_on"}));
  calls.clear(); values[second] = "on";
  draws.clear(); tile_fan(10, 110, 20, 120, fans, big);
  assert(draws.size() == 1 && draws[0].color == yellow && draws[0].font == big && draws[0].text == "\U0000f168");
  ToggleFanPower(fans);
  assert((calls == std::vector<std::string>{fan + ":turn_off", second + ":turn_off"}));
  calls.clear();
  draws.clear(); tile_fan_speed(10, 110, 20, 120, fans, small, text_big_bold);
  assert(draws.size() == 2 && draws[0].color == white && draws[0].align == TOP_LEFT);
  assert(draws[0].x == 12 && draws[0].y == 22 && draws[0].font == small && draws[0].text == "\U0000f168");
  assert(draws[1].text == "33%" && draws[1].color == white && draws[1].font == text_big_bold);
  CycleFanSpeed(fans);
  assert((calls == std::vector<std::string>{fan + ":set_percentage:66", second + ":set_percentage:66"}));
  calls.clear();
  CycleFanSpeed(fans);
  assert((calls == std::vector<std::string>{fan + ":set_percentage:100", second + ":set_percentage:100"}));
  ReconcileFanAttribute(fan + "|percentage", "66");
  assert(GetFanAttribute(fan + "|percentage") == "100");
  calls.clear();
  CycleFanSpeed(fans);
  assert((calls == std::vector<std::string>{fan + ":set_percentage:33", second + ":set_percentage:33"}));
  calls.clear();
  draws.clear(); tile_fan_direction(10, 110, 20, 120, fans, medium);
  assert(draws.size() == 2);
  assert(draws[0].text == "\U0000f4b5" && draws[0].color == red && draws[0].font == medium && draws[0].x == 60 && draws[0].y == 70);
  assert(draws[1].text == "\U0000f168" && draws[1].color == white && draws[1].font == medium && draws[1].x == 60 && draws[1].y == 70);
  CycleFanDirection(fans);
  assert((calls == std::vector<std::string>{fan + ":set_direction:forward", second + ":set_direction:forward"}));
  draws.clear(); tile_fan_direction(10, 110, 20, 120, fans, small);
  assert(draws.size() == 2);
  assert(draws[0].text == "\U0000f4b6" && draws[0].color == blue && draws[0].font == small && draws[0].x == 60 && draws[0].y == 70);
  assert(draws[1].text == "\U0000f168" && draws[1].color == white && draws[1].font == small && draws[1].x == 60 && draws[1].y == 70);
  calls.clear(); CycleFanDirection(fans);
  assert((calls == std::vector<std::string>{fan + ":set_direction:reverse", second + ":set_direction:reverse"}));
  for (auto& callback : esphome::App.scheduler.callbacks) callback();
  assert(pending_fan_attributes.empty());
  calls.clear();
  values[fan + "|percentage"] = "80";
  values[second + "|percentage"] = "25";
  CycleFanSpeed(fans);
  assert((calls == std::vector<std::string>{fan + ":set_percentage:50", second + ":set_percentage:50"}));
  for (auto& callback : esphome::App.scheduler.callbacks) callback();
  esphome::App.scheduler.callbacks.clear();
  calls.clear();
  values[fan + "|percentage_step"] = "unknown";
  draws.clear(); tile_fan_speed(10, 110, 20, 120, fans, tiny, text_bold);
  assert(draws[1].text == "25%" && draws[1].font == text_bold);
  CycleFanSpeed(fans);
  assert((calls == std::vector<std::string>{second + ":set_percentage:50"}));
  calls.clear();
  values[second + "|supported_features"] = "0";
  draws.clear(); tile_fan_speed(10, 110, 20, 120, fans, tiny, text_bold);
  assert(draws[1].text == "--");
  CycleFanSpeed(fans);
  assert(calls.empty());
  values[fan] = "unavailable";
  values[second] = "unavailable";
  draws.clear(); tile_fan(10, 110, 20, 120, fans, big);
  assert(draws.size() == 1 && draws[0].color == gray && draws[0].text == "\U0000ec17");
  draws.clear(); tile_fan_direction(10, 110, 20, 120, fans, big);
  assert(draws.size() == 2 && draws[0].text == "\U0000f168" && draws[0].font == tiny && draws[0].align == TOP_LEFT);
  assert(draws[1].text == "--" && draws[1].color == white && draws[1].font == text_bold && draws[1].x == 60 && draws[1].y == 70);
  ToggleFanPower(fans); CycleFanDirection(fans);
  assert(calls.empty());
}
"""
        compile_and_run(code)

    def test_ha_action_short_long_and_navigation(self):
        source = (ROOT / "esphome/lib/tiles.h").read_text()
        tile = source.split("class HAActionTile : public Tile {", 1)[1].split(
            "\n// A tile that navigates", 1
        )[0]
        code = r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#define id(x) x
template<class T> using optional = std::optional<T>;
uint32_t clock_ms = 0;
uint32_t millis() { return clock_ms; }
namespace esphome {
namespace display { struct DisplayPage {}; }
struct Scheduler {
  struct Entry { uint32_t due_ms; std::function<void()> cb; };
  std::vector<Entry> entries;
  void set_timeout(void*, const char*, uint32_t delay, std::function<void()> cb) {
    assert(delay == 1500 || delay == 150);
    entries.push_back({clock_ms + delay, std::move(cb)});
  }
  void advance_to(uint32_t target_ms) {
    clock_ms = target_ms;
    bool ran = true;
    while (ran) {
      ran = false;
      for (size_t i = 0; i < entries.size(); ++i) {
        if (entries[i].due_ms <= clock_ms) {
          auto cb = std::move(entries[i].cb);
          entries.erase(entries.begin() + i);
          cb();
          ran = true;
          break;
        }
      }
    }
  }
};
struct Application { Scheduler scheduler; } App;
}
int last_x = 20, last_y = 30;
bool ignore_touch = false;
int x_start(int x) { return x * 100; }
int y_start(int y) { return y * 100; }
int x_rect() { return 100; }
int y_rect() { return 100; }
struct Display {
  esphome::display::DisplayPage* page = nullptr;
  auto get_active_page() { return page; }
  void show_page(esphome::display::DisplayPage* p) { page = p; }
  void update() {}
} disp;
struct Sensor {
  std::vector<std::function<void(bool)>> callbacks;
  void add_on_state_callback(std::function<void(bool)> cb) { callbacks.push_back(cb); }
  template<class T> void add_filter(T*) {}
  void send(bool b) { for (auto& cb : callbacks) cb(b); }
};
namespace esphome { namespace binary_sensor {
struct LambdaFilter { template<class T> explicit LambdaFilter(T) {} };
}}
class Tile {
public:
  static constexpr uint32_t kTouchReleaseGraceMs = 150;
  Tile(int x, int y) : x_(x), y_(y) {}
  virtual ~Tile() = default;
  virtual bool requiresFastRefresh() { return false; }
  virtual bool updateOnEntitiesMapChange() { return false; }
  virtual void initSensors() {}
  virtual void decodeEntities() {}
  static bool isTouchBlockedFor(const Tile* tile) {
    return active_touch_tile_ != nullptr && active_touch_tile_ != tile;
  }
  static bool hasActiveTouchSession() {
    return screen_touch_active_ || active_touch_tile_ != nullptr;
  }
  static bool isScreenTouchActive() { return screen_touch_active_; }
  static void claimTouchTile(Tile* tile) {
    if (active_touch_tile_ == nullptr) active_touch_tile_ = tile;
  }
  static void releaseTouchTile(const Tile* tile) {
    if (active_touch_tile_ == tile) active_touch_tile_ = nullptr;
  }
  static void notifyScreenTouch() {
    screen_touch_active_ = true;
    ++screen_release_gen_;
    if (active_touch_tile_ != nullptr) active_touch_tile_->onScreenTouchResume();
  }
  static void notifyScreenRelease() {
    screen_touch_active_ = false;
    const uint32_t gen = ++screen_release_gen_;
    if (active_touch_tile_ != nullptr) {
      if (active_touch_tile_->holdsTouchDuringReleaseGrace()) {
        active_touch_tile_->onScreenTouchPause();
      } else {
        active_touch_tile_ = nullptr;
      }
    }
    if (id(ignore_touch)) {
      esphome::App.scheduler.set_timeout(
          nullptr, static_cast<const char*>(nullptr), kTouchReleaseGraceMs, [gen]() {
            if (!screen_touch_active_ && gen == screen_release_gen_) id(ignore_touch) = false;
          });
    }
  }
  void start(esphome::display::DisplayPage* page) { display_page_ = page; customInit(); }
  void touch(bool b) { sensor.send(b); }
  void leave() { onScreenLeave(); }
  bool checkActivationMaybeToggle() { return active; }
  bool active = true;
  std::function<void()> change_screen_callback_ = []() {};
  std::function<void()> change_entities_callback_ = []() {};
protected:
  virtual void customInit() = 0;
  virtual void customDraw() = 0;
  virtual void onScreenLeave() {}
  virtual bool holdsTouchDuringReleaseGrace() const { return false; }
  virtual void onScreenTouchPause() {}
  virtual void onScreenTouchResume() {}
  Sensor sensor;
  Sensor* binary_sensor_ = &sensor;
  esphome::display::DisplayPage* display_page_ = nullptr;
  int x_, y_, x_span_ = 1, y_span_ = 1;
private:
  inline static Tile* active_touch_tile_ = nullptr;
  inline static bool screen_touch_active_ = false;
  inline static uint32_t screen_release_gen_ = 0;
};
std::set<std::string> repository;
const std::string* Pointer(const std::string& s) { return &*repository.insert(s).first; }
std::vector<const std::string*> Pointer(const std::vector<std::string>& values) {
  std::vector<const std::string*> result; for (const auto& s : values) result.push_back(Pointer(s)); return result;
}
std::vector<std::string> Deref(const std::vector<const std::string*>& values) {
  std::vector<std::string> result; for (auto* s : values) result.push_back(*s); return result;
}
std::map<std::string, std::string> entity_states;
std::string GetTextSensorValue(const std::string& entity) { return entity_states[entity]; }
std::map<std::string, std::vector<const std::string*>> dynamic;
void EMSet(const std::string* key, const std::vector<const std::string*>& values) { dynamic[*key] = values; }
bool HasDynamicEntity(const std::vector<const std::string*>&) { return false; }
std::vector<const std::string*> ReplaceDynamicEntities(std::vector<const std::string*>& v) { return v; }
void InitSensor(const std::string&) {}
std::string GetSensor(const std::string& s) { return s.substr(0, s.find('|')); }
template<class... Args> void ExecuteScripts(const std::vector<std::function<void(Args...)>>& scripts, Args... args) {
  for (const auto& script : scripts) script(args...);
}
class HAActionTile : public Tile {
""" + tile + r"""
int main() {
  esphome::display::DisplayPage page, destination;
  disp.page = &page;
  int short_count = 0, long_count = 0, changes = 0, leaves = 0;
  std::function<void(std::vector<std::string>)> short_action = [&](auto e) {
    assert(e == std::vector<std::string>{"fan.one|percentage"}); ++short_count;
  };
  std::function<void(std::vector<std::string>)> long_action = [&](auto) { ++long_count; };
  HAActionTile tile(0, 0, {}, {short_action}, {"fan.one|percentage"});
  HAActionTile other_tile(1, 0, {}, {short_action}, {"fan.one|percentage"});
  tile.setLongPress({long_action}, &destination, "FAN");
  tile.change_entities_callback_ = [&]() { ++changes; };
  tile.change_screen_callback_ = [&]() { ++leaves; tile.leave(); };
  tile.start(&page); tile.decodeEntities();
  other_tile.start(&page); other_tile.decodeEntities();

  // 1. Short tap (100ms hold, confirmed after 150ms release debounce)
  Tile::notifyScreenTouch(); tile.touch(true); assert(short_count == 0);
  esphome::App.scheduler.advance_to(100);
  Tile::notifyScreenRelease(); tile.touch(false); assert(short_count == 0);
  esphome::App.scheduler.advance_to(250);
  assert(short_count == 1 && long_count == 0);
  esphome::App.scheduler.advance_to(1600);
  assert(short_count == 1 && long_count == 0);

  // 2. Steady 1.5s (1500ms) hold triggers long press and keeps ignore_touch across 50ms dropout
  Tile::notifyScreenTouch(); tile.touch(true);
  assert(Tile::isTouchBlockedFor(&other_tile));
  esphome::App.scheduler.advance_to(3100);
  assert(long_count == 1 && short_count == 1 && changes == 1 && leaves == 1);
  assert(disp.page == &destination && ignore_touch && Deref(dynamic["FAN"]) == std::vector<std::string>{"fan.one"});
  // Brief 50ms dropout while finger is still resting on new page must NOT clear ignore_touch
  esphome::App.scheduler.advance_to(3150);
  Tile::notifyScreenRelease(); tile.touch(false);
  esphome::App.scheduler.advance_to(3200);
  Tile::notifyScreenTouch();
  esphome::App.scheduler.advance_to(3400);
  assert(ignore_touch);
  // Genuine lift clears ignore_touch after 150ms
  Tile::notifyScreenRelease();
  esphome::App.scheduler.advance_to(3550);
  assert(!ignore_touch && short_count == 1);

  // 3. Leaving screen cancels active hold without firing short or long press
  disp.page = &page;
  Tile::notifyScreenTouch(); tile.touch(true); tile.leave(); Tile::notifyScreenRelease();
  esphome::App.scheduler.advance_to(5200);
  assert(long_count == 1 && short_count == 1);

  // 4. Mid-hold 50ms touch dropout on same tile does NOT fire short press in the middle and fires long press at 1500ms
  esphome::App.scheduler.advance_to(6000);
  Tile::notifyScreenTouch(); tile.touch(true);
  esphome::App.scheduler.advance_to(6600);
  Tile::notifyScreenRelease(); tile.touch(false);
  assert(short_count == 1 && long_count == 1);
  esphome::App.scheduler.advance_to(6650);
  Tile::notifyScreenTouch(); tile.touch(true);
  assert(short_count == 1 && long_count == 1);
  esphome::App.scheduler.advance_to(7500);
  assert(long_count == 2 && short_count == 1 && disp.page == &destination);
  Tile::notifyScreenRelease(); tile.touch(false);
  esphome::App.scheduler.advance_to(7700);
  disp.page = &page;

  // 5. Mid-hold dropout + finger drift onto another tile/padding keeps long press alive and blocks other tile
  esphome::App.scheduler.advance_to(8000);
  Tile::notifyScreenTouch(); tile.touch(true);
  esphome::App.scheduler.advance_to(8500);
  Tile::notifyScreenRelease(); tile.touch(false);
  esphome::App.scheduler.advance_to(8550);
  Tile::notifyScreenTouch(); // touch re-landed outside `tile`, on `other_tile` / padding!
  assert(Tile::isTouchBlockedFor(&other_tile));
  esphome::App.scheduler.advance_to(9500);
  assert(long_count == 3 && short_count == 1 && disp.page == &destination);
  Tile::notifyScreenRelease();
  esphome::App.scheduler.advance_to(9700);
  disp.page = &page;

  // 6. Glitch straddling the 1500ms mark fires long press as soon as touch resumes
  esphome::App.scheduler.advance_to(10000);
  Tile::notifyScreenTouch(); tile.touch(true);
  esphome::App.scheduler.advance_to(11450);
  Tile::notifyScreenRelease(); tile.touch(false);
  esphome::App.scheduler.advance_to(11500); // 1500ms mark while mid-glitch -> waits!
  assert(long_count == 3 && short_count == 1);
  esphome::App.scheduler.advance_to(11520);
  Tile::notifyScreenTouch(); // touch was still there!
  assert(long_count == 4 && short_count == 1 && disp.page == &destination);
  Tile::notifyScreenRelease();
  esphome::App.scheduler.advance_to(11700);
  disp.page = &page;

  // 7. Genuine release at 1420ms (< 1500ms) fires short press, NOT long press
  esphome::App.scheduler.advance_to(12000);
  Tile::notifyScreenTouch(); tile.touch(true);
  esphome::App.scheduler.advance_to(13420);
  Tile::notifyScreenRelease(); tile.touch(false);
  esphome::App.scheduler.advance_to(13500); // 1500ms mark while releasing -> does NOT false-fire long press
  assert(long_count == 4 && short_count == 1);
  esphome::App.scheduler.advance_to(13570); // 150ms release debounce completes
  assert(long_count == 4 && short_count == 2);

  // 8. Late release event arriving after >= 1500ms before scheduler tick fires long press immediately
  esphome::App.scheduler.advance_to(14000);
  Tile::notifyScreenTouch(); tile.touch(true);
  clock_ms = 15600;
  Tile::notifyScreenRelease(); tile.touch(false);
  assert(long_count == 5 && short_count == 2 && disp.page == &destination);
  esphome::App.scheduler.advance_to(15800);
  assert(long_count == 5 && short_count == 2);
  disp.page = &page;

  // 9. Non-long-press tile fires immediately on press and unlocks immediately on release
  HAActionTile legacy(0, 0, {}, {short_action}, {"fan.one|percentage"});
  legacy.start(&page); legacy.decodeEntities();
  Tile::notifyScreenTouch(); legacy.touch(true);
  assert(short_count == 3 && Tile::isTouchBlockedFor(&other_tile));
  Tile::notifyScreenRelease(); legacy.touch(false);
  assert(!Tile::hasActiveTouchSession() && !Tile::isTouchBlockedFor(&other_tile));

  HAActionTile cover(0, 0, {}, {short_action}, {"cover.one"});
  cover.start(&page); cover.decodeEntities();
  assert(!cover.requiresFastRefresh());
  entity_states["cover.one"] = "opening"; assert(cover.requiresFastRefresh());
  entity_states["cover.one"] = "closing"; assert(cover.requiresFastRefresh());
  entity_states["cover.one"] = "open"; assert(!cover.requiresFastRefresh());
}
"""
        compile_and_run(code)

    def test_perform_ha_action_string_ref_and_progmem_string_ref(self):
        source = (ROOT / "esphome/lib/utils.h").read_text()
        perform_ha_action = (
            "void PerformHaAction("
            + source.split("void PerformHaAction(", 1)[1].split(
                "\nstd::string GetFanAttribute(", 1
            )[0]
        )
        template = r"""
#include <cassert>
#include <cstddef>
#include <string>
#include <utility>
#include <vector>

#define id(x) x
template<class... Args> void log_info(Args...) {}
#define ESP_LOGI(...) log_info(__VA_ARGS__)

namespace esphome {
class StringRef {
 public:
  constexpr StringRef() = default;
  explicit StringRef(const std::string& s) : ptr_(s.data()), len_(s.size()) {}
  template<size_t N>
  static constexpr StringRef from_lit(const char (&s)[N]) {
    return StringRef(s, N - 1);
  }
  constexpr const char* c_str() const { return ptr_; }
  constexpr size_t size() const { return len_; }
 private:
  constexpr StringRef(const char* ptr, size_t len) : ptr_(ptr), len_(len) {}
  const char* ptr_ = "";
  size_t len_ = 0;
};

class ProgmemStringRef {
 public:
  constexpr ProgmemStringRef() = default;
  explicit constexpr ProgmemStringRef(const StringRef& ref)
      : ptr_(ref.c_str()), len_(ref.size()) {}
  constexpr const char* c_str() const { return ptr_; }
  constexpr size_t size() const { return len_; }
 private:
  const char* ptr_ = "";
  size_t len_ = 0;
};

template<typename T>
struct FixedVector {
  bool initialized = false;
  size_t capacity = 0;
  std::vector<T> items;
  void init(size_t n) {
    initialized = true;
    capacity = n;
    items.clear();
    items.reserve(n);
  }
  void push_back(const T& item) {
    assert(initialized && items.size() < capacity);
    items.push_back(item);
  }
};

namespace api {
struct HomeassistantServiceMap {
  __FIELD_TYPE__ key;
  __FIELD_TYPE__ value;
};

struct HomeassistantActionRequest {
  __FIELD_TYPE__ service;
  FixedVector<HomeassistantServiceMap> data;
};
}  // namespace api
}  // namespace esphome

using esphome::StringRef;

struct CapturedCall {
  std::string service;
  std::vector<std::pair<std::string, std::string>> data;
};

struct ApiServer {
  std::vector<CapturedCall> sent;
  void send_homeassistant_action(const esphome::api::HomeassistantActionRequest& req) {
    CapturedCall call;
    call.service.assign(req.service.c_str(), req.service.size());
    for (const auto& kv : req.data.items) {
      call.data.emplace_back(
          std::string(kv.key.c_str(), kv.key.size()),
          std::string(kv.value.c_str(), kv.value.size()));
    }
    sent.push_back(std::move(call));
  }
} api_server;

__PERFORM_HA_ACTION__

int main() {
  PerformHaAction("light.kitchen", "toggle", {{"brightness_pct", "80"}});
  assert(api_server.sent.size() == 1);
  assert(api_server.sent[0].service == "light.toggle");
  assert((api_server.sent[0].data == std::vector<std::pair<std::string, std::string>>{
      {"entity_id", "light.kitchen"},
      {"brightness_pct", "80"},
  }));

  PerformHaAction("fan.bedroom", "homeassistant.turn_off");
  assert(api_server.sent.size() == 2);
  assert(api_server.sent[1].service == "homeassistant.turn_off");
  assert((api_server.sent[1].data == std::vector<std::pair<std::string, std::string>>{
      {"entity_id", "fan.bedroom"},
  }));
}
"""
        for field_type in ("esphome::StringRef", "esphome::ProgmemStringRef"):
            with self.subTest(field_type=field_type):
                code = (
                    template
                    .replace("__FIELD_TYPE__", field_type)
                    .replace("__PERFORM_HA_ACTION__", perform_ha_action)
                )
                compile_and_run(code)


if __name__ == "__main__":
    unittest.main()
