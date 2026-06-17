"""
topology_router.py
All T-Fiber topology endpoints.
Mount this in main.py with:
    app.include_router(topology_router)
"""

import json
from pprint import pprint
from functools import wraps



import math
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from services.topology_data import topo

topology_router = APIRouter(prefix="/api/topology", tags=["Topology"])


# ── Helpers ───────────────────────────────────────────────────────────────

def _clean(val):
    """Convert NaN / float nan to None so FastAPI serialises to JSON null."""
    if val is None:
        return None
    try:
        if math.isnan(val):
            return None
    except TypeError:
        pass
    return val

def log_endpoint(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print("\n" + "=" * 80)
        print(f"ENDPOINT: {func.__name__}")
        print("-" * 80)

        if kwargs:
            print("REQUEST:")
            pprint(kwargs)

        try:
            response = func(*args, **kwargs)

            print("\nRESPONSE:")
            try:
                print(json.dumps(response, indent=2, default=str))
            except Exception:
                pprint(response)

            print("=" * 80)
            return response

        except Exception as e:
            print("\nERROR:")
            print(str(e))
            print("=" * 80)
            raise

    return wrapper


def _row_to_topology(r: pd.Series) -> dict:
    """Convert a merged-dataframe row into the standard topology response."""
    return {
        "lgd_code": _clean(r.get("ONT LGD")),
        "location": {
            "name":      _clean(r.get("Location Name")),
            "type":      _clean(r.get("Type of Location")),
            "district":  _clean(r.get("District")),
            "mandal":    _clean(r.get("Mandal")),
            "package":   _clean(r.get("Package ")),
            "latitude":  _clean(r.get("LATITUDE")),
            "longitude": _clean(r.get("LONGITUDE")),
        },
        "device": {
            "hostname":  _clean(r.get("Host Name")),
            "ip_address": _clean(r.get("IP Address")),
            "serial_no": _clean(r.get("Serial No")),
            "node_type": _clean(r.get("Node Type")),
            "vendor":    _clean(r.get("Vendor")),
            "model":     _clean(r.get("Model")),
        },
        "olt": {
            "hostname":     _clean(r.get("OLT HostName")),
            "ip_address":   _clean(r.get("OLT IP Address")),
            "ont_id":       _clean(r.get("Ont ID")),
            "eth_port":     _clean(r.get("OLT ETH Port")),
            "admin_status": _clean(r.get("AdminStatus")),
            "capacity":     _clean(r.get("Capacity")),
            "package":      _clean(r.get("PKG")),
        },
        "upstream": {
            "gp_router_hostname":  _clean(r.get("GP Router Hostname")),
            "gp_router_ip":        _clean(r.get("GP Router IP Address")),
            "gp_router_interface": _clean(r.get("GP Router Interface")),
            "mandal_router_hostname":  _clean(r.get("Mandal Router Hostname")),
            "mandal_router_ip":        _clean(r.get("Mandal Router IP address")),
            "mandal_router_interface": _clean(r.get("Mandal Router Interface")),
        },
    }


def _compact(r: pd.Series) -> dict:
    """Compact summary row for list responses."""
    return {
        "lgd_code":     _clean(r.get("ONT LGD")),
        "location_name": _clean(r.get("Location Name")),
        "district":     _clean(r.get("District")),
        "mandal":       _clean(r.get("Mandal")),
        "hostname":     _clean(r.get("Host Name")),
        "ip_address":   _clean(r.get("IP Address")),
        "serial_no":    _clean(r.get("Serial No")),
        "node_type":    _clean(r.get("Node Type")),
        "vendor":       _clean(r.get("Vendor")),
        "olt_hostname": _clean(r.get("OLT HostName")),
        "olt_status":   _clean(r.get("AdminStatus")),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────

@topology_router.get("/device/{lgd_code}")
@log_endpoint
def get_device_topology(lgd_code: str):

    print("\n========== CALLED ==========")
    print("lgd_code =", lgd_code)

    df = topo.merged
    match = df[df["ONT LGD"] == lgd_code.strip()]

    if match.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No device found with LGD code '{lgd_code}'"
        )

    return _row_to_topology(match.iloc[0])


@topology_router.get("/device/{lgd_code}/olt")
@log_endpoint
def get_device_olt(lgd_code: str):
    """
    Quick answer: what is the OLT of this device?
    Checks the node type first — only ONTs have an OLT parent.
    """
    df = topo.merged
    match = df[df["ONT LGD"] == lgd_code.strip()]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"LGD code '{lgd_code}' not found")

    r = match.iloc[0]
    node_type = _clean(r.get("Node Type"))

    if node_type != "ONT":
        return {
            "lgd_code":  lgd_code,
            "node_type": node_type,
            "is_ont":    False,
            "message":   f"Device is a {node_type}, not an ONT — no OLT parent.",
            "olt":       None,
        }

    olt_hostname = _clean(r.get("OLT HostName"))
    if not olt_hostname:
        return {
            "lgd_code":  lgd_code,
            "node_type": node_type,
            "is_ont":    True,
            "message":   "ONT found but OLT mapping not available in ONT2OLT sheet.",
            "olt":       None,
        }

    return {
        "lgd_code":  lgd_code,
        "node_type": node_type,
        "is_ont":    True,
        "message":   "ONT with OLT parent found.",
        "olt": {
            "hostname":     olt_hostname,
            "ip_address":   _clean(r.get("OLT IP Address")),
            "ont_id":       _clean(r.get("Ont ID")),
            "admin_status": _clean(r.get("AdminStatus")),
        },
    }


