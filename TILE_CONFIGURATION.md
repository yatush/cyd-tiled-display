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
    background:            # optional — one or more background layers (see Screen Background)
      - color: dark_dark_gray
    tiles:
      - tile_type:
          x: 0
          y: 0
          # tile-specific configuration

images:               # optional — maintained automatically by the Configurator
  img_my_photo:       # unique ID you reference from tiles
    filename: my_photo.png
    type: RGB565      # RGB565 (default) or RGBA (for alpha-transparent PNGs)
    scale: 80         # 10–100 — percentage of the tile area the image fills

screen_images:        # optional — maintained automatically by the Configurator
  bg_living_room:     # unique ID you reference from 'background:' entries
    filename: living_room.jpg
    type: RGB565
```

> **Note:** The `images:` dictionary at the top level is managed automatically by the Configurator's **Images** panel in the left sidebar. You do not need to edit it by hand.

### Screen Properties

- **id**: Unique identifier for the screen (used in `destination` fields for navigation)
- **rows**: (Optional) Number of rows in the grid for this screen. Overrides the global default.
- **cols**: (Optional) Number of columns in the grid for this screen. Overrides the global default.
- **flags**: List of optional flags that control screen behavior
  - `BASE`: This is the base/home screen that loads first, also `TEMPORARY` screens fall back to this screen after timeout. There should be exactly 1 `BASE` screen.
  - `TEMPORARY`: Screen is temporary - i.e. after 60 seconds of inactivity, it will change back to the `BASE` screen
  - `FAST_REFRESH`: Screen that refresh several times per second, in contrast to others that might refesh every few seconds. This should be set in case the screen has values that change often.
- **background**: (Optional) One or more background layers drawn behind all tiles. See [Screen Background](#screen-background) below.

### Screen Layout

Screens are organized as a 2D grid. Each tile occupies one or more positions using:
- **x**: Column (0-based, horizontal position)
- **y**: Row (0-based, vertical position)
- **x_span**: (Optional, default: 1) Number of columns the tile spans
- **y_span**: (Optional, default: 1) Number of rows the tile spans

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
- **x_span, y_span**: (Optional) Tile dimensions (default: 1)
- **entities**: *(Required)* List of entities to be passed to the display script (see Entity Formats below)
- **display**: *(Required)* List of display scripts to render the tile
  - **Draw Function Arguments**: The display scripts can receive `{x_start, x_end, y_start, y_end, entities}` (coordinates are required) where:
    - `x_start`: Integer - Pixel x-coordinate of the left edge
    - `x_end`: Integer - Pixel x-coordinate of the right edge
    - `y_start`: Integer - Pixel y-coordinate of the top edge
    - `y_end`: Integer - Pixel y-coordinate of the bottom edge
    - `entities`: String array - The resolved entity values (with dynamic entities replaced at runtime)
  - **Parameterized Scripts**: You can pass static parameters to scripts by using a dictionary format:
    ```yaml
    display:
      - tile_icon:
          icon: '"\U0000e8b8"'
          color: id(gray)
          size: TileFonts::MEDIUM
    ```
- **omit_frame**: (Optional) Whether to hide the tile frame/border
- **display_assets**: (Optional) See [Display Assets](#display-assets)

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
- **x_span, y_span**: (Optional) Tile dimensions (default: 1)
- **entities**: *(Required)* List of entities to be passed to the display script
- **display**: *(Required)* List of display scripts
  - **Draw Function Arguments**: The display scripts can receive `{x_start, x_end, y_start, y_end, entities}` (coordinates are required) where:
    - `x_start`: Integer - Pixel x-coordinate of the left edge
    - `x_end`: Integer - Pixel x-coordinate of the right edge
    - `y_start`: Integer - Pixel y-coordinate of the top edge
    - `y_end`: Integer - Pixel y-coordinate of the bottom edge
    - `entities`: String array - The resolved entity values (with dynamic entities replaced at runtime)
- **perform**: *(Required if location_perform not set)* Action function(s) to call when tile is pressed
  - **Action Function Arguments**: The action scripts can receive `{entities}` where:
    - `entities`: String array - The resolved entity values
- **location_perform**: *(Required if perform not set)* Location-based action functions for multiple locations
  - **Location Action Function Arguments**: The action scripts can receive `{x_percent, y_percent, entities}` (x_percent and y_percent are required) where:
    - `x_percent`: Float - Touch position as percentage (0.0-1.0) of tile width
    - `y_percent`: Float - Touch position as percentage (0.0-1.0) of tile height
    - `entities`: String array - The resolved entity values
- **display_page_if_no_entity**: (Optional) Navigate to screen if entity is not available (requires dynamic_entity)
- **requires_fast_refresh**: (Optional) Condition (see [Conditions](#conditions) section) determining if fast refresh is needed
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border
- **display_assets**: (Optional) See [Display Assets](#display-assets)

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
- **x_span, y_span**: (Optional) Tile dimensions (default: 1)
- **display**: *(Required)* List of display scripts
  - **Draw Function Arguments**: The display scripts can receive `{x_start, x_end, y_start, y_end}` (coordinates are required) where:
    - `x_start`: Integer - Pixel x-coordinate of the left edge
    - `x_end`: Integer - Pixel x-coordinate of the right edge
    - `y_start`: Integer - Pixel y-coordinate of the top edge
    - `y_end`: Integer - Pixel y-coordinate of the bottom edge
- **destination**: *(Required)* Screen ID to navigate to (must be valid screen ID)
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **dynamic_entry**: (Optional) See [Common Modifiers](#dynamic-entry)
- **omit_frame**: (Optional) Whether to hide the tile frame/border
- **display_assets**: (Optional) See [Display Assets](#display-assets)

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
- **x_span, y_span**: (Optional) Tile dimensions (default: 1)
- **display**: *(Required)* List of display scripts
  - **Draw Function Arguments**: The display scripts can receive `{x_start, x_end, y_start, y_end}` (coordinates are required) where:
    - `x_start`: Integer - Pixel x-coordinate of the left edge
    - `x_end`: Integer - Pixel x-coordinate of the right edge
    - `y_start`: Integer - Pixel y-coordinate of the top edge
    - `y_end`: Integer - Pixel y-coordinate of the bottom edge
- **on_press**: (Optional*) Function to call when tile is pressed
  - **Function Arguments**: No parameters passed to the script
- **on_release**: (Optional*) Function to call when tile is released
  - **Function Arguments**: No parameters passed to the script
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border
- **display_assets**: (Optional) See [Display Assets](#display-assets)

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
- **x_span, y_span**: (Optional) Tile dimensions (default: 1)
- **display**: *(Required)* List of display scripts
  - **Draw Function Arguments**: The display scripts can receive `{x_start, x_end, y_start, y_end, presentation_name, state}` (coordinates are required) where:
    - `x_start`: Integer - Pixel x-coordinate of the left edge
    - `x_end`: Integer - Pixel x-coordinate of the right edge
    - `y_start`: Integer - Pixel y-coordinate of the top edge
    - `y_end`: Integer - Pixel y-coordinate of the bottom edge
    - `presentation_name`: String - The label to display for this option
    - `state`: Boolean - `true` if the tile is currently selected, `false` otherwise
- **dynamic_entity**: *(Required)* Key for the dynamic_entity whose value is set by this tile.
- **entity**: *(Required)* The entity ID that is set to the dynamic_entity by this tile. Can be a **comma-separated list** of entities (e.g., `light.kitchen, light.living_room`) to control multiple entities at once.
- **presentation_name**: (Optional) Display name for this option - sent to the display scripts
- **initially_chosen**: (Optional, default: false) Whether this is the initially selected option
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border
- **display_assets**: (Optional) See [Display Assets](#display-assets)

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
- **x_span, y_span**: (Optional) Tile dimensions (default: 1)
- **display**: *(Required)* List of display scripts
  - **Draw Function Arguments**: The display scripts can receive `{x_start, x_end, y_start, y_end, presentation_name, options}` (coordinates are required) where:
    - `x_start`: Integer - Pixel x-coordinate of the left edge
    - `x_end`: Integer - Pixel x-coordinate of the right edge
    - `y_start`: Integer - Pixel y-coordinate of the top edge
    - `y_end`: Integer - Pixel y-coordinate of the bottom edge
    - `presentation_name`: String - The label for the currently selected option
    - `options`: String array - All entity IDs from the currently selected option (one or more if comma-separated). **Note**: If the option is `"*"` (All), this list will contain **all other entities** defined in the `options` list, instead of the literal string `"*"`.
- **dynamic_entity**: *(Required)* Key for the entity whose value is being changed when pressing the tile.
- **options**: *(Required)* List of options to cycle through (at least one required)
  - Each item must have:
    - **entity**: *(Required)* The entity ID that will be set for the *dynamic_entity*. Can be a **comma-separated list** of entities.
      - **Special Value `"*"`**: If set to `"*"`, the dynamic entity will be populated with **all other entities** defined in the `options` list.
    - **label**: *(Required)* Display name for this option, passed to the display script
- **reset_on_leave**: (Optional, default: false) Reset to first option when leaving screen
- **activation_var**: (Optional) See [Common Modifiers](#activation-variable)
- **omit_frame**: (Optional) Whether to hide the tile frame/border
- **display_assets**: (Optional) See [Display Assets](#display-assets)

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

### Tile Spanning

Tiles can span multiple grid cells.

```yaml
- ha_action:
    x: 0
    y: 0
    x_span: 2
    y_span: 2
    # ... other properties ...
