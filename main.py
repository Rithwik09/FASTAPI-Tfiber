import os

from dotenv import load_dotenv

load_dotenv()import asyncio

import httpx

from models.request_models import BandwidthRequest

from contextlib import asynccontextmanager
import json

from fastapi import FastAPI

from pprint import pprint

from services.topology_data import topo

from services.topology_router import topology_router

from cache.status_cache import status_data

from services.refresh_service import (
    refresh_cache
)

from services.filter_service import (
    filter_devices
)

from models.request_models import (
    DeviceSearchRequest
)


@asynccontextmanager
async def lifespan(app: FastAPI):
 
    await asyncio.get_event_loop().run_in_executor(None, topo.load)

    asyncio.create_task(
        refresh_cache()
    )

    yield


app = FastAPI(
    lifespan=lifespan
)

app.include_router(topology_router)


@app.get("/")
def home():

    return {
        "message": "TFiber Status API"
    }


@app.get("/summary")
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

@app.post("/device-search")
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

BANDWIDTH_API_BASE = os.getenv("BANDWIDTH_API_BASE")

BANDWIDTH_AUTH = (
    os.getenv("BANDWIDTH_USERNAME"),
    os.getenv("BANDWIDTH_PASSWORD")
)
 
def _process_bandwidth_raw(raw: dict, scope: str, granularity: str, date: str) -> dict:
    """
    The external API returns this shape:
    {
      "interval": "daily",
      "month": "2026-06",
      "unit": "Kbps",
      "record_count": 6000,
      "data": [
        {
          "location": "GI-GP-JALUGADDA-TANDA_280124",
          "service_id": "",
          "month": "2026-06",
          "total_entries": 10,
          "entries": [
            {"date": "2026-06-01", "rx_kbps": 0.027, "tx_kbps": 0.027, "total_kbps": 0.055},
            ...
          ],
          "grand_total": {"rx_kbps": 0.344, "tx_kbps": 0.349, "total_kbps": 0.693}
        },
        ...
      ]
    }
    We pre-process everything so the LLM just reads plain numbers.
    """
 
    data_list = raw.get("data", [])
    total_locations = len(data_list)
 
    if total_locations == 0:
        return {
            "scope": scope,
            "granularity": granularity,
            "date": date,
            "message": f"No bandwidth data found for {scope}.",
            "suggested_questions": [
                f"Show device status for {scope}",
                f"Try daily bandwidth for {scope}",
            ]
        }
 
    # ── Per-location totals ──────────────────────────────────────────────────
    location_totals = []
    for loc in data_list:
        gt = loc.get("grand_total", {})
        location_totals.append({
            "location": loc.get("location", "").strip(),
            "total_entries": loc.get("total_entries", 0),
            "rx_kbps": round(gt.get("rx_kbps", 0), 4),
            "tx_kbps": round(gt.get("tx_kbps", 0), 4),
            "total_kbps": round(gt.get("total_kbps", 0), 4),
        })
 
    # ── Active vs zero locations ─────────────────────────────────────────────
    active = [l for l in location_totals if l["total_kbps"] > 0]
    zero   = [l for l in location_totals if l["total_kbps"] == 0]
 
    active_count  = len(active)
    zero_count    = len(zero)
    active_pct    = round(active_count / total_locations * 100, 1) if total_locations else 0
 
    # ── Network-wide totals ──────────────────────────────────────────────────
    total_rx    = round(sum(l["rx_kbps"]    for l in location_totals), 4)
    total_tx    = round(sum(l["tx_kbps"]    for l in location_totals), 4)
    total_bw    = round(sum(l["total_kbps"] for l in location_totals), 4)
 
    avg_bw_per_active = (
        round(total_bw / active_count, 4) if active_count else 0
    )
 
    # ── Top 5 highest and lowest (active only) ───────────────────────────────
    sorted_active = sorted(active, key=lambda l: l["total_kbps"], reverse=True)
    top5    = sorted_active[:5]
    bottom5 = sorted_active[-5:] if len(sorted_active) >= 5 else sorted_active
 
    # ── For single location — show daily trend ───────────────────────────────
    daily_trend = []
    if total_locations == 1 and data_list:
        entries = data_list[0].get("entries", [])
        daily_trend = [
            {
                "date": e["date"],
                "rx_kbps": round(e.get("rx_kbps", 0), 4),
                "tx_kbps": round(e.get("tx_kbps", 0), 4),
                "total_kbps": round(e.get("total_kbps", 0), 4),
            }
            for e in entries
        ]
 
    # ── Suggested follow-ups ─────────────────────────────────────────────────
    other_gran = "daily" if granularity == "monthly" else "monthly"
    suggested_questions = [
        f"Show {other_gran} bandwidth for {scope}",
        f"Which locations have zero bandwidth in {scope}?",
        f"Show top consuming locations in {scope}",
    ]
 
    return {
        "scope": scope,
        "granularity": granularity,
        "date": date,
        "unit": raw.get("unit", "Kbps"),
 
        # ── Summary numbers — LLM reads these directly ──────────────────────
        "summary": {
            "total_locations":      total_locations,
            "active_locations":     active_count,
            "zero_traffic_locations": zero_count,
            "active_percent":       active_pct,
            "total_rx_kbps":        total_rx,
            "total_tx_kbps":        total_tx,
            "total_bandwidth_kbps": total_bw,
            "avg_bandwidth_per_active_location_kbps": avg_bw_per_active,
        },
 
        # ── Top / bottom — LLM presents these if asked ──────────────────────
        "top_5_locations_by_bandwidth":    top5,
        "bottom_5_locations_by_bandwidth": bottom5,
 
        # ── Only populated for single-location queries ───────────────────────
        "daily_trend": daily_trend,
 
        "suggested_questions": suggested_questions,
    }
 
 
