"""
MIDAS Dashboard Chart Components
Chart types and rendering functionality for dashboards
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Dict, List, Any, Optional, Union, Callable
import numpy as np
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)

class ChartDataConnector:
    """Connects charts to data sources"""
    
    def __init__(self):
        self.data_sources = {}
        self.connections = {}
    
    def register_data_source(self, name: str, data_getter: Callable):
        """Register a data source function"""
        self.data_sources[name] = data_getter
    
    def get_data(self, source_config: Dict[str, Any]) -> pd.DataFrame:
        """Get data based on source configuration"""
        source_type = source_config.get('type', 'static')
        
        if source_type == 'static':
            # Static data embedded in config
            data = source_config.get('data', [])
            return pd.DataFrame(data)
        
        elif source_type == 'function':
            # Data from registered function
            func_name = source_config.get('function')
            params = source_config.get('params', {})
            
            if func_name in self.data_sources:
                return self.data_sources[func_name](**params)
            else:
                logger.warning(f"Data source function not found: {func_name}")
                return pd.DataFrame()
        
        elif source_type == 'sql':
            # SQL query data
            from integrated_sql_rag_search import IntegratedSQLRAGSearch
            search = IntegratedSQLRAGSearch()
            
            query = source_config.get('query')
            database = source_config.get('database')
            
            if query and database:
                try:
                    return search.execute_sql(query, database)
                except Exception as e:
                    logger.error(f"SQL execution failed: {e}")
                    return pd.DataFrame()
        
        elif source_type == 'api':
            # API endpoint data
            import requests
            
            url = source_config.get('url')
            method = source_config.get('method', 'GET')
            headers = source_config.get('headers', {})
            params = source_config.get('params', {})
            
            try:
                response = requests.request(method, url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                return pd.DataFrame(data)
            except Exception as e:
                logger.error(f"API request failed: {e}")
                return pd.DataFrame()
        
        else:
            logger.warning(f"Unknown data source type: {source_type}")
            return pd.DataFrame()

class ChartRenderer:
    """Renders different chart types using Plotly"""
    
    def __init__(self, theme: Dict[str, str] = None):
        self.theme = theme or {
            'background': '#FFFFFF',
            'text': '#000000',
            'primary': '#1976D2',
            'secondary': '#DC004E',
            'grid': '#E0E0E0'
        }
        self.data_connector = ChartDataConnector()
    
    def render_chart(self, chart_config: Dict[str, Any], 
                    data: Optional[pd.DataFrame] = None) -> go.Figure:
        """Render chart based on configuration"""
        chart_type = chart_config.get('type', 'line')
        
        # Get data if not provided
        if data is None:
            data = self.data_connector.get_data(chart_config.get('data_source', {}))
        
        # Apply filters
        data = self._apply_filters(data, chart_config.get('filters', []))
        
        # Render based on type
        render_method = getattr(self, f'render_{chart_type}', None)
        if render_method:
            fig = render_method(data, chart_config)
        else:
            fig = self.render_default(data, chart_config)
        
        # Apply theme
        self._apply_theme(fig, chart_config)
        
        return fig
    
    def _apply_filters(self, data: pd.DataFrame, filters: List[Dict[str, Any]]) -> pd.DataFrame:
        """Apply filters to data"""
        if data.empty or not filters:
            return data
        
        filtered_data = data.copy()
        
        for filter_config in filters:
            column = filter_config.get('column')
            operator = filter_config.get('operator', '=')
            value = filter_config.get('value')
            
            if column not in filtered_data.columns:
                continue
            
            if operator == '=':
                filtered_data = filtered_data[filtered_data[column] == value]
            elif operator == '!=':
                filtered_data = filtered_data[filtered_data[column] != value]
            elif operator == '>':
                filtered_data = filtered_data[filtered_data[column] > value]
            elif operator == '<':
                filtered_data = filtered_data[filtered_data[column] < value]
            elif operator == '>=':
                filtered_data = filtered_data[filtered_data[column] >= value]
            elif operator == '<=':
                filtered_data = filtered_data[filtered_data[column] <= value]
            elif operator == 'in':
                filtered_data = filtered_data[filtered_data[column].isin(value)]
            elif operator == 'contains':
                filtered_data = filtered_data[filtered_data[column].str.contains(value, na=False)]
        
        return filtered_data
    
    def _apply_theme(self, fig: go.Figure, chart_config: Dict[str, Any]):
        """Apply theme to figure"""
        fig.update_layout(
            paper_bgcolor=self.theme['background'],
            plot_bgcolor=self.theme['background'],
            font_color=self.theme['text'],
            title_font_color=self.theme['text'],
            title=chart_config.get('title', ''),
            showlegend=chart_config.get('options', {}).get('show_legend', True),
            margin=dict(l=40, r=40, t=60, b=40)
        )
        
        # Update axes
        fig.update_xaxes(
            gridcolor=self.theme['grid'],
            showgrid=chart_config.get('options', {}).get('show_grid', True)
        )
        fig.update_yaxes(
            gridcolor=self.theme['grid'],
            showgrid=chart_config.get('options', {}).get('show_grid', True)
        )
    
    def render_metric(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render metric/KPI card"""
        value_column = config.get('options', {}).get('value_column')
        aggregation = config.get('options', {}).get('aggregation', 'sum')
        
        if data.empty or not value_column or value_column not in data.columns:
            value = 0
            delta = 0
        else:
            if aggregation == 'sum':
                value = data[value_column].sum()
            elif aggregation == 'mean':
                value = data[value_column].mean()
            elif aggregation == 'count':
                value = len(data)
            elif aggregation == 'max':
                value = data[value_column].max()
            elif aggregation == 'min':
                value = data[value_column].min()
            else:
                value = data[value_column].iloc[-1] if len(data) > 0 else 0
            
            # Calculate delta if comparison column exists
            compare_column = config.get('options', {}).get('compare_column')
            if compare_column and compare_column in data.columns:
                if aggregation == 'sum':
                    compare_value = data[compare_column].sum()
                elif aggregation == 'mean':
                    compare_value = data[compare_column].mean()
                else:
                    compare_value = data[compare_column].iloc[0] if len(data) > 0 else 0
                
                delta = value - compare_value
            else:
                delta = 0
        
        # Format value
        format_type = config.get('options', {}).get('format', 'number')
        if format_type == 'currency':
            value_text = f"${value:,.2f}"
            delta_text = f"${delta:+,.2f}"
        elif format_type == 'percentage':
            value_text = f"{value:.1%}"
            delta_text = f"{delta:+.1%}"
        else:
            value_text = f"{value:,.0f}"
            delta_text = f"{delta:+,.0f}"
        
        fig = go.Figure()
        
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=value,
            delta={
                'reference': value - delta,
                'relative': True,
                'valueformat': '.1%' if format_type == 'percentage' else '.0f'
            },
            number={'valueformat': '.1%' if format_type == 'percentage' else '.0f'},
            title={'text': config.get('title', 'Metric')},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        
        fig.update_layout(height=200)
        
        return fig
    
    def render_line(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render line chart"""
        x_column = config.get('options', {}).get('x_column')
        y_columns = config.get('options', {}).get('y_columns', [])
        
        if data.empty or not x_column or not y_columns:
            return self.render_empty(config)
        
        fig = go.Figure()
        
        for y_column in y_columns:
            if y_column in data.columns:
                fig.add_trace(go.Scatter(
                    x=data[x_column],
                    y=data[y_column],
                    mode='lines+markers',
                    name=y_column,
                    line=dict(width=2),
                    marker=dict(size=6)
                ))
        
        fig.update_layout(
            xaxis_title=x_column,
            yaxis_title=', '.join(y_columns),
            hovermode='x unified'
        )
        
        return fig
    
    def render_bar(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render bar chart"""
        x_column = config.get('options', {}).get('x_column')
        y_columns = config.get('options', {}).get('y_columns', [])
        orientation = config.get('options', {}).get('orientation', 'vertical')
        
        if data.empty or not x_column or not y_columns:
            return self.render_empty(config)
        
        fig = go.Figure()
        
        for y_column in y_columns:
            if y_column in data.columns:
                if orientation == 'horizontal':
                    fig.add_trace(go.Bar(
                        y=data[x_column],
                        x=data[y_column],
                        name=y_column,
                        orientation='h'
                    ))
                else:
                    fig.add_trace(go.Bar(
                        x=data[x_column],
                        y=data[y_column],
                        name=y_column
                    ))
        
        barmode = config.get('options', {}).get('barmode', 'group')
        fig.update_layout(barmode=barmode)
        
        return fig
    
    def render_scatter(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render scatter plot"""
        x_column = config.get('options', {}).get('x_column')
        y_column = config.get('options', {}).get('y_column')
        size_column = config.get('options', {}).get('size_column')
        color_column = config.get('options', {}).get('color_column')
        
        if data.empty or not x_column or not y_column:
            return self.render_empty(config)
        
        marker_config = {'size': 8}
        
        if size_column and size_column in data.columns:
            marker_config['size'] = data[size_column]
            marker_config['sizemode'] = 'area'
            marker_config['sizeref'] = 2. * max(data[size_column]) / (40. ** 2)
            marker_config['sizemin'] = 4
        
        if color_column and color_column in data.columns:
            fig = px.scatter(
                data,
                x=x_column,
                y=y_column,
                color=color_column,
                size=size_column if size_column else None,
                title=config.get('title', '')
            )
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=data[x_column],
                y=data[y_column],
                mode='markers',
                marker=marker_config,
                name='Data'
            ))
        
        return fig
    
    def render_pie(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render pie chart"""
        labels_column = config.get('options', {}).get('labels_column')
        values_column = config.get('options', {}).get('values_column')
        
        if data.empty or not labels_column or not values_column:
            return self.render_empty(config)
        
        fig = go.Figure()
        
        fig.add_trace(go.Pie(
            labels=data[labels_column],
            values=data[values_column],
            hole=0.3 if config.get('options', {}).get('donut', False) else 0
        ))
        
        return fig
    
    def render_heatmap(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render heatmap"""
        x_column = config.get('options', {}).get('x_column')
        y_column = config.get('options', {}).get('y_column')
        z_column = config.get('options', {}).get('z_column')
        
        if data.empty or not all([x_column, y_column, z_column]):
            return self.render_empty(config)
        
        # Pivot data for heatmap
        pivot_data = data.pivot_table(
            index=y_column,
            columns=x_column,
            values=z_column,
            aggfunc='mean'
        )
        
        fig = go.Figure()
        
        fig.add_trace(go.Heatmap(
            x=pivot_data.columns,
            y=pivot_data.index,
            z=pivot_data.values,
            colorscale='Blues'
        ))
        
        return fig
    
    def render_table(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render data table"""
        columns = config.get('options', {}).get('columns', list(data.columns))
        max_rows = config.get('options', {}).get('max_rows', 100)
        
        if data.empty:
            return self.render_empty(config)
        
        # Limit columns and rows
        display_data = data[columns].head(max_rows)
        
        fig = go.Figure()
        
        fig.add_trace(go.Table(
            header=dict(
                values=list(display_data.columns),
                fill_color=self.theme['primary'],
                font_color='white',
                align='left'
            ),
            cells=dict(
                values=[display_data[col] for col in display_data.columns],
                fill_color='white',
                align='left'
            )
        ))
        
        return fig
    
    def render_gauge(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Render gauge chart"""
        value_column = config.get('options', {}).get('value_column')
        min_value = config.get('options', {}).get('min_value', 0)
        max_value = config.get('options', {}).get('max_value', 100)
        
        if data.empty or not value_column or value_column not in data.columns:
            value = 0
        else:
            value = data[value_column].iloc[-1] if len(data) > 0 else 0
        
        fig = go.Figure()
        
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=value,
            title={'text': config.get('title', 'Gauge')},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [min_value, max_value]},
                'bar': {'color': self.theme['primary']},
                'steps': [
                    {'range': [min_value, (max_value - min_value) * 0.5 + min_value], 
                     'color': "lightgray"},
                    {'range': [(max_value - min_value) * 0.5 + min_value, 
                              (max_value - min_value) * 0.8 + min_value], 
                     'color': self.theme['warning']},
                    {'range': [(max_value - min_value) * 0.8 + min_value, max_value], 
                     'color': self.theme['error']}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': (max_value - min_value) * 0.9 + min_value
                }
            }
        ))
        
        return fig
    
    def render_empty(self, config: Dict[str, Any]) -> go.Figure:
        """Render empty chart placeholder"""
        fig = go.Figure()
        
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=20, color="gray")
        )
        
        fig.update_layout(
            xaxis={'visible': False},
            yaxis={'visible': False},
            title=config.get('title', 'Chart')
        )
        
        return fig
    
    def render_default(self, data: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
        """Default renderer for unknown chart types"""
        return self.render_empty(config)

class InteractiveFilter:
    """Manages interactive filters for dashboards"""
    
    def __init__(self):
        self.filters = {}
        self.filter_values = {}
    
    def register_filter(self, filter_id: str, filter_config: Dict[str, Any]):
        """Register a filter"""
        self.filters[filter_id] = filter_config
        
        # Initialize filter value
        filter_type = filter_config.get('type', 'select')
        if filter_type == 'select':
            self.filter_values[filter_id] = filter_config.get('default')
        elif filter_type == 'multiselect':
            self.filter_values[filter_id] = filter_config.get('default', [])
        elif filter_type == 'range':
            self.filter_values[filter_id] = filter_config.get('default', [0, 100])
        elif filter_type == 'date_range':
            self.filter_values[filter_id] = filter_config.get('default', 
                [datetime.now() - timedelta(days=30), datetime.now()])
    
    def update_filter_value(self, filter_id: str, value: Any):
        """Update filter value"""
        if filter_id in self.filters:
            self.filter_values[filter_id] = value
    
    def get_filter_value(self, filter_id: str) -> Any:
        """Get current filter value"""
        return self.filter_values.get(filter_id)
    
    def apply_filters_to_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply all active filters to data"""
        filtered_data = data.copy()
        
        for filter_id, filter_config in self.filters.items():
            value = self.filter_values.get(filter_id)
            if value is None:
                continue
            
            column = filter_config.get('column')
            filter_type = filter_config.get('type')
            
            if column not in filtered_data.columns:
                continue
            
            if filter_type == 'select' and value:
                filtered_data = filtered_data[filtered_data[column] == value]
            
            elif filter_type == 'multiselect' and value:
                filtered_data = filtered_data[filtered_data[column].isin(value)]
            
            elif filter_type == 'range' and len(value) == 2:
                filtered_data = filtered_data[
                    (filtered_data[column] >= value[0]) & 
                    (filtered_data[column] <= value[1])
                ]
            
            elif filter_type == 'date_range' and len(value) == 2:
                # Convert column to datetime if needed
                if not pd.api.types.is_datetime64_any_dtype(filtered_data[column]):
                    filtered_data[column] = pd.to_datetime(filtered_data[column])
                
                filtered_data = filtered_data[
                    (filtered_data[column] >= value[0]) & 
                    (filtered_data[column] <= value[1])
                ]
        
        return filtered_data
    
    def get_filter_options(self, data: pd.DataFrame, column: str) -> List[Any]:
        """Get available options for a filter column"""
        if column in data.columns:
            return sorted(data[column].dropna().unique().tolist())
        return []

# Example data generation functions
def generate_sample_timeseries(days: int = 30) -> pd.DataFrame:
    """Generate sample time series data"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    data = {
        'date': dates,
        'value': np.random.randn(days).cumsum() + 100,
        'category': np.random.choice(['A', 'B', 'C'], days),
        'sales': np.random.randint(50, 200, days),
        'profit': np.random.randint(10, 50, days)
    }
    return pd.DataFrame(data)

def generate_sample_categorical() -> pd.DataFrame:
    """Generate sample categorical data"""
    categories = ['Electronics', 'Clothing', 'Food', 'Books', 'Sports']
    data = {
        'category': categories,
        'sales': np.random.randint(1000, 5000, len(categories)),
        'profit': np.random.randint(100, 1000, len(categories)),
        'items': np.random.randint(50, 200, len(categories))
    }
    return pd.DataFrame(data)

if __name__ == "__main__":
    # Test chart rendering
    renderer = ChartRenderer()
    
    # Test data
    data = generate_sample_timeseries()
    
    # Test line chart
    line_config = {
        'type': 'line',
        'title': 'Sales Trend',
        'options': {
            'x_column': 'date',
            'y_columns': ['value', 'sales']
        }
    }
    
    fig = renderer.render_chart(line_config, data)
    print("Line chart created successfully")