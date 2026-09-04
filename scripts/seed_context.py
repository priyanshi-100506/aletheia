import asyncio
from app.services.database import AsyncSessionLocal, init_db
from app.services.rag import ingest_document

SAMPLE_BUGGY_CODE = """
# payment_service/worker.py

def calculate_transaction_fee(amount: float, discount_tier: int) -> float:
    # BUG: Can cause ZeroDivisionError if discount_tier is 0
    fee_rate = 0.05
    discount_factor = discount_tier / discount_tier  # ZeroDivisionError risk
    return amount * fee_rate * discount_factor
"""

async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        await ingest_document(
            db=db,
            file_path="payment_service/worker.py",
            content=SAMPLE_BUGGY_CODE,
            doc_type="source_code"
        )
        print("Successfully seeded sample buggy file into pgvector!")

if __name__ == "__main__":
    asyncio.run(seed())
