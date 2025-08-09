"""
Intelligent Chatbot Service with OpenAI Function Calling
Uses OpenAI Function Calling to intelligently decide when and what visualizations to generate
Includes pet data caching to avoid repeated database queries
"""

import os
import json
import openai
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import re
from collections import Counter

from firestore_store import db, get_pet_by_id
from visualization_service import PetVisualizationService
from simple_rag_service import SimplePetHealthRAGService


class IntelligentChatbotService:
    """Enhanced chatbot that uses OpenAI Function Calling for smart visualization decisions with data caching"""

    def __init__(self):
        self.openai_client = openai.OpenAI()
        self.rag_service = SimplePetHealthRAGService()
        self.visualization_service = PetVisualizationService()

        # Define available functions for OpenAI Function Calling
        self.available_functions = self._define_visualization_functions()

        # Pet data cache to avoid repeated database queries
        self.pet_data_cache = {}
        self.cache_timestamps = {}
        self.cache_expiry_minutes = 30  # Cache expires after 30 minutes

    def _is_cache_valid(self, pet_id: str) -> bool:
        """Check if cached data for pet is still valid"""
        if pet_id not in self.cache_timestamps:
            return False

        cache_time = self.cache_timestamps[pet_id]
        expiry_time = cache_time + timedelta(minutes=self.cache_expiry_minutes)
        return datetime.utcnow() < expiry_time

    async def preload_pet_data(self, pet_id: str, days: int = 30) -> Dict[str, Any]:
        """Preload and cache all pet data for efficient subsequent queries"""
        print(f"🔄 Preloading data for pet {pet_id} (last {days} days)")

        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # Get pet basic info
            pet_info = get_pet_by_id(pet_id)

            # Get analytics data
            analytics_query = (
                db.collection("pets").document(pet_id).collection("analytics").where("timestamp", ">=", cutoff_date)
            )

            analytics_data = []
            for doc in analytics_query.stream():
                data = doc.to_dict()
                analytics_data.append(data)

            # Get voice notes
            voice_query = (
                db.collection("pets").document(pet_id).collection("voice-notes").where("timestamp", ">=", cutoff_date)
            )

            voice_notes = []
            for doc in voice_query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                voice_notes.append(data)

            # Get text inputs
            text_query = db.collection("pets").document(pet_id).collection("textinput").where("timestamp", ">=", cutoff_date)

            text_inputs = []
            for doc in text_query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                text_inputs.append(data)

            # Get medical records
            records_query = db.collection("pets").document(pet_id).collection("records").where("timestamp", ">=", cutoff_date)

            medical_records = []
            for doc in records_query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                medical_records.append(data)

            # Cache all data
            cached_data = {
                "pet_info": pet_info,
                "analytics_data": analytics_data,
                "voice_notes": voice_notes,
                "text_inputs": text_inputs,
                "medical_records": medical_records,
                "days": days,
                "loaded_at": datetime.utcnow().isoformat(),
            }

            self.pet_data_cache[pet_id] = cached_data
            self.cache_timestamps[pet_id] = datetime.utcnow()

            print(f"✅ Cached data for pet {pet_id}:")
            print(f"   Analytics: {len(analytics_data)} entries")
            print(f"   Voice Notes: {len(voice_notes)} entries")
            print(f"   Text Inputs: {len(text_inputs)} entries")
            print(f"   Medical Records: {len(medical_records)} entries")

            return {
                "status": "success",
                "message": f"Preloaded data for pet {pet_id}",
                "data_summary": {
                    "analytics_entries": len(analytics_data),
                    "voice_notes": len(voice_notes),
                    "text_inputs": len(text_inputs),
                    "medical_records": len(medical_records),
                    "pet_name": pet_info.get('name', 'Unknown') if pet_info else 'Unknown',
                    "cache_valid_until": (datetime.utcnow() + timedelta(minutes=self.cache_expiry_minutes)).isoformat(),
                },
            }

        except Exception as e:
            print(f"❌ Error preloading pet data: {e}")
            return {"status": "error", "message": f"Failed to preload data: {str(e)}"}

    def get_cached_pet_data(self, pet_id: str) -> Optional[Dict]:
        """Get cached pet data if available and valid"""
        if self._is_cache_valid(pet_id):
            print(f"✅ Using cached data for pet {pet_id}")
            return self.pet_data_cache[pet_id]
        else:
            print(f"⚠️ No valid cache for pet {pet_id}")
            return None

    def clear_pet_cache(self, pet_id: str = None):
        """Clear cache for specific pet or all pets"""
        if pet_id:
            if pet_id in self.pet_data_cache:
                del self.pet_data_cache[pet_id]
                del self.cache_timestamps[pet_id]
                print(f"🗑️ Cleared cache for pet {pet_id}")
        else:
            self.pet_data_cache.clear()
            self.cache_timestamps.clear()
            print("🗑️ Cleared all pet data cache")

    def _define_visualization_functions(self) -> List[Dict]:
        """Define all available visualization functions for OpenAI Function Calling"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "generate_weekly_activity_chart",
                    "description": "Generate a line chart showing ONLY exercise and physical activity trends over the last 7 days. Use ONLY when users specifically ask about exercise trends, workout patterns, or physical activity over time. Do NOT use for daily routines or energy comparisons.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_activity_energy_correlation",
                    "description": "Generate a correlation chart comparing activity levels with energy levels over time. Use this when users ask to compare activity vs energy, show relationships between exercise and energy, or analyze how activity affects energy levels.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_energy_distribution_chart",
                    "description": "Generate a doughnut chart showing the distribution of energy levels (low, medium, high). Use this when users ask specifically about energy patterns, energy distribution, or energy level analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_diet_frequency_chart",
                    "description": "Generate a bar chart showing diet and feeding frequency over time. Use this when users ask about eating habits, meal patterns, or nutrition tracking.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_health_overview_chart",
                    "description": "Generate a comprehensive radar chart showing multiple health metrics at once. Use this when users ask for comprehensive views, daily routines overview, overall health summaries, general status, or multi-metric comparisons across different categories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_exercise_duration_histogram",
                    "description": "Generate a histogram showing exercise duration distribution. Use this when users ask about workout intensity, exercise time patterns, or physical activity analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_behavior_mood_chart",
                    "description": "Generate a chart analyzing behavior patterns and mood trends over time. Use this when users ask about behavioral changes, mood tracking, or temperament analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_social_interaction_chart",
                    "description": "Generate a chart showing social interaction frequency and patterns. Use this when users ask about social behavior, playmates, or interaction with other pets/people.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_sleep_pattern_chart",
                    "description": "Generate a chart showing sleep patterns and rest cycles. Use this when users ask about sleep quality, rest patterns, or bedtime routines.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_medical_records_timeline",
                    "description": "Generate a timeline chart of medical events and health records. Use this when users ask about medical history, vet visits, or health event tracking.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_summary_metrics",
                    "description": "Generate summary statistics and key metrics visualization. Use this when users ask for general summaries, key statistics, or overall data insights.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            }
                        },
                        "required": ["reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_dynamic_chart",
                    "description": "Generate custom charts with flexible parameters. Use this when users request specific chart types, custom axis combinations, filtered data, or unique visualizations not covered by standard functions. Examples: 'bar chart of exercise by day', 'scatter plot of energy vs duration', 'line chart of diet count by month'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chart_type": {
                                "type": "string",
                                "enum": ["line", "bar", "doughnut", "area", "scatter"],
                                "description": "Type of chart to generate",
                            },
                            "x_axis": {
                                "type": "string",
                                "enum": ["date", "category", "hour", "day_of_week", "month"],
                                "description": "X-axis data dimension",
                            },
                            "y_axis": {
                                "type": "string",
                                "enum": ["count", "duration", "level", "value", "average"],
                                "description": "Y-axis data dimension",
                            },
                            "filters": {
                                "type": "object",
                                "description": "Filters to apply to data (optional). Format: {'category': ['diet', 'exercise']}",
                            },
                            "aggregation": {
                                "type": "string",
                                "enum": ["count", "sum", "average", "max", "min"],
                                "description": "How to aggregate the data",
                            },
                            "time_period": {"type": "integer", "description": "Number of days to look back (default: 30)"},
                            "group_by": {
                                "type": "string",
                                "enum": ["category", "date", "hour", "day_of_week"],
                                "description": "Group data by this dimension for multi-series charts (optional)",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why this visualization would be helpful for the user's question",
                            },
                        },
                        "required": ["chart_type", "x_axis", "y_axis", "reason"],
                    },
                },
            },
        ]

    async def get_pet_analytics_data(self, pet_id: str, days: int = 30) -> List[Dict]:
        """Get analytics data for visualization (uses cache if available)"""
        try:
            # Try to get from cache first
            cached_data = self.get_cached_pet_data(pet_id)
            if cached_data and cached_data.get('days', 30) >= days:
                print(f"📊 Using cached analytics data ({len(cached_data['analytics_data'])} entries)")
                return cached_data['analytics_data']

            # Fallback to database query if no cache
            print(f"🔍 Cache miss - querying database for pet {pet_id}")
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            analytics_query = (
                db.collection("pets").document(pet_id).collection("analytics").where("timestamp", ">=", cutoff_date)
            )

            analytics_data = []
            for doc in analytics_query.stream():
                data = doc.to_dict()
                analytics_data.append(data)

            print(f"📊 Retrieved {len(analytics_data)} analytics entries from database")
            return analytics_data
        except Exception as e:
            print(f"Error getting analytics data: {e}")
            return []

    def _execute_visualization_function(
        self, function_name: str, analytics_data: List[Dict], function_args: Dict = None
    ) -> Optional[Dict]:
        """Execute the specified visualization function with given data"""
        try:
            if function_args is None:
                function_args = {}

            if function_name == "generate_weekly_activity_chart":
                return self.visualization_service.generate_weekly_activity_chart(analytics_data)
            elif function_name == "generate_activity_energy_correlation":
                return self.visualization_service.generate_activity_energy_correlation(analytics_data)
            elif function_name == "generate_energy_distribution_chart":
                return self.visualization_service.generate_energy_distribution_chart(analytics_data)
            elif function_name == "generate_diet_frequency_chart":
                return self.visualization_service.generate_diet_frequency_chart(analytics_data)
            elif function_name == "generate_health_overview_chart":
                return self.visualization_service.generate_health_overview_chart(analytics_data)
            elif function_name == "generate_exercise_duration_histogram":
                return self.visualization_service.generate_exercise_duration_histogram(analytics_data)
            elif function_name == "generate_behavior_mood_chart":
                return self.visualization_service.generate_behavior_mood_chart(analytics_data)
            elif function_name == "generate_social_interaction_chart":
                return self.visualization_service.generate_social_interaction_chart(analytics_data)
            elif function_name == "generate_sleep_pattern_chart":
                return self.visualization_service.generate_sleep_pattern_chart(analytics_data)
            elif function_name == "generate_medical_records_timeline":
                return self.visualization_service.generate_medical_records_timeline(analytics_data)
            elif function_name == "generate_summary_metrics":
                return self.visualization_service.generate_summary_metrics(analytics_data)
            elif function_name == "generate_dynamic_chart":
                # Extract parameters for dynamic chart
                chart_type = function_args.get('chart_type', 'line')
                x_axis = function_args.get('x_axis', 'date')
                y_axis = function_args.get('y_axis', 'count')
                filters = function_args.get('filters', None)
                aggregation = function_args.get('aggregation', 'count')
                time_period = function_args.get('time_period', 30)
                group_by = function_args.get('group_by', None)

                return self.visualization_service.generate_dynamic_chart(
                    analytics_data, chart_type, x_axis, y_axis, filters, aggregation, time_period, group_by
                )
            else:
                print(f"Unknown visualization function: {function_name}")
                return None
        except Exception as e:
            print(f"Error executing visualization function {function_name}: {e}")
            return None

    async def generate_intelligent_response(self, pet_id: str, query: str) -> Dict[str, Any]:
        """Generate intelligent response using OpenAI Function Calling for visualization decisions"""

        # Try to use cached data for better performance
        cached_data = self.get_cached_pet_data(pet_id)

        # Get RAG response first to provide context (pass cached data if available)
        if cached_data:
            print("🚀 Using cached data for RAG processing")
            rag_response = await self.rag_service.generate_rag_response_with_cache(pet_id, query, cached_data)
        else:
            print("🔍 No cache available - using standard RAG processing")
            rag_response = await self.rag_service.generate_rag_response(pet_id, query)

        # Get pet information for context (from cache if available)
        if cached_data and cached_data.get('pet_info'):
            pet_data = cached_data['pet_info']
            print("✅ Using cached pet info")
        else:
            pet_data = get_pet_by_id(pet_id)
            print("🔍 Queried pet info from database")

        pet_info = ""
        if pet_data:
            pet_info = f" for {pet_data.get('name', 'your pet')}"
            if pet_data.get('breed') and pet_data.get('animal_type'):
                pet_info += f" (a {pet_data.get('breed')} {pet_data.get('animal_type')})"

        # Create system prompt for function calling
        system_prompt = f"""You are a specialized Pet Health Assistant AI with access to comprehensive health data{pet_info}.