@app.post("/bandwidth")
async def bandwidth(request: BandwidthRequest):
    print("\n========== BANDWIDTH ==========")
    print("granularity =", request.granularity)
    print("date        =", request.date)
    print("district    =", request.district)
    print("mandal      =", request.mandal)
    print("lgd_code    =", request.lgd_code)
    print("location    =", request.location)
    print("service_id  =", request.service_id)
 
    # ── Build scope label ────────────────────────────────────────────────────
    scope = (
        request.service_id or
        request.location or
        request.lgd_code or
        request.mandal or
        request.district or
        "overall"
    )
 
    # ── Build query params for external API ─────────────────────────────────
    params = {"date": request.date or "2026-05"}
 
    if request.service_id:
        params["service_id"] = request.service_id
    elif request.location:
        params["location"] = request.location
    elif request.lgd_code:
        # Resolve LGD → LOCATION string from device cache
        match = next(
            (d for d in status_data if str(d.get("LGDCode")) == str(request.lgd_code)),
            None
        )
        if match:
            params["location"] = match.get("LOCATION", "")
            scope = f"LGD {request.lgd_code} ({match.get('GPNAME', '')})"
            print(f"Resolved LGD {request.lgd_code} → {params['location']}")
        else:
            return {"error": True, "message": f"No device found for LGD code {request.lgd_code}"}
    elif request.mandal:
        params["location"] = request.mandal
    elif request.district:
        params["location"] = request.district
    # else: no location param → overall
 
    url = f"{BANDWIDTH_API_BASE}/{request.granularity}"
    print("Calling:", url, "| params:", params)
 
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, auth=BANDWIDTH_AUTH)
            resp.raise_for_status()
            raw = resp.json()
    except httpx.HTTPError as e:
        print("Bandwidth API error:", e)
        return {"error": True, "message": f"Bandwidth API unavailable: {str(e)}"}
 
    result = _process_bandwidth_raw(raw, scope, request.granularity, request.date or "2026-05")
 
    print("\n========== BANDWIDTH RESPONSE ==========")
    print(json.dumps(result, indent=2, default=str))
    return result
