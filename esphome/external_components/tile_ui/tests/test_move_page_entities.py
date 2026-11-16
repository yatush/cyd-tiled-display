import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class MovePageEntitiesTest(unittest.TestCase):
    def test_display_entities_and_navigation(self):
        source = (ROOT / "esphome/lib/tiles.h").read_text()
        tile = source.split("class MovePageTile : public Tile {", 1)[1].split(
            "\n// A tile that executes functions", 1
        )[0]
        code = r"""
#include <cassert>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>
#define id(x) x
namespace esphome { namespace display { struct DisplayPage {}; } }
using DrawImageFunc = std::function<void(int, int, int, int, std::vector<std::string>)>;
struct Sensor {
  std::vector<std::function<void(bool)>> callbacks;
  void add_on_state_callback(std::function<void(bool)> cb) { callbacks.push_back(cb); }
  void press() { for (auto& cb : callbacks) cb(true); }
};
struct Display {
  esphome::display::DisplayPage* page = nullptr;
  void show_page(esphome::display::DisplayPage* p) { page = p; }
  void update() {}
} disp;
bool ignore_touch = false;
int x_start(int x) { return x * 100; }
int y_start(int y) { return y * 100; }
int x_rect() { return 100; }
int y_rect() { return 100; }
class Tile {
public:
  Tile(int x, int y) : x_(x), y_(y) {}
  virtual ~Tile() = default;
  virtual void initSensors() {}
  virtual void decodeEntities() {}
  virtual bool updateOnEntitiesMapChange() { return false; }
  void start() { customInit(); initSensors(); }
  void draw() { customDraw(); }
  void press() { sensor.press(); }
  std::function<void()> change_screen_callback_ = []() {};
  std::function<void()> change_entities_callback_ = []() {};
protected:
  virtual void customInit() = 0;
  virtual void customDraw() = 0;
  Sensor sensor;
  Sensor* binary_sensor_ = &sensor;
  int x_, y_, x_span_ = 1, y_span_ = 1;
};
std::set<std::string> repository;
const std::string* Pointer(const std::string& value) { return &*repository.insert(value).first; }
std::vector<const std::string*> Pointer(const std::vector<std::string>& values) {
  std::vector<const std::string*> out;
  for (const auto& value : values) out.push_back(Pointer(value));
  return out;
}
std::vector<std::string> Deref(const std::vector<const std::string*>& values) {
  std::vector<std::string> out;
  for (const auto* value : values) out.push_back(*value);
  return out;
}
std::map<std::string, std::vector<const std::string*>> dynamic;
void EMSet(const std::string* key, const std::vector<const std::string*>& value) { dynamic[*key] = value; }
bool HasDynamicEntity(const std::vector<const std::string*>& values) {
  for (const auto* value : values) if (value->find("#{") == 0) return true;
  return false;
}
std::vector<const std::string*> ReplaceDynamicEntities(std::vector<const std::string*>& values) {
  std::vector<const std::string*> out;
  for (const auto* value : values) {
    if (value->find("#{") == 0) {
      auto& selected = dynamic[value->substr(2, value->size() - 3)];
      out.insert(out.end(), selected.begin(), selected.end());
    } else out.push_back(value);
  }
  return out;
}
std::set<std::string> subscriptions;
void InitSensor(const std::string& entity) { subscriptions.insert(entity); }
void ExecuteScripts(const std::vector<DrawImageFunc>& functions, int x1, int x2, int y1, int y2,
                    std::vector<std::string> entities) {
  for (const auto& function : functions) function(x1, x2, y1, y2, entities);
}
class MovePageTile : public Tile {
""" + tile + r"""
int main() {
  esphome::display::DisplayPage page;
  std::vector<std::string> rendered;
  DrawImageFunc draw = [&](int, int, int, int, std::vector<std::string> entities) { rendered = entities; };
  MovePageTile tile(0, 0, {draw}, &page, {"climate.static", "#{AC}"});
  tile.setDynamicEntry("ROOM", {"living"});
  int changes = 0, navigations = 0;
  tile.change_entities_callback_ = [&]() { ++changes; tile.decodeEntities(); };
  tile.change_screen_callback_ = [&]() { ++navigations; };
  dynamic["AC"] = Pointer(std::vector<std::string>{"climate.one"});
  tile.start(); tile.decodeEntities(); tile.draw();
  assert((rendered == std::vector<std::string>{"climate.static", "climate.one"}));
  assert(subscriptions.count("climate.static") && subscriptions.count("climate.one"));
  dynamic["AC"] = Pointer(std::vector<std::string>{"climate.two"});
  tile.decodeEntities(); tile.draw();
  assert((rendered == std::vector<std::string>{"climate.static", "climate.two"}));
  assert(subscriptions.count("climate.two"));
  tile.press();
  assert(changes == 1 && navigations == 1 && disp.page == &page && ignore_touch);
  assert(Deref(dynamic["ROOM"]) == std::vector<std::string>{"living"});
  MovePageTile legacy(0, 0, {draw}, &page);
  legacy.start(); legacy.decodeEntities(); legacy.draw(); assert(rendered.empty());
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
