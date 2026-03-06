#ifndef UTILS_H_
#define UTILS_H_

#include <iostream>
#include <regex>
#include <set>
#include <string>
#include <vector>
#include <map>
#include <sstream>
#include <type_traits>
#include <mutex>

// --- String repository ---

class Repository {
private:
  std::set<std::string> strings_; // Store strings directly
  mutable std::mutex mutex_;

public:
  static Repository& instance() {
    static Repository repo;
    return repo;
  }

  const std::string* ptr(const std::string& str) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = strings_.find(str);
    if (it != strings_.end()) {
      return &(*it); // Return pointer to existing string
    }

    it = strings_.insert(str).first; // Insert and get iterator
    return &(*it); // Return pointer to newly inserted string
  }

  std::vector<const std::string*> ptr(const std::vector<std::string>& str_vec) {
    std::vector<const std::string*> result;
    result.reserve(str_vec.size());

    std::transform(
      str_vec.begin(), str_vec.end(), std::back_inserter(result),
      [this](const std::string& str) { return this->ptr(str); });

    return result;
  }

  std::vector<std::string> dereference(const std::vector<const std::string*>& str_ptr_vec) const {
    std::vector<std::string> result;
    result.reserve(str_ptr_vec.size());

    std::transform(
      str_ptr_vec.begin(), str_ptr_vec.end(), std::back_inserter(result),
      [](const std::string* str_ptr) {
        return *str_ptr;
      });
      return result;
  }

  const std::pair<const std::string*, const std::string*> ptr(
      const std::pair<std::string, std::string>& str_pair) {
    return std::make_pair(ptr(str_pair.first), ptr(str_pair.second));
  }

  const std::pair<std::vector<const std::string*>, const std::string*> ptr(
      const std::pair<std::vector<std::string>, std::string>& pair) {
    return std::make_pair(ptr(pair.first), ptr(pair.second));
  }

  std::vector<std::pair<const std::string*, const std::string*>> ptr(
      const std::vector<std::pair<std::string, std::string>>& vec) {
    std::vector<std::pair<const std::string*, const std::string*>> result;
    result.reserve(vec.size());

    std::transform(
      vec.begin(), vec.end(), std::back_inserter(result),
      [this](const std::pair<std::string, std::string>& pair) {
        return this->ptr(pair);
      });

    return result;
  }

  std::vector<std::pair<std::vector<const std::string*>, const std::string*>> ptr(
      const std::vector<std::pair<std::vector<std::string>, std::string>>& vec) {
    std::vector<std::pair<std::vector<const std::string*>, const std::string*>> result;
    result.reserve(vec.size());

    std::transform(
      vec.begin(), vec.end(), std::back_inserter(result),
      [this](const std::pair<std::vector<std::string>, std::string>& pair) {
        return this->ptr(pair);
      });

    return result;
  }
};

const std::string* Pointer(const std::string& str) {
  return Repository::instance().ptr(str);
}

std::vector<const std::string*> Pointer(const std::vector<std::string>& vec) {
  return Repository::instance().ptr(vec);
}

std::vector<std::pair<const std::string*, const std::string*>> Pointer(
  const std::vector<std::pair<std::string, std::string>>& str_vec) {
  return Repository::instance().ptr(str_vec);
}

std::vector<std::pair<std::vector<const std::string*>, const std::string*>> Pointer(
  const std::vector<std::pair<std::vector<std::string>, std::string>>& vec) {
  return Repository::instance().ptr(vec);
}

std::vector<std::string> Deref(const std::vector<const std::string*>& vec) {
  return Repository::instance().dereference(vec);
}

// --- Entity Map Functions ---

// Checks if the entity map contains the given key and value.
bool EMContains(const std::string* key, const std::string* value) {
  return id(entities_map).count(key) > 0 &&
         id(entities_map)[key].find(value) != id(entities_map)[key].end();
}

// Checks if the entity map contains the given key and ALL of the given values.
bool EMContains(const std::string* key, const std::vector<const std::string*>& values) {
  if (id(entities_map).count(key) == 0) {
    return false;
  }
  for (const std::string* value : values) {
    if (id(entities_map)[key].find(value) == id(entities_map)[key].end()) {
      return false;
    }
  }
  return true;
}

