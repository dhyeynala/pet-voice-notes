"""
AI Analytics Service for Pet Health Insights
Generates intelligent insights, recommendations, and daily routine headlines
"""

from datetime import datetime
import json
import logging
import statistics
from typing import List, Dict, Any, Optional
from collections import defaultdict, Counter

from petpulse.deps import get_llm
from petpulse.providers.llm import LegacyTask

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _mean(values):
    """Arithmetic mean as a plain float (stdlib replacement for ``np.mean``)."""
    return statistics.fmean(values)


def _parse_timestamp(value) -> Optional[datetime]:
    """Parse an ISO timestamp; ``None`` for missing or unparseable values."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class PetAnalyticsAI:
    def __init__(self):
        # The LLM is resolved per call through petpulse.deps (fake unless OPENAI_API_KEY is set).
        pass

    def generate_daily_headlines(
        self, pet_name: str, daily_data: List[Dict], historical_data: List[Dict] = None, date: str = None
    ) -> List[str]:
        """Generate AI-powered daily routine headlines"""
        try:
            # Prepare context for AI
            context = self._prepare_analytics_context(pet_name, daily_data, historical_data, date)

            prompt = f"""
            You are an expert pet health analyst creating engaging daily routine headlines for {pet_name}.
            
            Daily Activities Data:
            {json.dumps(context['daily_summary'], indent=2)}
            
            Historical Patterns:
            {json.dumps(context['patterns'], indent=2)}
            
            Generate 3-5 engaging, themed headlines about {pet_name}'s day that:
            1. Are positive and encouraging
            2. Highlight notable activities or patterns
            3. Use appropriate emojis
            4. Vary in style (playful, informative, celebratory)
            5. Reference specific metrics when interesting
            
            Examples of good headlines:
            - "🌟 {pet_name} crushed their exercise goals with 45 minutes of activity!"
            - "🍽️ Foodie day: {pet_name} tried 3 different treats and loved them all"
            - "😴 Chill vibes: {pet_name} had a perfectly relaxed low-energy day"
            - "💊 Health hero: {pet_name} took all medications on schedule"
            
            Generate headlines as a JSON array of strings.
            """

            response = get_llm().legacy_chat(
                LegacyTask.DAILY_HEADLINES,
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300,
            )

            content = response.choices[0].message.content.strip()

            # Try to parse as JSON, fallback to simple parsing
            try:
                headlines = json.loads(content)
                if isinstance(headlines, list):
                    return headlines[:5]  # Limit to 5 headlines
            except json.JSONDecodeError:
                # Fallback: extract lines that look like headlines
                lines = content.split('\n')
                headlines = [
                    line.strip().strip('"').strip("'")
                    for line in lines
                    if line.strip() and any(emoji in line for emoji in ['🌟', '🍽️', '😴', '💊', '🏃', '⚡', '❤️', '🎾', '✨'])
                ]
                return headlines[:5]

        except Exception as e:
            logger.error(f"Error generating AI headlines: {e}")
            # Fallback to simple headlines
            return self._generate_fallback_headlines(pet_name, daily_data, date)

        return self._generate_fallback_headlines(pet_name, daily_data, date)

    def generate_health_insights(self, pet_name: str, analytics_data: List[Dict], timeframe_days: int = 30) -> Dict[str, Any]:
        """Generate AI-powered health insights and recommendations"""
        try:
            context = self._prepare_health_context(pet_name, analytics_data, timeframe_days)

            prompt = f"""
            You are a veterinary health analyst providing insights for {pet_name} based on {timeframe_days} days of health data.
            
            Health Data Summary:
            {json.dumps(context, indent=2)}
            
            Provide insights in the following JSON format:
            {{
                "overall_health_score": <1-10 score>,
                "key_insights": [
                    "insight 1",
                    "insight 2"
                ],
                "recommendations": [
                    "recommendation 1",
                    "recommendation 2"
                ],
                "alerts": [
                    "alert if any concerning patterns"
                ],
                "positive_trends": [
                    "positive observation 1"
                ]
            }}
            
            Focus on:
            - Exercise patterns and adequacy
            - Diet consistency and variety
            - Energy level trends
            - Medication compliance
            - Any concerning patterns in bowel movements or behavior
            - Positive health behaviors to celebrate
            """

            response = get_llm().legacy_chat(
                LegacyTask.HEALTH_INSIGHTS,
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )

            content = response.choices[0].message.content.strip()
            insights = json.loads(content)
            return insights

        except Exception as e:
            logger.error(f"Error generating health insights: {e}")
            return self._generate_fallback_insights(pet_name, analytics_data)

    def _prepare_analytics_context(
        self, pet_name: str, daily_data: List[Dict], historical_data: List[Dict] = None, date: str = None
    ) -> Dict:
        """Prepare analytics context for AI processing"""
        # Categorize daily data
        categories = defaultdict(list)
        for entry in daily_data:
            category = entry.get('category', 'unknown')
            categories[category].append(entry)

        # Create daily summary
        daily_summary = {}
        for category, entries in categories.items():
            if category == 'diet':
                daily_summary['diet'] = {
                    'meal_count': len(entries),
                    'foods': [e.get('food', '') for e in entries],
                    'meal_types': [e.get('type', '') for e in entries],
                }
            elif category == 'exercise':
                total_duration = sum(int(e.get('duration', 0)) for e in entries)
                daily_summary['exercise'] = {
                    'session_count': len(entries),
                    'total_duration': total_duration,
                    'types': [e.get('type', '') for e in entries],
                    'avg_intensity': self._calculate_avg_intensity(entries),
                }
            elif category == 'energy_levels':
                levels = [int(e.get('level', 3)) for e in entries]
                daily_summary['energy'] = {
                    'avg_level': _mean(levels) if levels else 3,
                    'recordings': len(levels),
                    'trend': self._calculate_energy_trend(levels),
                }
            elif category == 'medication':
                daily_summary['medication'] = {
                    'doses_given': len(entries),
                    'medications': [e.get('name', '') for e in entries],
                }

        # Analyze historical patterns if available
        patterns = {}
        if historical_data:
            patterns = self._analyze_historical_patterns(historical_data)

        return {'daily_summary': daily_summary, 'patterns': patterns, 'data_completeness': len(daily_data) > 0}

    def _prepare_health_context(self, pet_name: str, analytics_data: List[Dict], timeframe_days: int) -> Dict:
        """Prepare health context for AI analysis"""
        categories = defaultdict(list)
        for entry in analytics_data:
            category = entry.get('category', 'unknown')
            categories[category].append(entry)

        context = {
            'timeframe_days': timeframe_days,
            'total_entries': len(analytics_data),
            'categories_tracked': list(categories.keys()),
        }

        # Analyze each category
        for category, entries in categories.items():
            if category == 'exercise':
                durations = [int(e.get('duration', 0)) for e in entries]
                context['exercise_analysis'] = {
                    'total_sessions': len(entries),
                    'avg_duration': _mean(durations) if durations else 0,
                    'total_duration': sum(durations),
                    'consistency': len(entries) / timeframe_days,
                    'types': list(Counter(e.get('type', '') for e in entries).keys()),
                }

            elif category == 'diet':
                context['diet_analysis'] = {
                    'total_meals': len(entries),
                    'avg_meals_per_day': len(entries) / timeframe_days,
                    'variety': len(set(e.get('food', '') for e in entries)),
                    'meal_types': list(Counter(e.get('type', '') for e in entries).keys()),
                }

            elif category == 'energy_levels':
                levels = [int(e.get('level', 3)) for e in entries]
                context['energy_analysis'] = {
                    'avg_energy': _mean(levels) if levels else 3,
                    'recordings': len(levels),
                    'high_energy_days': sum(1 for l in levels if l >= 4),
                    'low_energy_days': sum(1 for l in levels if l <= 2),
                }

            elif category == 'medication':
                context['medication_analysis'] = {
                    'total_doses': len(entries),
                    'unique_medications': len(set(e.get('name', '') for e in entries)),
                    'compliance_rate': len(entries) / timeframe_days,  # Simplified
                }

            elif category == 'bowel_movements':
                consistencies = [e.get('consistency', 'normal') for e in entries]
                context['bowel_analysis'] = {
                    'total_movements': len(entries),
                    'avg_per_day': len(entries) / timeframe_days,
                    'consistency_breakdown': dict(Counter(consistencies)),
                    'normal_percentage': (consistencies.count('normal') / len(consistencies) * 100) if consistencies else 100,
                }

        return context

    def _calculate_avg_intensity(self, exercise_entries: List[Dict]) -> str:
        """Calculate average exercise intensity"""
        intensities = [e.get('intensity', 'moderate') for e in exercise_entries]
        intensity_map = {'low': 1, 'moderate': 2, 'high': 3}
        avg_value = _mean([intensity_map.get(i, 2) for i in intensities]) if intensities else 2

        if avg_value < 1.5:
            return 'low'
        elif avg_value < 2.5:
            return 'moderate'
        else:
            return 'high'

    def _calculate_energy_trend(self, energy_levels: List[int]) -> str:
        """Calculate energy level trend"""
        if len(energy_levels) < 2:
            return 'stable'

        # Least-squares slope (stdlib replacement for np.polyfit(..., 1)[0])
        trend = statistics.linear_regression(range(len(energy_levels)), energy_levels).slope
        if trend > 0.1:
            return 'increasing'
        elif trend < -0.1:
            return 'decreasing'
        else:
            return 'stable'

    def _analyze_historical_patterns(self, historical_data: List[Dict]) -> Dict:
        """Analyze historical patterns in pet data"""
        if not historical_data:
            return {}

        # Group by category (first-seen order), parsing timestamps once.
        by_category: Dict[str, List[Optional[datetime]]] = defaultdict(list)
        for entry in historical_data:
            by_category[entry.get('category')].append(_parse_timestamp(entry.get('timestamp')))

        patterns = {}
        for category, timestamps in by_category.items():
            # Rows whose timestamp is missing or unparseable count towards frequency only.
            parsed = [ts for ts in timestamps if ts is not None]
            patterns[category] = {
                'frequency': len(timestamps),
                'most_active_hour': self._find_most_active_hour(parsed),
                'weekday_pattern': self._analyze_weekday_pattern(parsed),
            }

        return patterns

    def _find_most_active_hour(self, timestamps: List[datetime]) -> int:
        """Most common hour of day; ties go to the earliest hour. Always a plain ``int``."""
        if not timestamps:
            return 12  # Default to noon

        counts = Counter(ts.hour for ts in timestamps)
        best = max(counts.values())
        return int(min(hour for hour, count in counts.items() if count == best))

    def _analyze_weekday_pattern(self, timestamps: List[datetime]) -> Dict:
        """Weekday distribution, most common first."""
        if not timestamps:
            return {}

        weekday_counts = Counter(WEEKDAY_NAMES[ts.weekday()] for ts in timestamps).most_common()

        return {
            'most_active_day': weekday_counts[0][0],
            'distribution': {day: int(count) for day, count in weekday_counts},
        }

    def _generate_fallback_headlines(self, pet_name: str, daily_data: List[Dict], date: str) -> List[str]:
        """Generate simple fallback headlines when AI fails"""
        headlines = []
        categories = defaultdict(list)

        for entry in daily_data:
            category = entry.get('category', 'unknown')
            categories[category].append(entry)

        if categories.get('diet'):
            meal_count = len(categories['diet'])
            headlines.append(f"🍽️ {pet_name} enjoyed {meal_count} meal{'s' if meal_count != 1 else ''} today")

        if categories.get('exercise'):
            total_duration = sum(int(e.get('duration', 0)) for e in categories['exercise'])
            if total_duration > 30:
                headlines.append(f"🏃 Active day: {pet_name} exercised for {total_duration} minutes!")

        if categories.get('energy_levels'):
            levels = [int(e.get('level', 3)) for e in categories['energy_levels']]
            avg_energy = sum(levels) / len(levels) if levels else 3
            if avg_energy >= 4:
                headlines.append(f"⚡ High energy day for {pet_name}!")
            elif avg_energy <= 2:
                headlines.append(f"😴 {pet_name} had a relaxed day")

        if not headlines:
            headlines.append(f"📅 Another wonderful day in {pet_name}'s life!")

        return headlines

    def _generate_fallback_insights(self, pet_name: str, analytics_data: List[Dict]) -> Dict[str, Any]:
        """Generate simple fallback insights when AI fails"""
        categories = defaultdict(list)
        for entry in analytics_data:
            categories[entry.get('category', 'unknown')].append(entry)

        insights = {
            "overall_health_score": 7,  # Default neutral score
            "key_insights": [],
            "recommendations": [],
            "alerts": [],
            "positive_trends": [],
        }

        # Simple rule-based insights
        if categories.get('exercise'):
            total_sessions = len(categories['exercise'])
            if total_sessions >= 20:  # Over 30 days
                insights["positive_trends"].append(f"{pet_name} maintains excellent exercise consistency")
            elif total_sessions < 5:
                insights["recommendations"].append("Consider increasing exercise frequency")

        if categories.get('diet'):
            if len(categories['diet']) > 60:  # More than 2 meals per day avg
                insights["key_insights"].append("Good feeding routine established")

        return insights


# Service class exported for lazy initialization
__all__ = ['PetAnalyticsAI']
