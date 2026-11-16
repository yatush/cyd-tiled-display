import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class BlindPositionTest(unittest.TestCase):
    def test_draw_drag_release_and_cancellation(self):
        source = (ROOT / "esphome/lib/tiles.h").read_text()
        tile = source.split("class BlindPositionTile : public Tile {", 1)[1].split(
            "\n// A tile that performs actions", 1
        )[0]
        code = r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#define id(x) x
#define ESP_LOGW(...) ((void) 0)
namespace esphome {
namespace touchscreen { struct TouchPoint { int y; }; }
template<class T> std::optional<T> parse_number(const std::string& value) {
  try { size_t n; float v = std::stof(value, &n); if (n == value.size()) return v; }
  catch (...) {}
  return {};
}
}
struct Display {
  int page = 1;
  std::vector<std::pair<int, int>> fills;
  int get_active_page() { return page; }
  void update() {}
  void filled_rectangle(int, int, int, int height, int color) { fills.emplace_back(height, color); }
} disp;
int last_y = 0, light_blue = 1, dark_gray = 2, white = 3, tile_border_width = 1;
int font1 = 4, font2 = 5, *text_bold = &font1, *text_small = &font2;
enum class TextAlign { CENTER };
std::string label;
std::vector<std::string> labels;
std::pair<int, int> measure(int*, const char*) { return {50, 10}; }
void print(int, int, int*, int, TextAlign, const char* text) { label = text; labels.push_back(text); }
int x_start(int x) { return x * 100; }
int y_start(int y) { return y * 100; }
int x_rect() { return 100; }
int y_rect() { return 100; }
struct Sensor {
  std::function<void(bool)> callback;
  void add_on_state_callback(std::function<void(bool)> cb) { callback = cb; }
};
class Tile {
public:
  Tile(int x, int y) : x_(x), y_(y) {}
  virtual ~Tile() = default;
  virtual void initSensors() {}
  virtual void decodeEntities() {}
  virtual bool updateOnEntitiesMapChange() { return false; }
  bool checkActivationMaybeToggle() { return enabled; }
  int getEffectiveBorderWidth() const { return -1; }
  void start() { customInit(); }
  void press() { binary_sensor_->callback(true); }
  void draw() { customDraw(); }
  void leave() { onScreenLeave(); }
  void span(int y) { y_span_ = y; }
  bool enabled = true;
protected:
  virtual void customInit() = 0;
  virtual void customDraw() = 0;
  virtual void onScreenLeave() {}
  Sensor sensor_;
  Sensor* binary_sensor_ = &sensor_;
  int display_page_ = 1, x_, y_, x_span_ = 1, y_span_ = 1;
};
std::set<std::string> repository;
std::vector<const std::string*> dynamic;
std::vector<const std::string*> Pointer(const std::vector<std::string>& values) {
  std::vector<const std::string*> out;
  for (const auto& value : values) out.push_back(&*repository.insert(value).first);
  return out;
}
std::vector<std::string> Deref(const std::vector<const std::string*>& values) {
  std::vector<std::string> out;
  for (const auto* value : values) out.push_back(*value);
  return out;
}
bool HasDynamicEntity(const std::vector<const std::string*>& values) {
  return !values.empty() && values[0]->at(0) == '#';
}
std::vector<const std::string*> ReplaceDynamicEntities(std::vector<const std::string*>&) { return dynamic; }
void InitSensor(const std::string&) {}
std::string GetSensor(const std::string& s) { return s.substr(0, s.find('|')); }
std::map<std::string, std::string> values;
std::string GetTextSensorValue(const std::string& key) { return values[key]; }
std::vector<std::pair<std::string, std::string>> calls;
void PerformHaAction(const std::string& entity, const std::string& action,
                     std::vector<std::pair<std::string, std::string>> data) {
  assert(action == "set_cover_position");
  calls.emplace_back(entity, data.at(0).second);
}
class BlindPositionTile : public Tile {
""" + tile + r"""
int main() {
  BlindPositionTile t(0, 0, {"#{BLINDS}"});
  dynamic = Pointer({"cover.a", "cover.b"});
  values = {{"cover.a|current_position", "100"}, {"cover.b|current_position", "0"}};
  t.start(); t.decodeEntities();
  t.draw(); assert(label == "0-100%"); assert(labels[0] == "Mixed");
  assert(disp.fills.size() == 1 && disp.fills[0].second == dark_gray);
  values["cover.a|current_position"] = "30"; values["cover.b|current_position"] = "70";
  disp.fills.clear(); t.draw(); assert(label == "30-70%");
  assert(disp.fills.size() == 2 && disp.fills[0].second == light_blue && disp.fills[1].second == dark_gray);
  values["cover.a|current_position"] = "100"; values["cover.b|current_position"] = "100";
  disp.fills.clear(); t.draw(); assert(label == "100%"); assert(disp.fills.empty());
  values["cover.a|current_position"] = "0"; values["cover.b|current_position"] = "0";
  t.draw(); assert(label == "0%"); assert(disp.fills.back().second == light_blue);
  values["cover.a|current_position"] = "unknown";
  t.draw(); assert(label == "--");
  t.span(2); last_y = 100; t.press(); t.draw(); assert(label == "50%");
  BlindPositionTile::updateTouch({{210}}); t.draw(); assert(label == "0%");
  assert(calls.empty()); BlindPositionTile::releaseTouch();
  assert(calls.size() == 2 && calls[0].second == "0" && calls[1].second == "0");
  BlindPositionTile::releaseTouch(); assert(calls.size() == 2);
  calls.clear(); last_y = 0; t.press(); t.draw(); assert(label == "100%");
  t.leave(); BlindPositionTile::releaseTouch(); assert(calls.empty());
  last_y = 0; t.press(); BlindPositionTile::updateTouch({{1}, {2}});
  BlindPositionTile::releaseTouch(); assert(calls.empty());
  t.press(); dynamic = Pointer({"cover.c"}); t.decodeEntities();
  BlindPositionTile::releaseTouch(); assert(calls.empty());
  t.press(); disp.page = 2; BlindPositionTile::releaseTouch(); assert(calls.empty());
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.cpp").write_text(code)
            subprocess.run(
                ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 str(path / "test.cpp"), "-o", str(path / "test")],
                check=True,
            )
            subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
