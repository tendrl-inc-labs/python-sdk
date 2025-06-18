from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class Message(BaseModel):
    msg_type: str
    data: dict | str
    context = Optional[dict]
    dest: Optional[str]
    timestamp: datetime

    class Config:
        arbitrary_types_allowed = True

class Context(BaseModel):
    wait: Optional[bool]
    tags: Optional[List[str]]

