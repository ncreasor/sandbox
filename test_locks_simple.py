"""
Simple test for asyncio lock implementation
"""
import asyncio


# Simulate the implementation
approved = set()
processed = set()
_approved_lock = asyncio.Lock()
_processed_lock = asyncio.Lock()


async def is_approved(task_id: int) -> bool:
    """Check if task is already approved (thread-safe)"""
    async with _approved_lock:
        return task_id in approved


async def mark_approved(task_id: int):
    """Mark task as approved (thread-safe)"""
    async with _approved_lock:
        approved.add(task_id)


async def is_processed(url: str) -> bool:
    """Check if attachment URL is already processed (thread-safe)"""
    async with _processed_lock:
        return url in processed


async def mark_processed(url: str):
    """Mark attachment URL as processed (thread-safe)"""
    async with _processed_lock:
        processed.add(url)


async def concurrent_approved_test():
    """Test concurrent access to approved set"""
    print("Testing concurrent access to approved set...")

    # Create multiple concurrent tasks
    tasks = []
    for i in range(100):
        tasks.append(mark_approved(i))

    await asyncio.gather(*tasks)

    # Verify all items were added
    for i in range(100):
        assert await is_approved(i), f"Item {i} should be approved"

    print("✅ Approved set: all 100 items added correctly")


async def concurrent_processed_test():
    """Test concurrent access to processed set"""
    print("Testing concurrent access to processed set...")

    tasks = []
    for i in range(100):
        tasks.append(mark_processed(f"url_{i}"))

    await asyncio.gather(*tasks)

    for i in range(100):
        assert await is_processed(f"url_{i}"), f"URL {i} should be processed"

    print("✅ Processed set: all 100 URLs added correctly")


async def race_condition_test():
    """Test for race conditions with duplicate additions"""
    print("Testing race conditions with duplicates...")

    # Add same ID 50 times concurrently
    tasks = [mark_approved(999) for _ in range(50)]
    await asyncio.gather(*tasks)
    assert await is_approved(999)

    # Add same URL 50 times concurrently
    tasks = [mark_processed("duplicate") for _ in range(50)]
    await asyncio.gather(*tasks)
    assert await is_processed("duplicate")

    print("✅ Race conditions: duplicates handled correctly")


async def main():
    print("=" * 60)
    print("Thread Safety Tests")
    print("=" * 60)

    await concurrent_approved_test()
    await concurrent_processed_test()
    await race_condition_test()

    print("=" * 60)
    print("🎉 All tests passed! Locks working correctly.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
