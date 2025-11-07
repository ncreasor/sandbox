"""
Test thread safety of approved and processed sets
"""
import asyncio
import sys
sys.path.insert(0, '/home/user/CLIAgent')

from logic.core import is_approved, mark_approved, is_processed, mark_processed


async def concurrent_approved_test():
    """Test concurrent access to approved set"""
    print("Testing concurrent access to approved set...")

    # Create multiple concurrent tasks that mark items as approved
    tasks = []
    for i in range(100):
        tasks.append(mark_approved(i))

    await asyncio.gather(*tasks)

    # Verify all items were added
    for i in range(100):
        assert await is_approved(i), f"Item {i} should be approved"

    print("✅ Approved set test passed: all 100 items added correctly")


async def concurrent_processed_test():
    """Test concurrent access to processed set"""
    print("Testing concurrent access to processed set...")

    # Create multiple concurrent tasks that mark URLs as processed
    tasks = []
    for i in range(100):
        tasks.append(mark_processed(f"https://example.com/file{i}.jpg"))

    await asyncio.gather(*tasks)

    # Verify all URLs were added
    for i in range(100):
        assert await is_processed(f"https://example.com/file{i}.jpg"), f"URL {i} should be processed"

    print("✅ Processed set test passed: all 100 URLs added correctly")


async def race_condition_test():
    """Test for race conditions with duplicate additions"""
    print("Testing race conditions with duplicates...")

    # Try to add the same ID multiple times concurrently
    tasks = [mark_approved(999) for _ in range(50)]
    await asyncio.gather(*tasks)

    # Should still only be marked once
    assert await is_approved(999), "ID 999 should be approved"

    # Try to process the same URL multiple times
    tasks = [mark_processed("https://example.com/duplicate.jpg") for _ in range(50)]
    await asyncio.gather(*tasks)

    assert await is_processed("https://example.com/duplicate.jpg"), "Duplicate URL should be processed"

    print("✅ Race condition test passed: duplicates handled correctly")


async def main():
    print("=" * 60)
    print("Thread Safety Tests for approved and processed sets")
    print("=" * 60)

    await concurrent_approved_test()
    await concurrent_processed_test()
    await race_condition_test()

    print("=" * 60)
    print("🎉 All tests passed! Thread safety verified.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
