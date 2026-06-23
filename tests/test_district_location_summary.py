import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.data_drivers.aggregator_driver import aggregate_status
from services.data_drivers.compression_driver import compress_status
from services.status_engine import get_status


class DistrictLocationSummaryTests(unittest.TestCase):
    """Protect the DISTRICT -> BLOCK -> GPNAME counting contract."""

    def setUp(self):
        self.devices = [
            {
                "DISTRICT": "SANGAREDDY",
                "BLOCK": " Sangareddy ",
                "GPNAME": "GP One",
                "SystemDown": "UP",
            },
            {
                # Same hierarchy with different case: this is another device,
                # not another mandal or gram panchayat.
                "DISTRICT": "SANGAREDDY",
                "BLOCK": "SANGAREDDY",
                "GPNAME": "gp one",
                "SystemDown": "DOWN",
            },
            {
                "DISTRICT": "SANGAREDDY",
                "BLOCK": "PATANCHERU",
                "GPNAME": "GP One",
                "SystemDown": "UP",
            },
            {
                "DISTRICT": "SANGAREDDY",
                "BLOCK": "PATANCHERU",
                "GPNAME": "GP Two",
                "SystemDown": "UP",
            },
            {
                # Placeholder hierarchy values must not affect counts.
                "DISTRICT": "SANGAREDDY",
                "BLOCK": "NA",
                "GPNAME": "UNKNOWN",
                "SystemDown": "UP",
            },
        ]

    @patch(
        "services.data_drivers.aggregator_driver.classify_device_type",
        return_value="ONT",
    )
    def test_district_counts_unique_mandals_and_gp_hierarchy(self, _classify):
        result = aggregate_status(
            entity_type="DISTRICT",
            entity_name="SANGAREDDY",
            scope="DISTRICT",
            devices=self.devices,
        )

        self.assertEqual(result["total_devices"], 5)
        self.assertEqual(
            result["location_summary"],
            {
                "total_mandals": 2,
                # GP One exists under two mandals and therefore counts twice.
                "total_gram_panchayats": 3,
            },
        )

    @patch(
        "services.data_drivers.aggregator_driver.classify_device_type",
        return_value="ONT",
    )
    def test_compression_exposes_district_location_summary(self, _classify):
        aggregated = aggregate_status(
            entity_type="DISTRICT",
            entity_name="SANGAREDDY",
            scope="DISTRICT",
            devices=self.devices,
        )

        compressed = compress_status(
            resolved={"scope_level": "DISTRICT", "lookup_type": "NAME"},
            aggregated=aggregated,
            devices=self.devices,
        )

        self.assertEqual(compressed["location_summary"]["total_mandals"], 2)
        self.assertEqual(
            compressed["location_summary"]["total_gram_panchayats"],
            3,
        )

    @patch(
        "services.data_drivers.aggregator_driver.classify_device_type",
        return_value="ONT",
    )
    def test_non_district_scope_does_not_include_location_summary(self, _classify):
        result = aggregate_status(
            entity_type="MANDAL",
            entity_name="SANGAREDDY",
            scope="MANDAL",
            devices=self.devices,
        )

        self.assertNotIn("location_summary", result)

    def test_empty_district_has_zero_location_counts(self):
        result = aggregate_status(
            entity_type="DISTRICT",
            entity_name="SANGAREDDY",
            scope="DISTRICT",
            devices=[],
        )

        self.assertEqual(
            result["location_summary"],
            {"total_mandals": 0, "total_gram_panchayats": 0},
        )

    @patch(
        "services.data_drivers.aggregator_driver.classify_device_type",
        return_value="ONT",
    )
    @patch("services.status_engine.count_affected_services", return_value=0)
    @patch(
        "services.status_engine.fetch_devices_for_resolved_scope",
        return_value=(
            [
                {
                    "DISTRICT": "SANGAREDDY",
                    "BLOCK": "SANGAREDDY",
                    "GPNAME": "GP One",
                    "SystemDown": "UP",
                },
                {
                    "DISTRICT": "SANGAREDDY",
                    "BLOCK": "PATANCHERU",
                    "GPNAME": "GP Two",
                    "SystemDown": "DOWN",
                },
            ],
            "STATUS_API_DISTRICT",
        ),
    )
    @patch("services.status_engine.get_devices_for_scope", return_value=[])
    @patch(
        "services.status_engine.resolve_entity",
        return_value={
            "status": "resolved",
            "entity_type": "DISTRICT",
            "entity_name": "SANGAREDDY",
            "lookup_type": "NAME",
            "confidence": 1.0,
            "scope_level": "DISTRICT",
            "context": {},
        },
    )
    @patch(
        "services.status_engine.parse_status_query",
        return_value=SimpleNamespace(
            intent_type="STATUS",
            entity_type="DISTRICT",
            entity_name="SANGAREDDY",
        ),
    )
    def test_status_engine_returns_location_summary_in_final_response(
        self,
        _parse,
        _resolve,
        _graph_devices,
        _monitoring_devices,
        _affected_services,
        _classify,
    ):
        # This covers the complete orchestration path without making network or
        # Neo4j calls, and verifies that compression does not drop the counts.
        response = get_status("status of sangareddy district")

        self.assertTrue(response["success"])
        self.assertEqual(response["raw_device_count"], 2)
        self.assertEqual(
            response["data"]["location_summary"],
            {"total_mandals": 2, "total_gram_panchayats": 2},
        )


if __name__ == "__main__":
    unittest.main()
