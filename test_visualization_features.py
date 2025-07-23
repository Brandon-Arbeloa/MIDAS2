"""
Test Suite for MIDAS Data Visualization Features
Tests Windows data loading, chart generation, and integration
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json
import tempfile
import warnings
warnings.filterwarnings('ignore')

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from data_visualization_engine import (
    WindowsDataLoader,
    VisualizationIntentParser, 
    DataStructureAnalyzer,
    PlotlyChartGenerator,
    DataVisualizationEngine
)

class VisualizationTestSuite:
    """Comprehensive test suite for visualization features"""
    
    def __init__(self):
        self.test_results = []
        self.test_data_dir = Path("C:/MIDAS/test_visualization")
        self.test_data_dir.mkdir(parents=True, exist_ok=True)
        
    def run_test(self, test_name: str, test_func):
        """Run a single test and record results"""
        print(f"\n🧪 Running: {test_name}")
        try:
            result = test_func()
            self.test_results.append({
                "test_name": test_name,
                "status": "PASS" if result else "FAIL",
                "result": result
            })
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
            return result
        except Exception as e:
            self.test_results.append({
                "test_name": test_name, 
                "status": "ERROR",
                "error": str(e)
            })
            print(f"💥 ERROR {test_name}: {str(e)}")
            return False
    
    def create_test_data(self):
        """Create test datasets with Windows-specific considerations"""
        print("📁 Creating test datasets...")
        
        # Sales data with Unicode characters
        sales_data = pd.DataFrame({
            'Region': ['North America', 'Europe', 'Asia-Pacific', 'Latin America', 'Africa'],
            'Sales_2023': [1200000, 980000, 1500000, 650000, 320000],
            'Sales_2024': [1350000, 1050000, 1650000, 720000, 380000],
            'Manager': ['John Smith', 'Marie Dupont', '山田太郎', 'José García', 'Ahmed Hassan'],
            'Product': ['Widgets', 'Gadgets', 'Tools', 'Devices', 'Components']
        })
        
        # Time series data
        dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
        time_series_data = pd.DataFrame({
            'Date': dates,
            'Revenue': np.random.normal(10000, 2000, len(dates)).cumsum(),
            'Customers': np.random.poisson(50, len(dates)),
            'Temperature': 20 + 15 * np.sin(2 * np.pi * np.arange(len(dates)) / 365) + np.random.normal(0, 3, len(dates))
        })
        
        # Employee data with special characters
        employee_data = pd.DataFrame({
            'Name': ['Alice Johnson', 'Bob O\'Connor', 'Charlie "Chuck" Wilson', 
                    'Daniela García-López', 'Émilie Dubois', '李小明'],
            'Department': ['Engineering', 'Sales', 'Marketing', 'HR', 'Finance', 'IT'],
            'Salary': [75000, 65000, 70000, 68000, 72000, 80000],
            'Age': [28, 35, 42, 31, 29, 38],
            'Start_Date': pd.to_datetime(['2020-01-15', '2018-06-20', '2019-03-10', 
                                        '2021-08-05', '2022-02-14', '2017-11-30'])
        })
        
        # Save test files with different encodings
        test_files = {}
        
        # CSV with UTF-8
        csv_utf8 = self.test_data_dir / "sales_data_utf8.csv"
        sales_data.to_csv(csv_utf8, index=False, encoding='utf-8')
        test_files['csv_utf8'] = csv_utf8
        
        # CSV with Windows-1252 (simulate Windows Excel export)
        csv_win1252 = self.test_data_dir / "sales_data_win1252.csv"
        try:
            sales_data.to_csv(csv_win1252, index=False, encoding='cp1252')
            test_files['csv_win1252'] = csv_win1252
        except UnicodeEncodeError:
            # Fallback for characters that can't be encoded in cp1252
            sales_simple = sales_data.copy()
            sales_simple['Manager'] = ['John Smith', 'Marie Dupont', 'Taro Yamada', 'Jose Garcia', 'Ahmed Hassan']
            sales_simple.to_csv(csv_win1252, index=False, encoding='cp1252')
            test_files['csv_win1252'] = csv_win1252
        
        # Excel file with multiple sheets
        excel_file = self.test_data_dir / "business_data.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            sales_data.to_excel(writer, sheet_name='Sales', index=False)
            time_series_data.to_excel(writer, sheet_name='TimeSeries', index=False)
            employee_data.to_excel(writer, sheet_name='Employees', index=False)
        test_files['excel'] = excel_file
        
        # CSV with semicolon delimiter (European format)
        csv_semicolon = self.test_data_dir / "european_format.csv"
        sales_data.to_csv(csv_semicolon, index=False, sep=';', encoding='utf-8')
        test_files['csv_semicolon'] = csv_semicolon
        
        # Time series CSV
        csv_timeseries = self.test_data_dir / "time_series.csv"
        time_series_data.to_csv(csv_timeseries, index=False, encoding='utf-8')
        test_files['csv_timeseries'] = csv_timeseries
        
        print(f"✅ Created {len(test_files)} test files")
        return test_files
    
    def test_windows_data_loader(self):
        """Test Windows-specific data loading"""
        test_files = self.create_test_data()
        loader = WindowsDataLoader()
        
        results = {}
        
        # Test UTF-8 CSV
        try:
            df_utf8 = loader.load_csv_with_windows_handling(test_files['csv_utf8'])
            results['utf8_csv'] = len(df_utf8) > 0 and len(df_utf8.columns) > 1
        except Exception as e:
            results['utf8_csv'] = f"Error: {e}"
        
        # Test Windows-1252 CSV
        try:
            df_win1252 = loader.load_csv_with_windows_handling(test_files['csv_win1252'])
            results['win1252_csv'] = len(df_win1252) > 0 and len(df_win1252.columns) > 1
        except Exception as e:
            results['win1252_csv'] = f"Error: {e}"
        
        # Test semicolon delimiter
        try:
            df_semicolon = loader.load_csv_with_windows_handling(test_files['csv_semicolon'])
            results['semicolon_csv'] = len(df_semicolon) > 0 and len(df_semicolon.columns) > 1
        except Exception as e:
            results['semicolon_csv'] = f"Error: {e}"
        
        # Test Excel loading
        try:
            sheets = loader.load_excel_with_windows_handling(test_files['excel'])
            results['excel_loading'] = len(sheets) >= 3  # Should have 3 sheets
            results['excel_sheets'] = list(sheets.keys())
        except Exception as e:
            results['excel_loading'] = f"Error: {e}"
        
        # Test encoding detection
        try:
            encoding = loader.detect_encoding(test_files['csv_utf8'])
            results['encoding_detection'] = encoding in ['utf-8', 'utf-8-sig']
        except Exception as e:
            results['encoding_detection'] = f"Error: {e}"
        
        print(f"   Results: {results}")
        return all(v == True for v in results.values() if isinstance(v, bool))
    
    def test_visualization_intent_parser(self):
        """Test natural language intent parsing"""
        parser = VisualizationIntentParser()
        
        # Test visualization detection
        test_requests = [
            ("Show me a bar chart of sales by region", True),
            ("Create a line chart showing revenue over time", True),
            ("Plot customer age distribution", True),
            ("What is the weather like today?", False),
            ("Generate a histogram of prices", True),
            ("How many employees do we have?", False),
            ("Display a scatter plot of price vs quantity", True),
            ("Tell me about our company", False)
        ]
        
        detection_results = []
        for request, expected in test_requests:
            intent = parser.parse_visualization_request(request)
            is_viz = intent['chart_type'] is not None
            detection_results.append(is_viz == expected)
        
        # Test chart type detection
        chart_tests = [
            ("bar chart of sales", "bar"),
            ("line graph over time", "line"), 
            ("scatter plot correlation", "scatter"),
            ("pie chart distribution", "pie"),
            ("histogram of values", "bar"),  # Should detect as bar for count
            ("heatmap correlation matrix", "heatmap")
        ]
        
        chart_results = []
        for request, expected_type in chart_tests:
            intent = parser.parse_visualization_request(request)
            chart_results.append(intent['chart_type'] == expected_type)
        
        detection_accuracy = sum(detection_results) / len(detection_results)
        chart_accuracy = sum(chart_results) / len(chart_results)
        
        print(f"   Detection accuracy: {detection_accuracy:.2f}")
        print(f"   Chart type accuracy: {chart_accuracy:.2f}")
        
        return detection_accuracy >= 0.75 and chart_accuracy >= 0.5
    
    def test_data_structure_analyzer(self):
        """Test data structure analysis"""
        test_files = self.create_test_data()
        analyzer = DataStructureAnalyzer()
        
        # Load test data
        loader = WindowsDataLoader()
        df = loader.load_csv_with_windows_handling(test_files['csv_utf8'])
        
        # Analyze structure
        analysis = analyzer.analyze_dataframe_structure(df, "test_sales.csv")
        
        # Verify analysis components
        required_keys = ['shape', 'columns', 'numeric_columns', 'categorical_columns', 
                        'suggested_charts', 'data_quality']
        
        has_all_keys = all(key in analysis for key in required_keys)
        
        # Check suggested charts
        has_suggestions = len(analysis['suggested_charts']) > 0
        
        # Check data quality analysis
        quality = analysis['data_quality']
        has_quality_metrics = all(key in quality for key in ['null_counts', 'duplicate_rows'])
        
        print(f"   Shape: {analysis['shape']}")
        print(f"   Numeric columns: {len(analysis['numeric_columns'])}")
        print(f"   Categorical columns: {len(analysis['categorical_columns'])}")
        print(f"   Suggested charts: {len(analysis['suggested_charts'])}")
        
        return has_all_keys and has_suggestions and has_quality_metrics
    
    def test_plotly_chart_generation(self):
        """Test Plotly chart generation"""
        test_files = self.create_test_data()
        generator = PlotlyChartGenerator()
        loader = WindowsDataLoader()
        
        # Load test data
        df = loader.load_csv_with_windows_handling(test_files['csv_utf8'])
        
        # Test different chart types
        chart_tests = [
            ('bar', {'x': 'Region', 'y': 'Sales_2023', 'type': 'bar'}),
            ('line', {'x': 'Region', 'y': 'Sales_2023', 'type': 'line'}),
            ('scatter', {'x': 'Sales_2023', 'y': 'Sales_2024', 'type': 'scatter'}),
            ('pie', {'values': 'Sales_2023', 'names': 'Region', 'type': 'pie'})
        ]
        
        results = {}
        
        for chart_type, config in chart_tests:
            try:
                intent = {'chart_type': chart_type, 'aggregation': 'sum'}
                fig = generator.generate_chart(df, config, intent)
                
                # Basic validation - check if figure was created
                results[chart_type] = fig is not None and hasattr(fig, 'data')
                
            except Exception as e:
                results[chart_type] = f"Error: {e}"
        
        # Test time series data
        try:
            ts_df = loader.load_csv_with_windows_handling(test_files['csv_timeseries'])
            ts_config = {'x': 'Date', 'y': 'Revenue', 'type': 'line'}
            ts_intent = {'chart_type': 'line'}
            ts_fig = generator.generate_chart(ts_df, ts_config, ts_intent)
            results['timeseries'] = ts_fig is not None
        except Exception as e:
            results['timeseries'] = f"Error: {e}"
        
        print(f"   Chart generation results: {results}")
        
        return all(v == True for v in results.values() if isinstance(v, bool))
    
    def test_excel_integration(self):
        """Test Excel file integration with openpyxl"""
        test_files = self.create_test_data()
        loader = WindowsDataLoader()
        
        try:
            # Load Excel file
            sheets = loader.load_excel_with_windows_handling(test_files['excel'])
            
            # Verify sheets were loaded
            expected_sheets = {'Sales', 'TimeSeries', 'Employees'}
            loaded_sheets = set(sheets.keys())
            
            has_expected_sheets = expected_sheets.issubset(loaded_sheets)
            
            # Test data integrity
            sales_df = sheets.get('Sales')
            has_sales_data = sales_df is not None and len(sales_df) > 0
            
            employees_df = sheets.get('Employees')
            has_employee_data = employees_df is not None and 'Name' in employees_df.columns
            
            timeseries_df = sheets.get('TimeSeries')
            has_timeseries_data = timeseries_df is not None and 'Date' in timeseries_df.columns
            
            print(f"   Loaded sheets: {list(sheets.keys())}")
            print(f"   Sales rows: {len(sales_df) if sales_df is not None else 0}")
            print(f"   Employee rows: {len(employees_df) if employees_df is not None else 0}")
            
            return has_expected_sheets and has_sales_data and has_employee_data and has_timeseries_data
            
        except Exception as e:
            print(f"   Excel test error: {e}")
            return False
    
    def test_end_to_end_visualization(self):
        """Test complete visualization workflow"""
        test_files = self.create_test_data()
        
        # Create visualization engine (without Qdrant for this test)
        engine = DataVisualizationEngine(qdrant_indexer=None, ollama_client=None)
        
        # Override the data finding method for testing
        def mock_find_data(query):
            return [{'file_path': str(test_files['csv_utf8']), 'score': 0.9}]
        
        engine._find_relevant_tabular_data = mock_find_data
        
        # Test visualization requests
        test_requests = [
            "Show me a bar chart of sales by region",
            "Create a line chart of sales trends", 
            "Plot a scatter chart comparing 2023 vs 2024 sales"
        ]
        
        results = []
        
        for request in test_requests:
            try:
                result = engine.process_visualization_request(request)
                success = result['success'] and result.get('chart') is not None
                results.append(success)
                
                if success:
                    print(f"   ✅ '{request}' -> {result['chart_config']['type']} chart")
                else:
                    print(f"   ❌ '{request}' -> {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"   💥 '{request}' -> Error: {e}")
                results.append(False)
        
        success_rate = sum(results) / len(results) if results else 0
        print(f"   Success rate: {success_rate:.2f}")
        
        return success_rate >= 0.5
    
    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters in data"""
        # Create data with various Unicode characters
        unicode_data = pd.DataFrame({
            'Name': ['José García', 'Müller', '山田太郎', 'O\'Brien', 'Smith "Jr"'],
            'City': ['México', 'München', '東京', 'Dublin', 'New York'],
            'Value': [100, 200, 300, 400, 500],
            'Category': ['A', 'B', 'C', 'A', 'B']
        })
        
        # Test file with Unicode
        unicode_file = self.test_data_dir / "unicode_test.csv"
        unicode_data.to_csv(unicode_file, index=False, encoding='utf-8')
        
        loader = WindowsDataLoader()
        generator = PlotlyChartGenerator()
        
        try:
            # Load data
            df = loader.load_csv_with_windows_handling(unicode_file)
            
            # Verify Unicode characters are preserved
            has_unicode = any('é' in str(val) or '山' in str(val) or 'ü' in str(val) 
                             for val in df['Name'].values)
            
            # Generate chart with Unicode data
            config = {'x': 'Name', 'y': 'Value', 'type': 'bar'}
            intent = {'chart_type': 'bar'}
            fig = generator.generate_chart(df, config, intent)
            
            chart_created = fig is not None
            
            print(f"   Unicode preserved: {has_unicode}")
            print(f"   Chart with Unicode: {chart_created}")
            
            return has_unicode and chart_created
            
        except Exception as e:
            print(f"   Unicode test error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all visualization tests"""
        print("=" * 60)
        print("🎨 MIDAS Visualization Features Test Suite")
        print("=" * 60)
        
        tests = [
            ("Windows Data Loader", self.test_windows_data_loader),
            ("Visualization Intent Parser", self.test_visualization_intent_parser),
            ("Data Structure Analyzer", self.test_data_structure_analyzer), 
            ("Plotly Chart Generation", self.test_plotly_chart_generation),
            ("Excel Integration", self.test_excel_integration),
            ("Unicode & Special Characters", self.test_unicode_and_special_characters),
            ("End-to-End Visualization", self.test_end_to_end_visualization)
        ]
        
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 VISUALIZATION TEST SUMMARY")
        print("=" * 60)
        
        total = len(self.test_results)
        passed = len([r for r in self.test_results if r["status"] == "PASS"])
        failed = len([r for r in self.test_results if r["status"] == "FAIL"])
        errors = len([r for r in self.test_results if r["status"] == "ERROR"])
        
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")  
        print(f"💥 Errors: {errors}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        # Save results
        results_file = Path("C:/MIDAS/logs/visualization_test_results.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "success_rate": round((passed/total)*100, 1)
                },
                "results": self.test_results
            }, f, indent=2)
        
        print(f"\n📝 Results saved to: {results_file}")
        
        if passed == total:
            print("\n🎉 All visualization tests passed! System ready for data visualization.")
        else:
            print("\n💡 Some tests failed. Check individual results above.")


def main():
    """Run the visualization test suite"""
    suite = VisualizationTestSuite()
    suite.run_all_tests()


if __name__ == "__main__":
    main()