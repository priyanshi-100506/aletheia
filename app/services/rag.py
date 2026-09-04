import logging
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.models.document import CodeDocument

logger = logging.getLogger("aletheia")
client = genai.Client(api_key=settings.GEMINI_API_KEY)

async def generate_embedding(text: str) -> list[float]:
    """
    Generates a 768-dimensional vector embedding using Google Gemini API.
    """
    response = await client.aio.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=768
        )
    )
    return response.embeddings[0].values

async def ingest_document(
    db: AsyncSession, 
    file_path: str, 
    content: str, 
    doc_type: str = "source_code"
) -> CodeDocument:
    """
    Embeds and stores a code file or runbook into pgvector.
    """
    embedding_vector = await generate_embedding(content)
    
    doc = CodeDocument(
        file_path=file_path,
        content=content,
        doc_type=doc_type,
        embedding=embedding_vector
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    logger.info(f"[RAG INGEST] Embedded & saved: {file_path}")
    return doc

async def query_relevant_context(
    db: AsyncSession, 
    error_query: str, 
    limit: int = 3
) -> list[CodeDocument]:
    """
    Performs vector cosine distance search against stored code snippets.
    """
    query_vector = await generate_embedding(error_query)
    
    stmt = (
        select(CodeDocument)
        .order_by(CodeDocument.embedding.cosine_distance(query_vector))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    return result.scalars().all()
