class Tile {
 public:
  Tile(int x, int y,
       std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
           draw_funcs)
      : x_(x), y_(y), draw_funcs_(draw_funcs) {
    // Initialize the binary sensor for touch detection.
    this->binary_sensor_ = new TouchscreenBinarySensor();
    this->binary_sensor_->set_parent(&id(touchscreen_id));
  }

  // Draw the tile on the display.
  void draw() {
    if (this->display_page_ != id(disp).get_active_page()) {
      return;
    }
    if (!this->omit_frame_) {
      id(draw_tile_frame).execute(this->x_, this->y_);
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

  // Configures the tile to omit drawing the frame.
  Tile* omitFrame() {
    this->omit_frame_ = true;
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

  friend class TiledScreen;

 protected:
  // Performs custom initialization specific to the tile type (pure virtual).
  virtual void customInit() = 0;

  // Performs custom drawing for the tile.
  // Default implementation executes provided draw functions.
  virtual void customDraw() {
    for (auto* func : this->draw_funcs_) {
      func->execute(this->x_, this->y_, {});
    }
  }

  // Pointer to the display page this tile belongs to.
  esphome::display::DisplayPage* display_page_ = nullptr;
  // Pointer to the binary sensor for touch input.
  TouchscreenBinarySensor* binary_sensor_;
  // X-coordinate of the tile.
  int x_;
  // Y-coordinate of the tile.
  int y_;
  // Vector of functions to draw the tile.
  std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
      draw_funcs_;
  // Flag to indicate if the frame should be omitted.
  bool omit_frame_ = false;
  // Callback function for entity changes.
  std::function<void()> change_entities_callback_ = []() {};

 private:
  // Initialize the Tile
  void init(esphome::display::DisplayPage* display_page) {
    this->display_page_ = display_page;
    this->customInit();
    if (this->binary_sensor_ != nullptr) {
      this->binary_sensor_->add_filter(new esphome::binary_sensor::LambdaFilter(
          [](bool x) -> optional<bool> {
            // Ignore touch events shortly after a page change.
            auto now = millis();
            if (x && (now - id(change_page_ms)) < 500) {
              return {};
            }
            if (!x || (now - id(turn_on_ms) < id(inactive_ms)) ||
                id(touch_calibration).state) {
              return false;
            }
            return true;
          }));
      // Define the touch area for the tile.
      this->binary_sensor_->set_area(
          id(x_start)[this->x_], id(x_start)[this->x_] + id(x_rect),
          id(y_start)[this->y_], id(y_start)[this->y_] + id(y_rect));
      this->binary_sensor_->add_page(this->display_page_);
      this->binary_sensor_->setup();
    }
    this->initSensors();
  }
};

// A tile that performs actions on Home Assistant entities when pressed.
class HAActionTile : public Tile {
 public:
  HAActionTile(
      int x, int y,
      std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
          draw_funcs,
      std::vector<esphome::script::Script<std::vector<std::string>>*>
          action_funcs,
      std::vector<std::string> entities)
      : Tile(x, y, draw_funcs) {
    this->action_funcs_ = action_funcs;
    this->entities_ = entities;
  }

  // Sets a function to determine if the tile requires fast refresh.
  HAActionTile* setRequiresFastRefreshFunc(std::function<bool()> func) {
    this->requiresFastRefreshFunc_ = func;
    return this;
  }

  bool requiresFastRefresh() override {
    return this->requiresFastRefreshFunc_();
  }

  void initSensors() override {
    for (const std::string& entity : this->entities_) {
      InitSensor(entity);
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
        for (auto* script : this->action_funcs_) {
          script->execute(this->decoded_entities_);
        }
      });
    }
  }

  void customDraw() override {
    for (auto* func : this->draw_funcs_) {
      func->execute(this->x_, this->y_, this->decoded_entities_);
    }
  }

 private:
  // Function to determine if the tile requires fast refresh (default: false).
  std::function<bool()> requiresFastRefreshFunc_ = []() { return false; };
  // Vector of scripts to execute when the tile is pressed.
  std::vector<esphome::script::Script<std::vector<std::string>>*> action_funcs_;
  // Vector of entities associated with the tile.
  std::vector<std::string> entities_;
  // Vector of decoded entities (after dynamic replacement).
  std::vector<std::string> decoded_entities_;
};

// A tile that navigates to a different page when pressed.
class MovePageTile : public Tile {
 public:
  MovePageTile(
      int x, int y,
      std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
          draw_funcs,
      esphome::display::DisplayPage* target_display_page)
      : Tile(x, y, draw_funcs), target_display_page_(target_display_page) {}

