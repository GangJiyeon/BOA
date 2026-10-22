"""Uncalibrated FDC2112 telemetry, deliberately separate from skin scores."""
from datetime import datetime
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class MoistureMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[1] = 1
    source: Literal["ble_sensor", "ble_simulation", "mock"]
    status: Literal["valid", "sensor_error", "not_ready"]
    raw_value: int | None = Field(default=None, strict=True, ge=0, le=4095)
    unit: Literal["fdc2112_count"] = "fdc2112_count"
    sequence: int = Field(strict=True, ge=0, le=65535)
    device_uptime_ms: int = Field(strict=True, ge=0, le=4294967295)
    received_at: AwareDatetime

    @model_validator(mode="after")
    def valid_raw(self):
        if (self.status == "valid") != (self.raw_value is not None):
            raise ValueError("valid requires raw_value; error/not_ready requires null")
        return self


class MoistureSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: int | None = Field(default=None, strict=True, gt=0)
    measurement: MoistureMeasurement


class MoistureReceipt(MoistureSubmission):
    server_received_at: datetime
    calibration_status: Literal["uncalibrated"] = "uncalibrated"
    persisted: Literal[False] = False
    used_for_scoring: Literal[False] = False
