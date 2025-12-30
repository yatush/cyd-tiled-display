// Define the TAG for ESPHome logging
static const char *const TAG = "CACHE_MGR";

// Key type is now canonicalized to std::string for maximum flexibility 
// in the static map storage.
using CoordKey = std::string;

// Value type: A vector of bytes to store the raw data
using RawData = std::vector<uint8_t>;

// Global cache manager (replace with your actual ESPHome component class)
class DrawState {
public:
    // Flag is 'is_delete_mode'. 
    // WARNING: If true, the system performs RESTORE/DRAW. If false, data is SAVED.
    static bool is_delete_mode;
    static std::map<CoordKey, RawData> storage;
};

// INITIALIZATION: Defining and initializing static members inline in the header
inline bool DrawState::is_delete_mode = false;
inline std::map<CoordKey, RawData> DrawState::storage = {};


// ----------------------------------------------------
// Key Serialization Helper (KeyType -> CoordKey/std::string)
// ----------------------------------------------------

/**
 * @brief Default template for converting KeyType to CoordKey (std::string).
 * This supports any type that is implicitly convertible to std::string, 
 * or can be passed directly as a string literal.
 */
template<typename KeyType>
CoordKey key_to_string(const KeyType& key_input) {
    return CoordKey(key_input);
}

/**
 * @brief Specialization for std::pair<int, int> to convert coordinates 
 * into a single unique string key (e.g., "10,20").
 */
template<>
CoordKey key_to_string<std::pair<int, int>>(const std::pair<int, int>& key_input) {
    return std::to_string(key_input.first) + "," + std::to_string(key_input.second);
}

// ----------------------------------------------------
// Data Serialization Helper Functions 
// ----------------------------------------------------

// --- Helper 1: Generic (POD) Save/Load ---

// Append raw bytes for Plain Old Data (POD) types using memcpy
template<typename T>
void serialize_value_to_buffer(RawData& buffer, const T& value) {
    size_t size = sizeof(T);
    size_t current_size = buffer.size();
    buffer.resize(current_size + size);
    std::memcpy(buffer.data() + current_size, &value, size);
}

// Read raw bytes for POD types using memcpy. Returns false on error.
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


// --- Helper 2: std::string Specialization and std::vector of std::string ---

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

// SPECIALIZATION: Saves vector size followed by each string
template<>
void serialize_value_to_buffer<std::vector<std::string>>(RawData& buffer, const std::vector<std::string>& value) {
    size_t size = value.size();
    serialize_value_to_buffer(buffer, size);
    for (const auto& str : value) {
        serialize_value_to_buffer(buffer, str);
    }
}

// SPECIALIZATION: Reads vector size, then each string. Returns false on error.
template<>
bool deserialize_value_from_buffer<std::vector<std::string>>(const RawData& buffer, size_t& offset, std::vector<std::string>& value) {
    size_t size = 0;
    if (!deserialize_value_from_buffer(buffer, offset, size)) {
        return false;
    }
    value.resize(size);
    for (size_t i = 0; i < size; ++i) {
        if (!deserialize_value_from_buffer(buffer, offset, value[i])) {
            return false;
        }
    }
    return true;
}


// ----------------------------------------------------
// Recursive Helper Functions (Using the New Helpers)
// ----------------------------------------------------

// ----------------- SAVE LOGIC (References -> Buffer) -----------------

// Base case for saving recursion
void save_recursive(RawData& buffer) {}

// Recursive step: processes one reference (Head) and forwards the rest (Tail)
template<typename HeadType, typename... TailTypes>
void save_recursive(RawData& buffer, HeadType& head_ref, TailTypes&... tail_refs) {
    
    // Calls the correct serialize_value_to_buffer overload (POD or std::string)
    serialize_value_to_buffer(buffer, head_ref);

    // Recurse on the remaining references
    save_recursive(buffer, tail_refs...);
}

// ----------------- RETRIEVE LOGIC (Buffer -> References) -----------------

// Base case for retrieval recursion
bool retrieve_recursive(const RawData& buffer, size_t& offset) { return true; }

// Recursive step: processes one reference (Head) and forwards the rest (Tail)
template<typename HeadType, typename... TailTypes>
bool retrieve_recursive(const RawData& buffer, size_t& offset, HeadType& head_ref, TailTypes&... tail_refs) {
    
    // Calls the correct deserialize_value_from_buffer overload
    if (!deserialize_value_from_buffer(buffer, offset, head_ref)) {
        return false; // Stop recursion on failure
    }

    // Recurse on the remaining references
    return retrieve_recursive(buffer, offset, tail_refs...);
}


// ----------------------------------------------------
// The Main Interface Function (Accepts Lvalue References)
// ----------------------------------------------------

/**
 * @brief Saves or restores variable values based on a unique key.
 * * @tparam KeyType The type of the key (e.g., std::string, std::pair<int, int>).
 * @tparam RefTypes The types of the variables to cache (e.g., int, float, std::string).
 * @param key_input The unique key used to identify the data in the cache.
 * @param refs The lvalue references to the variables being cached/restored.
 */
template<typename KeyType, typename... RefTypes>
void handle_caching(const KeyType& key_input, RefTypes&... refs) {
    
    // Convert the input key to the canonical string key for map lookup
    CoordKey key = key_to_string(key_input);
    
    // If NOT in delete mode, we are in SAVE mode
    if (!DrawState::is_delete_mode) {
        // --- SAVE MODE ---
        RawData new_data;
        save_recursive(new_data, refs...); // Passing references
        DrawState::storage[key] = std::move(new_data);
    } else {
        // --- RESTORE MODE (Activated when is_delete_mode is true) ---
        if (DrawState::storage.count(key) == 0) {
            ESP_LOGW(TAG, "RESTORE skipped for key '%s': No cache found. Variables remain uninitialized/defaulted.", key.c_str()); 
            return;
        }

        const RawData& cached_data = DrawState::storage.at(key);
        size_t cache_size = cached_data.size();
        size_t offset = 0;

        // Check if retrieval was successful and error was logged inside the helpers
        if (!retrieve_recursive(cached_data, offset, refs...)) {
            ESP_LOGE(TAG, "RESTORE failed for key '%s'. Serialization error occurred. Cache Size: %zu.", key.c_str(), cache_size);
            return; 
        }
            
        // Final size check
        if (offset != cache_size) {
             // If this warning appears, it means the variable list (refs...) is NOT the same 
             // as the list used to SAVE the data. This is the root cause of 'zeroing'.
             ESP_LOGE(TAG, "Cache load warning for key '%s': Deserialized size %zu does not match expected cache size %zu! This is the likely cause of 'zeroing'.", 
                 key.c_str(), offset, cache_size);
        }
    }
}

template<typename T>
struct draw_only_type {
    static T get_default() { return T{}; }
};

template<>
struct draw_only_type<void> {
    static void get_default() {}
};

// Executes the function call only when in RESTORE/DRAW mode (is_delete_mode is true).
// This is an expression macro. It returns a zero-initialized value during SAVE mode.
#define DRAW_ONLY(FUNC_CALL) \
    ((DrawState::is_delete_mode) ? (draw_only_type<std::remove_reference_t<decltype(FUNC_CALL)>>::get_default()) : (FUNC_CALL))
