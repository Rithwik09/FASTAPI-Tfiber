"""
topology_data.py
Loads the Topology Master Excel at startup and builds one pre-joined dataframe.
All routers import the singleton `topo` — no repeated file I/O.
"""

import logging
import threading
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

EXCEL_PATH = Path(__file__).with_name("Topology Master_updated.xlsx")

# Columns to keep from OLT2Router (avoids duplicate OLT IP Address column)
OLT2ROUTER_COLS = [
    "OLT Hostname", "PKG", "OLT ETH Port",
    "GP Router Hostname", "GP Router IP Address", "GP Router Interface",
    "Mandal Router Hostname", "Mandal Router IP address",
    "Mandal Router Interface", "Capacity", "AdminStatus",
]


class TopologyData:
    def __init__(self):
        # Raw sheets — kept for direct queries if needed
        self.nodes: pd.DataFrame = pd.DataFrame()
        self.location: pd.DataFrame = pd.DataFrame()
        self.ont2olt: pd.DataFrame = pd.DataFrame()
        self.olt2router: pd.DataFrame = pd.DataFrame()
        self.service: pd.DataFrame = pd.DataFrame()
        self.child2parent: pd.DataFrame = pd.DataFrame()

        # Main pre-joined table (Nodes + Location + ONT2OLT + OLT2Router)
        self.merged: pd.DataFrame = pd.DataFrame()

        # Fast device identity lookups used to enrich Status API records.
        self.node_type_by_serial: dict[str, str] = {}
        self.node_type_by_ip: dict[str, str] = {}
        self.node_type_by_hostname: dict[str, str] = {}

        self._loaded = False
        self._load_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(self, excel_path: Path = EXCEL_PATH) -> None:
        logger.info("Loading topology data from %s …", excel_path)
        xl = pd.read_excel(excel_path, sheet_name=None)

        self.nodes = self._prep_nodes(xl["Nodes"])
        self.location = self._prep_location(xl["Location"])
        self.ont2olt = self._prep_ont2olt(xl["ONT2OLT"])
        self.olt2router = xl["OLT2Router"].copy()
        self.service = xl["Service"].copy()
        self.child2parent = xl["Child2Parent"].copy()

        self._build_device_indexes()
        self.merged = self._build_merged()
        self._loaded = True
        logger.info("Topology loaded — %d devices in merged table", len(self.merged))

    def ensure_loaded(self) -> None:
        """Load the workbook once, including when used outside FastAPI startup."""
        if self._loaded:
            return

        with self._load_lock:
            if not self._loaded:
                self.load()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def resolve_device_type(self, device: dict) -> str | None:
        """Resolve a Status API record to its authoritative topology node type."""
        self.ensure_loaded()

        api_type = _normalize_identifier(
            device.get("ConfigurationItemType")
            or device.get("ConfigurationItemSubType")
        )
        serial = _normalize_identifier(
            device.get("SerialNumber")
            or device.get("serial_number")
            or device.get("serial")
        )
        ip_address = _normalize_identifier(
            device.get("IPAddress")
            or device.get("ip_address")
            or device.get("ip")
        )
        hostname = _normalize_identifier(
            device.get("hostname")
            or device.get("Hostname")
            or device.get("DisplayName")
            or device.get("LOGICAL_NAME")
        )

        # ONT IP addresses are not reliable inventory join keys. Serial number is.
        if api_type in {"ONT", "ONT DEVICE"}:
            return self.node_type_by_serial.get(serial)

        # OLT Device records also represent routers in the monitoring inventory.
        if api_type in {"OLT", "OLT DEVICE", "DEVICE"}:
            return (
                self.node_type_by_ip.get(ip_address)
                or self.node_type_by_hostname.get(hostname)
            )

        return (
            self.node_type_by_serial.get(serial)
            or self.node_type_by_ip.get(ip_address)
            or self.node_type_by_hostname.get(hostname)
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prep_nodes(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ONT LGD"] = df["ONT LGD"].astype(str).str.strip()
        df["Serial No"] = df["Serial No"].astype(str).str.strip()
        return df

    @staticmethod
    def _prep_location(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["LGD Code"] = df["LGD Code"].astype(str).str.strip()
        return df

    @staticmethod
    def _prep_ont2olt(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ONT Serial Number"] = df["ONT Serial Number"].astype(str).str.strip()
        return df

    def _build_merged(self) -> pd.DataFrame:
        """
        Join chain:
          Nodes  →  Location   (ONT LGD == LGD Code)
                 →  ONT2OLT    (Serial No == ONT Serial Number)
                 →  OLT2Router (OLT HostName == OLT Hostname)
        All left-joins so every device row is preserved.
        """
        # Step 1: Nodes + Location
        step1 = self.nodes.merge(
            self.location.drop(columns=["Sl.No"], errors="ignore"),
            left_on="ONT LGD",
            right_on="LGD Code",
            how="left",
        )

        # Step 2: + ONT2OLT
        step2 = step1.merge(
            self.ont2olt,
            left_on="Serial No",
            right_on="ONT Serial Number",
            how="left",
        )

        # Step 3: + OLT2Router (select subset to avoid column clashes)
        olt_sub = self.olt2router[OLT2ROUTER_COLS].copy()
        step3 = step2.merge(
            olt_sub,
            left_on="OLT HostName",
            right_on="OLT Hostname",
            how="left",
        )

        return step3

    def _build_device_indexes(self) -> None:
        self.node_type_by_serial = _build_unique_index(
            self.nodes,
            identifier_column="Serial No",
        )
        self.node_type_by_ip = _build_unique_index(
            self.nodes,
            identifier_column="IP Address",
        )
        self.node_type_by_hostname = _build_unique_index(
            self.nodes,
            identifier_column="Host Name",
        )


INVALID_IDENTIFIERS = {
    "",
    "-",
    "0",
    "NA",
    "N/A",
    "NAN",
    "NONE",
    "NULL",
    "DATANA",
}


def _normalize_identifier(value) -> str:
    normalized = str(value or "").strip().upper()
    return "" if normalized in INVALID_IDENTIFIERS else normalized


def _build_unique_index(
    nodes: pd.DataFrame,
    identifier_column: str,
) -> dict[str, str]:
    """Index only identifiers that map unambiguously to one node type."""
    candidates: dict[str, set[str]] = {}

    for identifier, node_type in zip(
        nodes[identifier_column],
        nodes["Node Type"],
    ):
        key = _normalize_identifier(identifier)
        value = str(node_type or "").strip()
        if not key or not value or value.upper() == "NAN":
            continue
        candidates.setdefault(key, set()).add(value)

    return {
        identifier: next(iter(node_types))
        for identifier, node_types in candidates.items()
        if len(node_types) == 1
    }


# ── Singleton ──────────────────────────────────────────────────────────────
topo = TopologyData()
