"""
MIDAS Data Visualization Engine
Intelligent chart generation for Windows RAG system using Plotly and local LLM analysis
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.figure_factory as ff
from plotly.subplots import make_subplots
import numpy as np
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import chardet
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from structured_data_indexer import MultiCollectionQdrantIndexer

class WindowsDataLoader:
    """Handles Windows-specific data loading with encoding detection"""
    
    @staticmethod
    def detect_encoding(file_path: Path) -> str:
        """Detect file encoding using chardet for Windows compatibility"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Sample first 10KB
                result = chardet.detect(raw_data)
                encoding = result.get('encoding', 'utf-8')
                confidence = result.get('confidence', 0.0)
                
                # Fallback to common Windows encodings if confidence is low
                if confidence < 0.7:
                    for fallback in ['utf-8', 'cp1252', 'iso-8859-1']:
                        try:
                            with open(file_path, 'r', encoding=fallback) as test_file:
                                test_file.read(1000)
                            return fallback
                        except UnicodeDecodeError:
                            continue
                
                return encoding or 'utf-8'
        except Exception:
            return 'utf-8'
    
    @staticmethod
    def load_csv_with_windows_handling(file_path: Path) -> pd.DataFrame:
        """Load CSV with Windows-specific handling"""
        encoding = WindowsDataLoader.detect_encoding(file_path)
        
        # Try different CSV dialects common on Windows
        dialects_to_try = [
            {'sep': ',', 'encoding': encoding},
            {'sep': ';', 'encoding': encoding},  # European CSV format
            {'sep': '\t', 'encoding': encoding},  # Tab-separated
            {'sep': ',', 'encoding': 'utf-8-sig'},  # UTF-8 with BOM
            {'sep': ',', 'encoding': 'cp1252'},  # Windows-1252
        ]
        
        for dialect in dialects_to_try:
            try:
                df = pd.read_csv(file_path, **dialect)
                if len(df.columns) > 1:  # Valid CSV should have multiple columns
                    return df
            except Exception:
                continue
        
        raise ValueError(f"Could not parse CSV file: {file_path}")
    
    @staticmethod
    def load_excel_with_windows_handling(file_path: Path) -> Dict[str, pd.DataFrame]:
        """Load Excel files with proper Windows Office integration"""
        try:
            # Read all sheets
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')
            sheets = {}
            
            for sheet_name in excel_file.sheet_names:
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')
                    # Skip empty sheets
                    if not df.empty and len(df.columns) > 0:
                        sheets[sheet_name] = df
                except Exception as e:
                    print(f"Warning: Could not read sheet '{sheet_name}': {e}")
                    continue
            
            return sheets
        except Exception as e:
            raise ValueError(f"Could not read Excel file: {file_path}. Error: {e}")

