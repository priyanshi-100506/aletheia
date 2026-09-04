from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.services.database import Base

class CodeDocument(Base):
    __tablename__ = "code_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_path: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(String(50), default="source_code") # 'source_code' or 'runbook'
    
    # 768-dimensional vector embedding for Gemini Text Embeddings
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
