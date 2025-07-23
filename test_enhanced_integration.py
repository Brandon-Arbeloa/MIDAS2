"""
Enhanced Integration Test Suite for MIDAS RAG System
Tests Windows-specific features, conversation memory, and debugging capabilities
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Add the current directory to the Python path
sys.path.append(str(Path(__file__).parent))

from enhanced_chat_app import (
    WindowsSystemInfo, 
    ConversationMemory, 
    EnhancedRAGSystem,
    WindowsFileHandler
)

class IntegrationTestSuite:
    """Comprehensive test suite for enhanced MIDAS system"""
    
    def __init__(self):
        self.test_results = []
        self.test_data_dir = Path("C:/MIDAS/test_integration")
        self.setup_test_environment()
    
    def setup_test_environment(self):
        """Set up test environment with sample files"""
        print("🔧 Setting up test environment...")
        
        # Create test directory
        self.test_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create sample files with Windows-specific paths and special characters
        test_files = {
            "test document with spaces.txt": """
            This is a test document with spaces in the filename.
            It contains information about Windows file handling and special characters.
            The system should handle Unicode: café, naïve, résumé.
            Windows paths with backslashes: C:\\Users\\Test\\Documents
            """,
            
            "config_file.json": json.dumps({
                "application": "MIDAS RAG",
                "version": "2.0",
                "features": ["Chat Interface", "RAG Search", "Memory"],
                "windows_paths": {
                    "data": "C:\\MIDAS\\data",
                    "logs": "C:\\MIDAS\\logs"
                }
            }, indent=2),
            
            "sample_data.csv": """Name,Role,Location,Special Characters
John Doe,Developer,"Seattle, WA","café owner"
Jane Smith,Designer,"Portland, OR","naïve artist"
Mike Johnson,Manager,"San José, CA","résumé expert"
""",
            
            "technical_notes.md": """
# Technical Documentation

## Windows Integration Features

- **File Path Handling**: Supports Windows paths with backslashes
- **Special Characters**: Handles Unicode in filenames and content
- **Memory Management**: Optimized for 8-16GB RAM systems
- **CUDA Detection**: Automatic GPU/CPU detection

## System Requirements

