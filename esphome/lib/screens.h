// Enum defining attributes that a Screen can have.
enum ScreenAtt {
  FAST_REFRESH,  // Indicates if the screen requires fast refresh.
  TEMPORARY,     // Indicates if the screen is temporary - i.e. it will be
                 // replaced by another screen after a certain period of time.
  BASE,          // Indicates if the screen is the base screen.
};

// Base class for screens displayed on the device.
class Screen {
public:
  Screen(esphome::display::DisplayPage* display_page,
         std::set<ScreenAtt> attributes)
      : display_page_(display_page), attributes_(attributes) {}

  // Virtual function to draw the Wi-Fi signal strength and current hour.
  virtual void drawWifiHour() {
    std::string wifi_icon = DRAW_ONLY(id(wifi_iconstring));
    esphome::ESPTime espt = DRAW_ONLY(id(esptime).now());
    handle_caching("time", wifi_icon, espt);
    
    // Print the Wi-Fi icon.
    print(id(width) - 24, 0, &id(mdi_medium), id(wifi_color), wifi_icon.c_str());
    // Print the current time.
    strftime(id(width) - 30, 3, &id(roboto_20), id(dark_gray), TextAlign::TOP_RIGHT, "%H:%M", espt);
  }

  // Returns the DisplayPage associated with this screen.
  esphome::display::DisplayPage* getDisplayPage() {
    return this->display_page_;
  }

  // Checks if the screen has the given attribute.
  virtual bool hasAtt(ScreenAtt att) {
    return this->attributes_.find(att) != this->attributes_.end();
  }

  // Pure virtual function to draw the screen content (must be implemented by
  // derived classes).
  virtual void draw() = 0;

  // Virtual function to decode entities (default: no-op).
  virtual void decodeEntities() {};

  // Virtual function to set a callback for entity changes (default: no-op).
  virtual void setChangeEntitiesCallback(
      std::function<void()> change_entities_callback) {};

  // A function that is called when the screen is changed.
  virtual void onScreenLeave() {};

private:
  // Pointer to the DisplayPage associated with this screen.
  esphome::display::DisplayPage* display_page_;
  // Set of attributes for this screen.
  std::set<ScreenAtt> attributes_;
};

// A screen composed of multiple tiles.
class TiledScreen : public Screen {
public:
  // Constructor to initialize a TiledScreen with a DisplayPage, attributes, and
  // a vector of Tile pointers.
  TiledScreen(esphome::display::DisplayPage* display_page,
              std::set<ScreenAtt> attributes, std::vector<Tile*> tiles)
      : Screen(display_page, attributes), tiles_(tiles) {
    for (Tile* tile : tiles) {
      tile->init(this->getDisplayPage(),
                [&]() { this->onScreenLeave(); });
    }
  }

  // Overrides the base class drawWifiHour to handle cases where tiles are
  // positioned below the Wi-Fi icon.
  void drawWifiHour() override {
    // Check if any tile is below the Wi-Fi icon.
    if (std::any_of(this->tiles_.begin(), this->tiles_.end(),
                    [](const Tile* tile) { return tile->isBelowWifi(); })) {
      auto x = id(x_start)[id(cols) - 1], y = id(x_start)[0], w = id(x_rect),
           h = id(y_rect), r = id(border_r), start_x = id(width) - 83,
           end_y = 30;
      for (int delta = 0; delta < id(tile_border_width); ++delta) {
        id(disp).start_clipping(x + w - r - 1, y, x + w, y + r);
        circle(x + w - r - 1, y + r, r - delta, id(dark_dark_gray));
        id(disp).end_clipping();
        line(start_x, y + delta, x + w - r - 1, y + delta, id(dark_dark_gray));
        line(x + w - 1 - delta, y + r, x + w - 1 - delta, end_y, id(dark_dark_gray));
      }
    }
    // Call the base class function to draw the Wi-Fi icon and time.
    Screen::drawWifiHour();
  }

  void draw() override {
    if (id(render_diffs)) {
      DrawState::is_delete_mode = true;
      for (Tile* tile : prev_tiles) {
        tile->draw();
      }
      prev_tiles.clear();
      this->drawWifiHour();
    }
    DrawState::is_delete_mode = false;
    for (Tile* tile : this->tiles_) {
      if (tile->checkActivationMaybeToggle()) {
        tile->draw();
        prev_tiles.push_back(tile);
      }
    }
    this->drawWifiHour();
  }

  bool hasAtt(ScreenAtt att) {
    for (Tile* tile : this->tiles_) {
      if (tile->requiresFastRefresh()) {
        return true;
      }
    }
    return Screen::hasAtt(att);
  }

  void decodeEntities() override {
    for (Tile* tile : this->tiles_) {
      tile->decodeEntities();
    }
  }

  void setChangeEntitiesCallback(
      std::function<void()> change_entities_callback) override {
    for (Tile* tile : this->tiles_) {
      tile->setChangeEntitiesCallback(change_entities_callback);
    }
  };

  void onScreenLeave() override {
    for (Tile* tile : this->tiles_) {
      tile->onScreenLeave();
    }
  }

  static std::vector<Tile*> prev_tiles;

private:
  // Vector of Tile pointers representing the tiles on this screen.
  std::vector<Tile*> tiles_;
};

inline std::vector<Tile*> TiledScreen::prev_tiles = {};