You have access to visualization tools that can help users understand their pet's health data better. However, your PRIMARY goal is to provide helpful, accurate text responses based on the pet's health data.

IMPORTANT: Always format your text responses using markdown formatting for better readability:
- Use **bold** for important points and key findings
- Use *italic* for emphasis and medical terms
- Use bullet points (• or -) for lists and recommendations
- Use numbered lists (1. 2. 3.) for steps or sequential information
- Use ### for section headers when organizing information
- Use `code` formatting for specific values, measurements, or technical terms
- Use > blockquotes for important warnings or veterinary advice

ONLY call visualization functions when users specifically ask for:
- Visual charts, graphs, or plots
- Trends "over time" or "patterns" they want to see visually
- Comparisons they want displayed as charts
- Data they want "shown" or "displayed" visually
- Explicit requests like "show me a chart" or "visualize"

DO NOT call visualization functions for:
- Simple summaries or overviews (provide detailed text instead)
- General questions about pet health or status
- Questions asking "how is my pet" or "summarize my pet's data"
- Informational queries that can be answered with text
- Basic health inquiries

When responding:
1. ALWAYS provide a comprehensive, helpful text response based on the available data using markdown formatting
2. Only call visualization functions if the user explicitly wants visual representations
3. Be empathetic and supportive while maintaining clinical accuracy
4. Always prioritize pet safety and recommend veterinary consultation for serious concerns
5. Use the rich health data to provide detailed, personalized insights in your text responses

