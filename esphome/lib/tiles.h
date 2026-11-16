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

  friend class TiledScreen;

protected:
  // Performs custom initialization specific to the tile type (pure virtual).
  virtual void customInit() = 0;

  // Performs custom drawing for the tile.
  virtual void customDraw() = 0;

  virtual void onActivation() {}

  virtual void onScreenLeave() {};

  // Pointer to the display page this tile belongs to.
  esphome::display::DisplayPage* display_page_ = nullptr;
  // Pointer to the binary sensor for touch input.
  TouchscreenBinarySensor* binary_sensor_;
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
  const std::string* var_name_;
  // Simple values to check the var_name against
  std::vector<const std::string*> var_values_;
  // Indicates if the tile was active before - to preserve activation state.
  bool was_active_ = false;
  bool always_active_ = true;

private:
  // Initialize the Tile
  void init(esphome::display::DisplayPage* display_page,
            std::function<void()> change_screen_callback) {
    this->display_page_ = display_page;
    this->change_screen_callback_ = change_screen_callback;
    this->customInit();
    if (this->binary_sensor_ != nullptr) {
      this->binary_sensor_->add_filter(new esphome::binary_sensor::LambdaFilter(
          [this](bool x) -> optional<bool> {
            // Ignore touch events shortly after a page change.
            auto now = millis();
            if (x && id(ignore_touch)) {
              return {};
            }
            if (!x || (now - id(turn_on_ms) < id(inactive_ms)) ||
                id(touch_calibration).state) {
              return false;
            }
            if (!this->checkActivationMaybeToggle()) {
              return false;
            }
            return true;
          }));
      // Define the touch area for the tile.
          this->binary_sensor_->set_area(
              x_start(this->x_), x_start(this->x_) + x_rect(),
              y_start(this->y_), y_start(this->y_) + y_rect());
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
    if (decoded != decoded_entities_) cancel();
    decoded_entities_ = decoded;
    for (const auto* entity : decoded_entities_) InitSensor(*entity);
  }

  bool updateOnEntitiesMapChange() override { return true; }

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
    if (sent.empty()) ESP_LOGW("BlindPosition", "No cover entities selected");
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
    std::string label = "--";
    bool mixed = false;
    if (valid) {
      const int solid = height * (100 - high) / 100;
      const int range = height * (100 - low) / 100;
      if (solid > 0) id(disp).filled_rectangle(left, top, width, solid, id(light_blue));
      if (range > solid) id(disp).filled_rectangle(left, top + solid, width, range - solid, id(dark_gray));
      label = low == high ? std::to_string(low) + "%" :
              std::to_string(low) + "-" + std::to_string(high) + "%";
      mixed = low != high;
    }
    auto* font = measure(id(text_bold), label.c_str()).first <= width ? id(text_bold) : id(text_small);
    if (mixed) {
      print((left + right) / 2, (top + bottom) / 2 - 10, id(text_small), id(white),
            TextAlign::CENTER, "Mixed");
    }
    print((left + right) / 2, (top + bottom) / 2 + (mixed ? 10 : 0), font, id(white),
          TextAlign::CENTER, label.c_str());
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
  inline static BlindPositionTile* active_ = nullptr;
  inline static bool multi_touch_ = false;
};

// A tile that performs actions on Home Assistant entities when pressed.
class HAActionTile : public Tile {
public:
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
    return this->requiresFastRefreshFunc_(Deref(this->decoded_entities_));
  }

  void initSensors() override {
    for (const std::string* entity : this->entities_) {
      InitSensor(*entity);
    }
  };

  void decodeEntities() override {
    this->decoded_entities_ = HasDynamicEntity(this->entities_)
                                  ? ReplaceDynamicEntities(this->entities_)
                                  : this->entities_;
  }

  bool updateOnEntitiesMapChange() override { return true; }

  // Adds a filter to change the display page if no entities are associated with
  // the tile.
  HAActionTile* setDisplayPageIfNoEntity(
      esphome::display::DisplayPage* target_display_page) {
    this->binary_sensor_->add_filter(new esphome::binary_sensor::LambdaFilter(
        [target_display_page, this](bool x) -> optional<bool> {
          if (x && this->decoded_entities_.empty()) {
            this->change_screen_callback_();
            id(disp).show_page(target_display_page);
            id(disp).update();
            return {};
          }
          return x;
        }));
    return this;
  }

protected:
  void customInit() override {
    if (this->binary_sensor_ != nullptr) {
      this->binary_sensor_->add_on_state_callback([&](bool x) {
        if (!x) {
          return;
        }
        auto entities_vec = Deref(this->decoded_entities_);
        ExecuteScripts(this->action_funcs_, entities_vec);
        if (this->location_action_funcs_.size() > 0) {
          int x_end_idx = this->x_ + this->x_span_ - 1;
          int y_end_idx = this->y_ + this->y_span_ - 1;
          int total_width = (x_start(x_end_idx) + x_rect()) - x_start(this->x_);
          int total_height = (y_start(y_end_idx) + y_rect()) - y_start(this->y_);
          
          float x_precent = 1.0 * (id(last_x) - x_start(this->x_)) / total_width;
          float y_precent = 1.0 * (id(last_y) - y_start(this->y_)) / total_height;
          ExecuteScripts(this->location_action_funcs_, x_precent, y_precent, entities_vec);
        }
      });
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
};

// A tile that navigates to a different page when pressed.
class MovePageTile : public Tile {
public:
  MovePageTile(
      int x, int y,
      std::vector<DrawImageFunc>
          draw_funcs,
      esphome::display::DisplayPage* target_display_page)
      : Tile(x, y), draw_funcs_(draw_funcs), target_display_page_(target_display_page) {}

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
  };

protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([&](bool x) {
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
    ExecuteScripts(this->draw_funcs_, x_start(this->x_), x_start(x_end_idx) + x_rect(), y_start(this->y_), y_start(y_end_idx) + y_rect(), std::vector<std::string>{});
  }

private:
  // Vector of functions to draw the tile.
  std::vector<DrawImageFunc> draw_funcs_;
  // Pointer to the target display page to navigate to.
  esphome::display::DisplayPage* target_display_page_;
  // Vector of dynamic entities associated with the tile.
  std::vector<const std::string*> dynamic_entities_;
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
    this->binary_sensor_->add_on_state_callback([&](bool x) {
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
    this->binary_sensor_->add_on_state_callback([&](bool x) {
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
    this->binary_sensor_->add_on_state_callback([&](bool x) {
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
