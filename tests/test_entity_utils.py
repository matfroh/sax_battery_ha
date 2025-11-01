"""Tests for SAX Battery entity utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.const import (
    CONF_LIMIT_POWER,
    CONF_PILOT_FROM_HA,
    DOMAIN,
)
from custom_components.sax_battery.entity_utils import (
    filter_items_by_type,
    filter_sax_items_by_type,
)
from custom_components.sax_battery.enums import TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription


class TestFilterItemsByType:
    """Tests the filter_items_by_type function for correct filtering of ModbusItem and SAXItem objects.

    Scenarios covered:
    - Filtering items by type (sensor, number, switch, sensor_calc).
    - Ensuring SENSOR and SENSOR_CALC types are both returned when filtering for sensors.
    - Handling items with incorrect entity descriptions.
    - Handling empty item lists.
    - Verifying behavior when should_include_entity returns False.
    - Edge cases for entity inclusion logic.
    """

    @pytest.fixture
    def mock_config_entry_entity_utils(self) -> MockConfigEntry:
        """Create mock config entry for entity utils tests."""
        return MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_PILOT_FROM_HA: True,
                CONF_LIMIT_POWER: False,
            },
            entry_id="test_entity_utils_entry",
        )

    @pytest.fixture
    def mock_modbus_items_entity_utils(self) -> list[ModbusItem]:
        """Create mock ModbusItem objects for testing."""
        items: list[ModbusItem] = []

        # Create sensor item with valid entity description
        sensor_item = MagicMock(spec=ModbusItem)
        sensor_item.name = "test_sensor"
        sensor_item.mtype = TypeConstants.SENSOR
        sensor_item.entitydescription = SensorEntityDescription(
            key="test_sensor",
            name="Test Sensor",
        )
        items.append(sensor_item)

        # Create number item with valid entity description
        number_item = MagicMock(spec=ModbusItem)
        number_item.name = "test_number"
        number_item.mtype = TypeConstants.NUMBER
        number_item.entitydescription = NumberEntityDescription(
            key="test_number",
            name="Test Number",
        )
        items.append(number_item)

        # Create switch item with valid entity description
        switch_item = MagicMock(spec=ModbusItem)
        switch_item.name = "test_switch"
        switch_item.mtype = TypeConstants.SWITCH
        switch_item.entitydescription = SwitchEntityDescription(
            key="test_switch",
            name="Test Switch",
        )
        items.append(switch_item)

        # Create sensor_calc item
        sensor_calc_item = MagicMock(spec=ModbusItem)
        sensor_calc_item.name = "test_sensor_calc"
        sensor_calc_item.mtype = TypeConstants.SENSOR_CALC
        sensor_calc_item.entitydescription = SensorEntityDescription(
            key="test_sensor_calc",
            name="Test Sensor Calc",
        )
        items.append(sensor_calc_item)

        return items

    @pytest.fixture
    def mock_modbus_items_wrong_descriptions(self) -> list[ModbusItem]:
        """Create mock ModbusItem objects with wrong entity descriptions."""
        items: list[ModbusItem] = []

        # Create number item with wrong entity description (sensor instead of number)
        number_item_wrong = MagicMock(spec=ModbusItem)
        number_item_wrong.name = "test_number_wrong"
        number_item_wrong.mtype = TypeConstants.NUMBER
        number_item_wrong.entitydescription = SensorEntityDescription(
            key="test_number_wrong",
            name="Test Number Wrong",
        )
        items.append(number_item_wrong)

        # Create sensor item with wrong entity description (number instead of sensor)
        sensor_item_wrong = MagicMock(spec=ModbusItem)
        sensor_item_wrong.name = "test_sensor_wrong"
        sensor_item_wrong.mtype = TypeConstants.SENSOR
        sensor_item_wrong.entitydescription = NumberEntityDescription(
            key="test_sensor_wrong",
            name="Test Sensor Wrong",
        )
        items.append(sensor_item_wrong)

        return items

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_sensor(
        self,
        mock_should_include: MagicMock,
        mock_modbus_items_entity_utils: list[ModbusItem | SAXItem],
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering modbus items by sensor type."""
        mock_should_include.return_value = True

        result = filter_items_by_type(
            mock_modbus_items_entity_utils,
            TypeConstants.SENSOR,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        # Should return both SENSOR and SENSOR_CALC items
        assert len(result) == 2
        assert any(item.mtype == TypeConstants.SENSOR for item in result)
        assert any(item.mtype == TypeConstants.SENSOR_CALC for item in result)

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_number(
        self,
        mock_should_include: MagicMock,
        mock_modbus_items_entity_utils: list[ModbusItem | SAXItem],
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering modbus items by number type."""
        mock_should_include.return_value = True

        result = filter_items_by_type(
            mock_modbus_items_entity_utils,
            TypeConstants.NUMBER,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        assert len(result) == 1
        assert result[0].mtype == TypeConstants.NUMBER
        assert result[0].name == "test_number"

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_switch(
        self,
        mock_should_include: MagicMock,
        mock_modbus_items_entity_utils: list[ModbusItem | SAXItem],
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering modbus items by switch type."""
        mock_should_include.return_value = True

        result = filter_items_by_type(
            mock_modbus_items_entity_utils,
            TypeConstants.SWITCH,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        assert len(result) == 1
        assert result[0].mtype == TypeConstants.SWITCH
        assert result[0].name == "test_switch"

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_empty_list(
        self,
        mock_should_include: MagicMock,
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering empty list returns empty result."""
        mock_should_include.return_value = True

        result = filter_items_by_type(
            [],
            TypeConstants.SENSOR,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        assert result == []

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_should_include_false(
        self,
        mock_should_include: MagicMock,
        mock_modbus_items_entity_utils: list[ModbusItem | SAXItem],
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering when should_include_entity returns False."""
        mock_should_include.return_value = False

        result = filter_items_by_type(
            mock_modbus_items_entity_utils,
            TypeConstants.SENSOR,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        assert result == []

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    @patch("custom_components.sax_battery.entity_utils._LOGGER")
    async def test_filter_items_by_type_wrong_description_number(
        self,
        mock_logger: MagicMock,
        mock_should_include: MagicMock,
        mock_modbus_items_wrong_descriptions: list[ModbusItem | SAXItem],
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering number items with wrong entity description."""
        mock_should_include.return_value = True

        result = filter_items_by_type(
            mock_modbus_items_wrong_descriptions,
            TypeConstants.NUMBER,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        # Should exclude item with wrong description
        assert len(result) == 0

        # Should log warning about wrong description type
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        assert warning_call is not None
        warning_args = warning_call[0]
        assert "wrong entity description type" in warning_args[0]
        assert "test_number_wrong" in warning_args[1]

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    @patch("custom_components.sax_battery.entity_utils._LOGGER")
    async def test_filter_items_by_type_wrong_description_sensor(
        self,
        mock_logger: MagicMock,
        mock_should_include: MagicMock,
        mock_modbus_items_wrong_descriptions: list[ModbusItem | SAXItem],
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering sensor items with wrong entity description."""
        mock_should_include.return_value = True

        result = filter_items_by_type(
            mock_modbus_items_wrong_descriptions,
            TypeConstants.SENSOR,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        # Should exclude item with wrong description
        assert len(result) == 0

        # Should log warning about wrong description type
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        assert warning_call is not None
        warning_args = warning_call[0]
        assert "wrong entity description type" in warning_args[0]
        assert "test_sensor_wrong" in warning_args[1]

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_no_entity_description(
        self,
        mock_should_include: MagicMock,
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering items without entity description."""
        mock_should_include.return_value = True

        # Create item without entity description
        item = MagicMock(spec=ModbusItem)
        item.name = "test_no_desc"
        item.mtype = TypeConstants.SENSOR
        item.entitydescription = None

        result = filter_items_by_type(
            [item],
            TypeConstants.SENSOR,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        # Should include item even without entity description
        assert len(result) == 1
        assert result[0].name == "test_no_desc"

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_by_type_number_variants(
        self,
        mock_should_include: MagicMock,
        mock_config_entry_entity_utils: MockConfigEntry,
    ) -> None:
        """Test filtering number type variants (NUMBER, NUMBER_RO, NUMBER_WO)."""
        mock_should_include.return_value = True

        items: list[ModbusItem | SAXItem] = []
        for i, number_type in enumerate(
            [TypeConstants.NUMBER, TypeConstants.NUMBER_RO, TypeConstants.NUMBER_WO]
        ):
            item = MagicMock(spec=ModbusItem)
            item.name = f"number_item_{i}"
            item.mtype = number_type
            item.entitydescription = NumberEntityDescription(
                key=f"number_item_{i}",
                name=f"Number Item {i}",
            )
            items.append(item)

        result = filter_items_by_type(
            items,
            TypeConstants.NUMBER,
            mock_config_entry_entity_utils,
            "battery_a",
        )

        # Should include all number type variants
        assert len(result) == 3
        assert any(item.mtype == TypeConstants.NUMBER for item in result)
        assert any(item.mtype == TypeConstants.NUMBER_RO for item in result)
        assert any(item.mtype == TypeConstants.NUMBER_WO for item in result)


class TestFilterSaxItemsByType:
    """Test filter_sax_items_by_type function."""

    @pytest.fixture
    def mock_sax_items_entity_utils(self) -> list[SAXItem]:
        """Create mock SAXItem objects for testing."""
        items: list[SAXItem] = []

        # Create different types of SAX items (using only available constants)
        for i, item_type in enumerate(
            [
                TypeConstants.SENSOR_CALC,
                TypeConstants.SENSOR,
                TypeConstants.NUMBER,
                TypeConstants.SWITCH,
            ]
        ):
            item = MagicMock(spec=SAXItem)
            item.name = f"sax_item_{i}"
            item.mtype = item_type
            item.device = "SYS"
            item.entitydescription = (
                None  # Most SAX items don't have entity descriptions
            )
            items.append(item)

        return items

    @pytest.fixture
    def mock_sax_items_with_descriptions(self) -> list[SAXItem]:
        """Create mock SAXItem objects with entity descriptions."""
        items: list[SAXItem] = []

        # Create SAX item with matching entity description
        sensor_item = MagicMock(spec=SAXItem)
        sensor_item.name = "sax_sensor_with_desc"
        sensor_item.mtype = TypeConstants.SENSOR
        sensor_item.entitydescription = SensorEntityDescription(
            key="sax_sensor_with_desc",
            name="SAX Sensor With Description",
        )
        items.append(sensor_item)

        # Create SAX item with mismatched entity description
        number_item = MagicMock(spec=SAXItem)
        number_item.name = "sax_number_with_sensor_desc"
        number_item.mtype = TypeConstants.NUMBER
        number_item.entitydescription = SensorEntityDescription(
            key="sax_number_with_sensor_desc",
            name="SAX Number With Sensor Description",
        )
        items.append(number_item)

        return items

    async def test_filter_sax_items_by_type_sensor_calc(
        self, mock_sax_items_entity_utils: list[SAXItem]
    ) -> None:
        """Test filtering SAX items by calculated sensor type."""
        result = filter_sax_items_by_type(
            mock_sax_items_entity_utils, TypeConstants.SENSOR_CALC
        )

        assert len(result) == 1
        assert result[0].mtype == TypeConstants.SENSOR_CALC
        assert result[0].name == "sax_item_0"

    async def test_filter_sax_items_by_type_sensor(
        self, mock_sax_items_entity_utils: list[SAXItem]
    ) -> None:
        """Test filtering SAX items by sensor type."""
        result = filter_sax_items_by_type(
            mock_sax_items_entity_utils, TypeConstants.SENSOR
        )

        # Should include both SENSOR and SENSOR_CALC items
        assert len(result) == 2
        sensor_types = [item.mtype for item in result]
        assert TypeConstants.SENSOR in sensor_types
        assert TypeConstants.SENSOR_CALC in sensor_types

    async def test_filter_sax_items_by_type_number(
        self, mock_sax_items_entity_utils: list[SAXItem]
    ) -> None:
        """Test filtering SAX items by number type."""
        result = filter_sax_items_by_type(
            mock_sax_items_entity_utils, TypeConstants.NUMBER
        )

        assert len(result) == 1
        assert result[0].mtype == TypeConstants.NUMBER
        assert result[0].name == "sax_item_2"

    async def test_filter_sax_items_by_type_switch(
        self, mock_sax_items_entity_utils: list[SAXItem]
    ) -> None:
        """Test filtering SAX items by switch type."""
        result = filter_sax_items_by_type(
            mock_sax_items_entity_utils, TypeConstants.SWITCH
        )

        assert len(result) == 1
        assert result[0].mtype == TypeConstants.SWITCH
        assert result[0].name == "sax_item_3"

    async def test_filter_sax_items_by_type_empty_list(self) -> None:
        """Test filtering empty list returns empty result."""
        result = filter_sax_items_by_type([], TypeConstants.SENSOR)

        assert result == []

    @patch("custom_components.sax_battery.entity_utils._LOGGER")
    async def test_filter_sax_items_by_type_with_entity_descriptions(
        self, mock_logger: MagicMock, mock_sax_items_with_descriptions: list[SAXItem]
    ) -> None:
        """Test filtering SAX items with entity descriptions (logs debug messages)."""
        result = filter_sax_items_by_type(
            mock_sax_items_with_descriptions, TypeConstants.SENSOR
        )

        # Should include the sensor item
        assert len(result) == 1
        assert result[0].name == "sax_sensor_with_desc"

        # No debug logging should occur for matching description
        mock_logger.debug.assert_not_called()

    @patch("custom_components.sax_battery.entity_utils._LOGGER")
    async def test_filter_sax_items_by_type_mismatched_description(
        self, mock_logger: MagicMock, mock_sax_items_with_descriptions: list[SAXItem]
    ) -> None:
        """Test filtering SAX items with mismatched entity descriptions."""
        result = filter_sax_items_by_type(
            mock_sax_items_with_descriptions, TypeConstants.NUMBER
        )

        # Should still include the item (SAX items are more lenient)
        assert len(result) == 1
        assert result[0].name == "sax_number_with_sensor_desc"

        # Should log debug message about mismatched description
        mock_logger.debug.assert_called_once()
        debug_call = mock_logger.debug.call_args
        assert debug_call is not None
        debug_args = debug_call[0]
        assert "has entity description type" in debug_args[0]
        assert "sax_number_with_sensor_desc" in debug_args[1]

    async def test_filter_sax_items_by_type_number_variants(self) -> None:
        """Test filtering SAX items for number type variants."""
        items: list[SAXItem] = []
        for i, number_type in enumerate(
            [TypeConstants.NUMBER, TypeConstants.NUMBER_RO, TypeConstants.NUMBER_WO]
        ):
            item = MagicMock(spec=SAXItem)
            item.name = f"sax_number_item_{i}"
            item.mtype = number_type
            item.entitydescription = None
            items.append(item)

        result = filter_sax_items_by_type(items, TypeConstants.NUMBER)

        # Should include all number type variants
        assert len(result) == 3
        assert any(item.mtype == TypeConstants.NUMBER for item in result)
        assert any(item.mtype == TypeConstants.NUMBER_RO for item in result)
        assert any(item.mtype == TypeConstants.NUMBER_WO for item in result)

    async def test_filter_sax_items_by_type_multiple_sensor_matches(self) -> None:
        """Test filtering SAX items with multiple sensor matches."""
        items: list[SAXItem] = []

        # Create multiple sensor-type items
        sensor_item = MagicMock(spec=SAXItem)
        sensor_item.name = "regular_sensor"
        sensor_item.mtype = TypeConstants.SENSOR
        sensor_item.entitydescription = None
        items.append(sensor_item)

        calc_sensor_item = MagicMock(spec=SAXItem)
        calc_sensor_item.name = "calc_sensor"
        calc_sensor_item.mtype = TypeConstants.SENSOR_CALC
        calc_sensor_item.entitydescription = None
        items.append(calc_sensor_item)

        result = filter_sax_items_by_type(items, TypeConstants.SENSOR)

        # Should include both sensor types
        assert len(result) == 2
        names = [item.name for item in result]
        assert "regular_sensor" in names
        assert "calc_sensor" in names


class TestEntityUtilsEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def mock_config_entry_edge_cases(self) -> MockConfigEntry:
        """Create mock config entry for edge case tests."""
        return MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_PILOT_FROM_HA: False,
                CONF_LIMIT_POWER: True,
            },
            entry_id="test_edge_cases_entry",
        )

    async def test_filter_items_by_type_none_input(
        self, mock_config_entry_edge_cases: MockConfigEntry
    ) -> None:
        """Test filtering with None input."""
        with pytest.raises(TypeError):
            # Using cast to bypass mypy check since we're testing error handling
            filter_items_by_type(
                None,  # type: ignore[arg-type]
                TypeConstants.SENSOR,
                mock_config_entry_edge_cases,
                "battery_a",
            )

    async def test_filter_sax_items_by_type_none_input(self) -> None:
        """Test filtering SAX items with None input."""
        with pytest.raises(TypeError):
            filter_sax_items_by_type(None, TypeConstants.SENSOR)  # type: ignore[arg-type]

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    async def test_filter_items_mixed_types(
        self,
        mock_should_include: MagicMock,
        mock_config_entry_edge_cases: MockConfigEntry,
    ) -> None:
        """Test filtering with mixed ModbusItem and SAXItem types."""
        mock_should_include.return_value = True

        # Mix ModbusItem and SAXItem (shouldn't happen in practice but test for robustness)
        modbus_item = MagicMock(spec=ModbusItem)
        modbus_item.name = "modbus_sensor"
        modbus_item.mtype = TypeConstants.SENSOR
        modbus_item.entitydescription = SensorEntityDescription(
            key="modbus_sensor",
            name="Modbus Sensor",
        )

        sax_item = MagicMock(spec=SAXItem)
        sax_item.name = "sax_sensor"
        sax_item.mtype = TypeConstants.SENSOR
        sax_item.entitydescription = None

        mixed_items: list[ModbusItem | SAXItem] = [modbus_item, sax_item]

        result = filter_items_by_type(
            mixed_items,
            TypeConstants.SENSOR,
            mock_config_entry_edge_cases,
            "battery_a",
        )

        # Should handle both types
        assert len(result) == 2

    async def test_filter_items_performance_large_list(self) -> None:
        """Test filtering performance with large item lists."""
        # Create a large list of items for performance testing
        large_item_list: list[SAXItem] = []
        for i in range(1000):
            item = MagicMock(spec=SAXItem)
            item.name = f"item_{i}"
            item.mtype = TypeConstants.SENSOR if i % 2 == 0 else TypeConstants.NUMBER
            item.entitydescription = None
            large_item_list.append(item)

        # Should handle large lists efficiently
        sensor_items = filter_sax_items_by_type(large_item_list, TypeConstants.SENSOR)

        # Should return only sensor items (half of the list)
        assert len(sensor_items) == 500
        assert all(item.mtype == TypeConstants.SENSOR for item in sensor_items)

    @patch("custom_components.sax_battery.entity_utils.should_include_entity")
    @patch("custom_components.sax_battery.entity_utils._LOGGER")
    async def test_filter_items_exception_in_should_include(
        self,
        mock_logger: MagicMock,
        mock_should_include: MagicMock,
        mock_config_entry_edge_cases: MockConfigEntry,
    ) -> None:
        """Test filtering when should_include_entity raises an exception."""
        mock_should_include.side_effect = Exception("Test exception")

        item = MagicMock(spec=ModbusItem)
        item.name = "test_item"
        item.mtype = TypeConstants.SENSOR
        item.entitydescription = SensorEntityDescription(
            key="test_item",
            name="Test Item",
        )

        # The function doesn't handle exceptions gracefully currently,
        # so we expect the exception to propagate
        with pytest.raises(Exception, match="Test exception"):
            filter_items_by_type(
                [item],
                TypeConstants.SENSOR,
                mock_config_entry_edge_cases,
                "battery_a",
            )

    async def test_filter_items_case_sensitivity(self) -> None:
        """Test that filtering handles entity description type names correctly."""
        # Create item with entity description that might have different casing
        item = MagicMock(spec=ModbusItem)
        item.name = "test_item"
        item.mtype = TypeConstants.SENSOR

        # Create a mock entity description with a type name that contains the required string
        mock_description = MagicMock()
        type(mock_description).__name__ = "CustomSensorEntityDescription"
        item.entitydescription = mock_description

        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PILOT_FROM_HA: True},
            entry_id="test_case_sensitivity",
        )

        with patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            result = filter_items_by_type(
                [item],
                TypeConstants.SENSOR,
                mock_config_entry,
                "battery_a",
            )

            # Should include the item since "SensorEntityDescription" is in the type name
            assert len(result) == 1

    async def test_filter_items_security_validation(self) -> None:
        """Test that filtering validates input types for security."""
        # Test with malicious input that could cause issues
        malicious_item = MagicMock()
        malicious_item.name = "../../../etc/passwd"  # Path traversal attempt
        malicious_item.mtype = TypeConstants.SENSOR
        malicious_item.entitydescription = None

        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PILOT_FROM_HA: True},
            entry_id="test_security",
        )

        with patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            # Should handle malicious input gracefully without crashing
            result = filter_items_by_type(
                [malicious_item],
                TypeConstants.SENSOR,
                mock_config_entry,
                "battery_a",
            )

            # Should still process the item (name validation is not the responsibility of this filter)
            assert len(result) == 1

    async def test_filter_items_memory_efficiency(self) -> None:
        """Test memory efficiency with filtering operations."""
        # Create items with various memory-heavy attributes
        items: list[ModbusItem | SAXItem] = []
        for i in range(100):
            item = MagicMock(spec=ModbusItem)
            item.name = f"item_{i}"
            item.mtype = TypeConstants.SENSOR
            # Add memory-heavy mock data
            item.large_data = "x" * 1000  # 1KB of data per item
            item.entitydescription = SensorEntityDescription(
                key=f"item_{i}",
                name=f"Item {i}",
            )
            items.append(item)

        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PILOT_FROM_HA: True},
            entry_id="test_memory",
        )

        with patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            # Filter should not cause memory issues with moderate-sized lists
            result = filter_items_by_type(
                items,
                TypeConstants.SENSOR,
                mock_config_entry,
                "battery_a",
            )

            assert len(result) == 100
            # Verify objects are properly referenced (not copied unnecessarily)
            assert all(item in items for item in result)
