"""
Simplified RAG Service for Pet Health Assistant
Uses basic similarity without heavy ML dependencies to avoid NumPy conflicts
"""

import os
import json
import openai
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re
import math
from collections import Counter

print("🔍 Starting import of simple_rag_service dependencies...")

try:
    from firestore_store import db, get_pet_by_id
    print("✅ firestore_store imported successfully")
except Exception as e:
    print(f"❌ firestore_store import failed: {e}")

print("🏗️ Defining SimplePetHealthRAGService class...")

try:
    class SimplePetHealthRAGService:
        """Simplified RAG Service using basic text similarity without heavy ML dependencies"""
        
        def __init__(self):
            print("🔧 Initializing SimplePetHealthRAGService...")
            # OpenAI client
            openai.api_key = os.getenv("OPENAI_API_KEY")
            self.client = openai.OpenAI()
            
            # API keys for breed information
            self.dog_api_key = os.getenv("DOG_API_KEY")
            self.cat_api_key = os.getenv("CAT_API_KEY")
            
            # Veterinary knowledge base
            self.vet_knowledge = self._load_veterinary_knowledge()
            
            # Breed data cache to avoid repeated API calls
            self.breed_cache = {}
            print("✅ SimplePetHealthRAGService initialized successfully")
        
        def _load_veterinary_knowledge(self) -> List[Dict]:
            """Load veterinary knowledge base"""
            return [
                {
                    "title": "Limping in Dogs",
                    "content": "Limping can indicate injury, arthritis, hip dysplasia, or paw problems. Look for swelling, heat, or reluctance to bear weight. Sudden limping may indicate acute injury, while gradual onset suggests chronic conditions.",
                    "category": "Orthopedic",
                    "keywords": ["limp", "limping", "favoring leg", "difficulty walking", "pain walking", "injured leg"],
                    "severity": "moderate"
                },
                {
                    "title": "Lethargy in Pets",
                    "content": "Lethargy or decreased energy can be caused by infections, pain, metabolic disorders, heart disease, or depression. Monitor for accompanying symptoms like loss of appetite, vomiting, or fever.",
                    "category": "General Health",
                    "keywords": ["tired", "low energy", "sleepy", "inactive", "lethargic", "no energy"],
                    "severity": "moderate"
                },
                {
                    "title": "Digestive Issues",
                    "content": "Vomiting, diarrhea, and loss of appetite can indicate dietary indiscretion, food allergies, parasites, or serious conditions like bloat. Monitor frequency and consistency of symptoms.",
                    "category": "Gastrointestinal",
                    "keywords": ["vomiting", "diarrhea", "loss of appetite", "stomach upset", "nausea", "not eating"],
                    "severity": "moderate"
                },
                {
                    "title": "Respiratory Symptoms",
                    "content": "Coughing, difficulty breathing, or wheezing may indicate respiratory infections, heart disease, allergies, or foreign objects. Watch for blue gums or excessive panting.",
                    "category": "Respiratory",
                    "keywords": ["coughing", "breathing difficulty", "wheezing", "panting", "shortness of breath"],
                    "severity": "high"
                },
                {
                    "title": "Behavioral Changes",
                    "content": "Sudden changes in behavior, aggression, or hiding can indicate pain, anxiety, cognitive dysfunction, or illness. Note any triggers or patterns in the behavior.",
                    "category": "Behavioral",
                    "keywords": ["aggression", "hiding", "behavior change", "anxiety", "depression", "mood change"],
                    "severity": "moderate"
                },
                {
                    "title": "Skin and Coat Issues",
                    "content": "Excessive scratching, hair loss, redness, or skin irritation may indicate allergies, parasites, infections, or hormonal imbalances. Check for fleas, ticks, or hot spots.",
                    "category": "Dermatological",
                    "keywords": ["scratching", "itching", "hair loss", "red skin", "rash", "hot spots"],
                    "severity": "low"
                },
                {
                    "title": "Eye Problems",
                    "content": "Discharge, redness, cloudiness, or squinting can indicate infections, injuries, allergies, or serious conditions like glaucoma. Never ignore sudden vision changes.",
                    "category": "Ophthalmology",
                    "keywords": ["eye discharge", "red eyes", "squinting", "cloudy eyes", "vision problems"],
                    "severity": "moderate"
                },
                {
                    "title": "Urinary Issues",
                    "content": "Frequent urination, straining, blood in urine, or accidents indoors may indicate UTIs, bladder stones, diabetes, or kidney disease. Monitor water intake and output.",
                    "category": "Urogenital",
                    "keywords": ["frequent urination", "straining", "blood in urine", "accidents", "drinking more"],
                    "severity": "moderate"
                },
                {
                    "title": "Weight Changes",
                    "content": "Sudden weight loss or gain can indicate various health issues including diabetes, thyroid problems, heart disease, or cancer. Regular weight monitoring is important.",
                    "category": "Metabolic",
                    "keywords": ["weight loss", "weight gain", "loss of appetite", "increased appetite"],
                    "severity": "moderate"
                },
                {
                    "title": "Emergency Signs",
                    "content": "Seizures, collapse, difficulty breathing, bloated abdomen, repeated vomiting, or pale gums require immediate veterinary attention. These can be life-threatening.",
                    "category": "Emergency",
                    "keywords": ["seizure", "collapse", "bloated abdomen", "pale gums", "emergency", "severe"],
                    "severity": "critical"
                }
            ]
        
        def _simple_text_similarity(self, text1: str, text2: str) -> float:
            """Calculate simple text similarity using word overlap"""
            # Clean and tokenize
            words1 = set(re.findall(r'\w+', text1.lower()))
            words2 = set(re.findall(r'\w+', text2.lower()))
            
            # Calculate Jaccard similarity
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            
            if union == 0:
                return 0.0
            
            return intersection / union
        
        def _tf_idf_similarity(self, query: str, documents: List[str]) -> List[float]:
            """Simple TF-IDF similarity calculation"""
            # Tokenize query
            query_words = re.findall(r'\w+', query.lower())
            
            similarities = []
            for doc in documents:
                doc_words = re.findall(r'\w+', doc.lower())
                
                # Calculate term frequency
                query_tf = Counter(query_words)
                doc_tf = Counter(doc_words)
                
                # Calculate similarity score
                score = 0
                for word in query_words:
                    if word in doc_tf:
                        score += query_tf[word] * doc_tf[word]
                
                # Normalize by document length
                if len(doc_words) > 0:
                    score = score / math.sqrt(len(doc_words))
                
                similarities.append(score)
            
            return similarities
        
        async def get_pet_data_for_rag(self, pet_id: str, days: int = 30) -> List[Dict]:
            """Retrieve pet data for RAG context"""
            documents = []
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            try:
                # Voice notes
                voice_query = db.collection("pets").document(pet_id).collection("voice-notes").where(
                    "timestamp", ">=", cutoff_date
                )
                
                for doc in voice_query.stream():
                    data = doc.to_dict()
                    content = f"Voice note: {data.get('transcript', '')} Summary: {data.get('summary', '')}"
                    
                    documents.append({
                        "content": content,
                        "type": "voice_note",
                        "timestamp": data.get("timestamp"),
                        "summary": data.get("summary"),
                        "source_id": doc.id
                    })
                
                # Text input
                text_query = db.collection("pets").document(pet_id).collection("textinput").where(
                    "timestamp", ">=", cutoff_date
                )
                
                for doc in text_query.stream():
                    data = doc.to_dict()
                    content = f"Text input: {data.get('input', '')} Summary: {data.get('summary', '')}"
                    
                    documents.append({
                        "content": content,
                        "type": "text_input",
                        "timestamp": data.get("timestamp"),
                        "summary": data.get("summary"),
                        "content_type": data.get("content_type"),
                        "source_id": doc.id
                    })
                
                # Medical records (PDFs)
                records_query = db.collection("pets").document(pet_id).collection("records").where(
                    "timestamp", ">=", cutoff_date
                )
                
                for doc in records_query.stream():
                    data = doc.to_dict()
                    content = f"Medical record: {data.get('summary', '')}"
                    
                    documents.append({
                        "content": content,
                        "type": "medical_record",
                        "timestamp": data.get("timestamp"),
                        "summary": data.get("summary"),
                        "file_name": data.get("file_name"),
                        "source_id": doc.id
                    })
                
                # Analytics data
                analytics_query = db.collection("pets").document(pet_id).collection("analytics").where(
                    "timestamp", ">=", cutoff_date
                )
                
                for doc in analytics_query.stream():
                    data = doc.to_dict()
                    
                    # Build comprehensive content from analytics data
                    category = data.get('category', 'unknown')
                    content_parts = [f"Health tracking ({category})"]
                    
                    # Add specific details based on category
                    if category == 'diet':
                        content_parts.append(f"Food: {data.get('food', '')}, Type: {data.get('type', '')}, Quantity: {data.get('quantity', '')}")
                    elif category == 'exercise':
                        content_parts.append(f"Activity: {data.get('type', '')}, Duration: {data.get('duration', '')} min, Intensity: {data.get('intensity', '')}")
                    elif category == 'medication':
                        content_parts.append(f"Medication: {data.get('name', '')}, Dose: {data.get('dose', '')}, Time: {data.get('time', '')}")
                    elif category == 'weight':
                        content_parts.append(f"Weight: {data.get('value', '')} {data.get('unit', '')}, Method: {data.get('method', '')}")
                    elif category == 'mood':
                        content_parts.append(f"Mood level: {data.get('level', '')}/5, Triggers: {data.get('triggers', '')}")
                    elif category == 'energy_levels':
                        content_parts.append(f"Energy level: {data.get('level', '')}/5")
                    elif category == 'sleep':
                        content_parts.append(f"Duration: {data.get('duration', '')} hours, Quality: {data.get('quality', '')}")
                    elif category == 'grooming':
                        content_parts.append(f"Type: {data.get('type', '')}, Duration: {data.get('duration', '')} min")
                    elif category == 'bowel_movements':
                        content_parts.append(f"Consistency: {data.get('consistency', '')}, Time: {data.get('time', '')}")
                    
                    # Add notes if available
                    notes = data.get('notes', '')
                    if notes and notes.strip():
                        content_parts.append(f"Notes: {notes}")
                    
                    # Add timestamp info
                    timestamp = data.get('timestamp', '')
                    if timestamp:
                        content_parts.append(f"Recorded: {timestamp[:10]}")  # Just date part
                    
                    content = ". ".join(filter(None, content_parts))
                    
                    documents.append({
                        "content": content,
                        "type": "analytics",
                        "category": data.get("category"),
                        "timestamp": data.get("timestamp"),
                        "notes": data.get("notes"),
                        "source_id": doc.id
                    })
                
                print(f"Retrieved {len(documents)} documents for pet {pet_id}")
                return documents
                
            except Exception as e:
                print(f"Error retrieving pet data: {e}")
                return []
        
        def search_knowledge_base(self, query: str, top_k: int = 3) -> List[Dict]:
            """Search veterinary knowledge base using simple similarity"""
            results = []
            
            for knowledge in self.vet_knowledge:
                # Combine all searchable text
                searchable_text = f"{knowledge['title']} {knowledge['content']} {' '.join(knowledge['keywords'])}"
                
                # Calculate similarity
                similarity = self._simple_text_similarity(query, searchable_text)
                
                # Check for direct keyword matches
                keyword_matches = sum(1 for keyword in knowledge['keywords'] if keyword.lower() in query.lower())
                if keyword_matches > 0:
                    similarity += keyword_matches * 0.2  # Boost for keyword matches
                
                results.append({
                    "knowledge": knowledge,
                    "score": similarity
                })
            
            # Sort by score and return top results
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        
        def similarity_search(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
            """Search pet documents using simple similarity"""
            if not documents:
                return []
            
            # Extract document texts
            doc_texts = [doc["content"] for doc in documents]
            
            # Calculate similarities
            similarities = self._tf_idf_similarity(query, doc_texts)
            
            # Create results with scores
            results = []
            for i, (doc, score) in enumerate(zip(documents, similarities)):
                results.append({
                    "document": doc,
                    "score": score,
                    "source_type": doc.get("type", "unknown")
                })
            
            # Sort by score and return top results
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        
        async def generate_rag_response(self, pet_id: str, query: str, include_context: bool = True) -> Dict[str, Any]:
            """Generate RAG-enhanced response for pet health query"""
            try:
                context_documents = []
                knowledge_results = []
                breed_info = {}
                
                # Get pet information for breed-specific context
                pet_data = get_pet_by_id(pet_id)
                if pet_data and pet_data.get("breed") and pet_data.get("animal_type"):
                    breed_info = await self.get_breed_information(
                        pet_data.get("breed"), 
                        pet_data.get("animal_type")
                    )
                
                # Always search the knowledge base for general veterinary information
                knowledge_results = self.search_knowledge_base(query, top_k=3)
                for kr in knowledge_results:
                    context_documents.append({
                        "document": {
                            "content": kr["knowledge"]["content"],
                            "type": "knowledge_base",
                            "title": kr["knowledge"]["title"],
                            "category": kr["knowledge"]["category"]
                        },
                        "score": kr["score"],
                        "source_type": "knowledge_base"
                    })
                
                if include_context and pet_data:
                    # Get pet data only if pet exists
                    pet_documents = await self.get_pet_data_for_rag(pet_id)
                if include_context and pet_data:
                    # Get pet data only if pet exists
                    pet_documents = await self.get_pet_data_for_rag(pet_id)
                    
                    # Search pet data
                    pet_results = self.similarity_search(query, pet_documents, top_k=5)
                    context_documents.extend(pet_results)
                
                # Add breed information to context if available (regardless of pet_data)
                if breed_info:
                    breed_content = self._format_breed_info_for_context(breed_info, pet_data.get("animal_type", "") if pet_data else "")
                    context_documents.append({
                        "document": {
                            "content": breed_content,
                            "type": "breed_information",
                            "breed": pet_data.get("breed", "") if pet_data else "",
                            "animal_type": pet_data.get("animal_type", "") if pet_data else ""
                        },
                        "score": 1.0,  # High relevance for breed info
                        "source_type": "breed_api"
                    })
                
                # Always generate an intelligent response, even without pet data
                context_text = self._prepare_context(context_documents)
                response = await self._generate_gpt_response(query, context_text, pet_id, pet_data)
                
                # Prepare sources
                sources = [
                    {
                        "type": result["source_type"],
                        "content": result["document"]["content"][:200] + "..." if len(result["document"]["content"]) > 200 else result["document"]["content"],
                        "score": result["score"],
                        "metadata": {k: v for k, v in result["document"].items() if k != "content"}
                    }
                    for result in context_documents[:5]
                ]
                
                return {
                    "response": response,
                    "sources": sources,
                    "context_used": len(context_documents) > 0,
                    "breed_info_used": bool(breed_info)
                }
                
            except Exception as e:
                print(f"Error generating RAG response: {e}")
                return {
                    "response": "I'm sorry, I encountered an error processing your request. Please try again.",
                    "sources": [],
                    "context_used": False,
                    "breed_info_used": False
                }
        
        def _prepare_context(self, results: List[Dict]) -> str:
            """Prepare context from search results for GPT"""
            if not results:
                return ""
            
            context_parts = []
            for result in results:
                source_type = result["source_type"]
                content = result["document"]["content"]
                
                context_parts.append(f"[{source_type.upper()}] {content}")
            
            return "\n\n".join(context_parts)
        
        async def _generate_gpt_response(self, query: str, context: str, pet_id: str, pet_data: Dict[str, Any] = None) -> str:
            """Generate response using GPT with RAG context"""
            
            # Build pet information for context
            pet_info = ""
            if pet_data:
                pet_name = pet_data.get("name", "Unknown")
                pet_breed = pet_data.get("breed", "Unknown")
                pet_type = pet_data.get("animal_type", "pet")
                pet_info = f"\nPet Information: {pet_name} is a {pet_breed} {pet_type}."
                
                if pet_data.get("age"):
                    pet_info += f" Age: {pet_data.get('age')}"
                if pet_data.get("weight"):
                    pet_info += f" Weight: {pet_data.get('weight')}"
                if pet_data.get("color"):
                    pet_info += f" Color: {pet_data.get('color')}"
            
            system_prompt = f"""You are a specialized Pet Health Assistant AI with access to veterinary knowledge and the complete health history for pet ID: {pet_id}.{pet_info}

Your capabilities include:
- Analyzing health patterns and trends from tracking data
- Providing veterinary insights based on symptoms and behavior
- Offering health recommendations based on historical data and breed-specific knowledge
- Identifying potential concerns from health tracking
- Generating comprehensive health reports and summaries
- Utilizing breed-specific health information for more targeted advice

Guidelines:
- When asked about patterns, analyze the provided health tracking data for trends, frequencies, and changes over time
- Look for patterns in diet, exercise, mood, energy levels, weight changes, and behavioral indicators
- Compare recent data to historical patterns when available
- Provide specific insights based on the actual data provided in the context
- Consider breed-specific health predispositions when available
- Always prioritize pet safety and recommend veterinary consultation for serious concerns
- Be empathetic and supportive while maintaining clinical accuracy
- If you see concerning patterns or sudden changes, highlight them appropriately
- If emergency signs are mentioned, emphasize immediate veterinary care
- When breed information is available, incorporate breed-specific health considerations and temperament traits

IMPORTANT: When analyzing patterns, focus on the specific data provided in the context. If health tracking data is available, analyze it thoroughly for:
- Frequency and consistency of activities (diet, exercise, etc.)
- Changes in energy levels, mood, or behavior over time
- Weight trends and fluctuations
- Medication compliance patterns
- Sleep and activity patterns
- Any notable variations or concerning trends
- Breed-specific health considerations and predispositions

Context from Pet's Health Data, Veterinary Knowledge, and Breed Information:
{context}

Remember: You are not replacing veterinary care but providing informed insights based on the pet's data, breed characteristics, and veterinary knowledge."""

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ],
                    temperature=0.3,
                    max_tokens=800
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                print(f"Error generating GPT response: {e}")
                return "I'm having trouble generating a response right now. Please try again or consult your veterinarian for immediate concerns."

        def _get_breed_health_info(self, breed_name: str, animal_type: str) -> str:
            """Get breed-specific health considerations (can be expanded with more detailed info)"""
            # This could be expanded with a more comprehensive database of breed health issues
            common_health_issues = {
                "dog": {
                    "german shepherd": "Hip dysplasia, elbow dysplasia, bloat, degenerative myelopathy",
                    "golden retriever": "Hip dysplasia, elbow dysplasia, heart disease, cancer",
                    "labrador retriever": "Hip dysplasia, elbow dysplasia, eye conditions, obesity",
                    "bulldog": "Brachycephalic airway syndrome, hip dysplasia, cherry eye",
                    "poodle": "Hip dysplasia, progressive retinal atrophy, epilepsy, bloat",
                    "beagle": "Hip dysplasia, epilepsy, hypothyroidism, cherry eye",
                    "rottweiler": "Hip dysplasia, elbow dysplasia, heart conditions, cancer"
                },
                "cat": {
                    "persian": "Polycystic kidney disease, respiratory issues, eye problems",
                    "maine coon": "Hypertrophic cardiomyopathy, hip dysplasia, spinal muscular atrophy",
                    "siamese": "Asthma, dental issues, progressive retinal atrophy",
                    "ragdoll": "Hypertrophic cardiomyopathy, bladder stones, hairballs",
                    "british shorthair": "Hypertrophic cardiomyopathy, polycystic kidney disease",
                    "bengal": "Progressive retinal atrophy, hypertrophic cardiomyopathy",
                    "abyssinian": "Gingivitis, progressive retinal atrophy, pyruvate kinase deficiency"
                }
            }
            
            breed_lower = breed_name.lower()
            if animal_type in common_health_issues and breed_lower in common_health_issues[animal_type]:
                return common_health_issues[animal_type][breed_lower]
            
            return "Monitor for general health issues common to this breed. Consult with your veterinarian for breed-specific health screening recommendations."
        
        def _format_breed_info_for_context(self, breed_info: Dict[str, Any], animal_type: str) -> str:
            """Format breed information for use in RAG context"""
            if not breed_info:
                return ""
            
            formatted_parts = []
            
            name = breed_info.get("name", "")
            if name:
                formatted_parts.append(f"Breed: {name}")
            
            if animal_type.lower() == "dog":
                temperament = breed_info.get("temperament", "")
                if temperament:
                    formatted_parts.append(f"Temperament: {temperament}")
                
                bred_for = breed_info.get("bred_for", "")
                if bred_for:
                    formatted_parts.append(f"Originally bred for: {bred_for}")
                
                breed_group = breed_info.get("breed_group", "")
                if breed_group:
                    formatted_parts.append(f"Breed group: {breed_group}")
            
            elif animal_type.lower() == "cat":
                temperament = breed_info.get("temperament", "")
                if temperament:
                    formatted_parts.append(f"Temperament: {temperament}")
                
                energy_level = breed_info.get("energy_level", "")
                if energy_level:
                    formatted_parts.append(f"Energy level: {energy_level}/5")
                
                grooming = breed_info.get("grooming", "")
                if grooming:
                    formatted_parts.append(f"Grooming needs: {grooming}/5")
            
            life_span = breed_info.get("life_span", "")
            if life_span:
                formatted_parts.append(f"Life span: {life_span}")
            
            weight = breed_info.get("weight", "")
            if weight:
                formatted_parts.append(f"Weight: {weight}")
            
            health_considerations = breed_info.get("health_considerations", "")
            if health_considerations:
                formatted_parts.append(f"Common health considerations: {health_considerations}")
            
            description = breed_info.get("description", "")
            if description:
                formatted_parts.append(f"Description: {description}")
            
            return "\n".join(formatted_parts)
        
        async def get_breed_information(self, breed_name: str, animal_type: str) -> Dict[str, Any]:
            """Fetch breed-specific information from APIs"""
            if not breed_name or not animal_type:
                return {}
            
            # Check cache first
            cache_key = f"{animal_type.lower()}_{breed_name.lower()}"
            if cache_key in self.breed_cache:
                return self.breed_cache[cache_key]
            
            breed_info = {}
            
            try:
                if animal_type.lower() == "dog" and self.dog_api_key:
                    breed_info = await self._fetch_dog_breed_info(breed_name)
                elif animal_type.lower() == "cat" and self.cat_api_key:
                    breed_info = await self._fetch_cat_breed_info(breed_name)
            except Exception as e:
                print(f"Error fetching breed information: {e}")
            
            # Cache the result
            self.breed_cache[cache_key] = breed_info
            return breed_info
        
        async def _fetch_dog_breed_info(self, breed_name: str) -> Dict[str, Any]:
            """Fetch dog breed information from The Dog API"""
            headers = {"x-api-key": self.dog_api_key}
            
            try:
                # Search for breed by name
                search_url = f"https://api.thedogapi.com/v1/breeds/search?q={breed_name}"
                response = requests.get(search_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    breeds = response.json()
                    if breeds and len(breeds) > 0:
                        breed = breeds[0]  # Take the first match
                        
                        # Format breed information for the knowledge base
                        breed_info = {
                            "name": breed.get("name", ""),
                            "temperament": breed.get("temperament", ""),
                            "life_span": breed.get("life_span", ""),
                            "weight": breed.get("weight", {}).get("metric", ""),
                            "height": breed.get("height", {}).get("metric", ""),
                            "bred_for": breed.get("bred_for", ""),
                            "breed_group": breed.get("breed_group", ""),
                            "origin": breed.get("origin", ""),
                            "description": f"The {breed.get('name', '')} is a {breed.get('breed_group', '')} breed known for being {breed.get('temperament', '')}. They typically live {breed.get('life_span', '')} and weigh {breed.get('weight', {}).get('metric', '')} kg.",
                            "health_considerations": self._get_breed_health_info(breed.get("name", ""), "dog")
                        }
                        
                        return breed_info
                        
            except Exception as e:
                print(f"Error fetching dog breed info: {e}")
            
            return {}
        
        async def _fetch_cat_breed_info(self, breed_name: str) -> Dict[str, Any]:
            """Fetch cat breed information from The Cat API"""
            headers = {"x-api-key": self.cat_api_key}
            
            try:
                # Search for breed by name
                search_url = f"https://api.thecatapi.com/v1/breeds/search?q={breed_name}"
                response = requests.get(search_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    breeds = response.json()
                    if breeds and len(breeds) > 0:
                        breed = breeds[0]  # Take the first match
                        
                        # Format breed information for the knowledge base
                        breed_info = {
                            "name": breed.get("name", ""),
                            "temperament": breed.get("temperament", ""),
                            "life_span": breed.get("life_span", ""),
                            "weight": breed.get("weight", {}).get("metric", ""),
                            "origin": breed.get("origin", ""),
                            "description": breed.get("description", ""),
                            "energy_level": breed.get("energy_level", ""),
                            "grooming": breed.get("grooming", ""),
                            "health_issues": breed.get("health_issues", ""),
                            "indoor": breed.get("indoor", ""),
                            "lap": breed.get("lap", ""),
                            "alt_names": breed.get("alt_names", ""),
                            "health_considerations": self._get_breed_health_info(breed.get("name", ""), "cat")
                        }
                        
                        return breed_info
                        
            except Exception as e:
                print(f"Error fetching cat breed info: {e}")
            
            return {}

    print("🎯 Class definition complete, creating global instance...")

    # Global service instance
    simple_rag_service = SimplePetHealthRAGService()

    print("✅ simple_rag_service instance created successfully!")

    # Export the class and instance for imports
    __all__ = ['SimplePetHealthRAGService', 'simple_rag_service']

    print("📤 Exports defined:", __all__)
except Exception as e:
    print(f"Error defining SimplePetHealthRAGService class: {e}")
