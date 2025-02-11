// Represents a collection of screens and manages the active screen.
class View {
public:
  View(std::vector<Screen*> screens) {
    for (Screen* screen : screens) {
      this->repository_[screen->getDisplayPage()] = screen;
      if (screen->hasAtt(BASE)) {
        this->base_screen_ = screen;
      }
      screen->setChangeEntitiesCallback([this]() { this->decodeEntities(); });
    }
    // If no base screen was found (shouldn't happen), use the first screen.
    if (this->base_screen_ == nullptr) {  // This should never happen
      this->base_screen_ = screens.at(0);
    }
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

// Global pointer to the View object.
// The view of the display
View* view = nullptr;