class VisualizationIntentParser:
    """Parses natural language requests to understand visualization intent"""
    
    def __init__(self):
        # Chart type keywords mapping
        self.chart_keywords = {
            'bar': ['bar chart', 'bar graph', 'column chart', 'histogram', 'count', 'frequency'],
            'line': ['line chart', 'line graph', 'trend', 'time series', 'over time', 'timeline'],
            'scatter': ['scatter plot', 'scatter chart', 'correlation', 'relationship', 'versus', 'vs'],
            'pie': ['pie chart', 'pie graph', 'proportion', 'percentage', 'share', 'distribution'],
            'heatmap': ['heatmap', 'heat map', 'correlation matrix', 'intensity', 'density'],
            'box': ['box plot', 'box chart', 'quartiles', 'outliers', 'distribution'],
            'violin': ['violin plot', 'distribution shape', 'density plot'],
            'area': ['area chart', 'area graph', 'filled line', 'stacked area']
        }
        
        # Aggregation keywords
        self.aggregation_keywords = {
            'sum': ['total', 'sum', 'add up', 'aggregate'],
            'mean': ['average', 'mean', 'avg'],
            'count': ['count', 'number of', 'how many'],
            'max': ['maximum', 'max', 'highest', 'largest'],
            'min': ['minimum', 'min', 'lowest', 'smallest'],
            'median': ['median', 'middle value']
        }
        
        # Grouping keywords
        self.grouping_keywords = ['by', 'group by', 'per', 'for each', 'broken down by']
    
    def parse_visualization_request(self, request: str) -> Dict[str, Any]:
        """Parse natural language visualization request"""
        request_lower = request.lower()
        
        # Detect chart type
        chart_type = self._detect_chart_type(request_lower)
        
        # Detect aggregation
        aggregation = self._detect_aggregation(request_lower)
        
        # Extract column names (simplified - looks for capitalized words or quoted strings)
        columns = self._extract_potential_columns(request)
        
        # Detect grouping
        grouping = self._detect_grouping(request_lower)
        
        # Extract filters
        filters = self._extract_filters(request_lower)
        
        return {
            'chart_type': chart_type,
            'aggregation': aggregation,
            'columns': columns,
            'grouping': grouping,
            'filters': filters,
            'original_request': request
        }
    
    def _detect_chart_type(self, request: str) -> str:
        """Detect the intended chart type from request"""
        scores = {}
        
        for chart_type, keywords in self.chart_keywords.items():
            score = sum(1 for keyword in keywords if keyword in request)
            if score > 0:
                scores[chart_type] = score
        
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        
        # Default chart type based on common patterns
        if any(word in request for word in ['over time', 'trend', 'timeline']):
            return 'line'
        elif any(word in request for word in ['vs', 'versus', 'relationship']):
            return 'scatter'
        elif any(word in request for word in ['count', 'frequency', 'how many']):
            return 'bar'
        else:
            return 'bar'  # Default
    
    def _detect_aggregation(self, request: str) -> str:
        """Detect aggregation function"""
        for agg_func, keywords in self.aggregation_keywords.items():
            if any(keyword in request for keyword in keywords):
                return agg_func
        return 'count'  # Default
    
    def _extract_potential_columns(self, request: str) -> List[str]:
        """Extract potential column names from request"""
        # Look for quoted strings
        quoted_matches = re.findall(r'"([^"]*)"', request)
        quoted_matches.extend(re.findall(r"'([^']*)'", request))
        
        # Look for capitalized words (potential column names)
        capitalized_matches = re.findall(r'\b[A-Z][a-zA-Z_]+\b', request)
        
        return quoted_matches + capitalized_matches
    
    def _detect_grouping(self, request: str) -> Optional[str]:
        """Detect if grouping is requested"""
        for keyword in self.grouping_keywords:
            if keyword in request:
                # Try to find what comes after the grouping keyword
                pattern = keyword + r'\s+(\w+)'
                match = re.search(pattern, request)
                if match:
                    return match.group(1)
        return None
    
    def _extract_filters(self, request: str) -> Dict[str, Any]:
        """Extract potential filters from request"""
        filters = {}
        
        # Look for "where" clauses
        where_pattern = r'where\s+(\w+)\s*(=|>|<|>=|<=)\s*([^\s]+)'
        matches = re.findall(where_pattern, request)
        
        for column, operator, value in matches:
            filters[column] = {'operator': operator, 'value': value}
        
        return filters