// Checks if the entity map contains the given key.
bool EMContains(const std::string* key) {
  return id(entities_map).count(key) > 0;
}

// Adds a key-value pair to the entity map.
void EMAdd(const std::string* key, const std::string* value) {
  if (value->empty()) {
    return;
  }
  id(entities_map)[key].insert(value);
}

// Adds multiple values to the entity map for the given key.
void EMAdd(const std::string* key, const std::vector<const std::string*>& values) {
  for (const std::string* value : values) {
    EMAdd(key, value);
  }
}

// Removes a value from the entity map for the given key.
// If the key has no more values, it's removed from the map.
void EMRemove(const std::string* key, const std::string* value) {
  id(entities_map)[key].erase(value);
  if (id(entities_map)[key].size() == 0) {
    id(entities_map).erase(key);
  }
}

// Removes multiple values from the entity map for the given key.
void EMRemove(const std::string* key, const std::vector<const std::string*>& values) {
  for (const std::string* value : values) {
    EMRemove(key, value);
  }
}

// Returns all values associated with the given key in the entity map.
std::vector<const std::string*> EMGetValues(const std::string* key) {
  return std::vector<const std::string*>(
    id(entities_map)[key].begin(), id(entities_map)[key].end());
}

// Sets the value for the given key in the entity map.
void EMSet(const std::string* key, const std::string* value) {
  if (value->empty()) {
    return;
  }
  id(entities_map)[key] = {value};
}

// Sets multiple values for the given key in the entity map.
void EMSet(const std::string* key, const std::vector<const std::string*>& values) {
  id(entities_map)[key] = {};
  for (const std::string* value : values) {
    if (!value->empty()) {
      id(entities_map)[key].insert(value);
    }
  }
}

// Clears the values for the given key in the entity map.
void EMClear(const std::string* key) {
  if (key->empty()) {
    return;
  }
  id(entities_map)[key] = {};
}

// --- String Utility Functions ---

// Checks if a string represents an integer.
bool IsInteger(const std::string& str) {
  return !str.empty() && std::all_of(str.begin(), str.end(), [](char c) {
    return c <= '9' && c >= '0';
  });
}

/**
 * @brief Extracts the sensor name from a combined string.
 * 
 * Example: "sensor.temperature|unit_of_measurement" -> "sensor.temperature"
 * 
 * @param text The input string containing sensor and optional attribute
 * @return std::string The sensor entity ID
 */
std::string GetSensor(const std::string& text) {
  if (text.find("|") == -1) {
    return text;
  }
  return text.substr(0, text.find("|"));
}

/**
 * @brief Extracts the attribute name from a combined string.
 * 
 * Example: "sensor.temperature|unit_of_measurement" -> "unit_of_measurement"
 * 
 * @param text The input string containing sensor and optional attribute
 * @return std::string The attribute name, or empty string if none
 */
std::string GetAtt(const std::string& text) {
  if (text.find("|") == -1) {
    return "";
  }
  return text.substr(text.find("|") + 1);
}

// --- Sensor Type Checking ---

/**
 * @brief Checks if a key represents a text sensor (e.g., climate, cover).
 * 
 * @param key The entity ID to check
 * @return true If the entity is treated as a text sensor
 * @return false Otherwise
 */
bool IsTextSensor(const std::string& key) {
  return key.find("climate.") == 0 || key.find("cover.") == 0;
}

/**
 * @brief Checks if a key represents a binary sensor (e.g., switch, light).
 * 
 * @param key The entity ID to check
 * @return true If the entity is treated as a binary sensor
 * @return false Otherwise
 */
bool IsBinSensor(const std::string& key) {
  return key.find("switch.") == 0 || key.find("light.") == 0;
}

// Returns a vector of required attributes for a given sensor.
std::vector<std::string> getRequiredAttributes(const std::string& sensor) {
  if (sensor.substr(0, 7) == "climate") {
    return {"temperature"};
  }
  if (sensor.substr(0, 5) == "cover") {
    return {"current_position"};
  }
  return {};
}

// --- Sensor Initialization ---

