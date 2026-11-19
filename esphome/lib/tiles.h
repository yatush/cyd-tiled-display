#ifndef TILES_H
#define TILES_H

class Tile {
public:
  Tile(int x, int y)
      : x_(x), y_(y) {
    // Initialize the binary sensor for touch detection.
    this->binary_sensor_ = new TouchscreenBinarySensor();
    this->binary_sensor_->set_parent(&id(touchscreen_id));
  }

  // Draw the tile on the display.
  void draw() {
    if (this->display_page_ != id(disp).get_active_page()) {
      return;
    }
    int eff_bw = this->getEffectiveBorderWidth();
    if (eff_bw < 0) eff_bw = id(tile_border_width);
    int eff_br = this->getEffectiveBorderRadius();
    if (eff_br < 0) eff_br = id(border_r);
    int max_bd = this->maxBorderDimension();
    eff_br = std::min(eff_br, max_bd);
    eff_bw = std::min(eff_bw, max_bd);
    for (auto& entry : this->fill_colors_) {
      if (entry.second({})) {
        id(_draw_tile_fill).execute(this->x_, this->y_, this->x_span_, this->y_span_, entry.first, eff_br);
      }
    }
    {
      Color border_c = this->getEffectiveBorderColor();
      id(_draw_tile_frame).execute(this->x_, this->y_, this->x_span_, this->y_span_, border_c, eff_bw, eff_br);
    }
    this->customDraw();
  }

  // Indicates if the tile needs frequent refreshing (default: false).
  virtual bool requiresFastRefresh() { return false; }

  // Indicates if the tile needs to be updated when the entities map changes
  // (default: false).
  virtual bool updateOnEntitiesMapChange() { return false; }

  // Checks if the tile is located below the Wi-Fi indicator.
  bool isBelowWifi() const {
    if (this->display_page_ != id(disp).get_active_page()) {
      return false;
    }
    return this->y_ == 0 && (this->x_ == id(cols) - 1);
  }

  // Adds an unconditional border color override.
  Tile* addBorderColor(Color c) {
    this->border_colors_.push_back({c, [](std::vector<std::string>) { return true; }});
    return this;
  }

  // Adds a conditional border color override.
  Tile* addBorderColor(Color c, std::function<bool(std::vector<std::string>)> cond) {
    this->border_colors_.push_back({c, cond});
    return this;
  }

  // Returns the effective border color: last entry whose condition is true, or id(gray) by default.
  Color getEffectiveBorderColor() const {
    for (int i = (int)this->border_colors_.size() - 1; i >= 0; --i) {
      if (this->border_colors_[i].second({})) {
        return this->border_colors_[i].first;
      }
    }
    return id(gray);
  }

  // Adds an unconditional border width override.
  Tile* addBorderWidth(int v) {
    this->border_widths_.push_back({v, [](std::vector<std::string>) { return true; }});
    return this;
  }

  // Adds a conditional border width override.
  Tile* addBorderWidth(int v, std::function<bool(std::vector<std::string>)> cond) {
    this->border_widths_.push_back({v, cond});
    return this;
  }

  // Returns the effective border width: last entry whose condition is true, or -1 (use global).
  int getEffectiveBorderWidth() const {
    for (int i = (int)this->border_widths_.size() - 1; i >= 0; --i) {
      if (this->border_widths_[i].second({})) {
        return this->border_widths_[i].first;
      }
    }
    return -1;
  }

  // Adds an unconditional border radius override.
  Tile* addBorderRadius(int v) {
    this->border_radii_.push_back({v, [](std::vector<std::string>) { return true; }});
    return this;
  }

  // Adds a conditional border radius override.
  Tile* addBorderRadius(int v, std::function<bool(std::vector<std::string>)> cond) {
    this->border_radii_.push_back({v, cond});
    return this;
  }

  // Returns the effective border radius: last entry whose condition is true, or -1 (use global).
  int getEffectiveBorderRadius() const {
    for (int i = (int)this->border_radii_.size() - 1; i >= 0; --i) {
      if (this->border_radii_[i].second({})) {
        return this->border_radii_[i].first;
      }
    }
    return -1;
  }

  // Returns max(w/2, h/2) in pixels for this tile — the upper bound for border width and radius.
  int maxBorderDimension() const {
    int tile_w = x_rect() * this->x_span_ + (this->x_span_ - 1) * id(x_pad);
    int tile_h = y_rect() * this->y_span_ + (this->y_span_ - 1) * id(y_pad);
    return std::min(tile_w, tile_h) / 2;
  }

  // Adds an unconditional background fill color.
  Tile* addFillColor(Color c) {
    this->fill_colors_.push_back({c, [](std::vector<std::string>) { return true; }});
    return this;
  }

  // Adds a conditional background fill color (rendered only when cond returns true).
  Tile* addFillColor(Color c, std::function<bool(std::vector<std::string>)> cond) {
    this->fill_colors_.push_back({c, cond});
    return this;
  }

