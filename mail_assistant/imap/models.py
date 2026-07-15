from pydantic import BaseModel
from datetime import datetime

class EmailHeader(BaseModel):
    uid: str
    from_: str
    subject: str
    date: datetime
    message_id: str
    headers: dict
    flags: set[str]
