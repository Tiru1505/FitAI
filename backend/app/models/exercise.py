from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[str] = mapped_column(String(16))
    muscle_group: Mapped[str] = mapped_column(String(80))
    # Any one of these satisfies the requirement; an empty list means bodyweight.
    equipment: Mapped[list[str]] = mapped_column(JSON, default=list)
    instructions: Mapped[list[str]] = mapped_column(JSON, default=list)
    form_cues: Mapped[list[str]] = mapped_column(JSON, default=list)
    substitutions: Mapped[list[str]] = mapped_column(JSON, default=list)
    safety_note: Mapped[str] = mapped_column(Text, default="")
