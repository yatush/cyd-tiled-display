import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import binary_sensor, esp32, esp32_ble_tracker, fan, light, number, sensor
from esphome.core import CORE
from esphome.const import (
    CONF_ESPHOME,
    CONF_ID,
    CONF_MAC_ADDRESS,
    CONF_NAME,
    CONF_OUTPUT_ID,
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_SIGNAL_STRENGTH,
    ENTITY_CATEGORY_DIAGNOSTIC,
    STATE_CLASS_MEASUREMENT,
    UNIT_DECIBEL_MILLIWATT,
)

try:
    from esphome.const import CONF_DEVICES, CONF_DEVICE_ID as ESPHOME_CONF_DEVICE_ID
    from esphome.core.config import CONF_RELATION, DEFAULT_DEVICE_RELATION, Device

    HAS_SUB_DEVICES = True
except ImportError:
    CONF_DEVICES = "devices"
    ESPHOME_CONF_DEVICE_ID = "device_id"
    CONF_RELATION = "relation"
    DEFAULT_DEVICE_RELATION = "via"
    Device = None
    HAS_SUB_DEVICES = False

DEPENDENCIES = ["esp32_ble_tracker"]
AUTO_LOAD = ["binary_sensor", "fan", "light", "number", "sensor"]

CONF_FANS = "fans"
CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_PRODUCT_ID = "product_id"
CONF_UUID = "uuid"
CONF_FAN_ENTITY_ID = "fan_entity_id"
CONF_LIGHT_ENTITY_ID = "light_entity_id"
CONF_EXPOSE_TO_HA = "expose_to_ha"
CONF_IDLE_DISCONNECT_S = "idle_disconnect_s"
CONF_MAX_CONNECTIONS = "max_connections"
CONF_SUB_DEVICE_ID = "sub_device_id"
CONF_FAN_COMPONENT_ID = "fan_component_id"
CONF_LIGHT_COMPONENT_ID = "light_component_id"
CONF_LIGHT_OUTPUT_ID = "light_output_id"
CONF_TIMER_COMPONENT_ID = "timer_component_id"
CONF_RSSI_SENSOR_ID = "rssi_sensor_id"
CONF_BLE_CONNECTED_SENSOR_ID = "ble_connected_sensor_id"

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


_FAN_ITEM_DICT = {
    cv.GenerateID(): cv.declare_id(TuyaBleFanDevice),
    cv.Required(CONF_NAME): cv.string,
    cv.Required(CONF_DEVICE_ID): cv.string,
    cv.Required(CONF_LOCAL_KEY): cv.string,
    cv.Optional(CONF_PRODUCT_ID, default=""): cv.string,
    cv.Optional(CONF_UUID, default=""): cv.string,
    cv.Optional(CONF_MAC_ADDRESS, default=""): _validate_optional_mac,
    cv.Optional(CONF_FAN_ENTITY_ID, default=""): cv.string,
    cv.Optional(CONF_LIGHT_ENTITY_ID, default=""): cv.string,
    cv.Optional(CONF_EXPOSE_TO_HA, default=True): cv.boolean,
    cv.GenerateID(CONF_FAN_COMPONENT_ID): cv.declare_id(TuyaBleFanEntity),
    cv.GenerateID(CONF_LIGHT_COMPONENT_ID): cv.declare_id(light.LightState),
    cv.GenerateID(CONF_LIGHT_OUTPUT_ID): cv.declare_id(TuyaBleLightOutput),
    cv.GenerateID(CONF_TIMER_COMPONENT_ID): cv.declare_id(TuyaBleTimerNumber),
    cv.GenerateID(CONF_RSSI_SENSOR_ID): cv.declare_id(sensor.Sensor),
    cv.GenerateID(CONF_BLE_CONNECTED_SENSOR_ID): cv.declare_id(
        binary_sensor.BinarySensor
    ),
}
if HAS_SUB_DEVICES:
    _FAN_ITEM_DICT[cv.GenerateID(CONF_SUB_DEVICE_ID)] = cv.declare_id(Device)