  // Sets the span of the tile (default: 1x1).
  Tile* setSpan(int x_span, int y_span) {
    this->x_span_ = x_span;
    this->y_span_ = y_span;
    return this;
  }

  // Decodes dynamic entities within the tile (default: no-op).
  virtual void decodeEntities() {};

  // Initializes sensors associated with the tile (default: no-op).
  virtual void initSensors() {};

  // Sets a callback function to be called when entities related to the tile
  // change.
  void setChangeEntitiesCallback(
      std::function<void()> change_entities_callback) {
    this->change_entities_callback_ = change_entities_callback;
  }

  // The dynamic variable name and value for this tile to be active.
  Tile* setActivationVar(const std::string& var_name, const std::vector<std::string>& var_values) {
    this->var_name_ = Pointer(var_name);
    this->var_values_ = Pointer(var_values);
    this->always_active_ = false;
    return this;
  }

  // Indicates if this tile is active or not. In case this is becoming active,
  // run the onActivation function.
  bool checkActivationMaybeToggle() {
    if (this->always_active_) {
      return true;
    }
    if (EMContains(this->var_name_, this->var_values_)) {
      if (!this->was_active_) {
        this->onActivation();
      }
      this->was_active_ = true;
      return true;
    }
    this->was_active_ = false;
    return false;
  }

  void updateTouchArea() {
    if (this->binary_sensor_ != nullptr) {
      int x_end_idx = this->x_ + this->x_span_ - 1;
      int y_end_idx = this->y_ + this->y_span_ - 1;
      this->binary_sensor_->set_area(
          x_start(this->x_), x_start(x_end_idx) + x_rect(),
          y_start(this->y_), y_start(y_end_idx) + y_rect());
    }
  }

  static constexpr uint32_t kTouchReleaseGraceMs = 150;

  static bool isTouchBlockedFor(const Tile* tile) {
    return active_touch_tile_ != nullptr && active_touch_tile_ != tile;
  }

  static bool hasActiveTouchSession() {
    return screen_touch_active_ || active_touch_tile_ != nullptr;
  }

  static bool isScreenTouchActive() { return screen_touch_active_; }

  static void claimTouchTile(Tile* tile) {
    if (active_touch_tile_ == nullptr) {
      active_touch_tile_ = tile;
    }
  }

  static void releaseTouchTile(const Tile* tile) {
    if (active_touch_tile_ == tile) {
      active_touch_tile_ = nullptr;
    }
  }

  static void notifyScreenTouch() {
    screen_touch_active_ = true;
    ++screen_release_gen_;
    if (active_touch_tile_ != nullptr) {
      active_touch_tile_->onScreenTouchResume();
    }
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
            if (!screen_touch_active_ && gen == screen_release_gen_) {
              id(ignore_touch) = false;
            }
          });
    }
  }

  friend class TiledScreen;

protected:
  // Performs custom initialization specific to the tile type (pure virtual).
  virtual void customInit() = 0;

  // Performs custom drawing for the tile.
  virtual void customDraw() = 0;

  virtual void onActivation() {}

  virtual void onScreenLeave() {};

  virtual bool holdsTouchDuringReleaseGrace() const { return false; }

  virtual void onScreenTouchPause() {}

  virtual void onScreenTouchResume() {}

  // Pointer to the display page this tile belongs to.
  esphome::display::DisplayPage* display_page_ = nullptr;
  // Pointer to the binary sensor for touch input.
  TouchscreenBinarySensor* binary_sensor_ = nullptr;
  // X-coordinate of the tile.
  int x_;
  // Y-coordinate of the tile.
  int y_;
  // Span of the tile in the X direction.
  int x_span_ = 1;
  // Span of the tile in the Y direction.
  int y_span_ = 1;
  // Conditional fill colors for the tile background (rendered in order; last true wins).
  std::vector<std::pair<Color, std::function<bool(std::vector<std::string>)>>> fill_colors_;
  // Conditional border color overrides (last true wins; default is id(gray)).
  std::vector<std::pair<Color, std::function<bool(std::vector<std::string>)>>> border_colors_;
  // Conditional border width overrides (last true wins; -1 means use global tile_border_width).
  std::vector<std::pair<int, std::function<bool(std::vector<std::string>)>>> border_widths_;
  // Conditional border radius overrides (last true wins; -1 means use global border_r).
  std::vector<std::pair<int, std::function<bool(std::vector<std::string>)>>> border_radii_;
  // Callback function for entity changes.
  std::function<void()> change_entities_callback_ = []() {};
  // Callback function when leaving the screen
  std::function<void()> change_screen_callback_ = []() {};
  // A dynamic variable name to check for value for this tile to be active
  const std::string* var_name_ = nullptr;
  // Simple values to check the var_name against
  std::vector<const std::string*> var_values_;
  // Indicates if the tile was active before - to preserve activation state.
  bool was_active_ = false;
  bool always_active_ = true;