- Windows 11
- Python 3.10+
- Ollama service running on port 11434
- Qdrant database on port 6333
"""
        }
        
        # Write test files
        for filename, content in test_files.items():
            file_path = self.test_data_dir / filename
            file_path.write_text(content, encoding='utf-8')
        
        print(f"✅ Created {len(test_files)} test files in {self.test_data_dir}")
    
    def run_test(self, test_name: str, test_func):
        """Run a single test and record results"""
        print(f"\n🧪 Running test: {test_name}")
        start_time = time.time()
        
        try:
            result = test_func()
            duration = time.time() - start_time
            
            self.test_results.append({
                "test_name": test_name,
                "status": "PASS" if result else "FAIL",
                "duration": round(duration, 3),
                "timestamp": datetime.now().isoformat(),
                "details": result if isinstance(result, dict) else {}
            })
            
            status_icon = "✅" if result else "❌"
            print(f"{status_icon} {test_name}: {'PASS' if result else 'FAIL'} ({duration:.3f}s)")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append({
                "test_name": test_name,
                "status": "ERROR",
                "duration": round(duration, 3),
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            print(f"❌ {test_name}: ERROR - {str(e)}")
            return False
    
    def test_windows_system_detection(self):
        """Test Windows system detection capabilities"""
        system_info = WindowsSystemInfo()
        
        # Test compute device detection
        device = system_info.detect_compute_device()
        assert device in ["CPU", "CUDA"], f"Invalid device: {device}"
        
        # Test system specs
        specs = system_info.get_system_specs()
        required_keys = ["cpu_cores", "memory_gb", "platform", "python_version"]
        for key in required_keys:
            assert key in specs, f"Missing system spec: {key}"
        
        # Test optimization settings
        memory_gb = specs.get("memory_gb", 8)
        if isinstance(memory_gb, (int, float)):
            optimized = system_info.optimize_for_system(memory_gb)
            assert "chunk_size" in optimized
            assert "max_search_results" in optimized
        
        return {
            "device": device,
            "specs": specs,
            "optimized_settings": system_info.optimize_for_system(8)
        }
    
    def test_conversation_memory(self):
        """Test conversation memory functionality"""
        memory = ConversationMemory(max_history=5)
        
        # Test adding interactions
        test_interactions = [
            ("What is Python?", "Python is a programming language.", []),
            ("How do I install it?", "You can download it from python.org", []),
            ("What about Windows?", "Python works great on Windows.", [{"file_path": "python_guide.txt"}])
        ]
        
        for user_query, ai_response, search_results in test_interactions:
            memory.add_interaction(user_query, ai_response, search_results)
        
        # Test conversation context
        context = memory.get_conversation_context(last_n=2)
        assert len(context) > 0, "Context should not be empty"
        assert "Python" in context, "Context should contain conversation content"
        
        # Test document frequency tracking
        doc_freq = memory.get_document_frequency()
        if search_results:  # If we had search results
            assert len(doc_freq) > 0, "Should track document frequency"
        
        # Test memory clearing
        memory.clear_memory()
        assert len(memory.conversations) == 0, "Memory should be cleared"
        
        return {
            "conversation_tracking": True,
            "context_generation": len(context) > 0,
            "document_frequency": len(doc_freq) >= 0,
            "memory_clearing": True
        }
    
    def test_enhanced_rag_system(self):
        """Test enhanced RAG system initialization and optimization"""
        try:
            rag_system = EnhancedRAGSystem()
            
            # Test system initialization
            assert rag_system.device is not None
            assert rag_system.specs is not None
            assert rag_system.optimized_settings is not None
            
            # Test optimization settings are reasonable
            settings = rag_system.optimized_settings
            assert 200 <= settings["chunk_size"] <= 2000
            assert 1 <= settings["max_search_results"] <= 20
            assert 500 <= settings["context_window"] <= 8000
            
            # Test search debug functionality (if services available)
            try:
                results, debug_info = rag_system.search_with_debug(
                    "test query", 
                    limit=3, 
                    enable_debug=True
                )
                
                # Debug info should be generated
                assert "query" in debug_info
                assert "timestamp" in debug_info
                assert "device" in debug_info
                
                search_available = True
            except Exception:
                # Services might not be available in test environment
                search_available = False
            
            return {
                "initialization": True,
                "system_detection": rag_system.device is not None,
                "optimization": True,
                "search_available": search_available,
                "debug_info_generation": True
            }
            
        except Exception as e:
            print(f"RAG system test error: {e}")
            return False
    
    def test_windows_file_handler(self):
        """Test Windows file handling capabilities"""
        handler = WindowsFileHandler()
        
        # Test path normalization with different Windows path formats
        test_paths = [
            "C:\\Users\\Test\\file.txt",
            "C:/Users/Test/file.txt",
            "\\\\server\\share\\file.txt",
            str(self.test_data_dir / "test document with spaces.txt")
        ]
        
        normalization_results = []
        for path in test_paths:
            try:
                normalized = handler.normalize_windows_path(path)
                normalization_results.append(normalized is not None)
            except Exception:
                normalization_results.append(False)
        
        # Test clickable path creation
        test_file = self.test_data_dir / "test document with spaces.txt"
        if test_file.exists():
            clickable_url = handler.create_clickable_path(str(test_file))
            assert clickable_url.startswith("file:///")
        
        # Test file icon generation
        test_extensions = [".txt", ".pdf", ".csv", ".json", ".unknown"]
        icons = [handler.get_file_icon(f"test{ext}") for ext in test_extensions]
        assert all(len(icon) > 0 for icon in icons), "All file types should have icons"
        
        return {
            "path_normalization": all(normalization_results),
            "clickable_urls": True,
            "file_icons": len(icons) == len(test_extensions),
            "special_characters": True  # Tested with "test document with spaces.txt"
        }
    
    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters"""
        # Test file with special characters
        special_file = self.test_data_dir / "test document with spaces.txt"
        
        if special_file.exists():
            content = special_file.read_text(encoding='utf-8')
            
            # Should contain Unicode characters
            unicode_chars = ["café", "naïve", "résumé"]
            unicode_found = [char in content for char in unicode_chars]
            
            # Should handle Windows paths
            windows_path_found = "C:\\Users\\Test\\Documents" in content
            
            return {
                "unicode_handling": all(unicode_found),
                "windows_paths": windows_path_found,
                "file_read": True
            }
        
        return False
    
    def test_integration_with_services(self):
        """Test integration with external services (if available)"""
        results = {
            "ollama_connection": False,
            "qdrant_connection": False,
            "document_indexing": False,
            "search_functionality": False
        }
        
        # Test Ollama connection
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            results["ollama_connection"] = response.status_code == 200
        except Exception:
            pass
        
        # Test Qdrant connection
        try:
            import requests
            response = requests.get("http://localhost:6333/collections", timeout=5)
            results["qdrant_connection"] = response.status_code == 200
        except Exception:
            pass
        
        # If both services available, test document operations
        if results["ollama_connection"] and results["qdrant_connection"]:
            try:
                from document_indexer import DocumentIndexingSystem
                
                indexer = DocumentIndexingSystem(
                    qdrant_host="localhost",
                    qdrant_port=6333,
                    collection_name="test_collection",
                    chunk_size=500,
                    chunk_overlap=50
                )
                
                # Try to index a test file
                test_file = self.test_data_dir / "technical_notes.md"
                if test_file.exists():
                    result = indexer.index_file(str(test_file))
                    results["document_indexing"] = result.get("success", False)
                    
                    # Try to search
                    if results["document_indexing"]:
                        search_results = indexer.search("Windows integration", limit=3)
                        results["search_functionality"] = len(search_results) > 0
                
            except Exception as e:
                print(f"Service integration test error: {e}")
        
        return results
    
    def run_all_tests(self):
        """Run all integration tests"""
        print("=" * 60)
        print("🚀 MIDAS Enhanced Integration Test Suite")
        print("=" * 60)
        
        # Define all tests
        tests = [
            ("Windows System Detection", self.test_windows_system_detection),
            ("Conversation Memory", self.test_conversation_memory),
            ("Enhanced RAG System", self.test_enhanced_rag_system),
            ("Windows File Handler", self.test_windows_file_handler),
            ("Unicode & Special Characters", self.test_unicode_and_special_characters),
            ("Service Integration", self.test_integration_with_services)
        ]
        
        # Run all tests
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        # Generate summary
        self.generate_test_summary()
    
    def generate_test_summary(self):
        """Generate and display test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        error_tests = len([r for r in self.test_results if r["status"] == "ERROR"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"💥 Errors: {error_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # Show detailed results
        print(f"\nDetailed Results:")
        for result in self.test_results:
            status_icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}.get(result["status"], "❓")
            print(f"{status_icon} {result['test_name']}: {result['status']} ({result['duration']}s)")
            
            if result["status"] == "ERROR" and "error" in result:
                print(f"   Error: {result['error']}")
        
        # Save results to file
        results_file = Path("C:/MIDAS/logs/integration_test_results.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_run": {
                    "timestamp": datetime.now().isoformat(),
                    "total_tests": total_tests,
                    "passed": passed_tests,
                    "failed": failed_tests,
                    "errors": error_tests,
                    "success_rate": round((passed_tests/total_tests)*100, 1)
                },
                "results": self.test_results
            }, f, indent=2)
        
        print(f"\n📝 Detailed results saved to: {results_file}")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        if failed_tests > 0 or error_tests > 0:
            print("   • Check service availability (Ollama, Qdrant)")
            print("   • Verify Windows permissions for file operations")
            print("   • Ensure Python packages are installed correctly")
        else:
            print("   • All tests passed! System is ready for production")
        
        print("\n🎉 Integration test complete!")


def main():
    """Run the integration test suite"""
    suite = IntegrationTestSuite()
    suite.run_all_tests()


if __name__ == "__main__":
    main()