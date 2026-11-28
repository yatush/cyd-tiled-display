import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import (
    CONF_ID,
    CONF_NAME,
    ENTITY_CATEGORY_DIAGNOSTIC,
    STATE_CLASS_MEASUREMENT,
)

DEPENDENCIES = ["wifi"]
AUTO_LOAD = ["sensor"]

CONF_ROLE = "role"
CONF_NETWORK_KEY = "network_key"
CONF_FALLBACK_CHANNEL = "fallback_channel"
CONF_UDP_PORT = "udp_port"
CONF_CHANNEL_SENSOR = "channel_sensor"
CONF_FANS = "fans"
CONF_FAN_ENTITY_ID = "fan_entity_id"
CONF_LIGHT_ENTITY_ID = "light_entity_id"
CONF_SHELLYS = "shellys"
CONF_MAC_ADDRESS = "mac_address"
CONF_CHANNEL = "channel"
CONF_KIND = "kind"
CONF_ENTITY_ID = "entity_id"

espnow_ns = cg.esphome_ns.namespace("espnow_fan_bridge")
EspNowFanBridge = espnow_ns.class_("EspNowFanBridge", cg.Component)
BridgeRole = espnow_ns.enum("BridgeRole", is_class=True)

ROLES = {
    "hub": BridgeRole.HUB,
    "cyd": BridgeRole.CYD,
}

FAN_LINK_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_NAME): cv.string,
        cv.Optional(CONF_FAN_ENTITY_ID, default=""): cv.string,
        cv.Optional(CONF_LIGHT_ENTITY_ID, default=""): cv.string,
    }
)

SHELLY_LINK_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_NAME): cv.string,
        cv.Required(CONF_MAC_ADDRESS): cv.string,
        cv.Optional(CONF_CHANNEL, default=0): cv.int_range(min=0, max=3),
        cv.Optional(CONF_KIND, default="switch"): cv.one_of(
            "switch", "light", "cover", lower=True
        ),
        cv.Required(CONF_ENTITY_ID): cv.string,
    }
)

CHANNEL_SENSOR_SCHEMA = sensor.sensor_schema(
    accuracy_decimals=0,
    entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    state_class=STATE_CLASS_MEASUREMENT,
    icon="mdi:wifi-settings",
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(EspNowFanBridge),
        cv.Required(CONF_ROLE): cv.enum(ROLES, lower=True),
        cv.Optional(CONF_NETWORK_KEY, default="cyd_espnow_default"): cv.string,
        cv.Optional(CONF_FALLBACK_CHANNEL, default=1): cv.int_range(min=1, max=13),
        cv.Optional(CONF_UDP_PORT, default=42110): cv.int_range(min=0, max=65535),
        cv.Optional(CONF_CHANNEL_SENSOR): CHANNEL_SENSOR_SCHEMA,
        cv.Optional(CONF_FANS, default=[]): cv.ensure_list(FAN_LINK_SCHEMA),
        cv.Optional(CONF_SHELLYS, default=[]): cv.ensure_list(SHELLY_LINK_SCHEMA),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    cg.add_define("USE_ESPNOW_FAN_BRIDGE")
    role_key = config[CONF_ROLE]
    cg.add(var.set_role(ROLES[role_key]))
    if role_key == "hub":
        cg.add_define("USE_ESPNOW_FAN_HUB")
    else:
        cg.add_define("USE_ESPNOW_FAN_CYD")

    cg.add(var.set_network_key(config[CONF_NETWORK_KEY]))
    cg.add(var.set_fallback_channel(config[CONF_FALLBACK_CHANNEL]))
    cg.add(var.set_udp_port(config[CONF_UDP_PORT]))

    if CONF_CHANNEL_SENSOR in config:
        sens = await sensor.new_sensor(config[CONF_CHANNEL_SENSOR])
        cg.add(var.set_channel_sensor(sens))

    for fan_cfg in config.get(CONF_FANS, []):
        cg.add(
            var.add_remote_fan(
                fan_cfg[CONF_NAME],
                fan_cfg.get(CONF_FAN_ENTITY_ID, ""),
                fan_cfg.get(CONF_LIGHT_ENTITY_ID, ""),
            )
        )

    for sh_cfg in config.get(CONF_SHELLYS, []):
        is_cover = sh_cfg.get(CONF_KIND, "switch") == "cover"
        cg.add(
            var.add_remote_shelly(
                sh_cfg[CONF_NAME],
                sh_cfg[CONF_MAC_ADDRESS],
                sh_cfg.get(CONF_CHANNEL, 0),
                is_cover,
                sh_cfg[CONF_ENTITY_ID],
            )
        )
