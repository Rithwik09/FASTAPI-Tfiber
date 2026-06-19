from fastapi import APIRouter
import json

from cache.status_cache import status_data
from services.filter_service import filter_devices
from services.status_engine import get_status
from models.request_models import DeviceSearchRequest
from models.status_models import StatusRequest

router = APIRouter()


@router.get("/")
def home():
    return {
        "message": "TFiber Status API"
    }


# ══════════════════════════════════════════════════════════════════════════════
# NEW: STATUS ENGINE ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/status")
def status(request: StatusRequest):
    """
    Unified status endpoint.
    
    Query examples:
      - {"query": "Status of Sangareddy District"}
      - {"query": "Status of Nagalgidda Mandal"}
      - {"query": "Status of OLT001"}
      - {"query": "Status of 10.10.20.3"}
      - {"query": "Status of LGD 278693"}
    
    Returns compressed JSON with scope-based aggregation.
    """
    return get_status(request.query)


@router.post("/status-engine")
def status_engine(request: StatusRequest):
    """Backward-compatible alias for /status."""
    return get_status(request.query)


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY: SUMMARY & DEVICE SEARCH (kept for backward compatibility)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/summary")
def summary():

    print("\n========== SUMMARY CALLED ==========")

    total = len(status_data)

    up = sum(
        1
        for d in status_data
        if d.get("SystemDown") == "UP"
    )

    down = sum(
        1
        for d in status_data
        if d.get("SystemDown") == "DOWN"
    )

    print(
        f"SUMMARY -> total={total}, up={up}, down={down}"
    )

    return {
           "total": total,
           "up": up,
           "down": down,
           "summary": f"There are {total} total systems. {up} systems are currently UP and {down} systems are currently DOWN."
    } 

@router.post("/device-search")
def device_search(request: DeviceSearchRequest):
    print("\n========== DEVICE SEARCH ==========")
    print("district     =", request.district)
    print("system_down  =", request.system_down)
    print("vendor       =", request.vendor)
    print("olt          =", request.olt)
    print("ip_address   =", request.ip_address)
    print("lgd_code     =", request.lgd_code)
 
    results = filter_devices(
        district=request.district,
        system_down=request.system_down,
        vendor=request.vendor,
        olt=request.olt,
        ip_address=request.ip_address,
        lgd_code=request.lgd_code
    )
 
    total = len(results)
    print(f"\nFOUND {total} DEVICES")
 
    # ── Health summary ──────────────────────────────────────────────────────
    down_count = sum(1 for d in results if d.get("SystemDown") == "DOWN")
    up_count   = total - down_count
    down_pct   = round((down_count / total * 100), 1) if total > 0 else 0
    up_pct     = round((up_count   / total * 100), 1) if total > 0 else 0
 
    # ── Breakdowns (top-5 each, sorted by count desc) ───────────────────────
    def top_counts(field, limit=5):
        from collections import Counter
        counts = Counter(d.get(field, "UNKNOWN") for d in results)
        return [{"name": k, "count": v} for k, v in counts.most_common(limit)]
 
    # ── Sample devices — only for single-device lookups (lgd_code / ip) ─────
    is_specific_lookup = bool(request.lgd_code or request.ip_address)
    sample_fields = [
        "LGDCode", "LOCATION", "DISTRICT", "BLOCK", "OLT",
        "VENDOR", "EMS_TYPE", "IPAddress", "SystemDown",
        "Status", "lastupdate", "networkname"
    ]
    sample_devices = (
        [{f: d.get(f) for f in sample_fields} for d in results[:5]]
        if is_specific_lookup
        else []
    )
 
    # ── Active filters (non-empty only) ────────────────────────────────────
    active_filters = {
        k: v for k, v in {
            "district":   request.district,
            "system_down": request.system_down,
            "vendor":     request.vendor,
            "olt":        request.olt,
            "ip_address": request.ip_address,
            "lgd_code":   request.lgd_code,
        }.items() if v
    }
 
    response = {
        # What was searched
        "search_context": {
            "filters_applied": active_filters,
            "is_specific_lookup": is_specific_lookup,
        },
 
        # Top-level counts — the bot can quote these directly
        "summary": {
            "total_devices": total,
            "devices_up":    up_count,
            "devices_down":  down_count,
            "down_percent":  down_pct,
            "up_percent":    up_pct,
            "health_status": (
                "critical"  if down_pct >= 50 else
                "degraded"  if down_pct >= 20 else
                "healthy"
            ),
        },
 
        # Breakdowns — useful for "what vendors / OLTs / blocks are affected?"
        "breakdowns": {
            "by_vendor":  top_counts("VENDOR"),
            "by_olt":     top_counts("OLT"),
            "by_block":   top_counts("BLOCK"),
            "by_ems":     top_counts("EMS_TYPE"),
            "by_dept":    top_counts("Department"),
        },
 
        # Only populated for specific single-device lookups
        "devices": sample_devices,
    }
 
    print("\n========== RESPONSE ==========")
    print(json.dumps(response, indent=2, default=str))
    return response
