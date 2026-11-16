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
    def test_ac_icon_colors(self):
        yaml = (ROOT / "esphome/lib/lib_common.yaml").read_text()
        display = yaml.split("  - id: tile_ac\n", 1)[1].split(
            "\n  - id:", 1
        )[0].split("      - lambda: |-\n", 1)[1]
        source = """
#include <cassert>
#include <string>
#include <vector>
#define id(name) name
enum { big, blue, red, light_purple, gray, white };
enum class TextAlign { CENTER };
std::string state;
int color;
std::string GetTextSensorValue(const std::string&) { return state; }
void print(int, int, int, int chosen, TextAlign, const char*) { color = chosen; }
void draw(const std::vector<std::string>& entities) {
  int x_start = 0, x_end = 10, y_start = 0, y_end = 10;
""" + display + """
}
int main() {
  state = "off"; draw({"climate.ac"}); assert(color == gray);
  state = "unknown"; draw({"climate.ac"}); assert(color == white);
  state = "unavailable"; draw({"climate.ac"}); assert(color == white);
  state = "auto"; draw({"climate.ac"}); assert(color == white);
  state = "cool"; draw({"climate.ac"}); assert(color == blue);
  state = "heat"; draw({"climate.ac"}); assert(color == red);
  state = "heat_cool"; draw({"climate.ac"}); assert(color == light_purple);
  draw({}); assert(color == white);
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
  assert(NextClimateMode("off", all) == "cool");
  assert(NextClimateMode("cool", all) == "heat");
  assert(NextClimateMode("heat", all) == "heat_cool");
  assert(NextClimateMode("heat_cool", all) == "off");
  assert(NextClimateMode("off", "['off', 'heat_cool']") == "heat_cool");
  assert(NextClimateMode("off", "[\\"off\\", \\"heat\\"]") == "heat");
  assert(NextClimateMode("cool", "['heat_cool']") == "heat_cool");
  assert(NextClimateMode("auto", "['heat', 'off']") == "heat");
  const std::string extra = "['auto', 'dry', 'fan_only', 'cool', 'off']";
  assert(NextClimateMode("auto", extra) == "dry");
  assert(NextClimateMode("dry", extra) == "fan_only");
  assert(NextClimateMode("fan_only", extra) == "cool");
  assert(NextClimateMode("off", extra) == "auto");
  assert(NextClimateMode("heat", "['custom_mode', 'heat']") == "custom_mode");
  assert(NextClimateMode("unavailable", all).empty());
  assert(NextClimateMode("off", "").empty());
  assert(NextClimateMode("off", "[]").empty());
  assert(NextClimateMode("off", "['']").empty());
  assert(NextClimateMode("off", "['cool', bad]").empty());
  values = {{"climate.one", "heat"}, {"climate.one|hvac_modes", all},
            {"climate.two", "off"}, {"climate.two|hvac_modes", "['off', 'dry']"},
            {"climate.three", "off"}};
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
