from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

class FoodRequest(BaseModel):
    food: str

@app.get("/")
def home():
    return {"message": "CoachJaiDee AI Running"}

@app.post("/analyze")
def analyze(data: FoodRequest):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
                         {
        "role": "system",
        "content": "คุณคือเพื่อนคุมอาหารภาษาไทย ตอบเป็น JSON เท่านั้น ห้ามใส่คำอธิบายอื่น"
    },
    {
        "role": "user",
        "content": f"""
วิเคราะห์อาหารนี้: {data.food}

ตอบ JSON เท่านั้นในรูปแบบนี้:
{{
  "food": "{data.food}",
  "calories": 0,
  "protein": 0,
  "carbs": 0,
  "fat": 0,
  "advice": "คำแนะนำสั้น ๆ"
}}
"""
    }
]
    )

    ai_text = response.choices[0].message.content
    ai_json = json.loads(ai_text)

    return ai_json
