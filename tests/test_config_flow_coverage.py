"""Tests for config_flow.py to achieve 100% coverage.

This module contains additional tests for uncovered code paths in config_flow.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.config_flow import SAXBatteryConfigFlow
from custom_components.sax_battery.const import (
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_CONTROL_POWER,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_MIN_SOC,
    DEFAULT_PORT,
    DOMAIN,
)
from custom_components.sax_battery.entity_keys import SAX_MAX_CHARGE, SAX_MAX_DISCHARGE
from custom_components.sax_battery.items import ModbusItem
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


class TestConfigFlowReconfigureErrorPaths:
    """Test reconfigure error paths in battery_config step."""

    async def test_reconfigure_battery_config_no_entry_id_in_context(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery_config during reconfigure with missing entry_id.

        Coverage: config_flow.py line 285
        """
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1
        flow._data = {}

        # Set context to reconfigure but don't provide entry_id
        flow.context = {"source": "reconfigure"}

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
                CONF_MASTER_BATTERY: "bess_a",
            }
        )

        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "reconfigure_entry_not_found"

    async def test_reconfigure_battery_config_entry_not_found(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery_config during reconfigure with non-existent entry.

        Coverage: config_flow.py line 292
        """
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1
        flow._data = {}

        # Set context with entry_id that doesn't exist
        flow.context = {"source": "reconfigure", "entry_id": "non_existent_entry"}

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
                CONF_MASTER_BATTERY: "bess_a",
            }
        )

        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "reconfigure_entry_not_found"


class TestOptionsFlowHelperMethods:
    """Test options flow helper methods for full coverage."""

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_enable_power_limits_with_integration_data(
        self, hass: HomeAssistant
    ) -> None:
        """Test enabling power limits triggers entity enabling.

        Coverage: config_flow.py lines 570-633 (_async_enable_power_limit_entities)
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_enable_limits",
        )
        mock_entry.add_to_hass(hass)

        # Create mock ModbusItem instances
        mock_max_discharge_item = MagicMock(spec=ModbusItem)
        mock_max_discharge_item.name = SAX_MAX_DISCHARGE

        mock_max_charge_item = MagicMock(spec=ModbusItem)
        mock_max_charge_item.name = SAX_MAX_CHARGE

        # Mock integration data with SAXBatteryData
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_max_discharge"
        )

        hass.data[DOMAIN] = {
            mock_entry.entry_id: {
                "sax_data": mock_sax_data,
            }
        }

        # Mock entity registry
        with (
            patch(
                "custom_components.sax_battery.config_flow.er.async_get"
            ) as mock_ent_reg_get,
            patch(
                "custom_components.sax_battery.config_flow.MODBUS_BATTERY_POWER_LIMIT_ITEMS",
                [mock_max_discharge_item, mock_max_charge_item],
            ),
        ):
            mock_ent_reg = MagicMock()
            mock_ent_reg.async_get_entity_id = MagicMock(
                return_value="number.sax_max_discharge"
            )
            mock_ent_reg.async_update_entity = MagicMock()
            mock_ent_reg_get.return_value = mock_ent_reg

            # Initialize options flow
            result = await hass.config_entries.options.async_init(mock_entry.entry_id)
            assert result["type"] == FlowResultType.FORM

            # Enable limit power
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CONTROL_POWER: True,
                    CONF_LIMIT_POWER: True,
                },
            )

            # Verify entity was enabled
            assert mock_ent_reg.async_update_entity.call_count >= 1
            assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_disable_power_limits_with_integration_data(
        self, hass: HomeAssistant
    ) -> None:
        """Test disabling power limits triggers entity disabling.

        Coverage: config_flow.py lines 661-724 (_async_disable_power_limit_entities)
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_disable_limits",
        )
        mock_entry.add_to_hass(hass)

        # Create mock ModbusItem instances
        mock_max_discharge_item = MagicMock(spec=ModbusItem)
        mock_max_discharge_item.name = SAX_MAX_DISCHARGE

        mock_max_charge_item = MagicMock(spec=ModbusItem)
        mock_max_charge_item.name = SAX_MAX_CHARGE

        # Mock integration data
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_max_discharge"
        )

        hass.data[DOMAIN] = {
            mock_entry.entry_id: {
                "sax_data": mock_sax_data,
            }
        }

        # Mock entity registry
        with (
            patch(
                "custom_components.sax_battery.config_flow.er.async_get"
            ) as mock_ent_reg_get,
            patch(
                "custom_components.sax_battery.config_flow.MODBUS_BATTERY_POWER_LIMIT_ITEMS",
                [mock_max_discharge_item, mock_max_charge_item],
            ),
        ):
            mock_ent_reg = MagicMock()
            mock_ent_reg.async_get_entity_id = MagicMock(
                return_value="number.sax_max_discharge"
            )
            mock_ent_reg.async_update_entity = MagicMock()
            mock_ent_reg_get.return_value = mock_ent_reg

            # Initialize options flow
            result = await hass.config_entries.options.async_init(mock_entry.entry_id)
            assert result["type"] == FlowResultType.FORM

            # Disable limit power
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CONTROL_POWER: True,
                    CONF_LIMIT_POWER: False,
                },
            )

            # Verify entity was disabled
            assert mock_ent_reg.async_update_entity.call_count >= 1
            assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_disable_control_power_stops_power_manager(
        self, hass: HomeAssistant
    ) -> None:
        """Test disabling control power stops power manager.

        Coverage: config_flow.py lines 749-758 (_async_stop_power_manager)
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_stop_power_manager",
        )
        mock_entry.add_to_hass(hass)

        # Mock power manager before setup
        mock_power_manager = MagicMock()
        mock_power_manager.async_stop = AsyncMock()

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {
            "power_manager": mock_power_manager,
        }

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable control power
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify power manager was stopped
        mock_power_manager.async_stop.assert_called_once()
        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_change_limit_power_updates_soc_manager(
        self, hass: HomeAssistant
    ) -> None:
        """Test changing limit power updates SOC manager state.

        Coverage: config_flow.py lines 777-791 (_async_update_soc_manager_state)
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_soc_manager_update",
        )
        mock_entry.add_to_hass(hass)

        # Mock coordinator with SOC manager before setup
        mock_soc_manager = MagicMock()
        mock_soc_manager.enabled = False

        mock_coordinator = MagicMock()
        mock_coordinator.battery_id = "bess_a"
        mock_coordinator.soc_manager = mock_soc_manager

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {
            "coordinators": {"bess_a": mock_coordinator}
        }

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (triggers SOC manager update)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify SOC manager was enabled
        assert mock_soc_manager.enabled is True
        assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("_mock_setup_integration")
class TestConfigFlowPowerLimitEdgeCases:
    """Test edge cases in power limit entity handling."""

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_enable_power_limits_unique_id_generation_fails(
        self,
        mock_entity_registry,
        hass: HomeAssistant,
    ) -> None:
        """Test enable power limits when unique_id generation fails.

        Coverage: config_flow.py lines 595-599
        Security:
            OWASP A05: Validates handling when unique_id cannot be generated
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_unique_id_fail_enable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with get_unique_id_for_item returning None
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(return_value=None)

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (should handle unique_id=None gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify flow completes despite unique_id failure
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Entity registry should not be called since unique_id was None
        mock_ent_reg.async_get_entity_id.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_enable_power_limits_entity_not_found(
        self,
        mock_entity_registry,
        hass: HomeAssistant,
    ) -> None:
        """Test enable power limits when entity not found in registry.

        Coverage: config_flow.py lines 605-610
        Security:
            OWASP A05: Validates handling when entity doesn't exist in registry
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_entity_not_found_enable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with valid unique_id
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_cluster_max_discharge"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry to return None (entity not found)
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(return_value=None)
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (should handle entity not found gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify flow completes despite entity not found
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # async_update_entity should not be called since entity wasn't found
        mock_ent_reg.async_update_entity.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_sax_data_missing(
        self,
        mock_entity_registry,
        hass: HomeAssistant,
    ) -> None:
        """Test disable power limits when SAXBatteryData is missing.

        Coverage: config_flow.py lines 663-666
        Security:
            OWASP A05: Validates handling when SAXBatteryData not in integration data
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_sax_data_missing",
        )
        mock_entry.add_to_hass(hass)

        # Pre-create integration data WITHOUT sax_data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle missing sax_data gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite missing sax_data
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Entity registry should not be used since sax_data was missing
        mock_ent_reg.async_get_entity_id.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_unique_id_generation_fails(
        self,
        mock_entity_registry,
        hass: HomeAssistant,
    ) -> None:
        """Test disable power limits when unique_id generation fails.

        Coverage: config_flow.py lines 686-690
        Security:
            OWASP A05: Validates handling when unique_id cannot be generated
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_unique_id_fail_disable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with get_unique_id_for_item returning None
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(return_value=None)

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle unique_id=None gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite unique_id failure
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Entity registry should not be called since unique_id was None
        mock_ent_reg.async_get_entity_id.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_entity_not_found(
        self,
        mock_entity_registry,
        hass: HomeAssistant,
    ) -> None:
        """Test disable power limits when entity not found in registry.

        Coverage: config_flow.py lines 696-701
        Security:
            OWASP A05: Validates handling when entity doesn't exist in registry
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_entity_not_found_disable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with valid unique_id
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_cluster_max_discharge"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry to return None (entity not found)
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(return_value=None)
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle entity not found gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite entity not found
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # async_update_entity should not be called since entity wasn't found
        mock_ent_reg.async_update_entity.assert_not_called()
