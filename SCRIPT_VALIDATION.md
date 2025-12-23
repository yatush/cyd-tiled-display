# Script Type Validation

## Overview

The tile UI component now validates that all referenced scripts have the correct parameter signatures for their usage context. This prevents runtime errors and compilation issues caused by mismatched script types.

## Script Types

ESPhome scripts are categorized into several types based on their parameter signatures:

### 1. Standard Display Scripts
- **Parameters**: `x: int`, `y: int`, `entities: string[]`
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
- **Parameters**: `x: int`, `y: int`
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
- **Parameters**: `x: int`, `y: int`, `name: string`, `state: bool`
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
- **Parameters**: `x: int`, `y: int`, `name: string`, `options: string[]`
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
- **Parameters**: `entities: string[]` or no parameters
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
- **Parameters**: `x: float`, `y: float`, `entities: string[]`
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