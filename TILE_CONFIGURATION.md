# YAML Tile Configuration Guide

This document describes how to configure tiles for the CYD Tiled Display using the declarative YAML configuration system.

## Overview

Instead of hardcoding tile definitions in C++, the system now uses a pure YAML configuration file (`monitor_tiles.yaml`) that is automatically transpiled to C++ code at build time by the `tile_ui` ESPhome custom component.

### Key Benefits
- **Declarative Configuration**: Define tiles in simple, readable YAML
- **No C++ Required**: No need to edit C++ code to customize tiles
- **Type Safety**: Validation occurs at build time, catching errors early
- **Reusable**: Common modifiers can be applied to any tile type
- **Flexible Entities**: Support for dynamic entities, sensors, and multiple entities per tile

## File Location

The tile configuration is defined in:
```
esphome/monitor_tiles.yaml
```

## Basic Structure

```yaml
screens:
  - id: screen_name
    flags: [FLAG1, FLAG2]
    tiles:
      - tile_type:
          x: 0
          y: 0
          # tile-specific configuration
```

### Screen Properties

- **id**: Unique identifier for the screen (used in `destination` fields for navigation)
- **flags**: List of optional flags that control screen behavior
  - `BASE`: This is the base/home screen that loads first, also `TEMPORARY` screens fall back to this screen after timeout. There should be exactly 1 `BASE` screen.
  - `TEMPORARY`: Screen is temporary - i.e. after 60 seconds of inactivity, it will change back to the `BASE` screen
  - `FAST_REFRESH`: Screen that refresh several times per second, in contrast to others that might refesh every few seconds. This should be set in case the screen has values that change often.

### Screen Layout

Screens are organized as a 2D grid. Each tile occupies one position using:
- **x**: Column (0-based, horizontal position)
- **y**: Row (0-based, vertical position)

### Screen Navigation Validation

All non-TEMPORARY screens must have a navigation path (via `move_page` tiles) back to the BASE screen or to a TEMPORARY screen. TEMPORARY screens automatically return to the BASE screen after timeout, so they do not require explicit navigation back.

## Tile Types

### 1. Title Tile (Read-Only Display)

Displays entity values with optional sensor attributes. Read-only (cannot be interacted with).

```yaml
- title:
    x: 0
    y: 0
    entities: 
      - entity: light
        sensor: lumens
      - dynamic_entity: AC
        sensor: temp
    display:
      - tile_temperature
    omit_frame: false
```

**Properties:**
- **x, y**: *(Required)* Position on screen (non-negative integers)
- **entities**: *(Required)* List of entities to be passed to the display script (see Entity Formats below)
- **display**: *(Required)* List of display scripts to render the tile
- **omit_frame**: (Optional) Whether to hide the tile frame/border

### 2. HA Action Tile (Entity Control)

Displays entity state and performs an action (typically toggle) when pressed.

```yaml
- ha_action:
    x: 1
    y: 0
    entities:
      - dynamic_entity: LIGHT
        sensor: brightness
      - another_entity
    display:
      - tile_lights
    perform:
      - action_lights
    display_page_if_no_entity: light_settings
    requires_fast_refresh:
      conditions:
        - light_power_check
```