private:
  inline static Tile* active_touch_tile_ = nullptr;
  inline static bool screen_touch_active_ = false;
  inline static uint32_t screen_release_gen_ = 0;

  // Initialize the Tile
  void init(esphome::display::DisplayPage* display_page,
            std::function<void()> change_screen_callback) {
    this->display_page_ = display_page;
    this->change_screen_callback_ = change_screen_callback;
    this->customInit();
    if (this->binary_sensor_ != nullptr) {
      this->binary_sensor_->add_filter(new esphome::binary_sensor::LambdaFilter(
          [this](bool x) -> optional<bool> {
            // Ignore touch events shortly after a page change or while another tile owns the touch.
            auto now = millis();
            if (x && (id(ignore_touch) || Tile::isTouchBlockedFor(this))) {
              return {};
            }
            if (!x || (now - id(turn_on_ms) < id(inactive_ms)) ||
                id(touch_calibration).state) {
              return false;
            }
            if (!this->checkActivationMaybeToggle()) {
              return false;
            }
            Tile::claimTouchTile(this);
            return true;
          }));
      // Define the touch area for the tile (including spans).
      this->updateTouchArea();
      this->binary_sensor_->add_page(this->display_page_);
      this->binary_sensor_->setup();
    }
    this->initSensors();
  }
};

// A drag-controlled cover position meter. Home Assistant uses 100 for open.
class BlindPositionTile : public Tile {
public:
  BlindPositionTile(int x, int y, std::vector<std::string> entities)
      : Tile(x, y), entities_(Pointer(entities)) {}

  void initSensors() override {
    for (const auto* entity : entities_) InitSensor(*entity);
  }

  void decodeEntities() override {
    auto decoded = HasDynamicEntity(entities_) ? ReplaceDynamicEntities(entities_) : entities_;
    if (decoded != decoded_entities_) {
      target_ = -1;
      cancel();
    }
    decoded_entities_ = decoded;
    for (const auto* entity : decoded_entities_) InitSensor(*entity);
  }

  bool updateOnEntitiesMapChange() override { return true; }

  bool requiresFastRefresh() override {
    for (const auto* item : decoded_entities_) {
      const auto state = GetTextSensorValue(GetSensor(*item));
      if (state == "opening" || state == "closing") return true;
    }
    return false;
  }

  static void updateTouch(const std::vector<esphome::touchscreen::TouchPoint>& touches) {
    if (touches.size() > 1) {
      multi_touch_ = true;
      if (active_) active_->cancel();
      return;
    }
    if (active_ && !touches.empty()) {
      if (active_->display_page_ != id(disp).get_active_page() || !active_->checkActivationMaybeToggle()) {
        active_->cancel();
      } else {
        active_->updatePosition(touches[0].y);
      }
    }
  }

  static void releaseTouch() {
    multi_touch_ = false;
    if (!active_) return;
    auto* tile = active_;
    if (tile->display_page_ != id(disp).get_active_page() || !tile->checkActivationMaybeToggle()) {
      tile->cancel();
      return;
    }
    const int position = tile->preview_;
    const auto entities = Deref(tile->decoded_entities_);
    tile->cancel();
    std::set<std::string> sent;
    for (const auto& item : entities) {
      const auto entity = GetSensor(item);
      if (entity.find("cover.") != 0) {
        ESP_LOGW("BlindPosition", "Not a cover entity: %s", entity.c_str());
      } else if (sent.insert(entity).second) {
        PerformHaAction(entity, "set_cover_position", {{"position", std::to_string(position)}});
      }
    }
    if (sent.empty()) {
      ESP_LOGW("BlindPosition", "No cover entities selected");
    } else {
      tile->target_ = position;
      id(disp).update();
    }
  }

protected:
  void customInit() override {
    binary_sensor_->add_on_state_callback([this](bool pressed) {
      if (pressed && !multi_touch_ && !active_) {
        active_ = this;
        updatePosition(id(last_y));
      }
    });
  }

  void onScreenLeave() override { cancel(); }