// Initializes a sensor in ESPHome, connecting it to Home Assistant.
// Handles both binary and text sensors, optionally setting an attribute.
void InitSensor(const std::string& key, const std::string& sensor,
                const std::string& attribute = "") {
  if (IsBinSensor(sensor)) {
    if (id(binary_sensors).count(key) != 0) {
      return;
    }
    auto* bin_sensor = new esphome::homeassistant::HomeassistantBinarySensor();
    bin_sensor->set_internal(true);
    bin_sensor->set_entity_id(Repository::instance().ptr(sensor)->c_str());
    // Lambda function to update the display when the sensor state changes.
    bin_sensor->add_on_state_callback([](bool x) { id(disp).update(); });
    if (attribute != "") {
      bin_sensor->set_attribute(Repository::instance().ptr(attribute)->c_str());
    }
    ESP_LOGI("Init bin sensor", "Entity: %s, Attribute: %s", sensor.c_str(),
             attribute.c_str());
    bin_sensor->setup();
    id(binary_sensors)[key] = bin_sensor;
  } else if (IsTextSensor(sensor)) {
    if (id(text_sensors).count(key) != 0) {
      return;
    }
    auto* text_sensor = new esphome::homeassistant::HomeassistantTextSensor();
    text_sensor->set_internal(true);
    text_sensor->set_entity_id(Repository::instance().ptr(sensor)->c_str());
    // Lambda function to update the display when the sensor state changes.
    text_sensor->add_on_state_callback(
        [](std::string x) { id(disp).update(); });
    if (attribute != "") {
      text_sensor->set_attribute(Repository::instance().ptr(attribute)->c_str());
    }
    ESP_LOGI("Init text sensor", "Entity: %s, Attribute: %s", sensor.c_str(),
             attribute.c_str());
    text_sensor->setup();
    id(text_sensors)[key] = text_sensor;
  }
}

// Initializes a sensor and its required attributes.
void InitSensor(const std::string& sensor) {
  InitSensor(sensor, sensor, "");
  for (const std::string& att : getRequiredAttributes(sensor)) {
    InitSensor(sensor + "|" + att, sensor, att);
  }
}

// --- Sensor Value Retrieval ---

// Retrieves the value of a text sensor.
std::string GetTextSensorValue(const std::string& key) {
  if (!IsTextSensor(key) || id(text_sensors).count(key) == 0) {
    return "";
  }
  return id(text_sensors)[key]->state;
}

// Retrieves the value of a binary sensor.
bool GetBinSensorValue(const std::string& key) {
  if (!IsBinSensor(key) || id(binary_sensors).count(key) == 0) {
    return false;
  }
  return id(binary_sensors)[key]->state;
}

// --- Helper Functions ---

// Lambda function to check if any entity in a vector is "on".
std::function<bool(const std::vector<std::string>&)> IsAnyOn =
    [](const std::vector<std::string>& entities) {
      return std::any_of(entities.begin(), entities.end(),
                         [](const std::string& entity) {
                           if (IsBinSensor(entity)) {
                             return GetBinSensorValue(entity);
                           }
                           if (IsTextSensor(entity)) {
                             return GetTextSensorValue(entity) != "off";
                           }
                           return false;
                         });
    };

// Performs a Home Assistant service call.
void PerformHaAction(
    const std::string& entity, const std::string& action,
    std::vector<std::pair<std::string, std::string>> data = {}) {
  
  std::string service_name = (action.find('.') == -1)
          ? entity.substr(0, entity.find('.')).append(".").append(action)
          : action;

  ESP_LOGI("ha_action", "Service: %s, Entity: %s", service_name.c_str(), entity.c_str());
  for (const auto& pair : data) {
    ESP_LOGI("ha_action", "  Data: %s = %s", pair.first.c_str(), pair.second.c_str());
  }

  esphome::api::HomeassistantActionRequest request;
  // Set the service name using StringRef
  request.service = StringRef(service_name);
  
  // IMPORTANT: Must call init() before push_back - FixedVector requires this!
  request.data.init(1 + data.size());
  
  // Add entity_id as the first data item  
  esphome::api::HomeassistantServiceMap entity_id_kv;
  entity_id_kv.key = StringRef("entity_id");
  entity_id_kv.value = StringRef(entity);
  request.data.push_back(entity_id_kv);
  
  // Add any additional data to the service call
  for (const auto& pair : data) {
    esphome::api::HomeassistantServiceMap kv;
    kv.key = StringRef(pair.first);
    kv.value = StringRef(pair.second);
    request.data.push_back(kv);
  }
  
  id(api_server).send_homeassistant_action(request);
}

