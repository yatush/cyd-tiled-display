import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def extract_function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise ValueError(f"Unclosed function: {signature}")


class ClimateModeTest(unittest.TestCase):
    def test_temperature_optimistic_display_and_reconciliation(self):
        utils = (ROOT / "esphome/lib/utils.h").read_text()
        yaml = (ROOT / "esphome/lib/lib_common.yaml").read_text()
        pending = utils.split("struct PendingClimateTemperature {", 1)[1].split(
            "// --- Sensor Initialization ---", 1
        )[0]
        display = yaml.split("  - id: tile_ac_status\n", 1)[1].split(
            "\n  - id:", 1
        )[0].split("      - lambda: |-\n", 1)[1]
        source = r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#define id(name) name
#define ESP_LOGE(tag, ...) ((void) (tag))
#define ESP_LOGW(...) ((void) 0)
#define ESP_LOGI(...) ((void) 0)
namespace esphome {
template<class T> std::optional<T> parse_number(const std::string& value) {
  try { size_t n; float v = std::stof(value, &n); if (n == value.size()) return v; }
  catch (...) {}
  return {};
}
struct Api {};
struct Scheduler {
  std::vector<std::function<void()>> timeouts;
  void set_timeout(Api* component, const char*, uint32_t delay, std::function<void()> callback) {
    assert(component == nullptr && delay == 10000); timeouts.push_back(callback);
  }
};
struct Application { Scheduler scheduler; } App;
namespace homeassistant {
struct HomeassistantBinarySensor {
  void set_entity_id(const char*) {}
  void set_attribute(const char*) {}
  void add_on_state_callback(std::function<void(bool)>) {}
  void setup() {}
};
struct HomeassistantTextSensor {
  std::function<void(std::string)> callback;
  void set_entity_id(const char*) {}
  void set_attribute(const char*) {}
  void add_on_state_callback(std::function<void(std::string)> cb) { callback = cb; }
  void setup() {}
};
}
}
struct Display { int updates = 0; void update() { ++updates; } } disp;
struct Repository {
  std::set<std::string> strings;
  static Repository& instance() { static Repository repository; return repository; }
  const std::string* ptr(const std::string& value) { return &*strings.insert(value).first; }
};
bool IsBinSensor(const std::string&) { return false; }
bool IsTextSensor(const std::string&) { return true; }
std::map<std::string, esphome::homeassistant::HomeassistantBinarySensor*> binary_sensors;
std::map<std::string, esphome::homeassistant::HomeassistantTextSensor*> text_sensors;
""" + "\n".join(
            extract_function(utils, signature)
            for signature in ("std::string GetSensor(", "std::string GetAtt(")
        ) + "\nstruct PendingClimateTemperature {" + pending + "\n" + extract_function(
            utils, "void InitSensor(const std::string& key, const std::string& sensor,"
        ) + r"""