```

- **x_span**: (Optional, default: 1) Width of the tile in grid cells
- **y_span**: (Optional, default: 1) Height of the tile in grid cells

**Note on Overlaps**: If a spanned tile overlaps with other tiles (or if multiple tiles are placed at the same coordinates), **ALL** overlapping tiles MUST have an `activation_var` defined. This ensures the system knows which tile to display at any given time based on the active context.

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
      value: 
        - LIVING_ROOM
        - KITCHEN
```

- **activation_var**: (Optional) Set an activation variable
  - **dynamic_entity**: *(Required)* Dynamic entity name
  - **value**: *(Required)* Variable value. Can be a single string, a **comma-separated list** string, or a **YAML list** of strings. The tile will be active if the *dynamic_entity* matches **ANY** of the provided values.

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
  - **value**: *(Required)* Entity ID to set for this key. Can be a **comma-separated list** of entities.

### Fill Color

Override the tile's background fill color. When a fill color is set the tile interior is painted with the given color before the tile content is drawn. Useful for highlighting active states.

#### Unconditional fill

```yaml
- ha_action:
    x: 0
    y: 0
    # ...
    fill_color: dark_dark_gray   # any named color global
```

#### Conditional fill (evaluated in order; last matching entry wins)

```yaml
    fill_color:
      - color: red           # show red when light is on
        condition: light_on_fn
      - color: dark_dark_gray  # default
```