// Extracts an ID from a string using a regular expression.
// Example: "#{some_id}" -> "some_id"
std::string ExtractId(const std::string& input) {
  std::regex pattern("#\\{([^}]+)\\}");
  std::smatch match;
  if (std::regex_search(input, match, pattern)) {
    return match[1];
  } else {
    return "";
  }
}

// Replaces the first occurrence of a substring within a string.
std::string ReplaceFirstOccurrence(const std::string& input,
                                   const std::string& toReplace,
                                   const std::string& replacement) {
  size_t pos = input.find(toReplace);
  if (pos != std::string::npos) {
    std::string result = input;
    return result.replace(pos, (size_t)(toReplace.length()), replacement);
  } else {
    return input;
  }
}

// Splits a string by a delimiter.
std::vector<std::string> SplitString(const std::string& input, char delimiter) {
  std::vector<std::string> result;
  std::stringstream ss(input);
  std::string item;
  while (std::getline(ss, item, delimiter)) {
    if (!item.empty()) {
      result.push_back(item);
    }
  }
  return result;
}

// Replaces dynamic entity placeholders (e.g., "#{some_id}") with actual entity
// IDs from the entity map.
std::vector<const std::string*> ReplaceDynamicEntities(
    std::vector<const std::string*>& source) {
  std::vector<const std::string*> result = {};
  for (int i = 0; i < source.size(); ++i) {
    if (source[i]->find("#") == -1) {
      result.push_back(source[i]);
      continue;
    }
    const std::string* key = Pointer(ExtractId(*source[i]));
    if (!EMContains(key)) {
      continue;
    }
    auto replacements = EMGetValues(key);
    for (const std::string* replacement : replacements) {
      if (!replacement->empty()) {
        result.push_back(Pointer(
            ReplaceFirstOccurrence(*source[i], "#{" + *key + "}", *replacement)));
      }
    }
  }
  return result;
}

// Checks if a vector of strings contains any dynamic entity placeholders.
bool HasDynamicEntity(const std::vector<const std::string*>& vec) {
  return std::any_of(vec.begin(), vec.end(), [](const std::string* str) {
    return str->find("#") != -1;
  });
}

// Checks if a vector of strings contains any dynamic entity placeholders
// that are missing or have no valid replacements in the entity map.
bool MissingDynamicEntity(std::vector<const std::string*>& source) {
  for (int i = 0; i < source.size(); ++i) {
    if (source[i]->find("#") == -1) {
      continue;
    }
    const std::string* key = Pointer(ExtractId(*source[i]));
    if (!EMContains(key)) {
      return true;
    }
    auto replacements = EMGetValues(key);
    if (replacements.size() == 0) {
      return true;
    }
    // Check if all replacements are empty strings.
    if (std::all_of(replacements.begin(), replacements.end(),
                    [](const std::string* str) { return str->length() == 0; })) {
      return true;
    }
  }
  return false;
}

template <typename... Args>
void ExecuteScripts(const std::vector<std::function<void(Args...)>>& scripts, Args... args) {
  for (const auto& script : scripts) {
    script(args...);
  }
}

int x_rect() {
  return (id(width) - (id(cols) + 1) * id(x_pad)) / id(cols);
}

int y_rect() {
  return (id(height) - (id(rows) + 1) * id(y_pad)) / id(rows);
}

int x_start(int index) {
  return index * (x_rect() + id(x_pad)) + id(x_pad);
}

int y_start(int index) {
  return index * (y_rect() + id(y_pad)) + id(y_pad);
}

// Black drawing functionality - erase effectively.
Color mbb(Color value) {
  if (DrawState::is_delete_mode) { return Color::BLACK; }
  return value;
}

void print (int x, int y, BaseFont *font, Color color, TextAlign align, const char *text) {
  id(disp).print(x, y, font, mbb(color), align, text);
}

void print (int x, int y, BaseFont &font, Color color, TextAlign align, const char *text) {
  print(x, y, &font, color, align, text);
}

void print (int x, int y, BaseFont *font, Color color, const char *text) {
  id(disp).print(x, y, font, mbb(color), text);
}