For summary requests, analyze the pet's data and provide detailed text insights about:
- Activity levels and exercise patterns
- Diet and eating habits
- Energy and mood trends
- Health metrics and medication compliance
- Sleep patterns and behavior
- Recent observations and notable changes

Context from Pet's Health Data:
{rag_response.get('context_used', 'Limited context available')}"""

        try:
            # Call OpenAI with function calling enabled
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
                tools=self.available_functions,
                tool_choice="auto",  # Let the model decide when to use tools
                temperature=0.3,
                max_tokens=800,
            )

            # Process the response
            message = response.choices[0].message

            # Prepare the base response
            base_response_text = message.content or ""

            # If no text content but function calls were made, provide default text
            if not base_response_text and message.tool_calls:
                base_response_text = "I'm analyzing your pet's data and preparing visualizations to help answer your question."

            response_data = {
                "status": "success",
                "response": base_response_text,
                "sources": rag_response.get("sources", []),
                "context_used": rag_response.get("context_used", False),
                "timestamp": datetime.utcnow().isoformat(),
                "function_calls_made": [],
            }

            # Handle function calls if any were made
            if message.tool_calls:
                print(f"🔧 OpenAI requested {len(message.tool_calls)} function call(s)")

                # Get analytics data once for all visualizations
                analytics_data = await self.get_pet_analytics_data(pet_id)
                print(f"📊 Retrieved {len(analytics_data)} analytics data points")

                visualizations = {}

                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    print(f"🎯 Executing function: {function_name}")
                    print(f"   Reason: {function_args.get('reason', 'No reason provided')}")

                    # Execute the visualization function
                    if analytics_data:
                        chart_data = self._execute_visualization_function(function_name, analytics_data, function_args)
                        if chart_data:
                            visualizations[function_name] = chart_data
                            print(f"   ✅ Generated {function_name}")
                        else:
                            print(f"   ❌ Failed to generate {function_name}")
                    else:
                        print(f"   ❌ No analytics data available for {function_name}")

                    # Track function calls made
                    response_data["function_calls_made"].append(
                        {
                            "function": function_name,
                            "reason": function_args.get('reason', 'No reason provided'),
                            "success": function_name in visualizations,
                        }
                    )

                # Add visualizations to response if any were generated
                if visualizations:
                    response_data["visualizations"] = visualizations
                    response_data["data_points"] = len(analytics_data)
                    print(f"✅ Added {len(visualizations)} visualizations to response")

                    # Enhance the text response to mention the visualizations
                    if response_data["response"]:
                        response_data[
                            "response"
                        ] += f"\n\n📊 I've also prepared {len(visualizations)} visualization(s) to help you better understand the data patterns."
                else:
                    print("❌ No visualizations were generated despite function calls")
            else:
                print("🔍 No function calls were made - providing text-only response")

            return response_data

        except Exception as e:
            print(f"Error in generate_intelligent_response: {e}")
            return {
                "status": "error",
                "response": f"I'm having trouble processing your request: {str(e)}",
                "sources": rag_response.get("sources", []),
                "context_used": rag_response.get("context_used", False),
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            }
