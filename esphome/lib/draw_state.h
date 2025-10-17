// Define the TAG for ESPHome logging
static const char *const TAG = "CACHE_MGR"; // Define logging tag

// Key type: Coordinates (x, y)
using CoordKey = std::pair<int, int>;

// Value type: A vector of bytes to store the raw data
using RawData = std::vector<uint8_t>;

// Global cache manager (replace with your actual ESPHome component class)
class DrawState {
public:
    static bool is_delete_mode;
    static std::map<CoordKey, RawData> storage;
};

inline bool DrawState::is_delete_mode = false;
inline std::map<CoordKey, RawData> DrawState::storage = {};


// ----------------------------------------------------
// Serialization Helper Functions 
// ----------------------------------------------------

// --- Helper 1: Generic (POD) Save/Load ---
template<typename T>
void serialize_value_to_buffer(RawData& buffer, const T& value) {
    size_t size = sizeof(T);
    size_t current_size = buffer.size();
    buffer.resize(current_size + size);
    std::memcpy(buffer.data() + current_size, &value, size);
}

template<typename T>
bool deserialize_value_from_buffer(const RawData& buffer, size_t& offset, T& value) {
    size_t size = sizeof(T);
    if (offset + size > buffer.size()) {
        ESP_LOGE(TAG, "D/S Error (POD): Buffer too small for size %zu. Offset: %zu, Total: %zu", 
                 size, offset, buffer.size());
        return false;
    }
    std::memcpy(&value, buffer.data() + offset, size);
    offset += size;
    return true;
}


// --- Helper 2: std::string Specialization ---

// SPECIALIZATION: Saves string length followed by character data
template<>
void serialize_value_to_buffer<std::string>(RawData& buffer, const std::string& value) {
    // 1. Save the length of the string first (using size_t)
    size_t length = value.length();
    serialize_value_to_buffer(buffer, length);

    // 2. Save the character data
    size_t current_size = buffer.size();
    buffer.resize(current_size + length);
    std::memcpy(buffer.data() + current_size, value.data(), length);
}

// SPECIALIZATION: Reads string length, then reads character data. Returns false on error.
template<>
bool deserialize_value_from_buffer<std::string>(const RawData& buffer, size_t& offset, std::string& value) {
    // 1. Read the length
    size_t length = 0;
    // Check if reading the length itself fails
    if (!deserialize_value_from_buffer(buffer, offset, length)) {
        return false;
    }

    if (offset + length > buffer.size()) {
        ESP_LOGE(TAG, "D/S Error (String): String length %zu exceeds remaining buffer size %zu.", length, buffer.size() - offset);
        return false;
    }

    // 2. Resize and copy the character data
    value.resize(length);
    std::memcpy(value.data(), buffer.data() + offset, length);
    offset += length;
    return true;
}


// ----------------------------------------------------
// Recursive Helper Functions (Using the New Helpers)
// ----------------------------------------------------

// ----------------- SAVE LOGIC (References -> Buffer) -----------------

void save_recursive(RawData& buffer) {}

template<typename HeadType, typename... TailTypes>
void save_recursive(RawData& buffer, HeadType& head_ref, TailTypes&... tail_refs) {
    serialize_value_to_buffer(buffer, head_ref);
    save_recursive(buffer, tail_refs...);
}

// ----------------- RETRIEVE LOGIC (Buffer -> References) -----------------

bool retrieve_recursive(const RawData& buffer, size_t& offset) { return true; }

template<typename HeadType, typename... TailTypes>
bool retrieve_recursive(const RawData& buffer, size_t& offset, HeadType& head_ref, TailTypes&... tail_refs) {
    if (!deserialize_value_from_buffer(buffer, offset, head_ref)) {
        return false;
    }
    return retrieve_recursive(buffer, offset, tail_refs...);
}


// ----------------------------------------------------
// The Main Interface Function (Accepts Lvalue References)
// ----------------------------------------------------

template<typename... RefTypes>
void handle_caching(int x, int y, RefTypes&... refs) {
    CoordKey key = {x, y};

    // If NOT in restore mode, we are in SAVE mode
    if (!DrawState::is_delete_mode) {
        // --- SAVE MODE ---
        RawData new_data;
        save_recursive(new_data, refs...);
        DrawState::storage[key] = std::move(new_data);
    } else {
        // --- RESTORE MODE ---
        if (DrawState::storage.count(key) == 0) {
            ESP_LOGD(TAG, "Retrieval skipped at (%d, %d): No cache found.", x, y); 
            return;
        }

        const RawData& cached_data = DrawState::storage.at(key);
        size_t offset = 0;

        // Check if retrieval was successful and error was logged inside the helpers
        if (!retrieve_recursive(cached_data, offset, refs...)) {
            // Error logged by retrieve_recursive/deserialize_value_from_buffer
            return; 
        }
            
        if (offset != cached_data.size()) {
             ESP_LOGE(TAG, "Cache load warning at (%d, %d): Deserialized size %zu does not match expected cache size %zu! Data may be corrupted.", 
                 x, y, offset, cached_data.size());
        }
    }
}

// Skips the function call (returns zero-initialized type) during SAVE mode, 
// and executes the function call during RESTORE/DRAW mode.
#define DRAW_ONLY(FUNC_CALL) \
    ((DrawState::is_delete_mode) ? (std::remove_reference_t<decltype(FUNC_CALL)>{}) : (FUNC_CALL))