void print (int x, int y, BaseFont &font, Color color, const char *text) {
  print(x, y, &font, color, text);
}

void line (int x1, int y1, int x2, int y2, Color color) {
  id(disp).line(x1, y1, x2, y2, mbb(color));
}

void circle (int center_x, int center_y, int radius, Color color) {
  id(disp).circle(center_x, center_y, radius, mbb(color));
}

void rectangle (int x1, int y1, int width, int height, Color color) {
  id(disp).rectangle(x1, y1, width, height, mbb(color));
}

void filled_rectangle (int x1, int y1, int width, int height, Color color) {
  id(disp).filled_rectangle(x1, y1, width, height, mbb(color));
}

template<typename... Args>
void printf(int x, int y, BaseFont *font, Color color, const char *format, Args&&... args) {
  if (sizeof...(args) == 0) {
    id(disp).print(x, y, font, mbb(color), format);
  } else {
    id(disp).printf(x, y, font, mbb(color), format, std::forward<Args>(args)...);
  }
}

template<typename... Args>
void printf(int x, int y, BaseFont &font, Color color, const char *format, Args&&... args) {
  printf(x, y, &font, color, format, std::forward<Args>(args)...);
}

template<typename... Args>
void printf(int x, int y, BaseFont *font, Color color, TextAlign align, const char *format, Args&&... args) {
  if (sizeof...(args) == 0) {
    id(disp).print(x, y, font, mbb(color), align, format);
  } else {
    id(disp).printf(x, y, font, mbb(color), align, format, std::forward<Args>(args)...);
  }
}

template<typename... Args>
void printf(int x, int y, BaseFont &font, Color color, TextAlign align, const char *format, Args&&... args) {
  printf(x, y, &font, color, align, format, std::forward<Args>(args)...);
}

void strftime (int x, int y, BaseFont *font, Color color, TextAlign align, const char *format, ESPTime time) {
  id(disp).strftime(x, y, font, mbb(color), align, format, time);
}

void strftime (int x, int y, BaseFont &font, Color color, TextAlign align, const char *format, ESPTime time) {
  strftime(x, y, &font, color, align, format, time);
}

std::pair<int, int> measure(BaseFont* font, const char* str) {
  int width, x_offset, baseline, height;
  font->measure(str, &width, &x_offset, &baseline, &height);
  return std::pair{width, height};
}

std::pair<int, int> measure(BaseFont& font, const char* str) {
  return measure(&font, str);
}

#define RUN_SCRIPT(script, ...) ([&](auto&& s){ \
    if constexpr (std::is_pointer_v<std::remove_reference_t<decltype(s)>>) { \
        s->execute(__VA_ARGS__); \
    } else { \
        s.execute(__VA_ARGS__); \
    } \
    return id(script_output); \
}(script))

// ---------------------------------------------------------------------------
// Image draw helpers
// ---------------------------------------------------------------------------
// Padding (px) kept between a drawn image and the tile edge on every side.
// Must match _FIXED_PAD in configurator/generate_tiles_api.py.
constexpr int IMAGE_DRAW_PAD = 5;

// DrawImageFunc — the type expected by HAActionTile's draw_funcs vector.
using DrawImageFunc = std::function<void(int, int, int, int, std::vector<std::string>)>;

// make_image_draw — returns a DrawImageFunc that draws a single static image.
inline DrawImageFunc make_image_draw(esphome::image::Image* image) {
  return [image](int x0, int x1, int y0, int y1, std::vector<std::string>) {
    id(image_slot) = image;
    id(draw_image_static).execute(x0, x1, y0, y1);
  };
}

// make_image_draw — animated (single image, positional sweep).
//   from_x/y, to_x/y: fractions [0,1] of tile dimensions for image start/end position.
inline DrawImageFunc make_image_draw(esphome::image::Image* image, float from_x, float from_y, float to_x, float to_y, uint32_t duration_ms) {
  return [image, from_x, from_y, to_x, to_y, duration_ms](int x0, int x1, int y0, int y1, std::vector<std::string>) {
    id(image_slot) = image;
    id(draw_image_anim).execute(x0, x1, y0, y1, (int)duration_ms, from_x, from_y, to_x, to_y);
  };
}

