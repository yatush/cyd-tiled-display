#ifndef UTILS_H_
#define UTILS_H_

#include <iostream>
#include <regex>
#include <set>
#include <string>
#include <vector>
#include <map>
#include <sstream>

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
    bin_sensor->set_entity_id(*&sensor);
    // Lambda function to update the display when the sensor state changes.
    bin_sensor->add_on_state_callback([](bool x) { id(disp).update(); });
    if (attribute != "") {
      bin_sensor->set_attribute(attribute);
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
    text_sensor->set_entity_id(*&sensor);
    // Lambda function to update the display when the sensor state changes.
    text_sensor->add_on_state_callback(
        [](std::string x) { id(disp).update(); });
    if (attribute != "") {
      text_sensor->set_attribute(attribute);
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
  HomeassistantActionRequest request;
  // Construct the service name based on the entity and action.
  request.set_service(StringRef(
      (action.find('.') == -1)
          ? entity.substr(0, entity.find('.')).append(".").append(action)
          : action));
  HomeassistantServiceMap entity_id_kv;
  entity_id_kv.set_key(StringRef("entity_id"));
  entity_id_kv.value = entity;
  request.data.push_back(entity_id_kv);
  // Add any additional data to the service call.
  for (const auto pair : data) {
    entity_id_kv.set_key(StringRef(pair.first));
    entity_id_kv.value = pair.second;
    request.data.push_back(entity_id_kv);
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
void ExecuteScripts(const std::vector<esphome::script::Script<Args...>*>& scripts, Args... args) {
  for (auto* script : scripts) {
    script->execute(args...);
  }
}

// Black drawing functionality - erase effectively.
Color mbb(Color value) {
  if (DrawState::is_delete_mode) { return Color::BLACK; }
  return value;
}

class TileFonts {
public:
  enum Size {
    BIG,
    MEDIUM,
    SMALL,
    TINY,
    TEXT_BOLD,
    TEXT,
    TEXT_SMALL,
    TEXT_BIG_BOLD,
  };
  static std::map<TileFonts::Size, BaseFont*> fonts;
};

inline std::map<TileFonts::Size, BaseFont*> TileFonts::fonts = {};


void print (int x, int y, BaseFont *font, Color color, TextAlign align, const char *text) {
  id(disp).print(x, y, font, mbb(color), align, text);
}

void print (int x, int y, TileFonts::Size font_size, Color color, TextAlign align, const char *text) {
  id(disp).print(x, y, TileFonts::fonts[font_size], mbb(color), align, text);
}

void print (int x, int y, BaseFont *font, Color color, const char *text) {
  id(disp).print(x, y, font, mbb(color), text);
}

void print (int x, int y, TileFonts::Size font_size, Color color, const char *text) {
  id(disp).print(x, y, TileFonts::fonts[font_size], mbb(color), text);
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
  id(disp).printf(x, y, font, mbb(color), format, std::forward<Args>(args)...);
}

template<typename... Args>
void printf(int x, int y, TileFonts::Size font_size, Color color, const char *format, Args&&... args) {
  id(disp).printf(x, y, TileFonts::fonts[font_size], mbb(color), format, std::forward<Args>(args)...);
}

template<typename... Args>
void printf(int x, int y, BaseFont *font, Color color, TextAlign align, const char *format, Args&&... args) {
  id(disp).printf(x, y, font, mbb(color), align, format, std::forward<Args>(args)...);
}

template<typename... Args>
void printf(int x, int y, TileFonts::Size font_size, Color color, TextAlign align, const char *format, Args&&... args) {
  id(disp).printf(x, y, TileFonts::fonts[font_size], mbb(color), align, format, std::forward<Args>(args)...);
}

void strftime (int x, int y, BaseFont *font, Color color, TextAlign align, const char *format, ESPTime time) {
  id(disp).strftime(x, y, font, mbb(color), align, format, time);
}

void strftime (int x, int y, TileFonts::Size font_size, Color color, TextAlign align, const char *format, ESPTime time) {
  id(disp).strftime(x, y, TileFonts::fonts[font_size], mbb(color), align, format, time);
}

std::pair<int, int> measure(BaseFont* font, const char* str) {
  int width, x_offset, baseline, height;
  font->measure(str, &width, &x_offset, &baseline, &height);
  return std::pair{width, height};
}

std::pair<int, int> measure(TileFonts::Size font_size, const char* str) {
  return measure(TileFonts::fonts[font_size], str);
}

#endif // UTILS_H_