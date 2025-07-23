"""
Test script for MIDAS background processing system
Tests all components of the Celery-based task system
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from celery_config import app
from background_tasks.document_tasks import (
    process_document_file,
    process_document_batch,
    extract_document_metadata,
    cleanup_old_processed_files
)
from background_tasks.monitoring_tasks import (
    system_health_check,
    check_task_queue,
    generate_task_report
)

def test_redis_connection():
    """Test Redis connectivity"""
    print("\n1. Testing Redis Connection...")
    print("-" * 50)
    
    try:
        from redis import Redis
        redis_client = Redis.from_url(app.conf.broker_url)
        redis_client.ping()
        print("✅ Redis connection successful")
        
        # Get Redis info
        info = redis_client.info()
        print(f"   Redis version: {info.get('redis_version', 'unknown')}")
        print(f"   Connected clients: {info.get('connected_clients', 0)}")
        print(f"   Used memory: {info.get('used_memory_human', 'unknown')}")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_celery_workers():
    """Test Celery worker availability"""
    print("\n2. Testing Celery Workers...")
    print("-" * 50)
    
    try:
        inspector = app.control.inspect()
        active_workers = inspector.active()
        
        if active_workers:
            print(f"✅ Found {len(active_workers)} active worker(s)")
            for worker, tasks in active_workers.items():
                print(f"   Worker: {worker}")
                print(f"   Active tasks: {len(tasks)}")
        else:
            print("❌ No active workers found")
            print("   Run Start-Celery-Services.ps1 to start workers")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Worker inspection failed: {e}")
        return False

def test_document_processing():
    """Test document processing task"""
    print("\n3. Testing Document Processing...")
    print("-" * 50)
    
    # Create a test file
    test_dir = Path(__file__).parent / "test_documents"
    test_dir.mkdir(exist_ok=True)
    
    test_file = test_dir / f"test_document_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    test_content = """This is a test document for MIDAS background processing.
It contains some sample text to verify that the document processing system is working correctly.
The system should be able to extract this content and process it successfully."""
    
    test_file.write_text(test_content)
    print(f"Created test file: {test_file}")
    
    try:
        # Submit task
        result = process_document_file.delay(str(test_file))
        print(f"✅ Task submitted successfully")
        print(f"   Task ID: {result.id}")
        
        # Wait for result
        print("   Waiting for processing...")
        task_result = result.get(timeout=30)
        
        if task_result['status'] == 'completed':
            print("✅ Document processed successfully")
            print(f"   Chunks created: {task_result.get('chunks_created', 0)}")
            print(f"   Processing time: {task_result.get('processing_time', 0):.2f} seconds")
        else:
            print(f"❌ Processing failed: {task_result.get('errors', [])}")
            return False
        
        # Test metadata extraction
        print("\n   Testing metadata extraction...")
        meta_result = extract_document_metadata.delay(str(test_file))
        metadata = meta_result.get(timeout=10)
        print("✅ Metadata extracted successfully")
        print(f"   File size: {metadata.get('file_size', 0)} bytes")
        print(f"   File type: {metadata.get('file_type', 'unknown')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Document processing failed: {e}")
        return False
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()

def test_batch_processing():
    """Test batch document processing"""
    print("\n4. Testing Batch Processing...")
    print("-" * 50)
    
    # Create multiple test files
    test_dir = Path(__file__).parent / "test_documents"
    test_dir.mkdir(exist_ok=True)
    
    test_files = []
    for i in range(3):
        test_file = test_dir / f"batch_test_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        test_file.write_text(f"This is batch test document {i}")
        test_files.append(str(test_file))
    
    print(f"Created {len(test_files)} test files")
    
    try:
        # Submit batch task
        result = process_document_batch.delay(test_files)
        print("✅ Batch task submitted successfully")
        print(f"   Task ID: {result.id}")
        
        # Wait for result
        print("   Processing batch...")
        batch_result = result.get(timeout=60)
        
        print(f"✅ Batch processing completed")
        print(f"   Total files: {batch_result.get('total', 0)}")
        print(f"   Completed: {batch_result.get('completed', 0)}")
        print(f"   Failed: {batch_result.get('failed', 0)}")
        
        return batch_result.get('failed', 1) == 0
        
    except Exception as e:
        print(f"❌ Batch processing failed: {e}")
        return False
    finally:
        # Cleanup
        for file_path in test_files:
            try:
                Path(file_path).unlink()
            except:
                pass

def test_monitoring_tasks():
    """Test monitoring tasks"""
    print("\n5. Testing Monitoring Tasks...")
    print("-" * 50)
    
    try:
        # Test health check
        print("   Running system health check...")
        health_result = system_health_check.delay()
        health_data = health_result.get(timeout=15)
        
        print(f"✅ Health check completed")
        print(f"   Status: {health_data.get('status', 'unknown')}")
        print(f"   CPU usage: {health_data.get('checks', {}).get('cpu', {}).get('usage_percent', 0)}%")
        print(f"   Memory usage: {health_data.get('checks', {}).get('memory', {}).get('used_percent', 0)}%")
        
        # Test task queue check
        print("\n   Checking task queue...")
        queue_result = check_task_queue.delay()
        queue_data = queue_result.get(timeout=10)
        
        print("✅ Task queue check completed")
        
        # Test report generation
        print("\n   Generating task report...")
        report_result = generate_task_report.delay(period_hours=1)
        report_data = report_result.get(timeout=30)
        
        print("✅ Task report generated")
        print(f"   Total tasks: {report_data.get('summary', {}).get('total_tasks', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Monitoring task failed: {e}")
        return False

def test_cleanup_tasks():
    """Test cleanup tasks"""
    print("\n6. Testing Cleanup Tasks...")
    print("-" * 50)
    
    try:
        result = cleanup_old_processed_files.delay(days=30)
        cleanup_data = result.get(timeout=20)
        
        print("✅ Cleanup task completed")
        print(f"   Deleted files: {cleanup_data.get('deleted_files', 0)}")
        print(f"   Freed space: {cleanup_data.get('freed_space_mb', 0):.2f} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ Cleanup task failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 70)
    print("MIDAS Background Processing System Test")
    print("=" * 70)
    
    # Track test results
    tests_passed = 0
    tests_total = 6
    
    # Run tests
    if test_redis_connection():
        tests_passed += 1
    
    if test_celery_workers():
        tests_passed += 1
        
        # Only run task tests if workers are available
        if test_document_processing():
            tests_passed += 1
        
        if test_batch_processing():
            tests_passed += 1
        
        if test_monitoring_tasks():
            tests_passed += 1
        
        if test_cleanup_tasks():
            tests_passed += 1
    else:
        print("\nSkipping task tests - no workers available")
        tests_total = 2
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests passed: {tests_passed}/{tests_total}")
    
    if tests_passed == tests_total:
        print("\n✅ All tests passed! Background processing system is working correctly.")
    else:
        print(f"\n❌ {tests_total - tests_passed} test(s) failed.")
        print("\nTroubleshooting:")
        print("1. Ensure Redis is running: Start-Service Redis")
        print("2. Start Celery services: .\\Start-Celery-Services.ps1")
        print("3. Check logs in the 'logs' directory")

if __name__ == "__main__":
    main()