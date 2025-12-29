# Script Type Validation

## Overview

The tile UI component now validates that all referenced scripts have the correct parameter signatures for their usage context. This prevents runtime errors and compilation issues caused by mismatched script types.

## Parameter Flexibility

Scripts are not required to declare all parameters provided by the context. The system will match the script's declared parameters against the available arguments.

- **Partial Signatures**: A script can declare fewer parameters than available. For example, an action script can declare `()` (no parameters) even if `entities` are available.
- **Required Parameters**: For display and location-based scripts, the `x` and `y` coordinates are **mandatory** and must be declared in the script parameters.
- **Sequential Optional Parameters**: If a script type has multiple optional parameters (e.g., `name` and `state`), you cannot declare the second one without the first. For example, you cannot declare a script with `(x, y, state)` if the full signature is `(x, y, name, state)`. You must declare `(x, y, name, state)` or just `(x, y, name)` or `(x, y)`.

## Script Types

ESPhome scripts are categorized into several types based on their parameter signatures:

### 1. Standard Display Scripts
- **Parameters**: `x: int`, `y: int` (Required), `entities: string[]` (Optional)
- **Purpose**: Render tile content on the display at specific coordinates using a list of entities
- **Used in**: `display` field of `ha_action` and `title` tiles
- **Example**:
  ```yaml
  - id: tile_lights
    parameters: { x: int, y: int, entities: string[] }
    then:
      - lambda: |-
          id(disp).print(x, y, id(roboto_20), entities[0]);
  ```

### 2. Simple Display Scripts
- **Parameters**: `x: int`, `y: int` (Required)
- **Purpose**: Render static tile content (icon/text) without entity data
- **Used in**: `display` field of `move_page` and `function` tiles
- **Example**:
  ```yaml
  - id: draw_settings_icon
    parameters: { x: int, y: int }
    then:
      - lambda: |-
          id(disp).print(x, y, id(mdi_24), "\U0000F013"); // Cog icon
  ```

### 3. Toggle Display Scripts
- **Parameters**: `x: int`, `y: int` (Required), `name: string`, `state: bool` (Optional)
- **Purpose**: Render a toggle button state
- **Used in**: `display` field of `toggle_entity` tiles
- **Example**:
  ```yaml
  - id: draw_toggle
    parameters: { x: int, y: int, name: string, state: bool }
    then:
      - lambda: |-
          id(disp).print(x, y, id(roboto_20), name.c_str());
          if (state) {
             // Draw ON state
          }
  ```

### 4. Cycle Display Scripts
- **Parameters**: `x: int`, `y: int` (Required), `name: string`, `options: string[]` (Optional)
- **Purpose**: Render a cycle button with multiple options
- **Used in**: `display` field of `cycle_entity` tiles
- **Example**:
  ```yaml
  - id: draw_cycle
    parameters: { x: int, y: int, name: string, options: string[] }
    then:
      - lambda: |-
          id(disp).print(x, y, id(roboto_20), name.c_str());
          // options contains the list of values to cycle through
  ```

### 5. Action Scripts
- **Parameters**: `entities: string[]` (Optional) or no parameters
- **Purpose**: Execute actions when tiles are tapped (without location info)
- **Used in**: 
  - `perform` field of `ha_action` tiles
  - `on_press` / `on_release` fields of `function` tiles
- **Example**:
  ```yaml
  - id: action_lights
    parameters: { entities: string[] }
    then:
      - homeassistant.service:
          service: light.toggle
          data:
            entity_id: "{{ entities[0] }}"
  ```

### 6. Location Action Scripts
- **Parameters**: `x: float`, `y: float` (Required), `entities: string[]` (Optional)
- **Purpose**: Execute actions with tap location information (e.g., for sliding/dragging)
- **Used in**: `location_perform` field of `ha_action` tiles
- **Example**:
  ```yaml
  - id: action_blinds_up_down
    parameters: { x: float, y: float, entities: string[] }
    then:
      - lambda: |-
          float position = x / 100.0;  // Convert to 0-1 range
          id(blinds_entity).make_call().set_position(position).perform();
  ```

### No-Parameter Scripts
- **Parameters**: Empty or no `parameters` field
- **Usage**: Can be used as action scripts (most flexible)
- **Example**:
  ```yaml
  - id: simple_action
    then:
      - logger.log: "Action executed"
  ```

## Validation Rules

When the tiles configuration is processed, the component validates:

1. **Script Existence**: All referenced scripts must be defined in the ESPhome configuration
2. **Parameter Matching**: Each script usage matches its parameter signature:
   - Standard Display scripts must have `(int, int, string[])`
   - Simple Display scripts must have `(int, int)`
   - Toggle Display scripts must have `(int, int, string, bool)`
   - Cycle Display scripts must have `(int, int, string, string[])`
   - Action scripts must have `(string[])` or no parameters
   - Location action scripts must have `(float, float, string[])`
3. **Context Correctness**: 
   - Display field → correct display script type for the tile
   - Perform field → action scripts only
   - Location perform field → location action scripts only
   - On press/release → action scripts only

## Return Values

For scripts used as **Conditions** (e.g., in `requires_fast_refresh`), the script **cannot return a value directly** due to ESPHome limitations. As a workaround, it must set the `script_output` global variable to the boolean result.

Example:
```yaml
- id: my_condition_script
  parameters: { entities: string[] }
  then:
    - lambda: |-
        id(script_output) = true; // Set result
```