class DataStructureAnalyzer:
    """Analyzes data structure using local LLM to suggest appropriate visualizations"""
    
    def __init__(self, ollama_client=None):
        self.ollama_client = ollama_client
    
    def analyze_dataframe_structure(self, df: pd.DataFrame, file_name: str = "data") -> Dict[str, Any]:
        """Analyze DataFrame structure and suggest visualizations"""
        analysis = {
            'file_name': file_name,
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': df.dtypes.to_dict(),
            'numeric_columns': [],
            'categorical_columns': [],
            'datetime_columns': [],
            'suggested_charts': [],
            'data_quality': {}
        }
        
        # Analyze column types
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                analysis['numeric_columns'].append(col)
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                analysis['datetime_columns'].append(col)
            else:
                analysis['categorical_columns'].append(col)
        
        # Data quality analysis
        analysis['data_quality'] = {
            'null_counts': df.isnull().sum().to_dict(),
            'duplicate_rows': df.duplicated().sum(),
            'memory_usage': df.memory_usage(deep=True).sum()
        }
        
        # Suggest appropriate charts
        analysis['suggested_charts'] = self._suggest_charts(analysis)
        
        # Use LLM for additional insights if available
        if self.ollama_client:
            llm_insights = self._get_llm_insights(analysis)
            analysis['llm_insights'] = llm_insights
        
        return analysis
    
    def _suggest_charts(self, analysis: Dict) -> List[Dict]:
        """Suggest appropriate chart types based on data structure"""
        suggestions = []
        
        numeric_cols = analysis['numeric_columns']
        categorical_cols = analysis['categorical_columns']
        datetime_cols = analysis['datetime_columns']
        
        # Time series charts
        if datetime_cols and numeric_cols:
            for date_col in datetime_cols:
                for num_col in numeric_cols:
                    suggestions.append({
                        'type': 'line',
                        'x': date_col,
                        'y': num_col,
                        'title': f'{num_col} over {date_col}',
                        'priority': 'high'
                    })
        
        # Correlation analysis for numeric columns
        if len(numeric_cols) >= 2:
            suggestions.append({
                'type': 'heatmap',
                'data': 'correlation_matrix',
                'title': 'Correlation Matrix',
                'priority': 'medium'
            })
            
            # Scatter plots for pairs of numeric columns
            for i, col1 in enumerate(numeric_cols):
                for col2 in numeric_cols[i+1:]:
                    suggestions.append({
                        'type': 'scatter',
                        'x': col1,
                        'y': col2,
                        'title': f'{col1} vs {col2}',
                        'priority': 'medium'
                    })
        
        # Distribution charts
        for col in numeric_cols:
            suggestions.append({
                'type': 'histogram',
                'x': col,
                'title': f'Distribution of {col}',
                'priority': 'low'
            })
        
        # Category analysis
        if categorical_cols and numeric_cols:
            for cat_col in categorical_cols:
                for num_col in numeric_cols:
                    suggestions.append({
                        'type': 'bar',
                        'x': cat_col,
                        'y': num_col,
                        'title': f'{num_col} by {cat_col}',
                        'priority': 'high'
                    })
        
        # Count charts for categorical data
        for col in categorical_cols:
            suggestions.append({
                'type': 'bar',
                'x': col,
                'y': 'count',
                'title': f'Count of {col}',
                'priority': 'medium'
            })
        
        return suggestions
    
    def _get_llm_insights(self, analysis: Dict) -> str:
        """Get LLM insights about the data structure"""
        if not self.ollama_client:
            return "LLM analysis not available"
        
        prompt = f"""
        Analyze this dataset structure and provide insights for visualization:
        
        Dataset: {analysis['file_name']}
        Shape: {analysis['shape'][0]} rows, {analysis['shape'][1]} columns
        Numeric columns: {analysis['numeric_columns']}
        Categorical columns: {analysis['categorical_columns']}
        DateTime columns: {analysis['datetime_columns']}
        
        Provide:
        1. Key insights about the data
        2. Most interesting visualization opportunities
        3. Potential data quality issues to watch for
        4. Recommended chart types and why
        
        Keep response concise and actionable.
        """
        
        try:
            response = self.ollama_client.chat(
                model="llama3.2:3b",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.get('message', {}).get('content', 'No insights available')
        except Exception as e:
            return f"LLM analysis error: {str(e)}"

class PlotlyChartGenerator:
    """Generates interactive Plotly charts with Windows-compatible rendering"""
    
    def __init__(self):
        self.color_schemes = {
            'default': px.colors.qualitative.Set1,
            'professional': px.colors.qualitative.Set2,
            'vibrant': px.colors.qualitative.Vivid,
            'pastel': px.colors.qualitative.Pastel
        }
    
    def generate_chart(self, df: pd.DataFrame, chart_config: Dict, intent: Dict) -> go.Figure:
        """Generate Plotly chart based on configuration and intent"""
        chart_type = chart_config.get('type', intent.get('chart_type', 'bar'))
        
        # Apply filters if specified
        filtered_df = self._apply_filters(df, intent.get('filters', {}))
        
        # Generate chart based on type
        if chart_type == 'bar':
            return self._create_bar_chart(filtered_df, chart_config, intent)
        elif chart_type == 'line':
            return self._create_line_chart(filtered_df, chart_config, intent)
        elif chart_type == 'scatter':
            return self._create_scatter_chart(filtered_df, chart_config, intent)
        elif chart_type == 'pie':
            return self._create_pie_chart(filtered_df, chart_config, intent)
        elif chart_type == 'heatmap':
            return self._create_heatmap(filtered_df, chart_config, intent)
        elif chart_type == 'histogram':
            return self._create_histogram(filtered_df, chart_config, intent)
        elif chart_type == 'box':
            return self._create_box_plot(filtered_df, chart_config, intent)
        else:
            return self._create_bar_chart(filtered_df, chart_config, intent)
    
    def _apply_filters(self, df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
        """Apply filters to DataFrame"""
        filtered_df = df.copy()
        
        for column, filter_config in filters.items():
            if column in filtered_df.columns:
                operator = filter_config['operator']
                value = filter_config['value']
                
                try:
                    # Convert value to appropriate type
                    if pd.api.types.is_numeric_dtype(filtered_df[column]):
                        value = float(value)
                    
                    if operator == '=':
                        filtered_df = filtered_df[filtered_df[column] == value]
                    elif operator == '>':
                        filtered_df = filtered_df[filtered_df[column] > value]
                    elif operator == '<':
                        filtered_df = filtered_df[filtered_df[column] < value]
                    elif operator == '>=':
                        filtered_df = filtered_df[filtered_df[column] >= value]
                    elif operator == '<=':
                        filtered_df = filtered_df[filtered_df[column] <= value]
                except Exception:
                    continue  # Skip invalid filters
        
        return filtered_df
    
    def _create_bar_chart(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create interactive bar chart"""
        x_col = config.get('x', self._guess_x_column(df, intent))
        y_col = config.get('y', self._guess_y_column(df, intent))
        
        # Handle aggregation
        if y_col == 'count' or intent.get('aggregation') == 'count':
            # Count occurrences
            plot_data = df[x_col].value_counts().reset_index()
            plot_data.columns = [x_col, 'count']
            y_col = 'count'
        elif intent.get('aggregation') and intent['aggregation'] != 'count':
            # Apply aggregation
            agg_func = intent['aggregation']
            if agg_func in ['sum', 'mean', 'max', 'min', 'median']:
                plot_data = df.groupby(x_col)[y_col].agg(agg_func).reset_index()
            else:
                plot_data = df
        else:
            plot_data = df
        
        fig = px.bar(
            plot_data,
            x=x_col,
            y=y_col,
            title=config.get('title', f'{y_col} by {x_col}'),
            color_discrete_sequence=self.color_schemes['professional']
        )
        
        return self._apply_windows_styling(fig)
    
    def _create_line_chart(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create interactive line chart"""
        x_col = config.get('x', self._guess_x_column(df, intent))
        y_col = config.get('y', self._guess_y_column(df, intent))
        
        fig = px.line(
            df,
            x=x_col,
            y=y_col,
            title=config.get('title', f'{y_col} over {x_col}'),
            color_discrete_sequence=self.color_schemes['professional']
        )
        
        return self._apply_windows_styling(fig)
    
    def _create_scatter_chart(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create interactive scatter plot"""
        x_col = config.get('x', self._guess_x_column(df, intent))
        y_col = config.get('y', self._guess_y_column(df, intent))
        
        # Add color grouping if categorical column available
        color_col = None
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        if len(categorical_cols) > 0:
            color_col = categorical_cols[0]
        
        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=config.get('title', f'{x_col} vs {y_col}'),
            color_discrete_sequence=self.color_schemes['vibrant']
        )
        
        return self._apply_windows_styling(fig)
    
    def _create_pie_chart(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create interactive pie chart"""
        # For pie charts, we need categorical data
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        if len(categorical_cols) == 0:
            raise ValueError("No categorical columns found for pie chart")
        
        values_col = config.get('values', categorical_cols[0])
        names_col = config.get('names', categorical_cols[0])
        
        # Count occurrences if using same column for names and values
        if values_col == names_col:
            plot_data = df[names_col].value_counts().reset_index()
            plot_data.columns = [names_col, 'count']
            values_col = 'count'
        else:
            plot_data = df
        
        fig = px.pie(
            plot_data,
            values=values_col,
            names=names_col,
            title=config.get('title', f'Distribution of {names_col}')
        )
        
        return self._apply_windows_styling(fig)
    
    def _create_heatmap(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create correlation heatmap"""
        # Get numeric columns for correlation
        numeric_df = df.select_dtypes(include=[np.number])
        if numeric_df.empty:
            raise ValueError("No numeric columns found for heatmap")
        
        # Calculate correlation matrix
        corr_matrix = numeric_df.corr()
        
        fig = px.imshow(
            corr_matrix,
            text_auto=True,
            aspect="auto",
            title=config.get('title', 'Correlation Matrix'),
            color_continuous_scale='RdBu'
        )
        
        return self._apply_windows_styling(fig)
    
    def _create_histogram(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create histogram"""
        x_col = config.get('x', self._guess_numeric_column(df))
        
        fig = px.histogram(
            df,
            x=x_col,
            title=config.get('title', f'Distribution of {x_col}'),
            color_discrete_sequence=self.color_schemes['professional']
        )
        
        return self._apply_windows_styling(fig)
    
    def _create_box_plot(self, df: pd.DataFrame, config: Dict, intent: Dict) -> go.Figure:
        """Create box plot"""
        y_col = config.get('y', self._guess_numeric_column(df))
        x_col = config.get('x')
        
        if x_col and x_col in df.columns:
            fig = px.box(
                df,
                x=x_col,
                y=y_col,
                title=config.get('title', f'{y_col} by {x_col}')
            )
        else:
            fig = px.box(
                df,
                y=y_col,
                title=config.get('title', f'Distribution of {y_col}')
            )
        
        return self._apply_windows_styling(fig)
    
    def _guess_x_column(self, df: pd.DataFrame, intent: Dict) -> str:
        """Guess appropriate X column"""
        # Check if user specified columns
        if intent.get('columns'):
            return intent['columns'][0]
        
        # Prefer datetime columns for X axis
        datetime_cols = df.select_dtypes(include=['datetime64']).columns
        if len(datetime_cols) > 0:
            return datetime_cols[0]
        
        # Then categorical columns
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        if len(categorical_cols) > 0:
            return categorical_cols[0]
        
        # Finally any column
        return df.columns[0]
    
    def _guess_y_column(self, df: pd.DataFrame, intent: Dict) -> str:
        """Guess appropriate Y column"""
        # Check if user specified columns
        if intent.get('columns') and len(intent['columns']) > 1:
            return intent['columns'][1]
        
        # Prefer numeric columns for Y axis
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            return numeric_cols[0]
        
        return 'count'  # Default to count
    
    def _guess_numeric_column(self, df: pd.DataFrame) -> str:
        """Guess first numeric column"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            return numeric_cols[0]
        raise ValueError("No numeric columns found")
    
    def _apply_windows_styling(self, fig: go.Figure) -> go.Figure:
        """Apply Windows-compatible styling to Plotly chart"""
        fig.update_layout(
            font=dict(family="Segoe UI, Arial, sans-serif", size=12),
            plot_bgcolor='white',
            paper_bgcolor='white',
            title_font_size=16,
            showlegend=True,
            width=800,
            height=500
        )
        
        # Update axes styling
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
        
        return fig

class DataVisualizationEngine:
    """Main engine that orchestrates data visualization workflow"""
    
    def __init__(self, qdrant_indexer=None, ollama_client=None):
        self.qdrant_indexer = qdrant_indexer or MultiCollectionQdrantIndexer()
        self.data_loader = WindowsDataLoader()
        self.intent_parser = VisualizationIntentParser()
        self.structure_analyzer = DataStructureAnalyzer(ollama_client)
        self.chart_generator = PlotlyChartGenerator()
        self.loaded_datasets = {}  # Cache for loaded data
    
    def process_visualization_request(self, request: str) -> Dict[str, Any]:
        """Process a natural language visualization request"""
        try:
            # Parse the request
            intent = self.intent_parser.parse_visualization_request(request)
            
            # Find relevant data
            relevant_data = self._find_relevant_tabular_data(request)
            
            if not relevant_data:
                return {
                    'success': False,
                    'error': 'No relevant tabular data found for visualization',
                    'intent': intent
                }
            
            # Load and analyze the best matching dataset
            best_match = relevant_data[0]
            dataset_info = self._load_and_analyze_dataset(best_match['file_path'])
            
            if not dataset_info['success']:
                return {
                    'success': False,
                    'error': dataset_info['error'],
                    'intent': intent
                }
            
            # Generate appropriate chart
            chart_result = self._generate_chart_from_intent(
                dataset_info['dataframe'], 
                dataset_info['analysis'], 
                intent
            )
            
            return {
                'success': True,
                'intent': intent,
                'dataset_info': dataset_info,
                'chart': chart_result['chart'],
                'chart_config': chart_result['config'],
                'suggestions': dataset_info['analysis']['suggested_charts']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Visualization processing error: {str(e)}",
                'intent': intent if 'intent' in locals() else {}
            }
    
    def _find_relevant_tabular_data(self, query: str) -> List[Dict]:
        """Query Qdrant to find relevant tabular data"""
        try:
            # Search structured data collections
            collections_to_search = ['structured_data', 'structured_summaries', 'documents']
            all_results = []
            
            for collection in collections_to_search:
                try:
                    results = self.qdrant_indexer.search_collection(
                        collection, 
                        query, 
                        limit=5, 
                        score_threshold=0.5
                    )
                    if results:
                        for result in results:
                            # Prioritize results that mention data files
                            file_path = result.get('file_path', '')
                            if any(ext in file_path.lower() for ext in ['.csv', '.xlsx', '.xls']):
                                result['priority'] = 'high'
                            else:
                                result['priority'] = 'medium'
                        all_results.extend(results)
                except Exception:
                    continue
            
            # Sort by score and priority
            all_results.sort(key=lambda x: (
                1 if x.get('priority') == 'high' else 0,
                x.get('score', 0)
            ), reverse=True)
            
            return all_results[:5]  # Return top 5 matches
            
        except Exception:
            return []
    
    def _load_and_analyze_dataset(self, file_path: str) -> Dict[str, Any]:
        """Load and analyze a dataset"""
        try:
            path = Path(file_path)
            
            # Check cache first
            cache_key = str(path.resolve())
            if cache_key in self.loaded_datasets:
                return self.loaded_datasets[cache_key]
            
            if not path.exists():
                return {'success': False, 'error': f'File not found: {file_path}'}
            
            # Load based on file type
            if path.suffix.lower() == '.csv':
                df = self.data_loader.load_csv_with_windows_handling(path)
                analysis = self.structure_analyzer.analyze_dataframe_structure(df, path.name)
            elif path.suffix.lower() in ['.xlsx', '.xls']:
                sheets = self.data_loader.load_excel_with_windows_handling(path)
                if not sheets:
                    return {'success': False, 'error': 'No readable sheets found in Excel file'}
                
                # Use the first sheet or largest sheet
                sheet_name = max(sheets.keys(), key=lambda k: sheets[k].shape[0])
                df = sheets[sheet_name]
                analysis = self.structure_analyzer.analyze_dataframe_structure(df, f"{path.name}[{sheet_name}]")
            else:
                return {'success': False, 'error': f'Unsupported file type: {path.suffix}'}
            
            result = {
                'success': True,
                'dataframe': df,
                'analysis': analysis,
                'file_path': file_path
            }
            
            # Cache the result
            self.loaded_datasets[cache_key] = result
            
            return result
            
        except Exception as e:
            return {'success': False, 'error': f'Failed to load dataset: {str(e)}'}
    
    def _generate_chart_from_intent(self, df: pd.DataFrame, analysis: Dict, intent: Dict) -> Dict[str, Any]:
        """Generate chart based on user intent and data analysis"""
        # Find best matching suggested chart or use intent
        chart_config = self._select_best_chart_config(analysis['suggested_charts'], intent)
        
        # Generate the chart
        fig = self.chart_generator.generate_chart(df, chart_config, intent)
        
        return {
            'chart': fig,
            'config': chart_config,
            'data_shape': df.shape,
            'columns_used': [chart_config.get('x'), chart_config.get('y')]
        }
    
    def _select_best_chart_config(self, suggested_charts: List[Dict], intent: Dict) -> Dict:
        """Select the best chart configuration based on suggestions and intent"""
        user_chart_type = intent.get('chart_type')
        user_columns = intent.get('columns', [])
        
        # Try to find exact match with user intent
        if user_chart_type:
            for suggestion in suggested_charts:
                if suggestion['type'] == user_chart_type:
                    # Check if user specified columns match
                    if user_columns:
                        if any(col in str(suggestion) for col in user_columns):
                            return suggestion
                    else:
                        return suggestion
        
        # Find high priority suggestions
        high_priority = [s for s in suggested_charts if s.get('priority') == 'high']
        if high_priority:
            return high_priority[0]
        
        # Fall back to first suggestion or create default
        if suggested_charts:
            return suggested_charts[0]
        
        # Create default configuration
        return {
            'type': user_chart_type or 'bar',
            'title': 'Data Visualization',
            'priority': 'medium'
        }

# Export main class for use in Streamlit app
__all__ = ['DataVisualizationEngine', 'WindowsDataLoader', 'PlotlyChartGenerator']