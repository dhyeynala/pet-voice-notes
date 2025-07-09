#!/usr/bin/env python3
"""
Enhanced sample script to populate comprehensive analytics data for testing purposes.
Run this script to add sample data to your pet's analytics collection.
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import random
import json

def init_firebase():
    """Initialize Firebase if not already done"""
    if not firebase_admin._apps:
        cred = credentials.Certificate("gcloud-key.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

def generate_sample_data(pet_identifier, num_days=7):
    """Generate comprehensive sample analytics data for the past N days"""
    db = init_firebase()
    
    print(f"Generating comprehensive sample data for pet '{pet_identifier}' for the past {num_days} days...")
    
    # Sample data templates
    diet_foods = ["Dry kibble", "Wet food", "Chicken breast", "Treats", "Carrots", "Sweet potato", "Fish", "Rice"]
    exercise_types = ["walk", "run", "play", "fetch", "swimming", "training"]
    medications = ["Heartgard", "Rimadyl", "Vitamins", "Flea prevention"]
    grooming_types = ["bath", "brushing", "nail-trim", "ear-cleaning", "teeth-brushing"]
    exit_destinations = ["Dog park", "Vet clinic", "Pet store", "Friend's house", "Beach"]
    
    for day_offset in range(num_days):
        current_date = datetime.now() - timedelta(days=day_offset)
        
        # Generate 3-8 entries per day
        daily_entries = random.randint(3, 8)
        
        for _ in range(daily_entries):
            # Randomize time throughout the day
            hour = random.randint(6, 22)
            minute = random.randint(0, 59)
            entry_time = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Randomly select category
            categories = ["diet", "exercise", "medication", "grooming", "energy_levels", 
                         "bowel_movements", "exit_events", "weight", "sleep", "mood"]
            category = random.choice(categories)
            
            entry_data = {
                "timestamp": entry_time.isoformat(),
                "category": category
            }
            
            # Generate category-specific data
            if category == "diet":
                entry_data.update({
                    "food": random.choice(diet_foods),
                    "quantity": random.choice(["1/2 cup", "1 cup", "2 cups", "handful", "small piece"]),
                    "time": f"{hour:02d}:{minute:02d}",
                    "type": random.choice(["breakfast", "lunch", "dinner", "treat"]),
                    "notes": random.choice(["", "Ate eagerly", "Left some food", "Seemed very hungry"])
                })
                
            elif category == "exercise":
                duration = random.randint(10, 90)
                entry_data.update({
                    "type": random.choice(exercise_types),
                    "duration": duration,
                    "intensity": random.choice(["low", "moderate", "high"]),
                    "location": random.choice(["Backyard", "Park", "Beach", "Living room"]),
                    "notes": random.choice(["", "Very energetic", "Seemed tired", "Enjoyed it"])
                })
                
            elif category == "medication":
                entry_data.update({
                    "name": random.choice(medications),
                    "dosage": random.choice(["25mg", "50mg", "1 tablet", "2 tablets"]),
                    "time": f"{hour:02d}:{minute:02d}",
                    "frequency": random.choice(["once", "twice", "weekly", "monthly"]),
                    "purpose": random.choice(["Pain relief", "Heartworm prevention", "Joint health"])
                })
                
            elif category == "grooming":
                selected_types = random.sample(grooming_types, random.randint(1, 3))
                entry_data.update({
                    "types": selected_types,
                    "duration": random.randint(15, 60),
                    "products": random.choice(["Dog shampoo", "Nail clippers", "Brush", "Ear cleaner"]),
                    "notes": random.choice(["", "Cooperated well", "Was a bit anxious", "Enjoyed the attention"])
                })
                
            elif category == "energy_levels":
                entry_data.update({
                    "level": random.randint(1, 5),
                    "notes": random.choice(["", "Very playful", "Seemed sluggish", "Normal energy"])
                })
                
            elif category == "bowel_movements":
                entry_data.update({
                    "consistency": random.choice(["normal", "soft", "loose", "hard"]),
                    "time": f"{hour:02d}:{minute:02d}",
                    "notes": random.choice(["", "Regular timing", "Earlier than usual", "Later than usual"])
                })
                
            elif category == "exit_events":
                entry_data.update({
                    "type": random.choice(["walk", "potty", "car-ride", "vet-visit"]),
                    "duration": random.randint(10, 120),
                    "destination": random.choice(exit_destinations)
                })
                
            elif category == "weight":
                # Generate realistic weight variations
                base_weight = 25.0  # Base weight in lbs
                variation = random.uniform(-2.0, 2.0)
                entry_data.update({
                    "value": round(base_weight + variation, 1),
                    "unit": "lbs",
                    "method": random.choice(["home-scale", "vet-visit", "groomer"]),
                    "time": f"{hour:02d}:{minute:02d}",
                    "notes": random.choice(["", "Steady weight", "Slight increase", "Slight decrease"])
                })
                
            elif category == "sleep":
                entry_data.update({
                    "duration": round(random.uniform(6.0, 12.0), 1),
                    "quality": random.choice(["excellent", "good", "fair", "poor", "restless"]),
                    "location": random.choice(["Dog bed", "Couch", "Owner's bed", "Floor"]),
                    "interruptions": random.randint(0, 3),
                    "notes": random.choice(["", "Slept through the night", "Woke up early", "Restless sleep"])
                })
                
            elif category == "mood":
                triggers = ["food", "exercise", "visitors", "weather", "other-pets", "loud-noises"]
                behaviors = ["playful", "lethargic", "anxious", "affectionate", "withdrawn", "hyperactive"]
                entry_data.update({
                    "level": random.randint(1, 5),
                    "triggers": random.sample(triggers, random.randint(0, 3)),
                    "behavior": random.sample(behaviors, random.randint(1, 3)),
                    "time": f"{hour:02d}:{minute:02d}",
                    "notes": random.choice(["", "Happy and content", "Seemed stressed", "Very affectionate today"])
                })
            
            # Add entry to Firestore
            try:
                db.collection("pets").document(pet_identifier).collection("analytics").add(entry_data)
            except Exception as e:
                print(f"Error adding entry: {e}")
                continue
    
    print(f"Sample data generation complete!")
    print(f"Added approximately {num_days * 5} entries across all health categories")
    print("\nCategories included:")
    print("- Diet & Nutrition")
    print("- Exercise & Activity") 
    print("- Medication Tracking")
    print("- Grooming & Hygiene")
    print("- Energy Levels")
    print("- Bowel Movements")
    print("- Exit Events")
    print("- Weight Tracking")
    print("- Sleep Monitoring")
    print("- Mood Assessment")

if __name__ == "__main__":
    # Replace with your actual pet ID
    pet_id = input("Enter pet ID (e.g., 'nala' or your pet's ID): ").strip()
    if not pet_id:
        print("No pet ID provided. Exiting.")
        exit(1)
    
    days = int(input("Enter number of days to generate data for (default 7): ") or 7)
    
    print(f"Generating comprehensive sample data for pet '{pet_id}' for the past {days} days...")
    generate_sample_data(pet_id, days)
    print("Sample data generation complete!")
    print("\nYou can now view the analytics dashboard with rich data visualizations!")
    print("The AI will also be able to generate more meaningful insights with this data.")
