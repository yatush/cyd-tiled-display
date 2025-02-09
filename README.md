cyd-tiled-display
=================
**An ESPHome based implementation of HomeAssistant wall controller, using CYD. The controller wakes up on movement, and is fully customizable.**

# Background
This project aims to create a cheap, versatile, customizable, reliable controller for HA. It should be easy to use. I've created a couple of controllers in my house, and has been using them reliably for multiple months.

The Hardware is bought from AliExpress (I'll provide sample links, no attributions). The casing is 3D printed.

The project is based on the awesome [ESPHome](https://esphome.io/) project.

In order to customize the display, some programming knowledge is required (C++/yaml).

<p align="center">
  <img src="/images/cyd-tiled-display.png" width="400" />
  <img src="/images/cyd-vid.gif" />
  <img src="/images/cyd-move.png" width="400" /></br>  
</p>

# Hardware

## Touch screen - [CYD](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display)

<img src="/images/display.png" width="200" />

* This is a variant of the original CYD with USB-C port.
* Model: ESP32-2432S028
* [Aliexpress link](https://www.aliexpress.com/item/1005006470918908.html)
* Price: ~10 USD

## Power supply - AC-DC to DC Step-Down Power Supply Module AC85-220V to DC 5V 2A

<img src="/images/power-supply.png" width="200" />

* 110V/220V -> 5V2A converter that fits in the wall box.
* [Aliexpress link](https://www.aliexpress.com/item/1005005142108650.html)
* Price: ~6 USD

## Outlet box

<img src="/images/wall-box.png" width="200" />

* The casing is designed for 83.5mm installation distance.
* Any other outlet box with the same installation distance will fit.
* The deeper the outlet box is, the better.
* [Aliexpress link](https://www.aliexpress.com/item/1005005865130146.html)
* Price: ~2 USD

## Motion sensor - LD2410b

<img src="/images/ld2410b.png" width="200" />

* Choose a model where there are welded pins.
* [Aliexpress link](https://www.aliexpress.com/item/1005005242873516.html)
* Price: ~3 USD

## Cables

* JST 1.25mm, Single head, ~100mm, 4Pins
* Three are needed
* [Aliexpress link](https://www.aliexpress.com/item/1005007342411330.html)
* Price: ~4 USD for a pack of 10 (~1.2 USD for 3)

# On the wall wiring diagram

<img src="/images/wiring-diagram.png" />
<img src="/images/wall-0.png" />
<img src="/images/wall-1.png" />
<img src="/images/wall-2.png" />

## Notes

* Connection between the ends of the jst cables can be done in any method, as long as it's compact (it has to go in the outlet box).
* The JST connector on the ld2410b sensor is connected to 4 pins only (although there are 5 pins available)ץ

# Library

Here is a short descrtiption of the files that appear under ```/esphome/lib/``` directory.

## device_base.yaml
The yaml file that contains all the common definitions to all displays. Each display will need to define a yaml file that will "include" the device_base.yaml file. This file also points to the header files that contain parts of the implementation.

## view.h
Represents a collection of screens and manages the active screen. There is a single view to the display.

## screens.h
Definition of different types of screens in the display. A screen is what we see when we look at the display, there can be moves from one screen to another (for example, upon user input).

### ```TiledScreen```
* This is currently the only type of supported screenץ
* Constructor parameters:
  * ```esphome::display::DisplayPage*``` - A pointer to a screen that is defined in the ```device_base.yaml``` file. The screen is defined in ```device_base.yaml``` under ```display->pages```.
  * ```std::set<ScreenAtt>``` - A set of attributes:
    * *FAST_REFRESH* - Indicates if the screen requires fast refresh, this is needed in case we have animation in the screen.
    * *TEMPORARY* - Indicates if the screen is temporary - i.e. it will be replaced by another screen after a certain period of time.
    * *BASE* - This is the initial screen - only one screen should get this attribute. this is also the screen that temporary screens fall back to.
  * ```std::vector<Tile*>``` - Tiles to display on the screen.

## tiles.h
Tiles that can appear under ```TiledScreen``` are defined in this file.

### ```Tile```
* The base class for all tiles.
* Post initialization modification functions:
  * ```omitFrame``` - In case this function is called, the tile will not have the default frame.
  * ```setActivationVar``` - A function that gets two string variables, first one being the ```$DYNAMIC_ENTITIES```, and in case the value of it contains the second variable, this tile is activated. In case this is false, the tile is inactive - will not render and will not perform actions. In case this function is not called, the tile is always active. This is used to have two tiles on the same place, and activated based on an external rule.

### ```HAActionTile```
* A tile that performs an action in HomeAssistant (toggle light, toggle AC, open blinds, etc.).
* Constructor parameters:
  * ```int``` - The x coordinate of the tile, 0 based.
  * ```int``` - The y coordinate of the tile, 0 based.
  * ```std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>``` - The functions that draw the tile. These functions are defined in ```device_base.yaml```, and are executed in order. They get three parameters:
    * The x coordinate.
    * The y coordinate.
    * A vector of strings, which represent the entities that appear in the tile. See [here](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#homeassistant-entities) for more info.
  * ```std::vector<esphome::script::Script<std::vector<std::string>>*>``` - Action function that are executed once the tile is tapped. The functions are defined in ```device_base.yaml```. The functions get a vector of strings, which represent the entities that are "acted upon" once the tile is tapped. See [here](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#homeassistant-entities) for more info.
    * ```std::vector<std::string>``` The entities that are passed to the draw functions and the actions functions in this tile. See [here](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#homeassistant-entities) for more info.
* After construction, more modifications can be done using post-initialization functions:
  * ```setRequiresFastRefreshFunc``` - Gets a function defined in ```device_base.yaml``` that returns true iff the page should fast refresh. This is useful for tiles we don't want to fast refresh, unless a condition (for example, blinds are moving) is true.
  * ```setDisplayPageIfNoEntity``` - In case the entities that are passed to the constructor contain ```$DYNAMIC_ENTITIES```, and the dynamic entities is empty, this is the page that will be presented (the HAAction will not perform). This is useful if, for example, ```$DYNAMIC_ENTITIES``` represent a list of lights, and no light is chosen, the page can be the one where we choose which light to control with the tile.
* Instead of the Action function, there's another version that gets location action function - gets 3 parameters, x percentile in the tile, y percentile in the tile and the entities passed to the function. The function can also get both types of functions.

### ```MovePageTile```
* A tile that acts as navigation from one screen to the other.
* Constructor parameters:
  * ```int``` - The x coordinate of the tile, 0 based.
  * ```int``` - The y coordinate of the tile, 0 based.
  * ```std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>``` - Draw functions, see [```HAActionTile```](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#haactiontile) for more details.
  * ```esphome::display::DisplayPage*``` - The page to navigate to once tapped.
* After construction, more modifications can be done using post-initialization functions:
  * ```setDynamicEntry``` - A function that sets the value of a ```$DYNAMIC_ENTITIES``` before navigating to the target page. The function gets two parameters:
    * ```string``` - The ```$DYNAMIC_ENTITIES``` variable name to be set.
    * ```const std::vector<std::string>&``` - The ```$SIMPLE_ENTITY```s, or ```$ENTITY_WITH_ATTRIBUTE``` values to set as the ```$DYNAMIC_ENTITIES```.

### ```FunctionTile```
* A tile that performs functions that are defined in ```device_base.yaml```.
* This is useful for changing parameters of the display itself, for example, brighness.
* Constructor parameters:
  * ```int``` - The x coordinate of the tile, 0 based.
  * ```int``` - The y coordinate of the tile, 0 based.
  * ```std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>``` - Draw functions, see [```HAActionTile```](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#haactiontile) for more details.
  * ```esphome::script::Script<>*``` - A function defined in ```device_base.yaml``` to perform once the tile is pressed.
  * ```esphome::script::Script<>*``` - A function defined in ```device_base.yaml``` to perform once the tile is released.

### ```TitleTile```
* A special case of [```HAActionTile```](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#haactiontile) that does no action.
* It is used to show information on the screen, utilizing the ```setRequiresFastRefreshFunc``` and ```setDisplayPageIfNoEntity``` functions.
* The tile can be larger than a single tile, this is done in the draw functions.
* Constructor parameters:
  * ```int``` - The x coordinate of the tile, 0 based.
  * ```int``` - The y coordinate of the tile, 0 based.
  * ```std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>``` - Draw functions, see [```HAActionTile```](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#haactiontile) for more details.
  * ```std::vector<std::string>``` - Entities, see [```HAActionTile```](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#haactiontile) for more details

### ```ToggleEntityTile```
* A tile that adds/removes a ```$SIMPLE_ENTITY``` from ```$DYNAMIC_ENTITIES```. See [here](https://github.com/yatush/cyd-tiled-display/blob/main/README.md#homeassistant-entities) for more info.
* Constructor parameters:
  * ```int``` - The x coordinate of the tile, 0 based.
  * ```int``` - The y coordinate of the tile, 0 based.
  * ```std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>``` - Draw functions, This is a special case of function that gets the following:
    * The x coordinate.
    * The y coordinate.
    * A list of two strings:
      * The first is either "ON" in case the ```$SIMPLE_ENTITY``` is part of ```$DYNAMIC_ENTITIES``` or "OFF" otherwise.
      * The second represents a presentation name string to be shown on the tile.
  * ```string``` - Identifier of the ```$DYNAMIC_ENTITIES``` to set. This should be just the string representation of the ```$VAR_NAME```.
  * ```string``` - Identifier of the ```$SIMPLE_ENTITY``` to add/remove from the ```$DYNAMIC_ENTITIES```.
  * ```string``` - Presentation name to pass to the draw function.
  * ```bool``` (optional, defaults to FALSE) - Should this entity be initially chosen when the display is turned on.

### ```CycleEntityTile```
* A tile that changes a ```$DYNAMIC_ENTITIES``` to one of the given ```$SIMPLE_ENTITY```s every time it is pressed.
* Constructor parameters:
  * ```int``` - The x coordinate of the tile, 0 based.
  * ```int``` - The y coordinate of the tile, 0 based.
  * ```std::vector<esphome::script::Script<int, int, std::vector<std::string>>*>``` - Draw functions, This is a special case of function that gets the following:
    * The x coordinate.
    * The y coordinate.
    * A list of two strings:
      * The first represents the ```$SIMPLE_ENTITY``` that the tile refers to.
      * The second represents a presentation name string to be shown on the tile.
  * ```string``` - Identifier of the ```$DYNAMIC_ENTITIY``` to set. This should be just the string representation of the ```$VAR_NAME```.
  * ```std::vector<std::pair<std::string, std::string>>``` - A vector of the ```$SIMPLE_ENTITY```s to cycle by, and their presentation names.
    * A special case is when a ```SIMPLE_ENTITY``` name is equal to "*" - in that case, the ```$DYNAMIC_ENTITIES``` will be set to all of the other ```SIMPLE_ENTITY```s in the vector.


## utils.h
Common utility functions to be used in yaml files.

## HomeAssistant Entities

### Entities in configuration
In the configuration (yaml) file, when defining the UI using the C++ objects, there's a need to define which HA entities are acted upon. The following options are available:
* **$SIMPLE_ENTITY** An entity as it is defined in HomeAssistant (string).
* **DYNAMIC_ENTITIES** A placeholder (variable) that is set from a different place. This is a unique string that can represent a list of entities. The format in the configuration should be ```"#{$VAR_NAME}"```
* **$ENTITY_WITH_ATTRIBUTE** An entity and attribute, encoded as ```$SIMPLE_ENTITY|$ATTRIBUTE```, or ```$DYNAMIC_ENTITIES|$ATTRIBUTE```. The attribute is a string that is used in HA.
On execution time, when entities are passed to functions defined in ```device_base.yaml```, the ```$DYNAMIC_ENTITIES```s are resolved. This means that for any entity that is part of the ```DYNAMIC_ENTITIES``` a ```$SIMPLE_ENTITY``` or ```$SIMPLE_ENTITY|$ATTRIBUTE``` is passed.

**<ins>Example</ins>**

```new HAActionTile(0, 0, { id(tile_temp_up) }, { id(action_temp_up) }, { "#{AC}|temperature" })```

The following is initialization of a ```HAActionTile```. The entities that will be passed to the *id(tile_temp_up)* and *id(action_temp_up)* are the ones set on the variable ```AC```. For example, in case we set ```AC``` to be [climate.a, climate.b], two entities will be passed to the functions, with the "tempretaure" attribute.

# Installation steps

* **Initialize the CYD, and connect it to your ESPHome installation** - A great starting point can be found [here](https://esphome.io/guides/getting_started_hassio.html).
* **Copy library files** - Copy the files under ```/esphome/lib/``` to a newly created ```/esphome/lib/``` directory in your homeassistant.
* **Edit device files** - Once the CYD is connected to HA, edit the configuration file of the specific display. This is done through the [ESPHome interface](https://esphome.io/guides/getting_started_hassio.html#esphome-interface). Defining the actual menus is done here, please follow the given example in ```monitor.yaml``` and the documentation [above](https://github.com/yatush/cyd-tiled-display/tree/main?tab=readme-ov-file#library).
  * Make sure to update *api->encryption->key*.
* **Enable CYD to execute HA commands** - In your HA, go to *Settings -> Devices and Services -> ESPHome -> <sub>(on your device)</sub> Configure -> Enable "Allow the device to perform Home Assistant actions"*
* On ESPHome interface, go to the device, and click ```Update```
* That's it, you're all set!

# Built-in capabilities
* The implementation of movement identifier allows changing the distance at which the display will wake up.
* The code reads the brightness from the CYD light sensor and can adjust the screen brightness automatically. For this to happen, long press the brightness adjustment tile for more than 2 seconds.
* Sleep time can be manually set, this is the time without movement that the screen will go to sleep after.
* Screen calibration:
  * In case the screen is not calibrated (touch is not happening in the right place), a calibration might be needed.
  * In HomeAssistant, go to: *Settings -> Devices and Services -> ESPHome -> Your Device*
  * Toggle *Touch calibration*.
  * This enters a calibration mode. the red dot should be in the place where you tap the screen, in case this is incorrect, change the values in ```device_base.yaml``` ```touchscreen -> calibration``` to match the minimum and maximum *x_raw, y_raw* values.
  * Please note, the x/y axis are flipped, this is WAI.
