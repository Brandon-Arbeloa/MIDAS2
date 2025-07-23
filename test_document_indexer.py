"""
Test and Example Script for Document Indexing System
Demonstrates usage with Windows-specific path handling and comprehensive testing
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime
import time

# Import the document indexing system
from document_indexer import (
    DocumentIndexingSystem,
    WindowsLogger,
    QdrantIndexer
)


def create_sample_documents(test_dir: Path) -> Dict[str, Path]:
    """Create sample documents for testing"""
    sample_files = {}
    
    # Create TXT file
    txt_content = """
    This is a sample text document for testing the MIDAS RAG system.
    It contains multiple paragraphs with different types of content.
    
    The system should be able to chunk this text intelligently.
    Each chunk will be processed and stored with proper metadata.
    
    Windows path handling is crucial for proper file processing.
    The system handles Windows-specific file attributes and permissions.
    
    This document serves as a comprehensive test case for text processing.
    The chunking algorithm will create overlapping segments for better retrieval.
    """
    
    txt_file = test_dir / "sample_document.txt"
    txt_file.write_text(txt_content, encoding='utf-8')
    sample_files['txt'] = txt_file
    
    # Create CSV file
    csv_content = """Name,Age,City,Occupation
John Doe,30,New York,Software Engineer
Jane Smith,25,Los Angeles,Data Scientist
Mike Johnson,35,Chicago,Product Manager
Sarah Wilson,28,Houston,UX Designer
David Brown,32,Phoenix,DevOps Engineer"""
    
    csv_file = test_dir / "sample_data.csv"
    csv_file.write_text(csv_content, encoding='utf-8')
    sample_files['csv'] = csv_file
    
    # Create JSON file
    json_data = {
        "company": "MIDAS Corp",
        "products": [
            {
                "name": "RAG System",
                "version": "1.0",
                "features": [
                    "Document Processing",
                    "Vector Search",
                    "Local LLM Integration"
                ],
                "supported_formats": ["txt", "csv", "json", "pdf", "docx"]
            }
        ],
        "deployment": {
            "platform": "Windows 11",
            "architecture": "on-premises",
            "storage": {
                "vector_db": "Qdrant",
                "metadata_db": "PostgreSQL",
                "cache": "Redis"
            }
        },
        "configuration": {
            "chunk_size": 800,
            "chunk_overlap": 100,
            "embedding_model": "all-MiniLM-L6-v2"
        }
    }
    
    json_file = test_dir / "sample_config.json"
    json_file.write_text(json.dumps(json_data, indent=2), encoding='utf-8')
    sample_files['json'] = json_file
    
    # Create additional test files
    large_txt_content = "This is a test sentence. " * 1000  # Large file for memory testing
    large_txt_file = test_dir / "large_document.txt"
    large_txt_file.write_text(large_txt_content, encoding='utf-8')
    sample_files['large_txt'] = large_txt_file
    
    return sample_files


def test_individual_components():
    """Test individual components of the system"""
    logger = WindowsLogger(name="component_test")
    logger.info("Starting component tests")
    
    print("=== Component Tests ===")
    
    # Test 1: Document Processor
    print("\n1. Testing Document Processor...")
    from document_indexer import DocumentProcessor
    
    processor = DocumentProcessor()
    
    # Create temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("Test content for document processor.\nThis is line 2.\nThis is line 3.")
        temp_file_path = Path(f.name)
    
    try:
        result = processor.process_document(temp_file_path)
        if result:
            print("✅ Document processor working")
            print(f"   Content length: {len(result['content'])}")
            print(f"   Metadata keys: {list(result['metadata'].keys())}")
        else:
            print("❌ Document processor failed")
    finally:
        temp_file_path.unlink(exist_ok=True)
    
    # Test 2: Document Chunker
    print("\n2. Testing Document Chunker...")
    from document_indexer import DocumentChunker
    
    chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)  # Small for testing
    test_text = "This is sentence one. This is sentence two. This is sentence three. This is sentence four."
    test_metadata = {'file_path': 'test.txt', 'file_name': 'test.txt'}
    
    chunks = chunker.chunk_text(test_text, test_metadata)
    if chunks:
        print("✅ Document chunker working")
        print(f"   Generated {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            print(f"   Chunk {i}: {chunk['text'][:50]}...")
    else:
        print("❌ Document chunker failed")
    
    # Test 3: Qdrant Connection (if available)
    print("\n3. Testing Qdrant Connection...")
    try:
        indexer = QdrantIndexer()
        info = indexer.get_collection_info()
        if info:
            print("✅ Qdrant connection working")
            print(f"   Collection: {info.get('name', 'unknown')}")
            print(f"   Points: {info.get('points_count', 0)}")
        else:
            print("❌ Could not get collection info")
    except Exception as e:
        print(f"⚠️  Qdrant not available: {e}")
    
    print("\n=== Component Tests Complete ===")


def test_file_processing(test_dir: Path, sample_files: Dict[str, Path]):
    """Test processing of different file types"""
    logger = WindowsLogger(name="file_processing_test")
    logger.info("Starting file processing tests")
    
    print("\n=== File Processing Tests ===")
    
    # Initialize the indexing system
    try:
        indexer = DocumentIndexingSystem(
            chunk_size=200,  # Smaller for testing
            chunk_overlap=50
        )
        
        # Test each file type
        for file_type, file_path in sample_files.items():
            print(f"\nTesting {file_type.upper()} file: {file_path.name}")
            
            try:
                result = indexer.index_file(str(file_path))
                
                if result['success']:
                    print(f"✅ {file_type.upper()} processing successful")
                    print(f"   Chunks: {result['indexed_chunks']}/{result['total_chunks']}")
                    print(f"   Time: {result['processing_time']:.2f}s")
                    print(f"   File size: {result['file_size']} bytes")
                else:
                    print(f"❌ {file_type.upper()} processing failed: {result.get('message', 'Unknown error')}")
            
            except Exception as e:
                print(f"❌ Error processing {file_type.upper()}: {e}")
        
        # Test search functionality
        print("\n=== Search Tests ===")
        test_queries = [
            "software engineer",
            "document processing",
            "Windows system",
            "chunk size configuration"
        ]
        
        for query in test_queries:
            print(f"\nSearching for: '{query}'")
            results = indexer.search(query, limit=3, score_threshold=0.5)
            
            if results:
                print(f"✅ Found {len(results)} results")
                for i, result in enumerate(results):
                    print(f"   {i+1}. Score: {result['score']:.3f} - {result['text'][:100]}...")
            else:
                print("❌ No results found")
        
        # Get system status
        print("\n=== System Status ===")
        status = indexer.get_system_status()
        print(f"Status: {status.get('status', 'unknown')}")
        if 'collection' in status:
            collection = status['collection']
            print(f"Collection points: {collection.get('points_count', 0)}")
            print(f"Vector dimension: {collection.get('vector_size', 0)}")
    
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        return
    
    print("\n=== File Processing Tests Complete ===")


def test_directory_indexing(test_dir: Path):
    """Test directory indexing functionality"""
    logger = WindowsLogger(name="directory_indexing_test")
    logger.info("Starting directory indexing tests")
    
    print("\n=== Directory Indexing Tests ===")
    
    try:
        indexer = DocumentIndexingSystem(chunk_size=300, chunk_overlap=75)
        
        print(f"Indexing directory: {test_dir}")
        
        # Test directory indexing
        result = indexer.index_directory(str(test_dir), recursive=True)
        
        if result['success']:
            print("✅ Directory indexing successful")
            print(f"   Total files: {result['total_files']}")
            print(f"   Processed files: {result['processed_files']}")
            print(f"   Failed files: {result['failed_files']}")
            print(f"   Total chunks indexed: {result['indexed_chunks']}")
            print(f"   Processing time: {result['processing_time']:.2f}s")
            
            if result['processed_files'] > 0:
                avg_chunks = result['indexed_chunks'] / result['processed_files']
                print(f"   Average chunks per file: {avg_chunks:.1f}")
            
            # Show file-by-file results
            print("\n📊 File-by-file results:")
            for file_result in result['file_results']:
                status = "✅" if file_result['success'] else "❌"
                file_name = Path(file_result['file_path']).name
                chunks = file_result.get('indexed_chunks', 0)
                total = file_result.get('total_chunks', 0)
                print(f"   {status} {file_name}: {chunks}/{total} chunks")
        
        else:
            print(f"❌ Directory indexing failed: {result.get('message', 'Unknown error')}")
    
    except Exception as e:
        print(f"❌ Directory indexing error: {e}")
    
    print("\n=== Directory Indexing Tests Complete ===")


def test_memory_management():
    """Test memory management with large files"""
    print("\n=== Memory Management Tests ===")
    
    # Create a large temporary file
    large_content = "This is a test sentence for memory management. " * 10000  # ~500KB
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(large_content)
        large_file_path = Path(f.name)
    
    try:
        # Test with different chunk sizes
        chunk_sizes = [500, 1000, 2000]
        
        for chunk_size in chunk_sizes:
            print(f"\nTesting with chunk size: {chunk_size}")
            
            try:
                indexer = DocumentIndexingSystem(
                    chunk_size=chunk_size,
                    chunk_overlap=100
                )
                
                start_time = time.time()
                result = indexer.index_file(str(large_file_path))
                end_time = time.time()
                
                if result['success']:
                    print(f"✅ Large file processed successfully")
                    print(f"   Chunks: {result['indexed_chunks']}")
                    print(f"   Time: {end_time - start_time:.2f}s")
                    print(f"   Chunks/second: {result['indexed_chunks'] / (end_time - start_time):.1f}")
                else:
                    print(f"❌ Large file processing failed: {result.get('message', 'Unknown error')}")
            
            except Exception as e:
                print(f"❌ Error with chunk size {chunk_size}: {e}")
    
    finally:
        large_file_path.unlink(exist_ok=True)
    
    print("\n=== Memory Management Tests Complete ===")


def test_windows_specific_features():
    """Test Windows-specific features"""
    print("\n=== Windows-Specific Feature Tests ===")
    
    # Test Windows path handling
    windows_paths = [
        r"C:\Users\TestUser\Documents\test.txt",
        r"\\server\share\document.pdf",
        r"C:\Program Files\App\config.json"
    ]
    
    print("\nTesting Windows path handling:")
    for path_str in windows_paths:
        try:
            path = Path(path_str)
            print(f"✅ Path parsed: {path}")
            print(f"   Resolved: {path.resolve()}")
            print(f"   Parts: {path.parts}")
        except Exception as e:
            print(f"❌ Path error for {path_str}: {e}")
    
    # Test file metadata extraction
    print("\nTesting file metadata extraction:")
    from document_indexer import WindowsFileHandler
    
    # Create a temporary file to test metadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("Test content for metadata")
        temp_path = Path(f.name)
    
    try:
        metadata = WindowsFileHandler.get_file_metadata(temp_path)
        if metadata and 'error' not in metadata:
            print("✅ File metadata extraction successful")
            print(f"   File path: {metadata.get('file_path', 'N/A')}")
            print(f"   File size: {metadata.get('file_size', 0)} bytes")
            print(f"   Created: {metadata.get('created_time', 'N/A')}")
            print(f"   Modified: {metadata.get('modified_time', 'N/A')}")
            print(f"   MIME type: {metadata.get('mime_type', 'N/A')}")
        else:
            print(f"❌ Metadata extraction failed: {metadata.get('error', 'Unknown error')}")
    finally:
        temp_path.unlink(exist_ok=True)
    
    # Test logging
    print("\nTesting Windows logging:")
    try:
        logger = WindowsLogger(name="windows_test")
        logger.info("Test info message")
        logger.warning("Test warning message")
        logger.error("Test error message")
        print("✅ Windows logging working")
        print(f"   Log directory: {logger.log_dir}")
    except Exception as e:
        print(f"❌ Logging error: {e}")
    
    print("\n=== Windows-Specific Feature Tests Complete ===")


def main():
    """Main test function"""
    print("🚀 MIDAS Document Indexing System - Comprehensive Test Suite")
    print("=" * 70)
    
    # Create test directory
    test_dir = Path("C:/MIDAS/test_documents")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Test directory: {test_dir}")
    
    try:
        # Create sample documents
        print("\n📄 Creating sample documents...")
        sample_files = create_sample_documents(test_dir)
        print(f"Created {len(sample_files)} sample files:")
        for file_type, file_path in sample_files.items():
            print(f"   {file_type}: {file_path.name}")
        
        # Run tests
        test_individual_components()
        test_file_processing(test_dir, sample_files)
        test_directory_indexing(test_dir)
        test_memory_management()
        test_windows_specific_features()
        
        print("\n" + "=" * 70)
        print("🎉 All tests completed!")
        print("\n💡 Next steps:")
        print("   1. Ensure Qdrant is running: docker run -p 6333:6333 qdrant/qdrant")
        print("   2. Run: python test_document_indexer.py")
        print("   3. Check logs in C:/MIDAS/logs/")
        print("   4. Test with your own documents")
        
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup test files (optional)
        cleanup = input("\nCleanup test files? (y/N): ").lower().strip() == 'y'
        if cleanup:
            try:
                import shutil
                shutil.rmtree(test_dir)
                print(f"🧹 Cleaned up test directory: {test_dir}")
            except Exception as e:
                print(f"⚠️  Could not cleanup test directory: {e}")
        else:
            print(f"📁 Test files preserved in: {test_dir}")


if __name__ == "__main__":
    main()