  void customDraw() override {
    int border = getEffectiveBorderWidth();
    if (border < 0) border = id(tile_border_width);
    const int inset = std::max(3, border + 1);
    const int left = x_start(x_) + inset;
    const int top = y_start(y_) + inset;
    const int right = x_start(x_ + x_span_ - 1) + x_rect() - inset;
    const int bottom = y_start(y_ + y_span_ - 1) + y_rect() - inset;
    const int width = std::max(0, right - left);
    const int height = std::max(0, bottom - top);
    int low = 100, high = 0;
    bool valid = !decoded_entities_.empty();
    if (active_ == this) {
      low = high = preview_;
      valid = true;
    } else {
      for (const auto* item : decoded_entities_) {
        const auto entity = GetSensor(*item);
        const auto value = GetTextSensorValue(entity + "|current_position");
        auto position = esphome::parse_number<float>(value);
        if (entity.find("cover.") != 0 || !position.has_value() ||
            !std::isfinite(*position) || *position < 0 || *position > 100) {
          valid = false;
          break;
        }
        int rounded = static_cast<int>(std::round(*position));
        low = std::min(low, rounded);
        high = std::max(high, rounded);
      }
    }
    if (active_ != this && valid && low == high && low == target_) target_ = -1;

    std::string label = "--";
    if (valid) {
      const int solid = height * (100 - high) / 100;
      const int range = height * (100 - low) / 100;
      if (solid > 0) id(disp).filled_rectangle(left, top, width, solid, id(light_blue));
      if (range > solid) id(disp).filled_rectangle(left, top + solid, width, range - solid, id(dark_gray));
      label = std::to_string(low) + "%";
    }
    const int center_x = (left + right) / 2;
    int current_top = top;
    if (active_ != this && target_ >= 0 && width > 0 && height > 0) {
      const int marker_y = top + (height - 1) * (100 - target_) / 100;
      line(left, marker_y, right - 1, marker_y, id(yellow));
      const std::string target_label = std::to_string(target_) + "%";
      const auto target_size = measure(id(text_small), target_label.c_str());
      print(center_x, top + target_size.second / 2, id(text_small), id(yellow),
            TextAlign::CENTER, target_label.c_str());
      current_top = std::min(bottom, top + target_size.second + 4);
    }
    const int center_y = (current_top + bottom) / 2;
    if (valid && low != high) {
      const std::string high_label = std::to_string(high) + "%";
      const auto low_size = measure(id(text_bold), label.c_str());
      const auto high_size = measure(id(text_bold), high_label.c_str());
      const auto dash_size = measure(id(text_bold), "-");
      const int bold_width = std::max({low_size.first, high_size.first, dash_size.first});
      const int bold_line_height = std::max({low_size.second, high_size.second, dash_size.second}) + 2;
      auto& font = bold_width <= width && 3 * bold_line_height <= bottom - current_top ? id(text_bold) : id(text_small);
      const int line_height = std::max({measure(font, label.c_str()).second,
                                        measure(font, high_label.c_str()).second,
                                        measure(font, "-").second}) + 2;
      print(center_x, center_y - line_height, font, id(white), TextAlign::CENTER, label.c_str());
      print(center_x, center_y, font, id(white), TextAlign::CENTER, "-");
      print(center_x, center_y + line_height, font, id(white), TextAlign::CENTER, high_label.c_str());
    } else {
      auto& font = measure(id(text_bold), label.c_str()).first <= width ? id(text_bold) : id(text_small);
      print(center_x, center_y, font, id(white), TextAlign::CENTER, label.c_str());
    }
  }

private:
  void updatePosition(int y) {
    const int top = y_start(y_);
    const int bottom = y_start(y_ + y_span_ - 1) + y_rect();
    if (bottom <= top) return;
    int position = std::max(0, std::min(100, (bottom - y) * 100 / (bottom - top)));
    if (position != preview_) {
      preview_ = position;
      id(disp).update();
    }
  }

  void cancel() {
    if (active_ == this) {
      active_ = nullptr;
      preview_ = -1;
      id(disp).update();
    }
  }

  std::vector<const std::string*> entities_;
  std::vector<const std::string*> decoded_entities_;
  int preview_ = -1;
  int target_ = -1;
  inline static BlindPositionTile* active_ = nullptr;
  inline static bool multi_touch_ = false;
};

// A tile that performs actions on Home Assistant entities when pressed.
class HAActionTile : public Tile {
public:
  HAActionTile* setLongPress(
      std::vector<std::function<void(std::vector<std::string>)>> actions,
      esphome::display::DisplayPage* destination, const std::string& dynamic_entity) {
    long_press_enabled_ = true;
    long_action_funcs_ = actions;
    long_destination_ = destination;
    long_dynamic_entity_ = dynamic_entity;
    return this;
  }

  HAActionTile(
      int x, int y,
      std::vector<std::function<void(int, int, int, int, std::vector<std::string>)>>
          draw_funcs,
      std::vector<std::function<void(std::vector<std::string>)>>
          action_funcs,
      std::vector<std::function<void(float, float, std::vector<std::string>)>>
          location_action_funcs,
      std::vector<std::string> entities)
      : Tile(x, y),
        draw_funcs_(draw_funcs),
        action_funcs_ (action_funcs),
        location_action_funcs_(location_action_funcs),
        entities_(Pointer(entities)) {}

  HAActionTile(
      int x, int y,
      std::vector<std::function<void(int, int, int, int, std::vector<std::string>)>>
          draw_funcs,
      std::vector<std::function<void(std::vector<std::string>)>>
          action_funcs,
      std::vector<std::string> entities)
      : HAActionTile(x, y, draw_funcs, action_funcs, {}, entities) {}

  HAActionTile(
      int x, int y,
      std::vector<std::function<void(int, int, int, int, std::vector<std::string>)>>
          draw_funcs,
      std::vector<std::function<void(float, float, std::vector<std::string>)>>
          location_action_funcs,
      std::vector<std::string> entities)
      : HAActionTile(x, y, draw_funcs, {}, location_action_funcs, entities) {}

