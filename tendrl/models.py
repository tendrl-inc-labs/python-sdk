from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, field_serializer, field_validator


class Context(BaseModel):
    wait: Optional[bool] = None
    tags: Optional[List[str]] = None


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