Colors can reference a named global (e.g. `red`, `gray`) or an inline `Color(r, g, b)` literal with RGB values 0–255.

### Border Color

Override the color of the tile's rounded border frame. The default border color is `gray`. Supports the same unconditional and conditional syntax as Fill Color.

#### Unconditional border color

```yaml
- ha_action:
    x: 0
    y: 0
    # ...
    border_color: light_blue
```

#### Conditional border color (last matching entry wins)

```yaml
    border_color:
      - color: red             # highlight border when alarm is active
        condition: alarm_on_fn
      - color: gray            # default
```

> **Note on wifi/time indicator**: The top-right tile's effective border color is automatically darkened (each channel halved) and used as the background strip behind the wifi icon and clock, so the text remains visible regardless of which color you choose.

### Display Assets

Display one or more images or icons on a tile. Images are uploaded via the Configurator's **Images** section in the left sidebar, where they receive a unique ID (e.g., `img_kitchen`). When `display_assets:` is set on a tile it **replaces** the `display:` scripts — the tile renders the image or icon instead. Tiles with animated display assets automatically get `requires_fast_refresh` enabled.

#### Static image

```yaml
- ha_action:
    x: 0
    y: 0
    entities: [light.kitchen]
    perform: [action_lights]
    display_assets:
      - image: img_kitchen
```

#### Conditional display assets

Entries are evaluated in order; the first one whose `condition` script returns `true` (or that has no condition) is rendered.

```yaml
display_assets:
  - image: img_on
    condition: light_on_fn   # show when light is on
  - image: img_off           # fallback — no condition needed
```

#### Animated image (slide transition)

Animation is defined by a **start position** (`from`) and an **end position** (`to`), each expressed as an `[x, y]` pair where both values are in the range `0.0`–`1.0`:

- `x`: `0.0` = left edge, `0.5` = center, `1.0` = right edge
- `y`: `0.0` = top edge, `0.5` = center, `1.0` = bottom edge