  // Sets a function to determine if the tile requires fast refresh.
  HAActionTile* setRequiresFastRefreshFunc(std::function<bool(std::vector<std::string>)> func) {
    this->requiresFastRefreshFunc_ = func;
    return this;
  }

  bool requiresFastRefresh() override {
    if (this->requiresFastRefreshFunc_(Deref(this->decoded_entities_))) return true;
    for (const auto* entity : this->decoded_entities_) {
      const auto entity_id = GetSensor(*entity);
      if (entity_id.rfind("cover.", 0) != 0) continue;
      const auto state = GetTextSensorValue(entity_id);
      if (state == "opening" || state == "closing") return true;
    }
    return false;
  }

  void initSensors() override {
    for (const std::string* entity : this->entities_) {
      InitSensor(*entity);
    }
  };

  void decodeEntities() override {
    auto decoded = HasDynamicEntity(this->entities_)
                                  ? ReplaceDynamicEntities(this->entities_)
                                  : this->entities_;
    if (decoded != this->decoded_entities_) onScreenLeave();
    this->decoded_entities_ = decoded;
    for (const auto* entity : this->decoded_entities_) InitSensor(*entity);
  }

  bool updateOnEntitiesMapChange() override { return true; }

  // Adds a filter to change the display page if no entities are associated with
  // the tile.
  HAActionTile* setDisplayPageIfNoEntity(
      esphome::display::DisplayPage* target_display_page) {
    this->binary_sensor_->add_filter(new esphome::binary_sensor::LambdaFilter(
        [target_display_page, this](bool x) -> optional<bool> {
          if (x && (id(ignore_touch) || isTouchBlockedFor(this))) {
            return {};
          }
          if (x && this->decoded_entities_.empty()) {
            this->change_screen_callback_();
            id(disp).show_page(target_display_page);
            id(ignore_touch) = true;
            id(disp).update();
            return {};
          }
          return x;
        }));
    return this;
  }

  static constexpr uint32_t kLongPressDelayMs = 1500;
  static constexpr uint32_t kReleaseDebounceMs = 150;

protected:
  bool holdsTouchDuringReleaseGrace() const override {
    return long_press_enabled_ && pressed_ && !long_fired_;
  }

  void onScreenTouchPause() override {
    if (!long_press_enabled_ || !pressed_) return;
    if (long_fired_) {
      resetPressState();
      return;
    }
    if (millis() - press_started_ >= kLongPressDelayMs) {
      if (display_page_ == id(disp).get_active_page() && checkActivationMaybeToggle()) {
        fireLongPress();
      }
      resetPressState();
      return;
    }
    startReleaseDebounce();
  }

  void onScreenTouchResume() override {
    if (!long_press_enabled_ || !pressed_) return;
    releasing_ = false;
    ++release_generation_;
    if (!long_fired_ && millis() - press_started_ >= kLongPressDelayMs) {
      if (display_page_ == id(disp).get_active_page() && checkActivationMaybeToggle()) {
        fireLongPress();
      }
    }
  }

  void customInit() override {
    if (this->binary_sensor_ != nullptr) {
      this->binary_sensor_->add_on_state_callback([this](bool x) {
        if (!long_press_enabled_) {
          if (x) {
            claimTouchTile(this);
            runShortAction(Deref(decoded_entities_), id(last_x), id(last_y));
          }
          return;
        }
        if (x) {
          claimTouchTile(this);
          if (pressed_) {
            onScreenTouchResume();
            return;
          }
          pressed_ = true;
          releasing_ = false;
          long_fired_ = false;
          press_started_ = millis();
          press_entities_ = Deref(decoded_entities_);
          press_x_ = id(last_x);
          press_y_ = id(last_y);
          const uint32_t generation = ++press_generation_;
          ++release_generation_;
          esphome::App.scheduler.set_timeout(
              nullptr, static_cast<const char*>(nullptr), kLongPressDelayMs,
              [this, generation]() {
                if (pressed_ && !releasing_ && !long_fired_ &&
                    generation == press_generation_ &&
                    display_page_ == id(disp).get_active_page() &&
                    checkActivationMaybeToggle()) {
                  fireLongPress();
                }
              });
        } else if (pressed_) {
          if (long_fired_) {
            resetPressState();
          } else if (!isScreenTouchActive()) {
            onScreenTouchPause();
          }
        }
      });
    }
  }

  void onScreenLeave() override {
    resetPressState();
  }

  void startReleaseDebounce() {
    if (releasing_) return;
    releasing_ = true;
    release_started_ = millis();
    const uint32_t press_gen = press_generation_;
    const uint32_t rel_gen = ++release_generation_;
    esphome::App.scheduler.set_timeout(
        nullptr, static_cast<const char*>(nullptr), kReleaseDebounceMs,
        [this, press_gen, rel_gen]() {
          if (!pressed_ || !releasing_ || press_gen != press_generation_ ||
              rel_gen != release_generation_) {
            return;
          }
          finishConfirmedRelease();
        });
  }