  // Adds dynamic entities to the tile and a callback to update the entities map.
  MovePageTile* setDynamicEntry(const std::string& key,
                                const std::vector<std::string>& val) {
    this->binary_sensor_->add_on_state_callback([this, key, val](bool x) {
      if (!x) {
        return;
      }
      EMAdd(key, val);
      this->change_entities_callback_();
    });
    this->dynamic_entities_.insert(this->dynamic_entities_.end(), val.begin(),
                                   val.end());
    return this;
  }

  void initSensors() override {
    for (const std::string& entity : this->dynamic_entities_) {
      InitSensor(entity);
    }
  };

 protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([&](bool x) {
      if (!x) {
        return;
      }
      id(disp).show_page(this->target_display_page_);
      id(disp).update();
    });
  }

 private:
  // Pointer to the target display page to navigate to.
  esphome::display::DisplayPage* target_display_page_;
  // Vector of dynamic entities associated with the tile.
  std::vector<std::string> dynamic_entities_;
};

// A tile that executes functions when pressed and/or released.
class FunctionTile : public Tile {
 public:
  FunctionTile(
      int x, int y,
      std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
          draw_funcs,
      esphome::script::Script<>* on_press,
      esphome::script::Script<>* on_release = nullptr)
      : Tile(x, y, draw_funcs), on_press_(on_press), on_release_(on_release) {}

 protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([&](bool x) {
      if (x && this->on_press_ != nullptr) {
        this->on_press_->execute();
      }
      if (!x && this->on_release_ != nullptr) {
        this->on_release_->execute();
      }
      id(disp).update();
    });
  }

 private:
  // Pointer to the script to execute when the tile is pressed.
  esphome::script::Script<>* on_press_;
  // Pointer to the script to execute when the tile is released.
  esphome::script::Script<>* on_release_;
};

// A tile that displays a title.
class TitleTile : public HAActionTile {
 public:
  TitleTile(
      int x, int y,
      std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
          draw_funcs,
      std::vector<std::string> entities)
      : HAActionTile(x, y, draw_funcs, {}, entities) {}

 protected:
  void customInit() override {
    this->binary_sensor_ = nullptr;
    HAActionTile::customInit();
  }
};

// A tile that allows the user to choose an entity from a list.
class ChooseEntityTile : public Tile {
 public:
  ChooseEntityTile(
      int x, int y,
      std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>
          draw_funcs,
      const std::string& identifier, const std::string& entity,
      const std::string& presentation_name, bool initially_chosen = false)
      : Tile(x, y, draw_funcs),
        identifier_(identifier),
        entity_(entity),
        presentation_name_(presentation_name),
        initially_chosen_(initially_chosen) {}

  void initSensors() override { InitSensor(this->entity_); };

 protected:
  void customInit() override {
    this->binary_sensor_->add_on_state_callback([&](bool x) {
      if (!x) {
        return;
      }
      if (!EMContains(this->identifier_, this->entity_)) {
        EMAdd(this->identifier_, this->entity_);
      } else {
        EMRemove(this->identifier_, this->entity_);
      }
      this->change_entities_callback_();
      id(disp).update();
    });
    if (this->initially_chosen_) {
      EMAdd(this->identifier_, this->entity_);
    }
  }

  void customDraw() override {
    bool isOn = EMContains(this->identifier_, this->entity_);
    for (auto* func : this->draw_funcs_) {
      func->execute(this->x_, this->y_,
                    {isOn ? "ON" : "OFF", this->presentation_name_});
    }
  }

  // Identifier for the group of entities this tile belongs to.
  std::string identifier_;
  // The entity associated with this tile.
  std::string entity_;
  // The name to display for the entity.
  std::string presentation_name_;
  // Flag to indicate if the entity is initially chosen.
  bool initially_chosen_;
};