// make_image_draw — cycling through multiple images, static display.
//   duration_ms: total cycle time; per-image time = duration_ms / n
inline DrawImageFunc make_image_draw(std::vector<esphome::image::Image*> images, uint32_t duration_ms) {
  return [images, duration_ms](int x0, int x1, int y0, int y1, std::vector<std::string> s) {
    uint32_t n = (uint32_t)images.size();
    if (n == 0) return;
    make_image_draw(images[(millis() / (duration_ms / n)) % n])(x0, x1, y0, y1, s);
  };
}

// make_image_draw — cycling through multiple images, animated sweep.
//   duration_ms: total cycle time. ONE continuous sweep; image shown changes at
//   each 1/n boundary but position uses shared _frac for an uninterrupted sweep.
inline DrawImageFunc make_image_draw(std::vector<esphome::image::Image*> images, float from_x, float from_y, float to_x, float to_y, uint32_t duration_ms) {
  return [images, from_x, from_y, to_x, to_y, duration_ms](int x0, int x1, int y0, int y1, std::vector<std::string>) {
    uint32_t n = (uint32_t)images.size();
    if (n == 0) return;
    float _frac = fmodf(millis() / (float)duration_ms, 1.0f);
    uint32_t _idx = (uint32_t)(_frac * n) % n;
    id(image_slot) = images[_idx];
    id(draw_image_anim_frac).execute(x0, x1, y0, y1, _frac, from_x, from_y, to_x, to_y);
  };
}

// ---------------------------------------------------------------------------
// Cycle-aligned overloads — used for multi-step animations.
// ---------------------------------------------------------------------------

// Animated single image, cycle-aligned.
inline DrawImageFunc make_image_draw(esphome::image::Image* image, float from_x, float from_y, float to_x, float to_y, uint32_t step_dur_ms, uint32_t total_ms, uint32_t step_start_ms) {
  return [image, from_x, from_y, to_x, to_y, step_dur_ms, total_ms, step_start_ms](int x0, int x1, int y0, int y1, std::vector<std::string>) {
    uint32_t _ct = millis() % total_ms;
    float _frac = (_ct >= step_start_ms) ? (_ct - step_start_ms) / (float)step_dur_ms : 0.0f;
    if (_frac > 1.0f) _frac = 1.0f;
    id(image_slot) = image;
    id(draw_image_anim_frac).execute(x0, x1, y0, y1, _frac, from_x, from_y, to_x, to_y);
  };
}

// Cycling static images, cycle-aligned.
inline DrawImageFunc make_image_draw(std::vector<esphome::image::Image*> images, uint32_t step_dur_ms, uint32_t total_ms, uint32_t step_start_ms) {
  return [images, step_dur_ms, total_ms, step_start_ms](int x0, int x1, int y0, int y1, std::vector<std::string> s) {
    uint32_t n = (uint32_t)images.size();
    if (n == 0) return;
    uint32_t _ct = millis() % total_ms;
    float _frac = (_ct >= step_start_ms) ? (_ct - step_start_ms) / (float)step_dur_ms : 0.0f;
    if (_frac > 1.0f) _frac = 1.0f;
    make_image_draw(images[(uint32_t)(_frac * n) % n])(x0, x1, y0, y1, s);
  };
}

// Cycling animated images, cycle-aligned.
inline DrawImageFunc make_image_draw(std::vector<esphome::image::Image*> images, float from_x, float from_y, float to_x, float to_y, uint32_t step_dur_ms, uint32_t total_ms, uint32_t step_start_ms) {
  return [images, from_x, from_y, to_x, to_y, step_dur_ms, total_ms, step_start_ms](int x0, int x1, int y0, int y1, std::vector<std::string>) {
    uint32_t n = (uint32_t)images.size();
    if (n == 0) return;
    uint32_t _ct = millis() % total_ms;
    float _frac = (_ct >= step_start_ms) ? (_ct - step_start_ms) / (float)step_dur_ms : 0.0f;
    if (_frac > 1.0f) _frac = 1.0f;
    uint32_t _idx = (uint32_t)(_frac * n) % n;
    id(image_slot) = images[_idx];
    id(draw_image_anim_frac).execute(x0, x1, y0, y1, _frac, from_x, from_y, to_x, to_y);
  };
}

#endif // UTILS_H_