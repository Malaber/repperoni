from datetime import datetime

from sqlalchemy import DateTime, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PasskeyCeremonyClaim(Base):
    __tablename__ = "passkey_ceremony_claims"

    challenge_digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