std::map<std::string, std::string> values;
std::string GetTextSensorValue(const std::string& key) { return values[key]; }
""" + extract_function(utils, "std::string GetClimateTemperatureValue(") + r"""
std::vector<std::pair<std::string, std::string>> calls;
void PerformHaAction(const std::string& entity, const std::string& action,
                     std::vector<std::pair<std::string, std::string>> data) {
  assert(action == "set_temperature");
  calls.emplace_back(entity, data.at(0).second);
}
""" + extract_function(utils, "void AdjustClimateTemperature(") + r"""
int large_font, bold_font, small_font;
int* text_big_bold = &large_font;
int* text_bold = &bold_font;
int* text_small = &small_font;
int gray = 0;
enum class TextAlign { CENTER };
std::string rendered;
std::pair<int, int> measure(int*, const char*) { return {10, 10}; }
void print(int, int, int*, int, TextAlign, const char* text) { rendered = text; }
void draw(const std::vector<std::string>& entities) {
  int x_start = 0, x_end = 100, y_start = 0, y_end = 100;
""" + display + r"""
}
void report(const std::string& key, const std::string& value) {
  values[key] = value;
  text_sensors.at(key)->callback(value);
}
int main() {
  const std::string ac = "climate.living";
  const std::string key = ac + "|temperature";
  InitSensor(key, ac, "temperature");
  InitSensor("climate.other|temperature", "climate.other", "temperature");
  values[ac] = "cool"; values[key] = "20.5";
  AdjustClimateTemperature(ac, 1, "test");
  assert(calls.size() == 1 && calls.back().first == ac && std::stof(calls.back().second) == 21.5f);
  assert(disp.updates == 1);
  draw({ac, key}); assert(rendered == "cool 21.5°");

  AdjustClimateTemperature(key, 1, "test");
  assert(std::stof(calls.back().second) == 22.5f);
  esphome::App.scheduler.timeouts[0]();
  report(key, "21.5");
  draw({ac, key}); assert(rendered == "cool 22.5°");
  report(key, "22.5");
  draw({ac, key}); assert(rendered == "cool 22.5°");
  assert(pending_climate_temperatures.empty());
  esphome::App.scheduler.timeouts[1]();
  assert(GetClimateTemperatureValue(ac) == "22.5");

  AdjustClimateTemperature(ac, 1, "test");
  report(key, "22.5");
  assert(GetClimateTemperatureValue(ac) == "22.5");
  AdjustClimateTemperature(ac, -1, "test");
  report(key, "unknown");
  assert(GetClimateTemperatureValue(ac) == "unknown");
  const auto count = calls.size();
  AdjustClimateTemperature(ac, 1, "test");
  assert(calls.size() == count);

  report(key, "20");
  values["climate.other|temperature"] = "18";
  AdjustClimateTemperature(ac, 1, "test");
  AdjustClimateTemperature("climate.other", -1, "test");
  report(key, "19");
  assert(GetClimateTemperatureValue(ac) == "19");
  assert(GetClimateTemperatureValue("climate.other") == "17");
  const int updates_before_timeout = disp.updates;
  esphome::App.scheduler.timeouts.back()();
  assert(GetClimateTemperatureValue("climate.other") == "18");
  assert(disp.updates == updates_before_timeout + 1);
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.cpp").write_text(source)
            subprocess.run(
                ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-sign-compare", "-Wno-unused-parameter",
                 str(path / "test.cpp"), "-o", str(path / "test")],
                check=True,
            )
            subprocess.run([str(path / "test")], check=True)

    def test_ac_icon_colors(self):
        yaml = (ROOT / "esphome/lib/lib_common.yaml").read_text()
        utils = (ROOT / "esphome/lib/utils.h").read_text()
        displays = [
            yaml.split(f"  - id: {script}\n", 1)[1].split(
                "\n  - id:", 1
            )[0].split("      - lambda: |-\n", 1)[1]
            for script in ("tile_ac", "tile_ac_power")
        ]
        glyphs = (ROOT / "esphome/lib/mdi_glyphs.yaml").read_text()
        for glyph in (r'"\U0000f154"', r'"\U0000f418"'):
            self.assertIn(glyph, glyphs)
        source = """
#include <cassert>
#include <string>
#include <vector>
#define id(name) name
using BaseFont = int;
BaseFont big_font, small_font;
BaseFont* const big = &big_font;
BaseFont* const small = &small_font;
enum { blue = 1, red, light_purple, gray, white };
enum class TextAlign { CENTER };
std::string state;
std::string icon;
int color;
BaseFont* font;
std::string GetTextSensorValue(const std::string&) { return state; }
void print(int, int, BaseFont* chosen_font, int chosen, TextAlign, const char* glyph) {
  color = chosen;
  icon = glyph;
  font = chosen_font;
}
""" + extract_function(utils, "void DrawAcIcon(") + """
void draw_air(const std::vector<std::string>& entities) {
  int x_start = 0, x_end = 10, y_start = 0, y_end = 10;
  BaseFont* size = small;
""" + displays[0] + """
}
void draw_power(const std::vector<std::string>& entities) {
  int x_start = 0, x_end = 10, y_start = 0, y_end = 10;
""" + displays[1] + """
}
int main() {
  for (auto draw : {draw_air, draw_power}) {
    const std::string expected_icon = draw == draw_air ? "\\U0000f154" : "\\U0000f418";
    state = "off"; draw({"climate.ac"}); assert(color == gray); assert(icon == expected_icon);
    assert(font == (draw == draw_air ? small : big));
    state = "unknown"; draw({"climate.ac"}); assert(color == white);
    state = "unavailable"; draw({"climate.ac"}); assert(color == white);
    state = "auto"; draw({"climate.ac"}); assert(color == white);
    state = "cool"; draw({"climate.ac"}); assert(color == blue);
    state = "heat"; draw({"climate.ac"}); assert(color == red);
    state = "heat_cool"; draw({"climate.ac"}); assert(color == light_purple);
    draw({}); assert(color == white);
  }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.cpp").write_text(source)
            subprocess.run(
                ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 str(path / "test.cpp"), "-o", str(path / "test")],
                check=True,
            )
            subprocess.run([str(path / "test")], check=True)

    def test_mode_cycle_and_action(self):
        utils = (ROOT / "esphome/lib/utils.h").read_text()
        yaml = (ROOT / "esphome/lib/lib_common.yaml").read_text()
        action = yaml.split("  - id: action_ac_mode\n", 1)[1].split(
            "\n  - id:", 1
        )[0].split("      - lambda: |-\n", 1)[1]
        source = """
