"""Sensors"""

# region #-- imports --#
from __future__ import annotations

import dataclasses
import os.path
import re
from datetime import (
    date,
    datetime,
)
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
)

from homeassistant.components.sensor import (
    DOMAIN as ENTITY_DOMAIN,
    SensorEntity,
    StateType,
    SensorEntityDescription
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify

from . import (
    entity_cleanup,
    HDHomerunEntity,
)
from .const import (
    CONF_DATA_COORDINATOR_GENERAL,
    CONF_DATA_COORDINATOR_TUNER_STATUS,
    CONF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
    CONF_TUNER_CHANNEL_FORMAT,
    CONF_TUNER_CHANNEL_NAME,
    CONF_TUNER_CHANNEL_NUMBER_NAME,
    CONF_TUNER_CHANNEL_NUMBER,
    DEF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
    DEF_TUNER_CHANNEL_FORMAT,
    DOMAIN,
    ENTITY_SLUG,
    UPDATE_DOMAIN,
)
from .pyhdhr import HDHomeRunDevice


# endregion


# region #-- sensor descriptions --#
@dataclasses.dataclass
class RequiredHDHomerunSensorDescription:
    """Represent the required attributes of the sensor description."""


@dataclasses.dataclass
class OptionalHDHomerunSensorDescription:
    """Represent the optional attributes of the sensor description."""

    state_value: Optional[Callable[[Any], Any]] = None


@dataclasses.dataclass
class HDHomerunSensorEntityDescription(
    OptionalHDHomerunSensorDescription,
    SensorEntityDescription,
    RequiredHDHomerunSensorDescription
):
    """Describes sensor entity."""
# endregion


# region #-- sensor classes --#
class HDHomerunSensor(HDHomerunEntity, SensorEntity):
    """Representation of an HDHomeRun sensor"""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        description: HDHomerunSensorEntityDescription,
        hass: HomeAssistant,
    ) -> None:
        """Constructor"""

        super().__init__(config_entry=config_entry, coordinator=coordinator, hass=hass)

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self.entity_description: HDHomerunSensorEntityDescription = description
        self._attr_name = f"{ENTITY_SLUG} " \
                          f"{config_entry.title.replace(ENTITY_SLUG, '').strip()}: " \
                          f"{self.entity_description.name}"
        self._attr_unique_id = f"{config_entry.unique_id}::" \
                               f"{ENTITY_DOMAIN.lower()}::" \
                               f"{slugify(self.entity_description.name)}"

    @property
    def native_value(self) -> StateType | date | datetime:
        """Get the value of the sensor"""

        if self._device:  # we have data
            if self.entity_description.state_value:  # custom state_value function
                if self.entity_description.key:  # use the key attribute as the data for the state_value function
                    return self.entity_description.state_value(getattr(self._device, self.entity_description.key, None))
                else:  # use the hdhomerun device as the data
                    return self.entity_description.state_value(self._device)
            else:  # use the key attribute as the value
                return getattr(self._device, self.entity_description.key, None)
        else:  # no data
            return None


