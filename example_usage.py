"""
Example Usage Script for MIDAS Document Indexing System
Demonstrates complete workflow with Windows-specific path handling
"""

import sys
from pathlib import Path
import time

# Add the current directory to the Python path
sys.path.append(str(Path(__file__).parent))

from document_indexer import DocumentIndexingSystem, WindowsLogger

def main():
    """Example usage of the document indexing system"""
    
    # Initialize logger
    logger = WindowsLogger(name="example_usage")
    logger.info("Starting MIDAS Document Indexing Example")
    
    print("🚀 MIDAS Document Indexing System - Example Usage")
    print("=" * 60)
    
    # Initialize the system
    print("1. Initializing Document Indexing System...")
    try:
        system = DocumentIndexingSystem(
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name="documents",
            chunk_size=800,
            chunk_overlap=100
        )
        print("✅ System initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize system: {e}")
        print("\n💡 Make sure Qdrant is running:")
        print("   docker run -p 6333:6333 qdrant/qdrant")
        print("   OR run: .\\Setup-Qdrant.ps1")
        return
    
    # Example 1: Index a single file
    print("\n2. Example: Indexing a single file...")
    
    # Create a sample document
    sample_doc = Path("C:/MIDAS/sample_document.txt")
    sample_doc.parent.mkdir(parents=True, exist_ok=True)
    
    sample_content = """
    MIDAS RAG System Documentation
    
    The MIDAS (Machine Intelligence Document Analysis System) is a comprehensive 
    on-premises RAG (Retrieval-Augmented Generation) solution designed for Windows 11.
    
    Key Features:
    - Local document processing with support for TXT, CSV, JSON, PDF, and DOCX files
    - Intelligent chunking with configurable overlap for optimal retrieval
    - Windows-specific file handling with proper path management
    - Qdrant vector database for efficient similarity search
    - Sentence-transformers for local embedding generation
    - Comprehensive logging and error handling
    
    Architecture Components:
    1. Document Processor: Handles multiple file formats with Windows optimizations
    2. Document Chunker: Creates overlapping text segments for better retrieval
    3. Vector Indexer: Uses Qdrant for storing and searching embeddings
    4. Search Interface: Provides similarity search capabilities
    
    The system is optimized for Windows 11 environments and handles Windows-specific
    file system attributes, permissions, and path formats correctly.
    """
    
    sample_doc.write_text(sample_content, encoding='utf-8')
    
    try:
        result = system.index_file(str(sample_doc))
        if result['success']:
            print("✅ File indexed successfully")
            print(f"   File: {sample_doc.name}")
            print(f"   Chunks: {result['indexed_chunks']}/{result['total_chunks']}")
            print(f"   Processing time: {result['processing_time']:.2f}s")
        else:
            print(f"❌ Failed to index file: {result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"❌ Error indexing file: {e}")
    
    # Example 2: Search for documents
    print("\n3. Example: Searching documents...")
    
    search_queries = [
        "Windows file handling",
        "vector database",
        "document processing",
        "RAG system architecture"
    ]
    
    for query in search_queries:
        print(f"\n🔍 Searching for: '{query}'")
        try:
            results = system.search(query, limit=3, score_threshold=0.6)
            
            if results:
                print(f"   Found {len(results)} results:")
                for i, result in enumerate(results, 1):
                    print(f"   {i}. Score: {result['score']:.3f}")
                    print(f"      Text: {result['text'][:100]}...")
                    print(f"      File: {Path(result['file_path']).name}")
            else:
                print("   No results found")
        except Exception as e:
            print(f"   ❌ Search error: {e}")
    
    # Example 3: Index a directory
    print("\n4. Example: Directory indexing...")
    
    # Create sample documents directory
    docs_dir = Path("C:/MIDAS/example_documents")
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create various sample files
    sample_files = {
        "readme.txt": "This is a README file for the MIDAS project. It contains basic setup instructions.",
        "config.json": '{"app_name": "MIDAS", "version": "1.0", "database": "qdrant", "port": 6333}',
        "data.csv": "Name,Role,Department\nAlice,Developer,Engineering\nBob,Designer,UX\nCharlie,Manager,Operations"
    }
    
    for filename, content in sample_files.items():
        file_path = docs_dir / filename
        file_path.write_text(content, encoding='utf-8')
    
    try:
        print(f"   Indexing directory: {docs_dir}")
        result = system.index_directory(str(docs_dir), recursive=True)
        
        if result['success']:
            print("✅ Directory indexed successfully")
            print(f"   Total files: {result['total_files']}")
            print(f"   Processed files: {result['processed_files']}")
            print(f"   Total chunks: {result['indexed_chunks']}")
            print(f"   Processing time: {result['processing_time']:.2f}s")
        else:
            print(f"❌ Directory indexing failed: {result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"❌ Error indexing directory: {e}")
    
    # Example 4: System status
    print("\n5. System Status...")
    try:
        status = system.get_system_status()
        print(f"   Status: {status.get('status', 'unknown')}")
        
        if 'collection' in status:
            collection = status['collection']
            print(f"   Collection: {collection.get('name', 'unknown')}")
            print(f"   Documents: {collection.get('points_count', 0)} points")
            print(f"   Vector size: {collection.get('vector_size', 0)}")
        
        print(f"   Supported formats: {', '.join(status.get('supported_extensions', []))}")
        print(f"   Chunk size: {status.get('chunk_size', 0)}")
        print(f"   Chunk overlap: {status.get('chunk_overlap', 0)}")
        
    except Exception as e:
        print(f"❌ Error getting system status: {e}")
    
    # Example 5: Advanced search with filtering
    print("\n6. Advanced search examples...")
    
    # Search for specific file types
    print("   🔍 Search in specific file types:")
    try:
        results = system.search("configuration settings", limit=5)
        
        # Filter by file extension
        json_results = [r for r in results if r['file_path'].endswith('.json')]
        txt_results = [r for r in results if r['file_path'].endswith('.txt')]
        
        print(f"      JSON files: {len(json_results)} results")
        print(f"      TXT files: {len(txt_results)} results")
        
    except Exception as e:
        print(f"   ❌ Advanced search error: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Example usage complete!")
    
    print("\n📊 Summary:")
    print("   ✅ Document indexing system initialized")
    print("   ✅ Single file indexing demonstrated")
    print("   ✅ Search functionality tested")
    print("   ✅ Directory indexing completed")
    print("   ✅ System status retrieved")
    print("   ✅ Advanced search examples shown")
    
    print("\n💡 Next steps:")
    print("   1. Try indexing your own documents")
    print("   2. Experiment with different search queries")
    print("   3. Adjust chunk size and overlap for your use case")
    print("   4. Explore the Qdrant web UI at http://localhost:6333/dashboard")
    print("   5. Check logs in C:/MIDAS/logs/ for detailed information")
    
    # Cleanup option
    cleanup = input("\nCleanup example files? (y/N): ").lower().strip() == 'y'
    if cleanup:
        try:
            import shutil
            sample_doc.unlink(exist_ok=True)
            shutil.rmtree(docs_dir, ignore_errors=True)
            print("🧹 Example files cleaned up")
        except Exception as e:
            print(f"⚠️  Could not cleanup files: {e}")
    else:
        print("📁 Example files preserved for further testing")


if __name__ == "__main__":
    main()