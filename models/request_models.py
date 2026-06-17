from pydantic import BaseModel


class DeviceSearchRequest(
    BaseModel
):

    district: str | None = None

    system_down: str | None = None

    vendor: str | None = None

    olt: str | None = None

    ip_address: str | None = None

    lgd_code: str | None = None


class BandwidthRequest(BaseModel):
    date: str = ""
    granularity: str = "monthly"
    district: str = ""
    mandal: str = ""
    lgd_code: str = ""
    location: str = ""
    service_id: str = ""