@topology_router.get("/devices/search")
@log_endpoint
def search_devices(
    lgd_code:    Optional[str] = Query(None, description="Partial or full LGD code"),
    district:    Optional[str] = Query(None, description="District name (case-insensitive)"),
    mandal:      Optional[str] = Query(None, description="Mandal name (case-insensitive)"),
    vendor:      Optional[str] = Query(None, description="Vendor name e.g. Tejas, Nokia"),
    node_type:   Optional[str] = Query(None, description="ONT, OLT, Router …"),
    olt_hostname:Optional[str] = Query(None, description="OLT hostname (partial match)"),
    ip_address:  Optional[str] = Query(None, description="Device IP (partial match)"),
    limit:       int           = Query(50, le=500, description="Max results"),
):
    """
    Search devices across all topology dimensions.
    All filters are optional and AND-combined.
    """
    df = topo.merged.copy()

    if lgd_code:
        df = df[df["ONT LGD"].str.contains(lgd_code.strip(), case=False, na=False)]
    if district:
        df = df[df["District"].str.contains(district.strip(), case=False, na=False)]
    if mandal:
        df = df[df["Mandal"].str.contains(mandal.strip(), case=False, na=False)]
    if vendor:
        df = df[df["Vendor"].str.contains(vendor.strip(), case=False, na=False)]
    if node_type:
        df = df[df["Node Type"].str.contains(node_type.strip(), case=False, na=False)]
    if olt_hostname:
        df = df[df["OLT HostName"].astype(str).str.contains(olt_hostname.strip(), case=False, na=False)]
    if ip_address:
        df = df[df["IP Address"].astype(str).str.contains(ip_address.strip(), case=False, na=False)]

    total = len(df)
    df = df.drop_duplicates(subset=["ONT LGD"]).head(limit)

    return {
        "total_matched": total,
        "returned":      len(df),
        "limit":         limit,
        "devices":       [_compact(r) for _, r in df.iterrows()],
    }


@topology_router.get("/olt/{olt_hostname}/devices")
@log_endpoint
def get_olt_devices(olt_hostname: str, limit: int = Query(100, le=500)):
    """
    List all ONT devices connected to a specific OLT.
    """
    df = topo.merged
    match = df[df["OLT HostName"].astype(str).str.contains(olt_hostname.strip(), case=False, na=False)]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"No devices found for OLT '{olt_hostname}'")

    match = match.drop_duplicates(subset=["ONT LGD"]).head(limit)
    return {
        "olt_hostname": olt_hostname,
        "device_count": len(match),
        "devices":      [_compact(r) for _, r in match.iterrows()],
    }


@topology_router.get("/district/{district_name}/summary")
@log_endpoint
def get_district_summary(district_name: str):
    """
    Device count breakdown for a district — up/down by node type.
    """
    df = topo.merged
    match = df[df["District"].str.contains(district_name.strip(), case=False, na=False)]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"District '{district_name}' not found")

    match = match.drop_duplicates(subset=["ONT LGD"])
    total = len(match)
    by_type = match["Node Type"].value_counts().to_dict()
    by_vendor = match["Vendor"].value_counts().to_dict()
    olt_up = match[match["AdminStatus"] == "Up"]["OLT HostName"].nunique()
    olt_down = match[match["AdminStatus"] != "Up"]["OLT HostName"].nunique()

    return {
        "district":     district_name.upper(),
        "total_devices": total,
        "by_node_type": by_type,
        "by_vendor":    by_vendor,
        "olts": {
            "up":   olt_up,
            "down": olt_down,
        },
    }


@topology_router.get("/health")
@log_endpoint
def topology_health():
    """Quick check that data is loaded."""
    return {
        "loaded":       topo._loaded,
        "total_devices": len(topo.merged),
        "total_onts":   int((topo.nodes["Node Type"] == "ONT").sum()),
        "total_olts":   int((topo.nodes["Node Type"] == "OLT").sum()),
    }