  void finishConfirmedRelease() {
    const uint32_t held_ms = release_started_ - press_started_;
    const bool can_act = !long_fired_ &&
                         display_page_ == id(disp).get_active_page() &&
                         checkActivationMaybeToggle();
    const auto entities = press_entities_;
    const int tx = press_x_;
    const int ty = press_y_;
    resetPressState();
    if (can_act) {
      if (held_ms >= kLongPressDelayMs) {
        press_entities_ = entities;
        fireLongPress();
        resetPressState();
      } else {
        runShortAction(entities, tx, ty);
      }
    }
  }

  void resetPressState() {
    pressed_ = false;
    releasing_ = false;
    ++press_generation_;
    ++release_generation_;
    releaseTouchTile(this);
  }

  void runShortAction(const std::vector<std::string>& entities_vec, int touch_x, int touch_y) {
    ExecuteScripts(this->action_funcs_, entities_vec);
    if (this->location_action_funcs_.size() > 0) {
      int x_end_idx = this->x_ + this->x_span_ - 1;
      int y_end_idx = this->y_ + this->y_span_ - 1;
      int total_width = (x_start(x_end_idx) + x_rect()) - x_start(this->x_);
      int total_height = (y_start(y_end_idx) + y_rect()) - y_start(this->y_);
      float x_precent = 1.0 * (touch_x - x_start(this->x_)) / total_width;
      float y_precent = 1.0 * (touch_y - y_start(this->y_)) / total_height;
      ExecuteScripts(this->location_action_funcs_, x_precent, y_precent, entities_vec);
    }
  }

  void fireLongPress() {
    long_fired_ = true;
    ExecuteScripts(long_action_funcs_, press_entities_);
    if (long_destination_ && display_page_ == id(disp).get_active_page()) {
      if (!long_dynamic_entity_.empty()) {
        std::vector<std::string> entities;
        for (const auto& entity : press_entities_) entities.push_back(GetSensor(entity));
        EMSet(Pointer(long_dynamic_entity_), Pointer(entities));
        change_entities_callback_();
      }
      change_screen_callback_();
      id(disp).show_page(long_destination_);
      id(ignore_touch) = true;
      id(disp).update();
    }
  }

  void customDraw() override {
    int x_end_idx = this->x_ + this->x_span_ - 1;
    int y_end_idx = this->y_ + this->y_span_ - 1;
    ExecuteScripts(this->draw_funcs_, x_start(this->x_), x_start(x_end_idx) + x_rect(), y_start(this->y_), y_start(y_end_idx) + y_rect(), Deref(this->decoded_entities_));
  }

private:
  // Function to determine if the tile requires fast refresh (default: false).
  std::function<bool(std::vector<std::string>)> requiresFastRefreshFunc_ = [](std::vector<std::string>) { return false; };
  // Vector of functions to draw the tile.
  std::vector<std::function<void(int, int, int, int, std::vector<std::string>)>> draw_funcs_;
  // Vector of scripts to execute when the tile is pressed.
  std::vector<std::function<void(std::vector<std::string>)>> action_funcs_;
  // Vector of scripts to execute when the tile is pressed.
  std::vector<std::function<void(float, float, std::vector<std::string>)>> location_action_funcs_;
  // Vector of entities associated with the tile.
  std::vector<const std::string*> entities_;
  // Vector of decoded entities (after dynamic replacement).
  std::vector<const std::string*> decoded_entities_;
  std::vector<std::function<void(std::vector<std::string>)>> long_action_funcs_;
  esphome::display::DisplayPage* long_destination_ = nullptr;
  std::string long_dynamic_entity_;
  std::vector<std::string> press_entities_;
  uint32_t press_started_ = 0, release_started_ = 0;
  uint32_t press_generation_ = 0, release_generation_ = 0;
  int press_x_ = 0, press_y_ = 0;
  bool long_press_enabled_ = false, pressed_ = false, releasing_ = false, long_fired_ = false;
};

// A tile that navigates to a different page when pressed.
class MovePageTile : public Tile {
public:
  MovePageTile(
      int x, int y,
      std::vector<DrawImageFunc>
          draw_funcs,
      esphome::display::DisplayPage* target_display_page,
      const std::vector<std::string>& entities = {})
      : Tile(x, y), draw_funcs_(draw_funcs), target_display_page_(target_display_page),
        entities_(Pointer(entities)) {}

  // Sets dynamic entities to the tile and a callback to update the entities map.
  MovePageTile* setDynamicEntry(const std::string& key,
                                const std::vector<std::string>& val) {
    this->binary_sensor_->add_on_state_callback([this, key, val](bool x) {
      if (!x) {
        return;
      }
      EMSet(Pointer(key), Pointer(val));
      this->change_entities_callback_();
    });
    auto ptr_vec = Pointer(val);
    this->dynamic_entities_.insert(
      this->dynamic_entities_.end(), ptr_vec.begin(), ptr_vec.end());
    return this;
  }