FAN_ITEM_SCHEMA = cv.Schema(_FAN_ITEM_DICT)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TuyaBleFanHub),
        cv.GenerateID(esp32_ble_tracker.CONF_ESP32_BLE_ID): cv.use_id(
            esp32_ble_tracker.ESP32BLETracker
        ),
        cv.Optional(CONF_IDLE_DISCONNECT_S): cv.int_range(min=0, max=3600),
        cv.Optional(CONF_MAX_CONNECTIONS): cv.int_range(min=1, max=3),
        cv.Optional(CONF_FANS, default=[]): cv.ensure_list(FAN_ITEM_SCHEMA),
    }
).extend(cv.COMPONENT_SCHEMA)


def _register_sub_devices(config):
    if not HAS_SUB_DEVICES:
        return config
    fconf = fv.full_config.get()
    esphome_conf = fconf.setdefault(CONF_ESPHOME, {})
    devices = esphome_conf.setdefault(CONF_DEVICES, [])
    existing_ids = {
        d[CONF_ID].id for d in devices if isinstance(d, dict) and CONF_ID in d
    }
    for fan_cfg in config.get(CONF_FANS, []):
        if not fan_cfg.get(CONF_EXPOSE_TO_HA, True):
            continue
        sub_id = fan_cfg.get(CONF_SUB_DEVICE_ID)
        if sub_id is not None and sub_id.id not in existing_ids:
            devices.append(
                {
                    CONF_ID: sub_id,
                    CONF_NAME: fan_cfg[CONF_NAME],
                    CONF_RELATION: DEFAULT_DEVICE_RELATION,
                }
            )
            existing_ids.add(sub_id.id)
    return config


FINAL_VALIDATE_SCHEMA = _register_sub_devices


def _validate_light_subconfig(light_id, output_id, name):
    raw = {
        CONF_ID: light_id,
        CONF_OUTPUT_ID: output_id,
        CONF_NAME: name,
    }
    if hasattr(light, "LIGHT_SCHEMA"):
        return light.LIGHT_SCHEMA.extend(
            {cv.GenerateID(CONF_OUTPUT_ID): cv.declare_id(TuyaBleLightOutput)}
        )(raw)
    return raw


def _validate_fan_subconfig(fan_id, name):
    raw = {
        CONF_ID: fan_id,
        CONF_NAME: name,
    }
    if hasattr(fan, "fan_schema"):
        return fan.fan_schema(TuyaBleFanEntity)(raw)
    if hasattr(fan, "FAN_SCHEMA"):
        return fan.FAN_SCHEMA(raw)
    return raw


def _validate_number_subconfig(num_id, name):
    raw = {
        CONF_ID: num_id,
        CONF_NAME: name,
    }
    if hasattr(number, "number_schema"):
        return number.number_schema(TuyaBleTimerNumber)(raw)
    if hasattr(number, "NUMBER_SCHEMA"):
        return number.NUMBER_SCHEMA(raw)
    return raw


def _validate_rssi_sensor_subconfig(sensor_id, name):
    raw = {
        CONF_ID: sensor_id,
        CONF_NAME: name,
    }
    if hasattr(sensor, "sensor_schema"):
        return sensor.sensor_schema(
            unit_of_measurement=UNIT_DECIBEL_MILLIWATT,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_SIGNAL_STRENGTH,
            state_class=STATE_CLASS_MEASUREMENT,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        )(raw)
    return raw


def _validate_ble_connected_sensor_subconfig(sensor_id, name):
    raw = {
        CONF_ID: sensor_id,
        CONF_NAME: name,
    }
    if hasattr(binary_sensor, "binary_sensor_schema"):
        return binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_CONNECTIVITY,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        )(raw)
    return raw


