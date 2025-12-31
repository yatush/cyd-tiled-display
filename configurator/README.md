# CYD Tiled Display Configurator

This Home Assistant Add-on provides a visual configurator for the **CYD Tiled Display** project. It allows you to design your display layout, configure tiles, and generate the necessary ESPHome YAML configuration without manually editing complex files.

## Features

- **Visual Grid Editor**: Drag and drop tiles to design your display layout.
- **Tile Configuration**: Easily set up entities, icons, and actions for each tile.
- **HA Integration**: Browse your Home Assistant entities directly within the configurator.
- **File Management**: Save and load your configurations directly to/from your ESPHome directory (`/config/esphome/`).
- **YAML Generation**: Automatically generate the ESPHome YAML code for your display.

## Getting Started

1. **Install the Add-on**: Once installed, click "Open Web UI" to start the configurator.
2. **Configure Connection**: By default, it uses the local Home Assistant Supervisor API. You can also connect to a remote HA instance or use Mock Data in the settings.
3. **Design your Layout**: Add pages and tiles to match your needs.
4. **Save to HA**: Save your configuration to your ESPHome folder.
5. **Save Device**: Use the "Save Device" option in the File Management menu to generate and save the full ESPHome configuration directly to your ESPHome folder.
6. **Flash**: Open the ESPHome dashboard, find your new device, and click "Install".

## Documentation & Support

For detailed information on hardware requirements, wiring, and advanced configuration, please refer to the main project documentation on GitHub:

- [Main Project README](https://github.com/yatush/cyd-tiled-display/blob/main/README.md)
- [Hardware & Wiring Guide](https://github.com/yatush/cyd-tiled-display#hardware)
- [Tile Configuration Details](https://github.com/yatush/cyd-tiled-display/blob/main/TILE_CONFIGURATION.md)
- [Script Validation](https://github.com/yatush/cyd-tiled-display/blob/main/SCRIPT_VALIDATION.md)

## Credits

This project is based on the [ESPHome](https://esphome.io/) project and designed for the [ESP32 Cheap Yellow Display (CYD)](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display).
