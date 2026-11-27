import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import esp32_ble_tracker, text_sensor
from esphome.const import (
    CONF_ID,
    CONF_MAC_ADDRESS,
    CONF_NAME,
    ENTITY_CATEGORY_DIAGNOSTIC,
)

DEPENDENCIES = ["esp32_ble_tracker"]
AUTO_LOAD = ["text_sensor"]

CONF_NETWORK_KEY = "network_key"
CONF_SHELLYS = "shellys"
CONF_CHANNEL = "channel"
CONF_KIND = "kind"
CONF_ENTITY_ID = "entity_id"
CONF_DETACHED_SWITCHES = "detached_switches"
CONF_INPUT_CHANNEL = "input_channel"
CONF_TARGET_FAN_DEVICE_ID = "target_fan_device_id"
CONF_TARGET_LIGHT_ENTITY_ID = "target_light_entity_id"
CONF_VISIBLE_SHELLYS_SENSOR = "visible_shellys_sensor"
CONF_KNOWN_NAMES = "known_names"

shelly_ns = cg.esphome_ns.namespace("shelly_ble_bridge")
ShellyBleBridge = shelly_ns.class_(
    "ShellyBleBridge", cg.Component, esp32_ble_tracker.ESPBTClient
)
ShellyBleKind = shelly_ns.enum("ShellyBleKind", is_class=True)

SHELLY_KINDS = {
    "switch": ShellyBleKind.SWITCH,
    "light": ShellyBleKind.SWITCH,
    "cover": ShellyBleKind.COVER,
}

SHELLY_ITEM_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_NAME): cv.string,
        cv.Required(CONF_MAC_ADDRESS): cv.string,
        cv.Optional(CONF_CHANNEL, default=0): cv.int_range(min=0, max=3),
        cv.Optional(CONF_KIND, default="switch"): cv.enum(SHELLY_KINDS, lower=True),
        cv.Optional(CONF_ENTITY_ID, default=""): cv.string,
    }
)

DETACHED_SWITCH_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_NAME): cv.string,
        cv.Required(CONF_MAC_ADDRESS): cv.string,
        cv.Optional(CONF_INPUT_CHANNEL, default=0): cv.int_range(min=0, max=3),
        cv.Optional(CONF_TARGET_FAN_DEVICE_ID, default=""): cv.string,
        cv.Optional(CONF_TARGET_LIGHT_ENTITY_ID, default=""): cv.string,
    }
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(ShellyBleBridge),
        cv.GenerateID(esp32_ble_tracker.CONF_ESP32_BLE_ID): cv.use_id(
            esp32_ble_tracker.ESP32BLETracker
        ),
        cv.Optional(CONF_NETWORK_KEY, default="cyd_espnow_default"): cv.string,
        cv.Optional(CONF_SHELLYS, default=[]): cv.ensure_list(SHELLY_ITEM_SCHEMA),
        cv.Optional(CONF_DETACHED_SWITCHES, default=[]): cv.ensure_list(
            DETACHED_SWITCH_SCHEMA
        ),
        cv.Optional(CONF_KNOWN_NAMES, default={}): cv.Schema({cv.string: cv.string}),
        cv.Optional(CONF_VISIBLE_SHELLYS_SENSOR): text_sensor.text_sensor_schema(
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            icon="mdi:bluetooth-connect",
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    cg.add_define("USE_SHELLY_BLE_BRIDGE")

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await esp32_ble_tracker.register_client(var, config)

    tracker = await cg.get_variable(config[esp32_ble_tracker.CONF_ESP32_BLE_ID])
    cg.add(var.set_parent(tracker))
    cg.add(var.set_network_key(config[CONF_NETWORK_KEY]))

    if CONF_VISIBLE_SHELLYS_SENSOR in config:
        sens = await text_sensor.new_text_sensor(config[CONF_VISIBLE_SHELLYS_SENSOR])
        cg.add(var.set_visible_shellys_sensor(sens))

    for mac, label in config.get(CONF_KNOWN_NAMES, {}).items():
        cg.add(var.add_known_name(mac, label))

    for item in config.get(CONF_SHELLYS, []):
        cg.add(
            var.add_shelly(
                item[CONF_NAME],
                item[CONF_MAC_ADDRESS],
                item[CONF_CHANNEL],
                SHELLY_KINDS[item[CONF_KIND]],
                item.get(CONF_ENTITY_ID, ""),
            )
        )

    for binding in config.get(CONF_DETACHED_SWITCHES, []):
        cg.add(
            var.add_detached_switch(
                binding[CONF_NAME],
                binding[CONF_MAC_ADDRESS],
                binding[CONF_INPUT_CHANNEL],
                binding.get(CONF_TARGET_FAN_DEVICE_ID, ""),
                binding.get(CONF_TARGET_LIGHT_ENTITY_ID, ""),
            )
        )
