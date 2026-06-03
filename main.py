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

from fastapi import Request

import requests

def reply_line(reply_token, text):
    headers = {
        "Authorization": f"Bearer {os.getenv('LINE_CHANNEL_ACCESS_TOKEN')}",
        "Content-Type": "application/json"
    }

    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body
    )


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    print("LINE webhook received")
    print(body)

    event = body["events"][0]

    if event["type"] != "message":
        return {"status": "ok"}

    user_text = event["message"]["text"]
    reply_token = event["replyToken"]

    result = analyze(FoodRequest(food=user_text))

    reply_text = (
        f"{result['food']}\n"
        f"ประมาณ {result['calories']} kcal\n"
        f"โปรตีน {result['protein']} g\n"
        f"คาร์บ {result['carbs']} g\n"
        f"ไขมัน {result['fat']} g\n\n"
        f"{result['advice']}"
    )

    reply_line(reply_token, reply_text)

    return {"status": "ok"}

@app.post("/analyze")
def analyze(data: FoodRequest):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
                         {
        "role": "system",
        "content":"""
คุณคือ Coach Jai-dee

เป็นโค้ชคุมอาหารภาษาไทย
พูดเป็นกันเอง อบอุ่น
ไม่ดุ ไม่ตัดสินผู้ใช้

ให้ประเมินอาหารและตอบเป็น JSON เท่านั้น

{
  "food": "",
  "calories": 0,
  "protein": 0,
  "carbs": 0,
  "fat": 0,
  "advice": ""
}
""" ,
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
