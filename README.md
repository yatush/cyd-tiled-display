cyd-tiled-display
=================
**An ESPHome based implementation of HomeAssistant wall controller, using CYD. The controller wakes up on movement, and is fully customizable.**

# Background
This project aims to create a cheap, versatile, customizable, reliable controller for HA. It should be easy to use. I've created a couple of controllers in my house, and has been using them reliably for multiple months.

The Hardware is bought from AliExpress (I'll provide sample links, no attributions). The casing is 3D printed.

The project is based on the awesome [ESPHome](https://esphome.io/) project.

In order to customize the display, one has to change YAML configuration. To add new capabilities, some C++ knowledge is required.

<p align="center">
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/cyd-tiled-display.png" width="400" />
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/cyd-vid.gif" width="300"/>
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/cyd-move.png" width="400" />
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/2displays.png" width="300" />
  </br>  
</p>

# Hardware

## Touch screen - [CYD](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display)

### Option 1:
<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/display.png" width="200" />

* This is a variant of the original CYD with USB-C port.
* Model: ESP32-2432S028 - 2.8 inch, resistive touch screen.
* [Aliexpress link](https://www.aliexpress.com/item/1005006470918908.html)
* Price: ~10 USD

### Option 2:
<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/3248s035.jpg" width="300" />

* This is a variant of the original CYD with micro-USB port.
* Model: ESP32-3248s035C - 3.5 inch, capacitive touch screen.
* [Aliexpress link](https://www.aliexpress.com/item/1005008624700714.html)
* Price: ~20 USD

## Power supply - AC-DC to DC Step-Down Power Supply Module AC85-220V to DC 5V 2A

<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/power-supply.png" width="200" />

* 110V/220V -> 5V2A converter that fits in the wall box.
* [Aliexpress link](https://www.aliexpress.com/item/1005005142108650.html)
* Price: ~6 USD
* Another option is to have 0.6A, smaller converter, like [this](https://he.aliexpress.com/item/1005006321657147.html) - this is also cheaper, and easier to fit in the wall.

## Outlet box

<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/wall-box.png" width="200" />

* The casing is designed for 83.5mm installation distance.
* Any other outlet box with the same installation distance will fit.
* The deeper the outlet box is, the better.
* [Aliexpress link](https://www.aliexpress.com/item/1005005865130146.html)
* Price: ~2 USD

## Motion sensor - LD2410b

<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/ld2410b.png" width="200" />

* Choose a model where there are welded pins.
* [Aliexpress link](https://www.aliexpress.com/item/1005005242873516.html)
* Price: ~3 USD

## Cables

<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/JST125.png" width="200" />

* JST 1.25mm, Single head, ~100mm, 4Pins
* Three are needed
* Simple connectors [Aliexpress link](https://www.aliexpress.com/item/1005007342411330.html)
* Price: ~4 USD for a pack of 10 (~1.2 USD for 3)
* Another great option is [this](https://www.aliexpress.com/item/1005008299221682.html). Using this, connections can be made without external connectors.

# On the wall wiring diagram

<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/wiring-diagram.png" />
<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/wall-0.png" />
<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/wall-1.png" />
<img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/wall-2.png" />

## Notes

* Connection between the ends of the jst cables can be done in any method, as long as it's compact (it has to go in the outlet box).
* The JST connector on the ld2410b sensor is connected to 4 pins only (although there are 5 pins available).

# Library

Here is a short descrtiption of the files that appear under ```/esphome/lib/``` directory.

## Device base files
Model specific definitions Each display will need to define a yaml file that will "include" the device basse file. This file also points to the header files that contain parts of the implementation.
### 2432s028_base.yaml
This is the file for the 2.8 inch display.
### 3248s035_base.yaml
Same as above, for the 3.5 inch display.
## lib.yaml
The yaml file that contains all the common definitions to all displays. Each display will need to define a yaml file that will "include" the lib.yaml file.
### Important
> In the 2432s028 model, we're not using the clear screen before each frame is rendered, because it takes quite a few milliseconds. We actually overrite the last actions we had in black. This is done in a bit of a hacky way, please pay attention that any drawing function you add should have this capability. Look at other functions for reference, and pay attention that the actual color change happens in the display overriding functions in the utils file.

# Tiles Configuration

The tile UI is now configured using YAML with comprehensive validation. Instead of defining tiles in C++, you define them in the `monitor_tiles.yaml` file. The tile_ui ESPhome component automatically generates the C++ code from your YAML configuration.

## Validation

The system performs two-tier validation at build time:

1. **Schema Validation**: Ensures YAML structure, required fields, and data types are correct
2. **Runtime Validation**: Validates business logic, cross-references, and semantic correctness

All validation errors **stop compilation immediately** with detailed error messages including screen ID and tile position for easy debugging.

See [TILE_CONFIGURATION.md](https://github.com/yatush/cyd-tiled-display/blob/main/TILE_CONFIGURATION.md) for complete validation rules and [SCRIPT_VALIDATION.md](https://github.com/yatush/cyd-tiled-display/blob/main/SCRIPT_VALIDATION.md) for script type validation.

## Configuration File

Edit `monitor_tiles.yaml` to configure your screens and tiles. See [TILE_CONFIGURATION.md](https://github.com/yatush/cyd-tiled-display/blob/main/TILE_CONFIGURATION.md) for detailed documentation on all available tile types and configuration options.

### Quick Example

```yaml
screens:
  - id: main_screen
    flags: [BASE]
    tiles:
      - ha_action:
          x: 0
          y: 0
          entities:
            - entity: light.living_room
          display:
            - tile_lights
          perform:
            - action_lights
        
      - move_page:
          x: 1
          y: 0
          display:
            - tile_settings
          destination: settings_screen
```

## Tile Types

The following tile types are available in YAML configuration:

### HAActionTile
Performs actions in Home Assistant (toggle light, toggle AC, open blinds, etc.)

```yaml
- ha_action:
    x: 0
    y: 0
    entities:
      - entity: light.my_light
    display:
      - tile_lights
    perform:
      - action_lights
```

### MovePageTile
Navigation tile that moves to another screen.

```yaml
- move_page:
    x: 1
    y: 0
    display:
      - tile_settings
    destination: settings_screen
```

### FunctionTile
Performs functions defined in `lib.yaml` (e.g., brightness adjustment).

```yaml
- function:
    x: 0
    y: 1
    display:
      - tile_brightness
    on_press: on_brightness_press
    on_release: on_brightness_release
```

### TitleTile
Display-only tile that shows information.

```yaml
- title:
    x: 2
    y: 0
    entities:
      - entity: climate.ac
    display:
      - tile_ac_status
```

### ToggleEntityTile
Toggle entity on/off in a dynamic list.

```yaml
- toggle_entity:
    x: 0
    y: 0
    display:
      - tile_choose_light
    dynamic_entity: LIGHT
    entity: light.closet
    presentation_name: Closet
```

### CycleEntityTile
Cycle through predefined options.

```yaml
- cycle_entity:
    x: 1
    y: 0
    display:
      - tile_mode
    dynamic_entity: AC_MODE
    options:
      - entity: "off"
        label: "Off"
      - entity: "cool"
        label: "Cool"
      - entity: "heat"
        label: "Heat"
```

## Dynamic Entities

For advanced configurations using dynamic entity lists, see [TILE_CONFIGURATION.md](TILE_CONFIGURATION.md).

# Installation steps

* **Configurator (Still in development)** - Use the built-in visual editor to design your tiles.
  * Navigate to `configurator/` directory.
  * Run `npm install` and `npm run dev`.
  * Open the provided URL in your browser to design your screens visually.
  * The configurator provides real-time validation and C++ code generation.
* **Initialize the CYD, and connect it to your ESPHome installation** - A great starting point can be found [here](https://esphome.io/guides/getting_started_hassio.html).
* **Copy library files** - Copy the files under `esphome/lib/` to your Home Assistant's ESPHome configuration directory.
* **Configure tiles** - Edit `monitor_tiles.yaml` to define your screens and tiles. See [TILE_CONFIGURATION.md](TILE_CONFIGURATION.md) for detailed documentation.
* **Edit device files** - Once the CYD is connected to HA, edit the configuration file of the specific display through the [ESPHome interface](https://esphome.io/guides/getting_started_hassio.html#esphome-interface). Reference the example files:
  * `2432s028_monitor.yaml` - For 2.8" display (ESP32-2432S028)
  * `3248s035_monitor.yaml` - For 3.5" display (ESP32-3248s035C)
  * Make sure to update `api->encryption->key`.
* **Enable CYD to execute HA commands** - In your HA, go to *Settings -> Devices and Services -> ESPHome -> <device> -> Configure -> Enable "Allow the device to perform Home Assistant actions"*
* On ESPHome interface, go to the device, and click `Update`
* That's it, you're all set!

# Built-in capabilities
* The implementation of movement identifier allows changing the distance at which the display will wake up.
* The code reads the brightness from the CYD light sensor and can adjust the screen brightness automatically. For this to happen, long press the brightness adjustment tile for more than 2 seconds.
* Sleep time can be manually set, this is the time without movement that the screen will go to sleep after.
* Screen calibration:
  * In case the screen is not calibrated (touch is not happening in the right place), a calibration might be needed.
  * In HomeAssistant, go to: *Settings -> Devices and Services -> ESPHome -> Your Device*
  * Toggle *Touch calibration*.
  * This enters a calibration mode. the red dot should be in the place where you tap the screen, in case this is incorrect, change the values in the device base file (e.g. ```esphome/lib/2432s028__base.yaml```) under ```touchscreen -> calibration``` to match the minimum and maximum *x_raw, y_raw* values.
  * Please note, the x/y axis are flipped, this is WAI.
