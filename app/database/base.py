from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    type_annotation_map = {
        UUID: Uuid(as_uuid=True),
        datetime: DateTime(timezone=True),
    }
