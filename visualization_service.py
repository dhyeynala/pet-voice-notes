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
        
        if not labels or not values or len(labels) < 2 or len(values) < 2:
            return None

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
    
    def generate_activity_energy_correlation(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate correlation chart comparing activity levels with energy levels over time"""
        from collections import defaultdict
        from datetime import datetime, timedelta
        
        # Group data by day
        daily_data = defaultdict(lambda: {'activities': 0, 'energy_sum': 0, 'energy_count': 0})
        
        # Get last 14 days for better correlation analysis
        today = datetime.now()
        for i in range(14):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            daily_data[date] = {'activities': 0, 'energy_sum': 0, 'energy_count': 0}
        
        # Process analytics data
        for entry in analytics_data:
            try:
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                date = timestamp.strftime('%Y-%m-%d')
                
                if date in daily_data:
                    # Count activities (exercise, diet, social interactions, etc.)
                    if entry.get('category') in ['exercise', 'diet', 'social_interaction', 'grooming']:
                        daily_data[date]['activities'] += 1
                    
                    # Sum energy levels
                    if entry.get('category') == 'energy_levels':
                        level = entry.get('level', 0)
                        if isinstance(level, (int, float)) and 1 <= level <= 5:
                            daily_data[date]['energy_sum'] += level
                            daily_data[date]['energy_count'] += 1
            except:
                continue
        
        # Calculate averages and prepare data
        dates = []
        activity_counts = []
        energy_averages = []
        labels = []
        
        for date in sorted(daily_data.keys()):
            data = daily_data[date]
            
            # Calculate average energy for the day
            if data['energy_count'] > 0:
                avg_energy = data['energy_sum'] / data['energy_count']
                
                dates.append(date)
                activity_counts.append(data['activities'])
                energy_averages.append(round(avg_energy, 1))
                labels.append(datetime.strptime(date, '%Y-%m-%d').strftime('%a %m/%d'))
        
        if len(labels) < 3:  # Need at least 3 data points for meaningful correlation
            return None
        
        # Create dual-axis chart
        return {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Activity Count',
                        'data': activity_counts,
                        'borderColor': self.chart_colors['primary'],
                        'backgroundColor': self.chart_colors['primary'] + '30',
                        'fill': False,
                        'tension': 0.4,
                        'yAxisID': 'y'
                    },
                    {
                        'label': 'Energy Level (Avg)',
                        'data': energy_averages,
                        'borderColor': self.chart_colors['secondary'],
                        'backgroundColor': self.chart_colors['secondary'] + '30',
                        'fill': False,
                        'tension': 0.4,
                        'yAxisID': 'y1'
                    }
                ]
            },
            'options': {
                'responsive': True,
                'interaction': {
                    'mode': 'index',
                    'intersect': False
                },
                'plugins': {
                    'legend': {
                        'display': True,
                        'position': 'top'
                    },
                    'title': {
                        'display': True,
                        'text': 'Activity vs Energy Level Correlation'
                    }
                },
                'scales': {
                    'x': {
                        'display': True,
                        'title': {
                            'display': True,
                            'text': 'Date'
                        }
                    },
                    'y': {
                        'type': 'linear',
                        'display': True,
                        'position': 'left',
                        'beginAtZero': True,
                        'title': {
                            'display': True,
                            'text': 'Activity Count'
                        },
                        'ticks': {
                            'stepSize': 1
                        }
                    },
                    'y1': {
                        'type': 'linear',
                        'display': True,
                        'position': 'right',
                        'min': 1,
                        'max': 5,
                        'title': {
                            'display': True,
                            'text': 'Energy Level (1-5)'
                        },
                        'grid': {
                            'drawOnChartArea': False
                        },
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
        
        if not labels or not values or sum(values) == 0:
            return None

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
        
        if not labels or not values or sum(values) == 0:
            return None

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
        categories = ['diet', 'exercise', 'medication', 'grooming', 'energy_levels', 'daily_activity']
        category_counts = defaultdict(int)
        
        for entry in analytics_data:
            category = entry.get('category', '')
            if category in categories:
                category_counts[category] += 1
        
        # Normalize scores (0-10 scale based on activity frequency)
        max_count = max(category_counts.values()) if category_counts.values() else 1
        labels = ['Diet', 'Exercise', 'Medication', 'Grooming', 'Energy Tracking', 'Daily Activities']
        values = []
        
        for category in categories:
            count = category_counts[category]
            # Scale to 0-10, with 5 as average
            score = min(10, (count / max_count) * 10) if max_count > 0 else 0
            values.append(round(score, 1))
        
        if not labels or not values or sum(values) == 0:
            return None

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
        """Generate exercise duration histogram including daily activities"""
        # Include both exercise and daily_activity entries
        exercise_entries = [entry for entry in analytics_data if entry.get('category') in ['exercise', 'daily_activity']]
        durations = []
        
        for entry in exercise_entries:
            duration = int(entry.get('duration', 0))
            
            # For daily activities from voice notes, try to extract duration
            if duration == 0 and entry.get('category') == 'daily_activity':
                text = (entry.get('summary', '') + ' ' + entry.get('transcript', '')).lower()
                import re
                # Look for patterns like "30 minute", "1 hour", etc.
                minute_match = re.search(r'(\d+)\s*(?:minute|min)', text)
                hour_match = re.search(r'(\d+)\s*(?:hour|hr)', text)
                if minute_match:
                    duration = int(minute_match.group(1))
                elif hour_match:
                    duration = int(hour_match.group(1)) * 60
                else:
                    duration = 15  # Default duration for daily activities
            
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
    
    def generate_medical_records_timeline(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate timeline chart for medical records and health events"""
        medical_entries = [entry for entry in analytics_data if entry.get('category') in ['medical_notes', 'medication', 'health_events']]
        
        if not medical_entries:
            return self._empty_chart_config("No medical records available")
        
        # Sort by timestamp
        medical_entries.sort(key=lambda x: x.get('timestamp', ''))
        
        # Prepare timeline data
        dates = []
        events = []
        categories = []
        
        for entry in medical_entries[-10:]:  # Last 10 events
            try:
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                date_str = timestamp.strftime('%m/%d')
                dates.append(date_str)
                events.append(entry.get('summary', entry.get('notes', 'Health Event'))[:30])
                categories.append(entry.get('category', 'medical'))
            except:
                continue
        
        return {
            'type': 'line',
            'data': {
                'labels': dates,
                'datasets': [{
                    'label': 'Medical Events',
                    'data': list(range(1, len(dates) + 1)),
                    'borderColor': self.chart_colors['error'],
                    'backgroundColor': self.chart_colors['error'] + '20',
                    'pointBackgroundColor': self.chart_colors['error'],
                    'pointBorderColor': '#ffffff',
                    'pointRadius': 6,
                    'pointHoverRadius': 8,
                    'fill': False,
                    'tension': 0.1
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': False
                    },
                    'tooltip': {
                        'callbacks': {
                            'label': 'function(context) { return events[context.dataIndex]; }'
                        }
                    }
                },
                'scales': {
                    'y': {
                        'display': False
                    }
                }
            }
        }
    
    def generate_behavior_mood_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate behavior and mood analysis chart"""
        behavior_entries = [entry for entry in analytics_data if entry.get('category') in ['behavior', 'mood', 'daily_activity']]
        
        if not behavior_entries:
            return self._empty_chart_config("No behavior data available")
        
        # Analyze behavior patterns
        behavior_keywords = {
            'happy': ['happy', 'excited', 'playful', 'joy', 'good mood'],
            'calm': ['calm', 'relaxed', 'peaceful', 'quiet', 'serene'],
            'anxious': ['anxious', 'nervous', 'worried', 'stress', 'fear'],
            'active': ['active', 'energetic', 'playful', 'running', 'jumping'],
            'tired': ['tired', 'sleepy', 'lethargic', 'rest', 'sleep']
        }
        
        behavior_counts = defaultdict(int)
        
        for entry in behavior_entries:
            text = (entry.get('summary', '') + ' ' + entry.get('notes', '')).lower()
            for behavior, keywords in behavior_keywords.items():
                if any(keyword in text for keyword in keywords):
                    behavior_counts[behavior] += 1
        
        if not behavior_counts:
            return self._empty_chart_config("No behavior patterns detected")
        
        labels = list(behavior_counts.keys())
        values = list(behavior_counts.values())
        colors = [
            self.chart_colors['success'],  # happy
            self.chart_colors['info'],     # calm
            self.chart_colors['warning'],  # anxious
            self.chart_colors['primary'],  # active
            self.chart_colors['secondary'] # tired
        ][:len(labels)]
        
        return {
            'type': 'doughnut',
            'data': {
                'labels': [label.title() for label in labels],
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
    
    def generate_social_interaction_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate social interaction frequency chart"""
        social_entries = [entry for entry in analytics_data if entry.get('category') in ['social', 'daily_activity']]
        
        if not social_entries:
            return self._empty_chart_config("No social interaction data available")
        
        # Analyze social interactions
        social_keywords = {
            'play_with_other_dogs': ['play with dog', 'dog friend', 'dog park', 'other dogs'],
            'play_with_other_cats': ['play with cat', 'cat friend', 'other cats'],
            'human_interaction': ['play with human', 'family', 'owner', 'petting', 'cuddling'],
            'alone_time': ['alone', 'independent', 'solo', 'by myself'],
            'training': ['training', 'commands', 'obedience', 'learning']
        }
        
        social_counts = defaultdict(int)
        
        for entry in social_entries:
            text = (entry.get('summary', '') + ' ' + entry.get('notes', '')).lower()
            for interaction, keywords in social_keywords.items():
                if any(keyword in text for keyword in keywords):
                    social_counts[interaction] += 1
        
        if not social_counts:
            return self._empty_chart_config("No social interaction patterns detected")
        
        labels = list(social_counts.keys())
        values = list(social_counts.values())
        
        return {
            'type': 'bar',
            'data': {
                'labels': [label.replace('_', ' ').title() for label in labels],
                'datasets': [{
                    'label': 'Interactions',
                    'data': values,
                    'backgroundColor': [
                        self.chart_colors['success'],
                        self.chart_colors['info'],
                        self.chart_colors['warning'],
                        self.chart_colors['secondary'],
                        self.chart_colors['purple']
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
    
    def generate_sleep_pattern_chart(self, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate sleep pattern analysis chart"""
        sleep_entries = [entry for entry in analytics_data if entry.get('category') in ['sleep', 'daily_activity']]
        
        if not sleep_entries:
            return self._empty_chart_config("No sleep data available")
        
        # Analyze sleep patterns
        sleep_keywords = {
            'deep_sleep': ['deep sleep', 'sound sleep', 'peaceful sleep'],
            'light_sleep': ['light sleep', 'restless', 'waking up'],
            'naps': ['nap', 'short sleep', 'rest'],
            'night_sleep': ['night sleep', 'bedtime', 'overnight'],
            'day_sleep': ['day sleep', 'daytime rest']
        }
        
        sleep_counts = defaultdict(int)
        
        for entry in sleep_entries:
            text = (entry.get('summary', '') + ' ' + entry.get('notes', '')).lower()
            for sleep_type, keywords in sleep_keywords.items():
                if any(keyword in text for keyword in keywords):
                    sleep_counts[sleep_type] += 1
        
        # Only proceed if there are at least 2 types
        if not sleep_counts or len(sleep_counts) < 2:
            return None
        labels = list(sleep_counts.keys())
        values = list(sleep_counts.values())
        if not labels or not values or len(labels) < 2 or len(values) < 2:
            return None

        return {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': 'Sleep Pattern',
                    'data': values,
                    'borderColor': '#3182ce',
                    'backgroundColor': '#3182ce20',
                    'fill': True,
                    'tension': 0.4
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {'display': False}
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'ticks': {'stepSize': 1}
                    }
                }
            }
        }

    def generate_dynamic_chart(self, analytics_data: List[Dict], chart_type: str, 
                              x_axis: str, y_axis: str, filters: Dict = None, 
                              aggregation: str = "count", time_period: int = 30,
                              group_by: str = None) -> Dict[str, Any]:
        """
        Dynamic Visualization Engine - Generate custom charts based on parameters
        
        Args:
            chart_type: 'line', 'bar', 'doughnut', 'radar', 'scatter', 'area'
            x_axis: 'date', 'category', 'hour', 'day_of_week', 'month'
            y_axis: 'count', 'duration', 'level', 'value', 'average'
            filters: {'category': ['diet', 'exercise'], 'level': [3, 4, 5]}
            aggregation: 'count', 'sum', 'average', 'max', 'min'
            time_period: days to look back
            group_by: 'category', 'date', 'hour', 'day_of_week'
        """
        from collections import defaultdict
        from datetime import datetime, timedelta
        import calendar
        
        try:
            # Filter data by time period
            cutoff_date = datetime.now() - timedelta(days=time_period)
            filtered_data = []
            
            for entry in analytics_data:
                try:
                    timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                    if timestamp >= cutoff_date:
                        filtered_data.append(entry)
                except:
                    continue
            
            # Apply filters
            if filters:
                for filter_key, filter_values in filters.items():
                    if isinstance(filter_values, list):
                        filtered_data = [e for e in filtered_data if e.get(filter_key) in filter_values]
                    else:
                        filtered_data = [e for e in filtered_data if e.get(filter_key) == filter_values]
            
            if not filtered_data:
                return None
            
            # Process data based on x_axis and y_axis
            processed_data = self._process_dynamic_data(filtered_data, x_axis, y_axis, aggregation, group_by)
            
            if not processed_data:
                return None
            
            # Generate chart configuration based on chart_type
            return self._build_dynamic_chart(processed_data, chart_type, x_axis, y_axis, aggregation, group_by)
            
        except Exception as e:
            print(f"Error in dynamic chart generation: {e}")
            return None
    
    def _process_dynamic_data(self, data: List[Dict], x_axis: str, y_axis: str, 
                             aggregation: str, group_by: str = None) -> Dict:
        """Process data for dynamic visualization"""
        from collections import defaultdict
        from datetime import datetime
        import calendar
        
        # Initialize data structure
        if group_by:
            result = defaultdict(lambda: defaultdict(list))
        else:
            result = defaultdict(list)
        
        for entry in data:
            try:
                # Get x-axis value
                x_val = self._extract_x_value(entry, x_axis)
                if x_val is None:
                    continue
                
                # Get y-axis value
                y_val = self._extract_y_value(entry, y_axis)
                if y_val is None:
                    continue
                
                # Store data
                if group_by:
                    group_val = entry.get(group_by, 'Other')
                    result[group_val][x_val].append(y_val)
                else:
                    result[x_val].append(y_val)
                    
            except Exception as e:
                continue
        
        # Apply aggregation
        return self._apply_aggregation(result, aggregation, group_by is not None)
    
    def _extract_x_value(self, entry: Dict, x_axis: str):
        """Extract x-axis value based on type"""
        try:
            if x_axis == 'date':
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                return timestamp.strftime('%Y-%m-%d')
            elif x_axis == 'hour':
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                return timestamp.hour
            elif x_axis == 'day_of_week':
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                return timestamp.strftime('%A')
            elif x_axis == 'month':
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                return timestamp.strftime('%B')
            elif x_axis == 'category':
                return entry.get('category', 'Unknown')
            else:
                return entry.get(x_axis)
        except:
            return None
    
    def _extract_y_value(self, entry: Dict, y_axis: str):
        """Extract y-axis value based on type"""
        try:
            if y_axis == 'count':
                return 1
            elif y_axis == 'duration':
                return float(entry.get('duration', 0))
            elif y_axis == 'level':
                return float(entry.get('level', 0))
            elif y_axis == 'value':
                return float(entry.get('value', 0))
            else:
                val = entry.get(y_axis)
                return float(val) if val is not None else None
        except:
            return None
    
    def _apply_aggregation(self, data: Dict, aggregation: str, is_grouped: bool) -> Dict:
        """Apply aggregation to the processed data"""
        result = {}
        
        if is_grouped:
            for group, group_data in data.items():
                result[group] = {}
                for x_val, y_vals in group_data.items():
                    if aggregation == 'count':
                        result[group][x_val] = len(y_vals)
                    elif aggregation == 'sum':
                        result[group][x_val] = sum(y_vals)
                    elif aggregation == 'average':
                        result[group][x_val] = sum(y_vals) / len(y_vals) if y_vals else 0
                    elif aggregation == 'max':
                        result[group][x_val] = max(y_vals) if y_vals else 0
                    elif aggregation == 'min':
                        result[group][x_val] = min(y_vals) if y_vals else 0
        else:
            for x_val, y_vals in data.items():
                if aggregation == 'count':
                    result[x_val] = len(y_vals)
                elif aggregation == 'sum':
                    result[x_val] = sum(y_vals)
                elif aggregation == 'average':
                    result[x_val] = sum(y_vals) / len(y_vals) if y_vals else 0
                elif aggregation == 'max':
                    result[x_val] = max(y_vals) if y_vals else 0
                elif aggregation == 'min':
                    result[x_val] = min(y_vals) if y_vals else 0
        
        return result
    
    def _build_dynamic_chart(self, data: Dict, chart_type: str, x_axis: str, 
                            y_axis: str, aggregation: str, group_by: str = None) -> Dict:
        """Build Chart.js configuration for dynamic chart"""
        
        # Determine if data is grouped
        is_grouped = group_by is not None and any(isinstance(v, dict) for v in data.values())
        
        # Build labels and datasets
        if is_grouped:
            # Multi-series chart
            all_x_values = set()
            for group_data in data.values():
                all_x_values.update(group_data.keys())
            labels = sorted(list(all_x_values))
            
            datasets = []
            colors = list(self.chart_colors.values())
            
            for i, (group_name, group_data) in enumerate(data.items()):
                color = colors[i % len(colors)]
                dataset_data = [group_data.get(label, 0) for label in labels]
                
                dataset = {
                    'label': str(group_name).title(),
                    'data': dataset_data,
                    'borderColor': color,
                    'backgroundColor': color + ('30' if chart_type in ['line', 'area'] else ''),
                }
                
                if chart_type == 'line':
                    dataset.update({'fill': False, 'tension': 0.4})
                elif chart_type == 'area':
                    dataset.update({'fill': True, 'tension': 0.4})
                    
                datasets.append(dataset)
        else:
            # Single series chart
            labels = list(data.keys())
            values = list(data.values())
            
            # Sort by labels if they're dates or numeric
            try:
                if x_axis == 'date':
                    sorted_pairs = sorted(zip(labels, values), key=lambda x: datetime.strptime(x[0], '%Y-%m-%d'))
                elif x_axis == 'hour':
                    sorted_pairs = sorted(zip(labels, values), key=lambda x: x[0])
                else:
                    sorted_pairs = list(zip(labels, values))
                
                labels, values = zip(*sorted_pairs) if sorted_pairs else ([], [])
                labels, values = list(labels), list(values)
            except:
                pass
            
            dataset = {
                'label': f'{y_axis.title()} by {x_axis.title()}',
                'data': values,
                'borderColor': self.chart_colors['primary'],
                'backgroundColor': self.chart_colors['primary'] + ('30' if chart_type in ['line', 'area'] else ''),
            }
            
            if chart_type == 'line':
                dataset.update({'fill': False, 'tension': 0.4})
            elif chart_type == 'area':
                dataset.update({'fill': True, 'tension': 0.4})
            elif chart_type == 'doughnut':
                dataset['backgroundColor'] = list(self.chart_colors.values())[:len(values)]
                
            datasets = [dataset]
        
        # Build chart configuration
        config = {
            'type': chart_type if chart_type != 'area' else 'line',
            'data': {
                'labels': [str(label) for label in labels],
                'datasets': datasets
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {
                        'display': chart_type == 'doughnut' or is_grouped
                    },
                    'title': {
                        'display': True,
                        'text': f'{y_axis.title()} {aggregation.title()} by {x_axis.title()}'
                    }
                },
                'scales': self._get_dynamic_scales(chart_type, x_axis, y_axis)
            }
        }
        
        return config
    
    def _get_dynamic_scales(self, chart_type: str, x_axis: str, y_axis: str) -> Dict:
        """Get appropriate scales for the chart type"""
        if chart_type in ['doughnut']:
            return {}
        
        scales = {
            'x': {
                'display': True,
                'title': {
                    'display': True,
                    'text': x_axis.replace('_', ' ').title()
                }
            },
            'y': {
                'display': True,
                'beginAtZero': True,
                'title': {
                    'display': True,
                    'text': y_axis.replace('_', ' ').title()
                }
            }
        }
        
        # Special handling for specific axis types
        if y_axis == 'level':
            scales['y'].update({'min': 1, 'max': 5, 'ticks': {'stepSize': 1}})
        elif y_axis in ['count', 'duration']:
            scales['y'].update({'ticks': {'stepSize': 1}})
        
        return scales

# Service class exported for lazy initialization
__all__ = ['PetVisualizationService']