class HDHomerunTunerSensor(HDHomerunSensor):
    """Representation of an HDHomeRun tuner"""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        description: HDHomerunSensorEntityDescription,
        hass: HomeAssistant,
    ) -> None:
        """Constructor"""

        super().__init__(config_entry=config_entry, coordinator=coordinator, description=description, hass=hass)

        self._tuner: dict = self._get_tuner()

    def _get_tuner(self) -> Dict[str, int | str]:
        """Get the tuner information from the coordinator"""

        tuner: Dict[str, int | str] = {}
        device: HDHomeRunDevice = self.coordinator.data
        for t in device.tuner_status:
            if t.get("Resource", "").lower() == self.entity_description.name.lower():
                tuner = t
                break

        return tuner

    def _handle_coordinator_update(self) -> None:
        """Update the device information when the coordinator updates"""

        self._tuner = self._get_tuner()
        super()._handle_coordinator_update()

    def _value(self) -> StateType | date | datetime:
        """Determine the value of the sensor"""

        ret = STATE_IDLE
        if self._tuner.get("VctNumber") and self._tuner.get("VctName"):
            channel_format = self._config.options.get(CONF_TUNER_CHANNEL_FORMAT, DEF_TUNER_CHANNEL_FORMAT)
            if channel_format == CONF_TUNER_CHANNEL_NAME:
                ret = self._tuner.get("VctName")
            elif channel_format == CONF_TUNER_CHANNEL_NUMBER:
                ret = self._tuner.get("VctNumber")
            elif channel_format == CONF_TUNER_CHANNEL_NUMBER_NAME:
                ret = f"{self._tuner.get('VctNumber')}: {self._tuner.get('VctName')}"
            else:
                ret = None
        elif self._tuner.get("Frequency"):
            ret = STATE_IN_USE

        return ret

    @property
    def entity_picture(self) -> Optional[str]:
        """Get the entity picture based on configured paths"""

        ret = None
        entity_picture_path = self._config.options.get(
            CONF_TUNER_CHANNEL_ENTITY_PICTURE_PATH,
            DEF_TUNER_CHANNEL_ENTITY_PICTURE_PATH
        )
        if entity_picture_path and self._value() not in (STATE_IDLE, STATE_IN_USE, STATE_SCANNING):
            ret = os.path.join(entity_picture_path, f"{self._tuner.get('VctName', '').lower()}.png")

        return ret

    @property
    def extra_state_attributes(self) -> Optional[Mapping[str, Any]]:
        """Define additional information for the sensor"""

        regex = re.compile(r'(?<!^)(?=[A-Z])')
        ret = {
            regex.sub("_", k).lower().replace("_i_p", "_ip"): v
            for k, v in self._tuner.items()
            if k.lower() != "resource"
        }

        return ret

    @property
    def icon(self) -> Optional[str]:
        """Get the icon for the sensor"""

        ret = "mdi:television-classic"
        if self._value() in (STATE_IDLE, STATE_IN_USE, STATE_SCANNING):
            ret = "mdi:television-classic-off"

        return ret

    @property
    def native_value(self) -> StateType | date | datetime:
        """Get the value of the sensor"""

        return self._value()
# endregion


SENSORS: tuple[HDHomerunSensorEntityDescription, ...] = (
    HDHomerunSensorEntityDescription(
        key="channels",
        name="Channel Count",
        state_value=lambda d: len(d)
    ),
    HDHomerunSensorEntityDescription(
        key="tuner_count",
        name="Tuner Count",
    ),
)

SENSOR_VERSIONS: tuple[HDHomerunSensorEntityDescription, ...] = (
    HDHomerunSensorEntityDescription(
        key="current_firmware",
        name="Version",
    ),
    HDHomerunSensorEntityDescription(
        key="",
        name="Newest Version",
        state_value=lambda d: d.latest_firmware or d.current_firmware
    ),
)

STATE_IDLE = "Idle"
STATE_IN_USE = "In use"
STATE_SCANNING = "Scanning"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor"""

    cg: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_DATA_COORDINATOR_GENERAL]
    cts: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id].get(CONF_DATA_COORDINATOR_TUNER_STATUS, None)

    # region #-- add default sensors --#
    sensors: List[HDHomerunSensor] = [
        HDHomerunSensor(
            config_entry=config_entry,
            coordinator=cg,
            description=description,
            hass=hass,
        )
        for description in SENSORS
    ]
    # endregion

    # region #-- add version sensors if need be --#
    if UPDATE_DOMAIN is None:
        for description in SENSOR_VERSIONS:
            sensors.append(
                HDHomerunSensor(
                    config_entry=config_entry,
                    coordinator=cg,
                    description=description,
                    hass=hass,
                )
            )
    # endregion

    # region #-- add tuner sensors --#
    if cts:
        hdhomerun_device: HDHomeRunDevice = cts.data
        if hdhomerun_device and hdhomerun_device.tuner_status:
            for tuner in hdhomerun_device.tuner_status:
                sensors.append(
                    HDHomerunTunerSensor(
                        config_entry=config_entry,
                        coordinator=cts,
                        description=HDHomerunSensorEntityDescription(
                            key="",
                            name=tuner.get("Resource"),
                        ),
                        hass=hass,
                    )
                )
    # endregion

    async_add_entities(sensors)

    sensors_to_remove: List[HDHomerunSensor] = []
    if UPDATE_DOMAIN is not None:  # remove the existing version sensors if the update entity is available
        for description in SENSOR_VERSIONS:
            sensors_to_remove.append(
                HDHomerunSensor(
                    config_entry=config_entry,
                    coordinator=cg,
                    description=description,
                    hass=hass,
                )
            )

    if sensors_to_remove:
        entity_cleanup(config_entry=config_entry, entities=sensors_to_remove, hass=hass)
