"""
Data Visualization Service for Pet Analytics
Generates chart configurations and data processing for pet health visualizations
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Dict, Any, Tuple
import statistics

class PetVisualizationService:
    
    def __init__(self):
        self.chart_colors = {
            'primary': '#667eea',
            'secondary': '#4ecdc4',
            'success': '#38a169',
            'warning': '#d69e2e',
            'error': '#e53e3e',
            'info': '#3182ce',
            'purple': '#805ad5',
            'pink': '#d53f8c',
            'teal': '#319795',
            'orange': '#dd6b20'
        }
    
    def generate_weekly_activity_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate data for weekly activity trend line chart"""
        # Group data by day and count activities
        daily_counts = defaultdict(int)
        
        # Get last 7 days
        today = datetime.now()
        for i in range(7):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            daily_counts[date] = 0
        
        # Count activities per day
        for entry in analytics_data:
            timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
            date = timestamp.strftime('%Y-%m-%d')
            if date in daily_counts:
                daily_counts[date] += 1
        
        # Prepare chart data
        dates = sorted(daily_counts.keys())
        values = [daily_counts[date] for date in dates]
        labels = [datetime.strptime(date, '%Y-%m-%d').strftime('%a') for date in dates]
        
        return {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': 'Daily Activities',
                    'data': values,
                    'borderColor': self.chart_colors['primary'],
                    'backgroundColor': self.chart_colors['primary'] + '20',
                    'fill': True,
                    'tension': 0.4
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'ticks': {
                            'stepSize': 1
                        }
                    }
                }
            }
        }
    
    def generate_energy_distribution_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate energy levels distribution doughnut chart"""
        energy_entries = [entry for entry in analytics_data if entry.get('category') == 'energy_levels']
        energy_counts = Counter()
        
        for entry in energy_entries:
            level = int(entry.get('level', 3))
            energy_counts[level] += 1
        
        # Prepare data for all energy levels (1-5)
        labels = ['Very Low (1)', 'Low (2)', 'Normal (3)', 'High (4)', 'Very High (5)']
        values = [energy_counts.get(i, 0) for i in range(1, 6)]
        colors = [
            '#e53e3e',  # Very Low - Red
            '#dd6b20',  # Low - Orange  
            '#d69e2e',  # Normal - Yellow
            '#38a169',  # High - Green
            '#3182ce'   # Very High - Blue
        ]
        
        return {
            'type': 'doughnut',
            'data': {
                'labels': labels,
                'datasets': [{
                    'data': values,
                    'backgroundColor': colors,
                    'borderWidth': 2,
                    'borderColor': '#ffffff'
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'position': 'bottom',
                        'labels': {
                            'padding': 20,
                            'usePointStyle': True
                        }
                    }
                }
            }
        }
    
    def generate_diet_frequency_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate diet frequency bar chart"""
        diet_entries = [entry for entry in analytics_data if entry.get('category') == 'diet']
        meal_type_counts = Counter()
        
        for entry in diet_entries:
            meal_type = entry.get('type', 'other')
            meal_type_counts[meal_type] += 1
        
        # Get top meal types
        top_types = meal_type_counts.most_common(6)
        labels = [item[0].title() for item in top_types]
        values = [item[1] for item in top_types]
        
        return {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': 'Meal Count',
                    'data': values,
                    'backgroundColor': [
                        self.chart_colors['success'],
                        self.chart_colors['info'],
                        self.chart_colors['warning'],
                        self.chart_colors['purple'],
                        self.chart_colors['teal'],
                        self.chart_colors['pink']
                    ][:len(values)],
                    'borderRadius': 8,
                    'borderSkipped': False
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'ticks': {
                            'stepSize': 1
                        }
                    }
                }
            }
        }
    
    def generate_health_overview_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate health metrics overview radar chart"""
        categories = ['diet', 'exercise', 'medication', 'grooming', 'energy_levels']
        category_counts = defaultdict(int)
        
        for entry in analytics_data:
            category = entry.get('category', '')
            if category in categories:
                category_counts[category] += 1
        
        # Normalize scores (0-10 scale based on activity frequency)
        max_count = max(category_counts.values()) if category_counts.values() else 1
        labels = ['Diet', 'Exercise', 'Medication', 'Grooming', 'Energy Tracking']
        values = []
        
        for category in categories:
            count = category_counts[category]
            # Scale to 0-10, with 5 as average
            score = min(10, (count / max_count) * 10) if max_count > 0 else 0
            values.append(round(score, 1))
        
        return {
            'type': 'radar',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': 'Health Tracking Score',
                    'data': values,
                    'borderColor': self.chart_colors['primary'],
                    'backgroundColor': self.chart_colors['primary'] + '30',
                    'pointBackgroundColor': self.chart_colors['primary'],
                    'pointBorderColor': '#ffffff',
                    'pointHoverBackgroundColor': '#ffffff',
                    'pointHoverBorderColor': self.chart_colors['primary']
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    }
                },
                'scales': {
                    'r': {
                        'beginAtZero': True,
                        'max': 10,
                        'ticks': {
                            'stepSize': 2
                        }
                    }
                }
            }
        }
    
    def generate_exercise_duration_histogram(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate exercise duration histogram"""
        exercise_entries = [entry for entry in analytics_data if entry.get('category') == 'exercise']
        durations = []
        
        for entry in exercise_entries:
            duration = int(entry.get('duration', 0))
            if duration > 0:
                durations.append(duration)
        
        if not durations:
            return self._empty_chart_config('No exercise data available')
        
        # Create bins for histogram
        min_duration = min(durations)
        max_duration = max(durations)
        
        # Create 5-8 bins
        bin_count = min(8, max(3, len(set(durations))))
        bin_size = max(5, (max_duration - min_duration) // bin_count)
        
        bins = []
        bin_labels = []
        current = min_duration
        
        while current < max_duration:
            next_bin = current + bin_size
            bins.append((current, next_bin))
            bin_labels.append(f'{current}-{next_bin}min')
            current = next_bin
        
        # Count durations in each bin
        bin_counts = [0] * len(bins)
        for duration in durations:
            for i, (bin_start, bin_end) in enumerate(bins):
                if bin_start <= duration < bin_end or (i == len(bins)-1 and duration == bin_end):
                    bin_counts[i] += 1
                    break
        
        return {
            'type': 'bar',
            'data': {
                'labels': bin_labels,
                'datasets': [{
                    'label': 'Exercise Sessions',
                    'data': bin_counts,
                    'backgroundColor': self.chart_colors['secondary'],
                    'borderRadius': 4
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    },
                    'title': {
                        'display': True,
                        'text': 'Exercise Duration Distribution'
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'ticks': {
                            'stepSize': 1
                        }
                    }
                }
            }
        }
    
    def generate_medication_adherence_chart(self, analytics_data: List[Dict], 
                                          expected_daily_doses: int = 1) -> Dict[str, Any]:
        """Generate medication adherence timeline chart"""
        medication_entries = [entry for entry in analytics_data if entry.get('category') == 'medication']
        
        if not medication_entries:
            return self._empty_chart_config('No medication data available')
        
        # Group by day
        daily_doses = defaultdict(int)
        today = datetime.now()
        
        # Initialize last 14 days
        for i in range(14):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            daily_doses[date] = 0
        
        # Count actual doses
        for entry in medication_entries:
            timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
            date = timestamp.strftime('%Y-%m-%d')
            if date in daily_doses:
                daily_doses[date] += 1
        
        # Calculate adherence percentage
        dates = sorted(daily_doses.keys())
        adherence_percentages = []
        labels = []
        
        for date in dates:
            actual_doses = daily_doses[date]
            adherence = min(100, (actual_doses / expected_daily_doses) * 100) if expected_daily_doses > 0 else 0
            adherence_percentages.append(round(adherence, 1))
            labels.append(datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d'))
        
        return {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': 'Adherence %',
                    'data': adherence_percentages,
                    'borderColor': self.chart_colors['success'],
                    'backgroundColor': self.chart_colors['success'] + '30',
                    'fill': True,
                    'tension': 0.3
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    },
                    'title': {
                        'display': True,
                        'text': 'Medication Adherence (14 days)'
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'max': 100,
                        'ticks': {
                            'callback': 'function(value) { return value + "%"; }'
                        }
                    }
                }
            }
        }
    
    def generate_activity_heatmap_data(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate activity heatmap data for different times of day"""
        hour_activity = defaultdict(int)
        
        # Initialize all hours
        for hour in range(24):
            hour_activity[hour] = 0
        
        # Count activities by hour
        for entry in analytics_data:
            try:
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                hour = timestamp.hour
                hour_activity[hour] += 1
            except:
                continue
        
        # Convert to format suitable for heatmap
        hours = list(range(24))
        activities = [hour_activity[hour] for hour in hours]
        
        # Create time labels
        time_labels = []
        for hour in hours:
            if hour == 0:
                time_labels.append('12 AM')
            elif hour < 12:
                time_labels.append(f'{hour} AM')
            elif hour == 12:
                time_labels.append('12 PM')
            else:
                time_labels.append(f'{hour-12} PM')
        
        return {
            'hours': hours,
            'activities': activities,
            'labels': time_labels,
            'max_activity': max(activities) if activities else 0
        }
    
    def generate_summary_metrics(self, analytics_data: List[Dict], days: int = 30) -> Dict[str, Any]:
        """Generate summary metrics for dashboard"""
        categories = defaultdict(list)
        
        for entry in analytics_data:
            category = entry.get('category', 'unknown')
            categories[category].append(entry)
        
        metrics = {}
        
        # Diet metrics
        if categories['diet']:
            meals_per_day = len(categories['diet']) / days
            unique_foods = len(set(entry.get('food', '') for entry in categories['diet']))
            metrics['diet'] = {
                'total_meals': len(categories['diet']),
                'avg_per_day': round(meals_per_day, 1),
                'food_variety': unique_foods,
                'trend': self._calculate_trend(categories['diet'], days)
            }
        
        # Exercise metrics
        if categories['exercise']:
            total_duration = sum(int(entry.get('duration', 0)) for entry in categories['exercise'])
            avg_duration = total_duration / len(categories['exercise'])
            metrics['exercise'] = {
                'total_sessions': len(categories['exercise']),
                'total_duration': total_duration,
                'avg_duration': round(avg_duration, 1),
                'avg_per_day': round(len(categories['exercise']) / days, 1),
                'trend': self._calculate_trend(categories['exercise'], days)
            }
        
        # Energy metrics
        if categories['energy_levels']:
            levels = [int(entry.get('level', 3)) for entry in categories['energy_levels']]
            avg_energy = statistics.mean(levels)
            metrics['energy'] = {
                'total_recordings': len(levels),
                'avg_level': round(avg_energy, 1),
                'high_energy_days': sum(1 for level in levels if level >= 4),
                'low_energy_days': sum(1 for level in levels if level <= 2),
                'trend': self._calculate_energy_trend(levels)
            }
        
        # Medication metrics
        if categories['medication']:
            unique_meds = len(set(entry.get('name', '') for entry in categories['medication']))
            metrics['medication'] = {
                'total_doses': len(categories['medication']),
                'unique_medications': unique_meds,
                'avg_per_day': round(len(categories['medication']) / days, 1),
                'trend': self._calculate_trend(categories['medication'], days)
            }
        
        return metrics
    
    def _calculate_trend(self, entries: List[Dict], days: int) -> str:
        """Calculate trend for a category"""
        if len(entries) < 2:
            return 'stable'
        
        # Split into first and second half
        mid_point = len(entries) // 2
        first_half = entries[:mid_point]
        second_half = entries[mid_point:]
        
        if len(second_half) > len(first_half):
            return 'increasing'
        elif len(second_half) < len(first_half):
            return 'decreasing'
        else:
            return 'stable'
    
    def _calculate_energy_trend(self, levels: List[int]) -> str:
        """Calculate energy trend"""
        if len(levels) < 2:
            return 'stable'
        
        # Simple trend calculation
        first_half_avg = statistics.mean(levels[:len(levels)//2])
        second_half_avg = statistics.mean(levels[len(levels)//2:])
        
        if second_half_avg > first_half_avg + 0.3:
            return 'increasing'
        elif second_half_avg < first_half_avg - 0.3:
            return 'decreasing'
        else:
            return 'stable'
    
    def _empty_chart_config(self, message: str) -> Dict[str, Any]:
        """Return empty chart configuration with message"""
        return {
            'type': 'bar',
            'data': {
                'labels': ['No Data'],
                'datasets': [{
                    'label': message,
                    'data': [0],
                    'backgroundColor': '#e2e8f0'
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    }
                }
            }
        }

# Global instance
visualization_service = PetVisualizationService()