  void initSensors() override {
    for (const std::string* entity : this->dynamic_entities_) {
      InitSensor(*entity);
    }
    for (const std::string* entity : this->entities_) {
      InitSensor(*entity);
    }
  };

  void decodeEntities() override {
    this->decoded_entities_ = HasDynamicEntity(this->entities_)
                                  ? ReplaceDynamicEntities(this->entities_)
                                  : this->entities_;
    for (const std::string* entity : this->decoded_entities_) {
      InitSensor(*entity);
    }
  }

  bool updateOnEntitiesMapChange() override { return true; }

protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([this](bool x) {
      if (!x) {
        return;
      }
      this->change_screen_callback_();
      id(disp).show_page(this->target_display_page_);
      id(ignore_touch) = true;
      id(disp).update();
    });
  }

  void customDraw() override {
    int x_end_idx = this->x_ + this->x_span_ - 1;
    int y_end_idx = this->y_ + this->y_span_ - 1;
    ExecuteScripts(this->draw_funcs_, x_start(this->x_), x_start(x_end_idx) + x_rect(), y_start(this->y_), y_start(y_end_idx) + y_rect(), Deref(this->decoded_entities_));
  }

private:
  // Vector of functions to draw the tile.
  std::vector<DrawImageFunc> draw_funcs_;
  // Pointer to the target display page to navigate to.
  esphome::display::DisplayPage* target_display_page_;
  // Vector of dynamic entities associated with the tile.
  std::vector<const std::string*> dynamic_entities_;
  std::vector<const std::string*> entities_;
  std::vector<const std::string*> decoded_entities_;
};

// A tile that executes functions when pressed and/or released.
class FunctionTile : public Tile {
public:
  FunctionTile(
      int x, int y,
      std::vector<DrawImageFunc>
          draw_funcs,
      std::function<void()> on_press,
      std::function<void()> on_release = nullptr)
      : Tile(x, y), draw_funcs_(draw_funcs), on_press_(on_press), on_release_(on_release) {}

protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([this](bool x) {
      if (x && this->on_press_) {
        this->on_press_();
      }
      if (!x && this->on_release_) {
        this->on_release_();
      }
      id(disp).update();
    });
  }

  void customDraw() override {
    int x_end_idx = this->x_ + this->x_span_ - 1;
    int y_end_idx = this->y_ + this->y_span_ - 1;
    ExecuteScripts(this->draw_funcs_, x_start(this->x_), x_start(x_end_idx) + x_rect(), y_start(this->y_), y_start(y_end_idx) + y_rect(), std::vector<std::string>{});
  }

private:
  // Vector of functions to draw the tile.
  std::vector<DrawImageFunc> draw_funcs_;
  // Pointer to the script to execute when the tile is pressed.
  std::function<void()> on_press_;
  // Pointer to the script to execute when the tile is released.
  std::function<void()> on_release_;
};

// A tile that displays a title.
class TitleTile : public HAActionTile {
public:
  TitleTile(
      int x, int y,
      std::vector<std::function<void(int, int, int, int, std::vector<std::string>)>>
          draw_funcs,
      std::vector<std::string> entities)
      : HAActionTile(x, y, draw_funcs, {}, {}, entities) {}

protected:
  void customInit() override {
    delete this->binary_sensor_;
    this->binary_sensor_ = nullptr;
    HAActionTile::customInit();
  }
};

// A tile that allows the user to choose an entity from a list.
// The draw function will receive {state ("ON"/"OFF"), presentation_name} as arguments.
class ToggleEntityTile : public Tile {
public:
  ToggleEntityTile(
      int x, int y,
      std::vector<std::function<void(int, int, int, int, std::string, bool)>>
          draw_funcs,
      const std::string& identifier, const std::vector<std::string>& entities,
      const std::string& presentation_name, bool initially_chosen = false)
      : Tile(x, y),
        draw_funcs_(draw_funcs),
        identifier_(Pointer(identifier)),
        entities_(Pointer(entities)),
        presentation_name_(presentation_name),
        initially_chosen_(initially_chosen) {}

  void initSensors() override {
    for (const std::string* entity : this->entities_) {
      InitSensor(*entity);
    }
  };

protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([this](bool x) {
      if (!x) {
        return;
      }
      if (!EMContains(this->identifier_, this->entities_)) {
        EMAdd(this->identifier_, this->entities_);
      } else {
        EMRemove(this->identifier_, this->entities_);
      }
      this->change_entities_callback_();
      id(disp).update();
    });
    if (this->initially_chosen_) {
      EMAdd(this->identifier_, this->entities_);
    }
  }

  void customDraw() override {
    bool isOn = EMContains(this->identifier_, this->entities_);
    int x_end_idx = this->x_ + this->x_span_ - 1;
    int y_end_idx = this->y_ + this->y_span_ - 1;
    ExecuteScripts(
      this->draw_funcs_, x_start(this->x_), x_start(x_end_idx) + x_rect(), y_start(this->y_), y_start(y_end_idx) + y_rect(),
      this->presentation_name_, isOn);
  }

  // Vector of functions to draw the tile.
  std::vector<std::function<void(int, int, int, int, std::string, bool)>> draw_funcs_;
  // Identifier for the group of entities this tile belongs to.
  const std::string* identifier_;
  // The entities associated with this tile.
  std::vector<const std::string*> entities_;
  // The name to display for the entity.
  std::string presentation_name_;
  // Flag to indicate if the entity is initially chosen.
  bool initially_chosen_;
};

