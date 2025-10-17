// Represents a collection of screens and manages the active screen.
class View {
public:
  View() = default;
  
  View(std::vector<Screen*> screens) {
    for (Screen* screen : screens) {
      this->addScreen(screen);
    }
	this->init();
  }
  
  void addScreen(Screen* screen) {
	  this->repository_[screen->getDisplayPage()] = screen;
      if (screen->hasAtt(BASE) || this->base_screen_ == nullptr) {
        this->base_screen_ = screen;
      }
      screen->setChangeEntitiesCallback([this]() { this->decodeEntities(); });
  }
  
  void init() {
    // Decode entities for all screens initially.
    this->decodeEntities();
  }

  // Returns the currently active screen based on the active DisplayPage.
  Screen* getActiveScreen() {
    if (this->repository_.count(id(disp).get_active_page()) != 0) {
      return this->repository_[id(disp).get_active_page()];
    }
    ESP_LOGE("View", "Missing page in repository, returning base");
    return this->base_screen_;
  }

  // Returns the base screen of the view.
  Screen* getBaseScreen() { return this->base_screen_; }

  // Decodes entities for all screens in the view.
  void decodeEntities() {
    for (auto& pair : this->repository_) {
      pair.second->decodeEntities();
    }
  }

private:
  // Map to store screens, keyed by their DisplayPage.
  std::map<const esphome::display::DisplayPage*, Screen*> repository_ = {};
  // Pointer to the base screen of the view.
  Screen* base_screen_ = nullptr;
};

// HEAP ALLOCATION: Use unique_ptr for automatic memory management
std::unique_ptr<View> view_ptr = nullptr;