The image slides from `from` toward `to`. When both positions are the same, there is no directional sweep — the image is pinned at that point. To show a static image with no motion at all, simply omit the `animation` block.

```yaml
display_assets:
  - image: img_a
    animation:
      from: [0.0, 0.5]   # enter from the left edge, vertically centered
      to: [1.0, 0.5]     # sweep toward the right edge
      duration: 0.5      # seconds per animation step
```

#### Multi-step animation

Define multiple animation phases, each with its own `from`/`to` and speed. Each step uses the entry-level image (or icon) by default, but can override it with a per-step `image` field.

```yaml
display_assets:
  - image: img_a
    animation:
      steps:
        - from: [0.0, 0.5]    # step 0: img_a sweeps left→right
          to: [1.0, 0.5]
          duration: 0.5
        - from: [0.5, 0.0]    # step 1: img_b sweeps top→bottom (image override)
          to: [0.5, 1.0]
          duration: 0.3
          image: img_b         # optional per-step image override
```

**`display_assets:` field properties:**
- **image**: *(Required for image entries)* ID of an image defined in the global `images:` dictionary.
- **icon**: *(Required for icon entries)* Icon glyph string (mutually exclusive with `image`).
- **icon_color**: (Optional) Color for the icon. Default: `white`.
- **icon_size**: (Optional) Font size for the icon. Default: `big`.
- **condition**: (Optional) Condition script (see [Conditions](#conditions)) that must return `true` for this entry to be rendered.
- **animation**: (Optional) Animate a slide transition.
  - **from**: *(Optional)* Start position as `[x, y]` where `x` and `y` are each `0.0`–`1.0`. Default: `[0.5, 0.5]` (center).
  - **to**: *(Optional)* End position as `[x, y]` where `x` and `y` are each `0.0`–`1.0`. Default: `[0.5, 0.5]` (center).
  - **duration**: *(Required)* Positive number — seconds per animation step.
  - **steps**: (Optional, multi-step) List of animation steps. Each step uses the entry-level image/icon by default; override it with a per-step `image` or `icon` field.

#### Scale

The `scale` property on each entry in the global `images:` dictionary (10–100, default `100`) controls what fraction of the tile area the image occupies. A minimum 5 px padding is always preserved on each side. Scale is set per-image in the Configurator's Images sidebar, not per-tile-reference.

#### `lib/images.yaml`

This file is auto-generated by the Configurator every time you save or compile. It contains ESPHome `image:` declarations with `resize:` values computed from tile dimensions. **Do not edit it manually.**

```yaml
# Example generated content
image:
  - file: images/kitchen.png
    id: img_kitchen
    resize: 120x88
    type: RGB565
```

When the same image is used across screens with different grid layouts, the system automatically creates separate size-specific variants (e.g., `img_kitchen_r2c2`, `img_kitchen_r3c4`). This is transparent — your YAML always uses the original ID.

## Conditions

Conditions are boolean expressions used throughout the tile configuration to define when certain behaviors occur. They are implemented as ESPHome scripts (functions) that receive the tile's `entities` as a parameter.

**Important Implementation Note:**
Due to ESPHome script limitations, condition scripts **cannot return a value directly**. As a workaround, they must set the global variable `script_output` to the boolean result.

**Example Condition Script:**
```yaml
- id: is_any_cover_open
  parameters:
    entities: string[]
  then:
    - lambda: |-
        bool result = false;
        for (auto entity : entities) {
           if (id(entity).state) result = true;
        }
        // Set the global variable instead of returning
        id(script_output) = result;
```

### Condition Structure

Conditions can be specified in two forms:

#### Simple Form

A single function name.

```yaml
conditions: is_light_on_fn
```

#### Complex Form (AND/OR/NOT Logic)

Nested conditions with explicit operators. If you have more than one condition, an `operator` is required.

```yaml
operator: AND
conditions:
  - light_on_fn
  - operator: OR
    conditions:
      - ac_running_fn
      - fan_running_fn
```

This evaluates to: `light_on_fn AND (ac_running_fn OR fan_running_fn)`

### Using Conditions - Requires Fast Refresh

Some tiles need to update frequently. Use the condition structure to specify when fast refresh is needed. In case the condition evaluates to true, the whole screen will refresh a few times per second.

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
      operator: OR
      conditions:
        - blinds_moving_up_fn
        - blinds_moving_down_fn
```

Or with complex logic:

```yaml
requires_fast_refresh:
  operator: AND
  conditions:
    - light_on_fn
    - operator: OR
      conditions:
        - ac_running_fn
        - fan_running_fn
```

#### Deeply Nested Logic

You can nest conditions to create complex boolean expressions. Each level must specify an `operator` if it contains multiple conditions.

```yaml
requires_fast_refresh:
  operator: OR
  conditions:
    # Condition 1: (NOT moving_up) AND moving_down
    - operator: AND
      conditions:
        - operator: NOT
          conditions: blinds_moving_up_fn
        - blinds_moving_down_fn
    # Condition 2: Just moving_down (redundant here, but shows the structure)
    - blinds_moving_down_fn
```

This evaluates to: `((!blinds_moving_up_fn) && blinds_moving_down_fn) || blinds_moving_down_fn`

## Screen Background

Each screen can display a full-screen background layer drawn behind all tiles. Backgrounds are configured per-screen using the `background:` key and are managed in the Configurator's **Screen Background** section of the Page properties panel.

A background is a list of entries evaluated from last to first; the **first entry (from the end) whose condition is true is drawn**. Only one layer is ever drawn per frame — if a solid-color entry has no condition and sits at the top of the list, it will always be shown and the image below it will never be drawn.

### Solid color background

```yaml
- id: living_room
  background:
    - color: dark_dark_gray
  tiles: []
```

### Image background

Images for screen backgrounds are uploaded via the Configurator's **Screen Background Images** panel (separate from tile images). They are stored in `screen_images:` at the top of the YAML and referenced by their ID.

```yaml
- id: living_room
  background:
    - image: bg_living_room
  tiles: []
```

Screen background images are automatically **cover-cropped** to the exact screen dimensions at two points:
1. **Upload time** (in the browser): cropped to 480×320 px to limit the stored file size.
2. **Compile time** (in the Docker/add-on container): PIL re-crops to the exact target device resolution using scale-to-fill + center-crop.

### Conditional background layers

Layers are listed top-to-bottom; the last entry whose condition is true is drawn. Put the most-specific (conditional) layers last so they override more general layers:

```yaml
- id: living_room
  background:
    - image: bg_living_room      # base layer — always shown if nothing else matches
    - color: red
      condition: alarm_active_fn # drawn instead of the image when alarm fires
  tiles: []
```

- **color**: Named color global (e.g. `red`, `gray`) or an `Color(r, g, b)` RGB literal.
- **image**: ID from the `screen_images:` dictionary.
- **condition**: (Optional) Condition script (see [Conditions](#conditions)). If omitted the layer is always active.

### Colors

Colors can be specified anywhere in the tile or screen configuration with a named global or an inline RGB value:

| Format | Example | Description |
|---|---|---|
| Named global | `gray` | Predefined color from `lib_common.yaml` |
| Inline RGB | `Color(255, 0, 0)` | Custom red (R, G, B, each 0–255) |

Built-in named colors: `blue`, `light_blue`, `red`, `light_red`, `light_green`, `light_purple`, `gray`, `dark_gray`, `dark_dark_gray`, `yellow`, `light_yellow`.

1. **Build Time**: When you run `esphome compile` or `esphome run`:
   - ESPhome loads your configuration
   - The `tile_ui` custom component reads the configuration from inline, or from tile_file.
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
python esphome/external_components/tile_ui/tests/test_output.py esphome/monitor_tiles.yaml

# Linux/Mac
python3 esphome/external_components/tile_ui/tests/test_output.py esphome/monitor_tiles.yaml
```

This will output the full C++ code for all screens defined in your YAML file, allowing you to verify:
- Correct tile types and arguments
- Proper application of modifiers (e.g., `setDisplayPageIfNoEntity`)
- Correct lambda generation for fast refresh
- Valid C++ syntax

### 3. Running Unit Tests

The project includes a suite of unit tests to verify the logic of the tile generation, schema validation, and utility functions. These tests are located in `esphome/external_components/tile_ui/tests/`.

To run the tests, execute the following command from the project root:

```powershell
# Run all tests
cd esphome/external_components
python -m unittest discover -v tile_ui/tests

# Run a specific test file
python tile_ui/tests/test_generation.py
```