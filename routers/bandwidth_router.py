import json
import os

import httpx
from fastapi import APIRouter

from cache.status_cache import status_data
from models.request_models import BandwidthRequest

router = APIRouter()

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
 
 
@router.post("/bandwidth")
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
