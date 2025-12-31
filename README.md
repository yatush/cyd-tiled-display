cyd-tiled-display
=================
**An ESPHome based implementation of HomeAssistant wall controller, using CYD. The controller wakes up on movement, and is fully customizable.**

# Background
This project aims to create a cheap, versatile, customizable, reliable controller for HA. It should be easy to use. I've created a couple of controllers in my house, and has been using them reliably for multiple months.

The Hardware is bought from AliExpress (I'll provide sample links, no attributions). The casing is 3D printed.

The project is based on the awesome [ESPHome](https://esphome.io/) project.

<p align="center">
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/cyd-tiled-display.png" width="400" />
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/cyd-vid.gif" width="300"/>
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/cyd-move.png" width="400" />
  <img src="https://github.com/yatush/cyd-tiled-display/raw/main/images/2displays.png" width="300" />
  </br>  
</p>

# How it Works

The project transforms a visual design into a working device through three stages:

1.  **Visual Design (The Configurator)**:
    You use the web-based Configurator to design your screen layout. You can create multiple pages, drag-and-drop tiles, and link them to Home Assistant entities (lights, switches, sensors, etc.).
    
2.  **YAML Configuration**:
    The Configurator saves your design as a structured YAML file (e.g., `tiles.yaml`). It then "Generates" the specific ESPHome YAML code required to render this design. This includes all the scripts, global variables, and display logic.

3.  **C++ Implementation**:
    Under the hood, the ESPHome YAML utilizes a custom C++ component (`tile_ui`) included in this repository. This C++ code handles the actual drawing on the screen, touch events, and page navigation, ensuring high performance on the ESP32.

# Installation

## Option 1: Home Assistant Add-on (Recommended)

This is the easiest way to get started. The Add-on runs the Configurator directly within Home Assistant and has access to your ESPHome configuration folder.

1.  **Add Repository**: Add this GitHub repository URL to your Home Assistant Add-on Store repositories.
2.  **Install**: Find "CYD Tiled Display Configurator" in the store and click Install.
3.  **Start**: Start the Add-on and click "Open Web UI".
4.  **Usage**: The Configurator will automatically detect your `/config/esphome` directory. You can save your designs and library files directly there.

## Option 2: Local Development

If you want to run the Configurator on your local machine (e.g., for development or if you don't use HA OS):

### Prerequisites
*   Python 3.x
*   Node.js & npm

### Steps
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yatush/cyd-tiled-display.git
    cd cyd-tiled-display
    ```

2.  **Start the Backend Server**:
    This Python server handles file operations and the ESPHome generation logic.
    ```bash
    # Install dependencies
    pip install flask pyyaml requests

    # Run the server
    python server.py
    ```
    The server will start on `http://localhost:8099`.

3.  **Start the Frontend**:
    Open a new terminal window.
    ```bash
    cd configurator
    
    # Install dependencies
    npm install

    # Run the development server
    npm run dev
    ```
    The UI will open at `http://localhost:5173`.

# Using the Configurator

 <img align="center" src="https://github.com/yatush/cyd-tiled-display/raw/main/images/configurator.jpg" width="500" />

The Configurator is designed to be intuitive:

1.  **Grid Editor**:
    *   The main view shows your screen grid (e.g., 4x3).
    *   **Drag and Drop** tiles from the sidebar onto the grid.
    *   **Resize** tiles by dragging their corners.


2.  **Tile Configuration**:
    *   Click on any tile in the grid to open the **Properties Sidebar**.
    *   **Entity**: Select the Home Assistant entity to control or monitor.
    *   **Label**: Set a custom label (or leave blank to use the entity's friendly name).
    *   **Icon**: Choose an icon from the Material Design Icons library.
    *   **Color**: Customize the tile color based on state.

3.  **File Management**:
    *   **Manage Screens File**: Save your current layout design (grid, tiles, etc.) to a YAML file on the server (e.g., `monitor_config/my_layout.yaml`). This allows you to reload your work later.

4.  **Generating the ESPHome device configuration**:
    *   **Option A (Recommended): Save Device**:
        1.  Open **File Management** and click **Save Device**.
        2.  Enter a device name (e.g., `monitor`) and a filename (e.g., `monitor.yaml`).
        3.  This will create a full ESPHome configuration file in your `/config/esphome/` directory.
        4.  Open the ESPHome dashboard, find the new device, and click **Install**.
    *   **Option B: Manual Generation**:
        1.  Click the **Generate** button to preview the YAML code.
        2.  Copy the code and paste it into your existing ESPHome configuration.

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

# Library Structure

The project relies on a set of library files that should be placed in your `/esphome/lib/` directory. The Configurator can help manage these files.

*   **`lib.yaml`**: Contains the core script definitions and global variables.
*   **`lib_custom.yaml`**: (Optional) For your own custom scripts and overrides.
*   **`*_base.yaml`**: Device-specific base configurations (e.g., `2432s028_base.yaml`).
*   **`mdi_glyphs.yaml`**: Definitions for Material Design Icons.
*   **`custom_components/tile_ui`**: The C++ component source code.