// A tile that cycles an entity from a given list
// The draw function will receive {entity_1, entity_2, ..., entity_n, presentation_name} as arguments.
class CycleEntityTile : public Tile {
public:
  CycleEntityTile(
      int x, int y,
      std::vector<std::function<void(int, int, int, int, std::string, std::vector<std::string>)>>
          draw_funcs,
      const std::string& identifier,
      std::vector<std::pair<std::vector<std::string>, std::string>> entities_and_presntation_names,
      bool reset_on_leave = false)
      : Tile(x, y),
        draw_funcs_(draw_funcs),
        identifier_(Pointer(identifier)),
        entities_and_presntation_names_(Pointer(entities_and_presntation_names)),
        reset_on_leave_(reset_on_leave) {}

  void initSensors() override {
    for (const auto& pair : this->entities_and_presntation_names_) {
      if (pair.first.size() == 1 && *pair.first[0] == "*") {
        continue;
      }
      for (const std::string* entity : pair.first) {
        InitSensor(*entity);
      }
    }
  };

protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([this](bool x) {
      if (!x) {
        return;
      }
      this->current_index_ =
          (this->current_index_ + 1) % this->entities_and_presntation_names_.size();
      this->updateEntities();
      id(disp).update();
    });
    this->updateEntities();
  }

  void customDraw() override {
    std::vector<std::string> args;
    const auto& current_option = this->entities_and_presntation_names_.at(this->current_index_);
    if (current_option.first.size() == 1 && *current_option.first[0] == "*") {
      for (int i = 0; i < this->entities_and_presntation_names_.size(); ++i) {
        if (i == this->current_index_)
          continue;
        for (const auto* entity : this->entities_and_presntation_names_.at(i).first) {
          args.push_back(*entity);
        }
      }
    } else {
      for (const auto* entity : current_option.first) {
        args.push_back(*entity);
      }
    }
    int x_end_idx = this->x_ + this->x_span_ - 1;
    int y_end_idx = this->y_ + this->y_span_ - 1;
    ExecuteScripts(this->draw_funcs_, x_start(this->x_), x_start(x_end_idx) + x_rect(), y_start(this->y_), y_start(y_end_idx) + y_rect(), *current_option.second, args);
  }

  void onActivation() override {
    this->setCurrentIndexAccordingToEntityState();
    this->updateEntities();
  }

  void onScreenLeave() override {
    if (this->checkActivationMaybeToggle() && this->reset_on_leave_) {
      this->current_index_ = 0;
      this->updateEntities();
    }
  }

private:
  // Updates the entities according to the status of the tile.
  void updateEntities() {
    if (this->entities_and_presntation_names_.at(this->current_index_).first.size() == 1 &&
        *this->entities_and_presntation_names_.at(this->current_index_).first[0] == "*") {
      EMClear(this->identifier_);
      for (int i = 0; i < this->entities_and_presntation_names_.size(); ++i) {
        if (i == this->current_index_) {
          continue;
        }
        EMAdd(this->identifier_, this->entities_and_presntation_names_.at(i).first);
      }
    } else {
      EMSet(this->identifier_, this->entities_and_presntation_names_.at(this->current_index_).first);
    }
    this->change_entities_callback_();
  }

  void setCurrentIndexAccordingToEntityState() {
    std::vector<const std::string*> current_values;
    if (EMContains(this->identifier_)) {
      current_values = EMGetValues(this->identifier_);
    }

    for (int i = 0; i < this->entities_and_presntation_names_.size(); ++i) {
      const auto& pair = this->entities_and_presntation_names_.at(i);
      if (pair.first.size() != current_values.size()) {
        continue;
      }
      if (pair.first.empty() || EMContains(this->identifier_, pair.first)) {
        this->current_index_ = i;
        return;
      }
    }
    this->current_index_ = 0;
  }

  // Vector of functions to draw the tile.
  std::vector<std::function<void(int, int, int, int, std::string, std::vector<std::string>)>> draw_funcs_;
  // Identifier to change.
  const std::string* identifier_;
  // The entities to set into the identifier and their presentation names. If the entity is not set, or
  // it's value is not in the set, the first one will be used. The vector is rotating.
  std::vector<std::pair<std::vector<const std::string*>, const std::string*>> entities_and_presntation_names_;
  // The current indeex.
  int current_index_ = 0;
  // Indicates if should be reset on screen leave
  bool reset_on_leave_ = false;
};

#endif // TILES_H
