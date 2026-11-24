import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import esp32_ble_tracker, fan, light, number
from esphome.const import (
    CONF_ID,
    CONF_MAC_ADDRESS,
    CONF_NAME,
    CONF_OUTPUT_ID,
)

DEPENDENCIES = ["esp32_ble_tracker"]
AUTO_LOAD = ["fan", "light", "number"]

CONF_FANS = "fans"
CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_PRODUCT_ID = "product_id"
CONF_UUID = "uuid"
CONF_FAN_ENTITY_ID = "fan_entity_id"
CONF_LIGHT_ENTITY_ID = "light_entity_id"
CONF_EXPOSE_TO_HA = "expose_to_ha"
CONF_IDLE_DISCONNECT_S = "idle_disconnect_s"
CONF_FAN_COMPONENT_ID = "fan_component_id"
CONF_LIGHT_COMPONENT_ID = "light_component_id"
CONF_LIGHT_OUTPUT_ID = "light_output_id"
CONF_TIMER_COMPONENT_ID = "timer_component_id"

tuya_ble_fan_ns = cg.esphome_ns.namespace("tuya_ble_fan")
TuyaBleFanHub = tuya_ble_fan_ns.class_(
    "TuyaBleFanHub", cg.Component, esp32_ble_tracker.ESPBTClient
)
TuyaBleFanDevice = tuya_ble_fan_ns.class_("TuyaBleFanDevice")
TuyaBleFanEntity = tuya_ble_fan_ns.class_("TuyaBleFanEntity", fan.Fan)
TuyaBleLightOutput = tuya_ble_fan_ns.class_("TuyaBleLightOutput", light.LightOutput)
TuyaBleTimerNumber = tuya_ble_fan_ns.class_("TuyaBleTimerNumber", number.Number)


def _validate_optional_mac(value):
    if value is None or value == "":
        return ""
    return str(cv.mac_address(value))


FAN_ITEM_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TuyaBleFanDevice),
        cv.Required(CONF_NAME): cv.string,
        cv.Required(CONF_DEVICE_ID): cv.string,
        cv.Required(CONF_LOCAL_KEY): cv.string,
        cv.Optional(CONF_PRODUCT_ID, default=""): cv.string,
        cv.Optional(CONF_UUID, default=""): cv.string,
        cv.Optional(CONF_MAC_ADDRESS, default=""): _validate_optional_mac,
        cv.Required(CONF_FAN_ENTITY_ID): cv.string,
        cv.Optional(CONF_LIGHT_ENTITY_ID, default=""): cv.string,
        cv.Optional(CONF_EXPOSE_TO_HA, default=True): cv.boolean,
        cv.GenerateID(CONF_FAN_COMPONENT_ID): cv.declare_id(TuyaBleFanEntity),
        cv.GenerateID(CONF_LIGHT_COMPONENT_ID): cv.declare_id(light.LightState),
        cv.GenerateID(CONF_LIGHT_OUTPUT_ID): cv.declare_id(TuyaBleLightOutput),
        cv.GenerateID(CONF_TIMER_COMPONENT_ID): cv.declare_id(TuyaBleTimerNumber),
    }
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TuyaBleFanHub),
        cv.GenerateID(esp32_ble_tracker.CONF_ESP32_BLE_ID): cv.use_id(
            esp32_ble_tracker.ESP32BLETracker
        ),
        cv.Optional(CONF_IDLE_DISCONNECT_S, default=30): cv.int_range(min=0, max=3600),
        cv.Required(CONF_FANS): cv.ensure_list(FAN_ITEM_SCHEMA),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    cg.add_define("USE_TUYA_BLE_FAN")

    hub = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(hub, config)

    tracker = await cg.get_variable(config[esp32_ble_tracker.CONF_ESP32_BLE_ID])
    cg.add(hub.set_parent(tracker))

    fans_cfg = config[CONF_FANS]
    idle_s = config[CONF_IDLE_DISCONNECT_S]
    # Single fan defaults to persistent unless explicitly overridden
    if len(fans_cfg) == 1 and CONF_IDLE_DISCONNECT_S not in config:
        idle_s = 0
    cg.add(hub.set_idle_disconnect_s(idle_s))

    for fan_cfg in fans_cfg:
        dev = cg.new_Pvariable(fan_cfg[CONF_ID])
        name = fan_cfg[CONF_NAME]
        cg.add(dev.set_name(name))
        cg.add(dev.set_device_id(fan_cfg[CONF_DEVICE_ID]))
        cg.add(dev.set_local_key(fan_cfg[CONF_LOCAL_KEY]))
        cg.add(dev.set_product_id(fan_cfg[CONF_PRODUCT_ID]))
        if fan_cfg[CONF_UUID]:
            cg.add(dev.set_uuid(fan_cfg[CONF_UUID]))
        if fan_cfg[CONF_MAC_ADDRESS]:
            mac_int = int(fan_cfg[CONF_MAC_ADDRESS].replace(":", ""), 16)
            cg.add(dev.set_mac_address(mac_int))
        cg.add(dev.set_fan_entity_id(fan_cfg[CONF_FAN_ENTITY_ID]))
        if fan_cfg[CONF_LIGHT_ENTITY_ID]:
            cg.add(dev.set_light_entity_id(fan_cfg[CONF_LIGHT_ENTITY_ID]))

        if fan_cfg[CONF_EXPOSE_TO_HA]:
            fan_entity = cg.new_Pvariable(fan_cfg[CONF_FAN_COMPONENT_ID], dev)
            await fan.register_fan(
                fan_entity,
                {
                    CONF_ID: fan_cfg[CONF_FAN_COMPONENT_ID],
                    CONF_NAME: name,
                },
            )
            cg.add(dev.set_fan_entity(fan_entity))

            light_out = cg.new_Pvariable(fan_cfg[CONF_LIGHT_OUTPUT_ID], dev)
            light_state = cg.new_Pvariable(
                fan_cfg[CONF_LIGHT_COMPONENT_ID], light_out
            )
            await light.register_light(
                light_state,
                {
                    CONF_ID: fan_cfg[CONF_LIGHT_COMPONENT_ID],
                    CONF_OUTPUT_ID: fan_cfg[CONF_LIGHT_OUTPUT_ID],
                    CONF_NAME: f"{name} Light",
                },
            )
            cg.add(light_out.set_light_state(light_state))
            cg.add(dev.set_light_output(light_out))

            timer_num = cg.new_Pvariable(fan_cfg[CONF_TIMER_COMPONENT_ID], dev)
            await number.register_number(
                timer_num,
                {
                    CONF_ID: fan_cfg[CONF_TIMER_COMPONENT_ID],
                    CONF_NAME: f"{name} Timer",
                },
                min_value=0,
                max_value=540,
                step=1,
            )
            cg.add(dev.set_timer_number(timer_num))

        cg.add(hub.add_fan(dev))