**Properties:**
- **x, y**: *(Required)* Position on screen (non-negative integers)
- **entities**: *(Required)* List of entities to be passed to the display script
- **display**: *(Required)* List of display scripts
- **perform**: *(Required if location_perform not set)* Action function(s) to call when tile is pressed
- **location_perform**: *(Required if perform not set)* Location-based action functions for multiple locations
- **display_page_if_no_entity**: (Optional) Navigate to screen if entity is not available (requires dynamic_entity)
- **requires_fast_refresh**: (Optional) Condition (see [Conditions](#conditions) section) determining if fast refresh is needed
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border

### 3. Move Page Tile (Navigation)

Navigates to another screen when pressed.

```yaml
- move_page:
    x: 2
    y: 0
    display:
      - tile_settings
    destination: settings_screen
    activation_var:
      dynamic_entity: ROOM
      value: LIVING_ROOM
    dynamic_entry:
      dynamic_entity: LIGHT
      value: light_entity_1
```

**Properties:**
- **x, y**: *(Required)* Position on screen (non-negative integers)
- **display**: *(Required)* List of display scripts
- **destination**: *(Required)* Screen ID to navigate to (must be valid screen ID)
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **dynamic_entry**: (Optional) See [Common Modifiers](#dynamic-entry)
- **omit_frame**: (Optional) Whether to hide the tile frame/border

### 4. Function Tile (Script Execution)

Calls a script/function when pressed.

```yaml
- function:
    x: 0
    y: 1
    display:
      - tile_brightness
      - tile_brightness_label
    on_press: on_brightness_press
    on_release: on_brightness_release
```

**Properties:**
- **x, y**: *(Required)* Position on screen (non-negative integers)
- **display**: *(Required)* List of display scripts
- **on_press**: (Optional*) Function to call when tile is pressed
- **on_release**: (Optional*) Function to call when tile is released
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border

> **Note**: At least one of `on_press` or `on_release` must be specified.

### 5. Toggle Entity Tile (Entity Selection)

Allows user to set the value of a dynamic_entity to an entity when tapping the tile. The tile automatically sets to be selected/not-selected according to the dynamic_entity value.

```yaml
- toggle_entity:
    x: 0
    y: 0
    display:
      - tile_choose_light
    dynamic_entity: LIGHT
    entity: light_entity_1
    presentation_name: Kitchen
    initially_chosen: true
```

**Properties:**
- **x, y**: *(Required)* Position on screen (non-negative integers)
- **display**: *(Required)* List of display scripts
- **dynamic_entity**: *(Required)* Key for the dynamic_entity whose value is set by this tile.
- **entity**: *(Required)* The entity ID that is set to the dynamic_entity by this tile. Can be a **comma-separated list** of entities (e.g., `light.kitchen, light.living_room`) to control multiple entities at once.
- **presentation_name**: (Optional) Display name for this option - sent to the display scripts
- **initially_chosen**: (Optional, default: false) Whether this is the initially selected option
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border

### 6. Cycle Entity Tile (Entity Cycling)

Cycles through multiple options on each press. Sets the value of the dynamic_entity to one of the static ones each time.

```yaml
- cycle_entity:
    x: 0
    y: 1
    display:
      - tile_cycle_light
    dynamic_entity: LIGHT
    options:
      - entity: "*"
        label: All
      - entity: light_entity_1
        label: Kitchen
      - entity: light_entity_2
        label: Bedroom
    reset_on_leave: true
```

**Properties:**
- **x, y**: *(Required)* Position on screen (non-negative integers)
- **display**: *(Required)* List of display scripts
- **dynamic_entity**: *(Required)* Key for the entity whose value is being changed when pressing the tile.
- **options**: *(Required)* List of options to cycle through (at least one required)
  - Each item must have:
    - **entity**: *(Required)* The entity ID that will be set for the *dynamic_entity*. Can be a **comma-separated list** of entities.
      - **Special Value `"*"`**: If set to `"*"`, the dynamic entity will be populated with **all other entities** defined in the `options` list.
    - **label**: *(Required)* Display name for this option, passed to the display script
- **reset_on_leave**: (Optional, default: false) Reset to first option when leaving screen
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border

## Entity Formats

Entities can be specified in several formats, providing flexibility in how you reference and display them.

### Simple Entity (String)

```yaml
entities:
  - light_entity
```
Displays the entity ID directly.

### Entity with Sensor

Display an entity along with one of its attributes:

```yaml
entities:
  - entity: light
    sensor: brightness
```
Generates output like: `light|brightness`

### Dynamic Entity

Reference an entity from the dynamic entity map (populated at runtime). This acts like a variable, and is a key concept in the UI.

```yaml
entities:
  - dynamic_entity: LIGHT
    sensor: brightness
```

The dynamic entity is replaced at runtime with the actual selected entity.

**Note**: A dynamic entity can store multiple entity IDs simultaneously (acting as a vector/group). This allows a single tile to control multiple devices at once. This is typically populated using the `"*"` special value in a `cycle_entity` tile, or by providing a **comma-separated list** of entities (e.g., `light.kitchen, light.living_room`).

### Mixed List

Entities can be mixed in a single tile:

```yaml
entities:
  - dynamic_entity: LIGHT
    sensor: brightness
  - entity: light_kitchen
    sensor: color_temp
  - sensor_value_only
```

## Common Modifiers

These modifiers can be applied to any tile type and control additional behavior. All common modifiers are optional.

### Omit Frame

Hide the tile's border/frame:

```yaml
- ha_action:
    x: 0
    y: 0
    # ... other properties ...
    omit_frame: true
```

- **omit_frame**: (Optional, default: false) Whether to hide the tile frame/border

### Activation Variable

Show the tile, only in case the value of the dynamic_entity is as given.

```yaml
- move_page:
    x: 2
    y: 0
    # ... other properties ...
    activation_var:
      dynamic_entity: ROOM
      value: LIVING_ROOM
```

- **activation_var**: (Optional) Set an activation variable
  - **dynamic_entity**: *(Required)* Dynamic entity name
  - **value**: *(Required)* Variable value. Can be a **comma-separated list** of values, in that case, the *dynamic_entity* should have **ALL** of them set.

Multiple tiles can use the same variable name to track context (e.g., which room is selected).

### Dynamic Entry

Populate a dynamic entity when entering a screen (used in `move_page`):

```yaml
dynamic_entry:
  dynamic_entity: LIGHT
  value: light_entity_1
```

- **dynamic_entry**: (Optional)
  - **dynamic_entity**: *(Required)* Identifier key for the dynamic entity
  - **value**: *(Required)* Entity ID to populate for this key. Can be a **comma-separated list** of entities.

## Conditions

Conditions are boolean expressions used throughout the tile configuration to define when certain behaviors occur. They are built from boolean global variables and support both simple and complex nested logic.

### Condition Structure

Conditions can be specified in two forms:

#### Simple Form (OR Logic)

A list of boolean global variables. The condition evaluates to true if ANY of the globals are true.

```yaml
conditions:
  - is_light_on
  - is_ac_running
```

#### Complex Form (AND/OR Logic)

Nested conditions with explicit operators:

```yaml
operator: AND
items:
  - conditions: [light_on]
  - operator: OR
    conditions: [ac_running, fan_running]
```

This evaluates to: `light_on AND (ac_running OR fan_running)`

### Using Conditions

Currently, conditions are used in:

- **requires_fast_refresh**: Determines if a tile needs frequent updates
  ```yaml
  requires_fast_refresh:
    conditions:
      - is_moving
      - is_updating
  ```

More uses for conditions may be added in the future.

### Requires Fast Refresh

Some tiles need to update frequently. Use the condition structure to specify when fast refresh is needed:

```yaml
- ha_action:
    x: 0
    y: 0
    entities:
      - dynamic_entity: COVER
    display:
      - tile_blinds
    perform:
      - action_blinds
    requires_fast_refresh:
      conditions:
        - blinds_moving_up
        - blinds_moving_down
```

Or with complex logic:

```yaml
requires_fast_refresh:
  operator: AND
  items:
    - conditions: [light_on]
    - operator: OR
      conditions: [ac_running, fan_running]
```

Tile refreshes fast if light is on AND (ac is running OR fan is running).

## Example Configuration

Here's a complete example showing multiple tile types:

```yaml
screens:
  - id: home
    flags: [BASE]
    tiles:
      - title:
          x: 0
          y: 0
          entities:
            - entity: temperature_sensor
              sensor: temp
          display:
            - tile_temperature
          omit_frame: true
      
      - ha_action:
          x: 1
          y: 0
          entities:
            - dynamic_entity: LIGHT
          display:
            - tile_lights
          perform:
            - toggle_light
      
      - move_page:
          x: 2
          y: 0
          display:
            - tile_settings
          destination: settings

  - id: settings
    flags: [TEMPORARY]
    tiles:
      - toggle_entity:
          x: 0
          y: 0
          display:
            - tile_choose_light
          dynamic_entity: LIGHT
          entity: kitchen_light
          presentation_name: Kitchen
          initially_chosen: true
      
      - toggle_entity:
          x: 1
          y: 0
          display:
            - tile_choose_light
          dynamic_entity: LIGHT
          entity: bedroom_light
          presentation_name: Bedroom
      
      - cycle_entity:
          x: 2
          y: 0
          display:
            - tile_cycle_light
          dynamic_entity: LIGHT
          options:
            - entity: kitchen_light
              label: Kitchen
            - entity: bedroom_light
              label: Bedroom
          reset_on_leave: true
      
      - move_page:
          x: 0
          y: 1
          display:
            - tile_back_arrow
          destination: home
```

## How It Works

1. **Build Time**: When you run `esphome compile` or `esphome run`:
   - ESPhome loads your configuration
   - The `tile_ui` custom component reads `monitor_tiles.yaml`
   - Python code validates the YAML structure
   - C++ code is generated from the YAML

2. **Generated C++**: The component generates valid C++ tile initialization code:
   ```cpp
   new HAActionTile(0, 0, { id(tile_lights) }, { id(action_lights) }, {"#{LIGHT}"}),
   (new MovePageTile(2, 0, { id(tile_settings) }, id(settings)))->setActivationVar("ROOM", "LIVING_ROOM"),
   ```

3. **Compilation**: The generated C++ code is compiled into the firmware

4. **Runtime**: The compiled tiles display and respond to user input as configured

## Testing & Debugging

If you want to verify the generated C++ code without running a full ESPHome build, you have two options:

### 1. Enable Debug Output in Build

Add `debug_output: true` to your `tile_ui` configuration in your main ESPHome YAML file (e.g., `monitor_tiles.yaml` or where `tile_ui` is included):

```yaml
tile_ui:
  tiles_file: monitor_tiles.yaml
  debug_output: true  # Prints generated C++ to console during build
```

### 2. Standalone Test Script

You can run the Python generation logic directly to see exactly what C++ code will be produced for your YAML file. This is much faster than running a full compile.

Run the following command from the project root:

```powershell
# Windows
python esphome/custom_components/tile_ui/test_output.py esphome/monitor_tiles.yaml

# Linux/Mac
python3 esphome/custom_components/tile_ui/test_output.py esphome/monitor_tiles.yaml
```

This will output the full C++ code for all screens defined in your YAML file, allowing you to verify:
- Correct tile types and arguments
- Proper application of modifiers (e.g., `setDisplayPageIfNoEntity`)
- Correct lambda generation for fast refresh
- Valid C++ syntax