async def to_code(config):
    cg.add_define("USE_TUYA_BLE_FAN")

    hub = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(hub, config)
    await esp32_ble_tracker.register_client(hub, config)

    tracker = await cg.get_variable(config[esp32_ble_tracker.CONF_ESP32_BLE_ID])
    cg.add(hub.set_parent(tracker))

    fans_cfg = config[CONF_FANS]
    has_ble_proxy = "bluetooth_proxy" in (CORE.config or {})
    max_fan_slots = 2 if has_ble_proxy else 3
    default_fan_conns = max(1, min(len(fans_cfg), max_fan_slots))
    fan_conns = config.get(CONF_MAX_CONNECTIONS, default_fan_conns)
    total_ble_conns = min(3, fan_conns + (1 if has_ble_proxy else 0))

    # Dynamically size ESP-IDF Bluedroid ACL/BLE connection slots at compile time
    if hasattr(esp32, "add_idf_sdkconfig_option"):
        esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_BLE_MAX_CONN", total_ble_conns)
        esp32.add_idf_sdkconfig_option("CONFIG_BT_ACL_CONNECTIONS", total_ble_conns)

    cg.add(hub.set_max_connections(fan_conns))
    idle_s = config.get(CONF_IDLE_DISCONNECT_S, 0 if len(fans_cfg) <= fan_conns else 30)
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
            sub_dev_id = fan_cfg.get(CONF_SUB_DEVICE_ID) if HAS_SUB_DEVICES else None

            fan_sub = _validate_fan_subconfig(
                fan_cfg[CONF_FAN_COMPONENT_ID], "Fan" if sub_dev_id is not None else name
            )
            if sub_dev_id is not None:
                fan_sub[ESPHOME_CONF_DEVICE_ID] = sub_dev_id
            fan_entity = cg.new_Pvariable(fan_sub[CONF_ID], dev)
            await fan.register_fan(fan_entity, fan_sub)
            cg.add(dev.set_fan_entity(fan_entity))

            light_sub = _validate_light_subconfig(
                fan_cfg[CONF_LIGHT_COMPONENT_ID],
                fan_cfg[CONF_LIGHT_OUTPUT_ID],
                "Light" if sub_dev_id is not None else f"{name} Light",
            )
            if sub_dev_id is not None:
                light_sub[ESPHOME_CONF_DEVICE_ID] = sub_dev_id
            light_out = cg.new_Pvariable(light_sub[CONF_OUTPUT_ID], dev)
            await light.register_light(light_out, light_sub)
            light_state = await cg.get_variable(light_sub[CONF_ID])
            cg.add(light_state.set_default_transition_length(0))
            cg.add(light_out.set_light_state(light_state))
            cg.add(dev.set_light_output(light_out))

            num_sub = _validate_number_subconfig(
                fan_cfg[CONF_TIMER_COMPONENT_ID],
                "Timer" if sub_dev_id is not None else f"{name} Timer",
            )
            if sub_dev_id is not None:
                num_sub[ESPHOME_CONF_DEVICE_ID] = sub_dev_id
            timer_num = cg.new_Pvariable(num_sub[CONF_ID], dev)
            await number.register_number(
                timer_num,
                num_sub,
                min_value=0,
                max_value=540,
                step=1,
            )
            cg.add(dev.set_timer_number(timer_num))

            rssi_sub = _validate_rssi_sensor_subconfig(
                fan_cfg[CONF_RSSI_SENSOR_ID],
                "BLE Signal Strength"
                if sub_dev_id is not None
                else f"{name} BLE Signal Strength",
            )
            if sub_dev_id is not None:
                rssi_sub[ESPHOME_CONF_DEVICE_ID] = sub_dev_id
            rssi_sens = await sensor.new_sensor(rssi_sub)
            cg.add(dev.set_rssi_sensor(rssi_sens))

            conn_sub = _validate_ble_connected_sensor_subconfig(
                fan_cfg[CONF_BLE_CONNECTED_SENSOR_ID],
                "BLE Connected"
                if sub_dev_id is not None
                else f"{name} BLE Connected",
            )
            if sub_dev_id is not None:
                conn_sub[ESPHOME_CONF_DEVICE_ID] = sub_dev_id
            conn_sens = await binary_sensor.new_binary_sensor(conn_sub)
            cg.add(dev.set_ble_connected_sensor(conn_sens))

        cg.add(hub.add_fan(dev))