#include <algorithm>
#include <cassert>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#define ESP_LOGW(...) ((void) 0)
""" + "\n".join(
            extract_function(utils, signature)
            for signature in (
                "std::string GetSensor(",
                "std::string GetAtt(",
                "std::vector<std::string> getRequiredAttributes(",
                "std::string NextClimateMode(",
            )
        ) + """
std::vector<std::string> subscriptions;
void InitSensor(const std::string& key, const std::string&, const std::string& = "") {
  subscriptions.push_back(key);
}
""" + extract_function(utils, "void InitSensor(const std::string& sensor) {") + """
std::map<std::string, std::string> values;
std::vector<std::pair<std::string, std::string>> calls;
std::string GetTextSensorValue(const std::string& key) { return values[key]; }
void PerformHaAction(const std::string& entity, const std::string& action,
                     std::vector<std::pair<std::string, std::string>> data) {
  assert(action == "set_hvac_mode");
  calls.emplace_back(entity, data.at(0).second);
}
void run(const std::vector<std::string>& entities) {
""" + action + """
}
int main() {
  InitSensor("climate.one|temperature");
  assert(std::find(subscriptions.begin(), subscriptions.end(), "climate.one") != subscriptions.end());
  assert(std::find(subscriptions.begin(), subscriptions.end(), "climate.one|hvac_modes") != subscriptions.end());
  const std::string all = "['off', 'cool', 'heat', 'heat_cool']";
  assert(NextClimateMode("off", all) == "heat_cool");
  assert(NextClimateMode("cool", all) == "heat");
  assert(NextClimateMode("heat", all) == "heat_cool");
  assert(NextClimateMode("heat_cool", all) == "cool");
  assert(NextClimateMode("off", "['off', 'heat_cool']") == "heat_cool");
  assert(NextClimateMode("off", "['heat', 'off', 'heat_cool', 'cool']") == "heat_cool");
  assert(NextClimateMode("off", "[\\"off\\", \\"heat\\"]") == "heat");
  assert(NextClimateMode("cool", "['heat_cool']") == "heat_cool");
  assert(NextClimateMode("auto", "['heat', 'off']") == "heat");
  const std::string extra = "['auto', 'dry', 'fan_only', 'cool', 'off']";
  assert(NextClimateMode("auto", extra) == "dry");
  assert(NextClimateMode("dry", extra) == "fan_only");
  assert(NextClimateMode("fan_only", extra) == "cool");
  assert(NextClimateMode("cool", extra) == "auto");
  assert(NextClimateMode("off", extra) == "auto");
  assert(NextClimateMode("cool", "['cool', 'off', 'heat']") == "heat");
  assert(NextClimateMode("off", "['off']").empty());
  assert(NextClimateMode("heat", "['off', 'heat']") == "heat");
  assert(NextClimateMode("heat", "['custom_mode', 'heat']") == "custom_mode");
  assert(NextClimateMode("unavailable", all).empty());
  assert(NextClimateMode("off", "").empty());
  assert(NextClimateMode("off", "[]").empty());
  assert(NextClimateMode("off", "['']").empty());
  assert(NextClimateMode("off", "['cool', bad]").empty());
  values = {{"climate.one", "heat"}, {"climate.one|hvac_modes", all},
            {"climate.two", "off"}, {"climate.two|hvac_modes", "['off', 'dry']"},
            {"climate.three", "off"}, {"climate.three|hvac_modes", "['off']"}};
  run({"climate.one|temperature", "climate.two", "climate.three"});
  assert(calls.size() == 2);
  assert(calls[0] == std::make_pair(std::string("climate.one"), std::string("heat_cool")));
  assert(calls[1] == std::make_pair(std::string("climate.two"), std::string("dry")));
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.cpp").write_text(source)
            subprocess.run(
                ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-sign-compare",
                 str(path / "test.cpp"), "-o", str(path / "test")],
                check=True,
            )
            subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
