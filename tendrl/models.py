from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_serializer, field_validator


class Context(BaseModel):
    wait: Optional[bool] = None
    tags: Optional[List[str]] = None


class HeartbeatData(BaseModel):
    """Pydantic model for heartbeat message data validation"""
    mem_free: float = Field(..., ge=0, description="Available RAM in bytes (non-negative)")
    mem_total: float = Field(..., ge=0, description="Total RAM in bytes (non-negative)")
    disk_free: float = Field(..., ge=0, description="Available filesystem space in bytes (non-negative)")
    disk_size: float = Field(..., ge=0, description="Total filesystem size in bytes (non-negative)")


class HeartbeatMessage(BaseModel):
    """Pydantic model for heartbeat message validation"""
    msg_type: str = Field(default="heartbeat", description="Message type, must be 'heartbeat'")
    data: HeartbeatData = Field(..., description="System resource information")
    timestamp: Union[datetime, str] = Field(..., description="ISO8601 formatted timestamp in UTC with 'Z' suffix")
    
    @field_validator('msg_type')
    @classmethod
    def validate_msg_type(cls, v):
        if v != "heartbeat":
            raise ValueError("msg_type must be 'heartbeat'")
        return v
    
    @field_validator('timestamp', mode='before')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate timestamp is in ISO8601 format with Z suffix"""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                # Try to parse the timestamp
                parsed = datetime.fromisoformat(v.replace('Z', '+00:00'))
                if not v.endswith('Z'):
                    raise ValueError("Timestamp must end with 'Z' for UTC")
                return parsed
            except ValueError as e:
                raise ValueError(f"Invalid timestamp format: {e}")
        return v
    
    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime, _info):
        """Serialize datetime to ISO format string for JSON."""
        if isinstance(value, datetime):
            # Format as ISO8601 with Z suffix
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")
        return value
    
    def model_dump(self, **kwargs) -> dict:
        """Override to ensure timestamp is serialized as string for API compatibility."""
        data = super().model_dump(**kwargs)
        # Ensure timestamp is string for JSON serialization
        if isinstance(data.get('timestamp'), datetime):
            data['timestamp'] = data['timestamp'].strftime("%Y-%m-%dT%H:%M:%SZ")
        return data


class Message(BaseModel):
    msg_type: str
    data: Union[dict, str]
    context: Optional[Context] = None
    dest: Optional[str] = None
    timestamp: Union[datetime, str]

    @field_validator('timestamp', mode='before')
    @classmethod
    def parse_timestamp(cls, v):
        """Accept both datetime objects and ISO format strings."""
        if isinstance(v, str):
            # Try to parse ISO format string
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return v
        return v

    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime, _info):
        """Serialize datetime to ISO format string for JSON."""
        if isinstance(value, datetime):
            return value.isoformat(timespec='milliseconds')
        return value

    @field_validator('context', mode='before')
    @classmethod
    def parse_context(cls, v):
        """Convert dict context to Context model if needed."""
        if isinstance(v, dict):
            return Context(**v)
        return v

    def model_dump(self, **kwargs) -> dict:
        """Override to ensure timestamp is serialized as string for API compatibility."""
        data = super().model_dump(**kwargs)
        # Ensure timestamp is string for JSON serialization
        if isinstance(data.get('timestamp'), datetime):
            data['timestamp'] = data['timestamp'].isoformat(timespec='milliseconds')
        # Remove None values to match current behavior
        return {k: v for k, v in data.items() if v is not None}

    class Config:
        arbitrary_types_allowed = True

