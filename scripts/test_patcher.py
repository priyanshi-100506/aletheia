import asyncio
from app.db.database import AsyncSessionLocal
from app.services.patcher import generate_patch

async def main():
    sample_error = "ZeroDivisionError: float division by zero in calculate_transaction_fee at discount_tier / discount_tier"
    
    async with AsyncSessionLocal() as db:
        print("Analyzing error and generating patch with Gemini...")
        result = await generate_patch(db, error_log=sample_error)
        
        print("\n=== PATCH RESULT ===")
        print(f"File Path: {result.file_path}")
        print(f"Confidence: {result.confidence_score}")
        print(f"\nBug Summary:\n{result.bug_description}")
        print(f"\nExplanation:\n{result.explanation}")
        print(f"\nUnified Diff:\n{result.unified_diff}")

if __name__ == "__main__":
    asyncio.run(main())
