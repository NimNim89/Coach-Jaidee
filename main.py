from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from datetime import date
import os
import json
import requests
from supabase import create_client

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI()
supabase = create_client(
    os.getenv("SUPABASE_URL")
    os.getenv("SUPABASE_KEY")
)

daily_logs = {}

class FoodRequest(BaseModel):
    food: str

@app.get("/")
def home():
    return {"message": "CoachJaiDee AI Running"}

def reply_line(reply_token, text):
    headers = {
        "Authorization": f"Bearer {os.getenv('LINE_CHANNEL_ACCESS_TOKEN')}",
        "Content-Type": "application/json"
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
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

    if not body.get("events"):
        return {"status": "ok"}

    event = body["events"][0]

    if event["type"] != "message" or event["message"]["type"] != "text":
        return {"status": "ok"}

    user_id = event["source"]["userId"]
    user_text = event["message"]["text"]
    reply_token = event["replyToken"]
    
    if user_text.strip() == "สรุปวันนี้":
        today = str(date.today())
        key = f"{user_id}_{today}"
        total = daily_logs.get(key, 0)
        target = 1500
        remaining = target - total

        reply_text = (
            f"สรุปวันนี้ 🍱\n"
            f"ทานไปแล้ว {total} kcal\n"
            f"เหลืออีกประมาณ {remaining} kcal\n"
            f"จากเป้าหมาย {target} kcal"
        )

        reply_line(reply_token, reply_text)
        return {"status": "ok"}
    result = analyze(FoodRequest(food=user_text))

    supabase.table("food_logs").insert({
    "user_id": user_id,
    "food": result["food"],
    "calories": result["calories"],
    "protein": result["protein"],
    "carbs": result["carbs"],
    "fat": result["fat"]
    }).execute()

    today = str(date.today())
    key = f"{user_id}_{today}"
    daily_logs[key] = daily_logs.get(key, 0) + int(result["calories"])

    total = daily_logs[key]
    target = 1500
    remaining = target - total

    reply_text = (
        f"{result['food']}\n"
        f"ประมาณ {result['calories']} kcal\n"
        f"โปรตีน {result['protein']} g\n"
        f"คาร์บ {result['carbs']} g\n"
        f"ไขมัน {result['fat']} g\n\n"
        f"{result['advice']}\n\n"
        f"วันนี้สะสมแล้ว {total} kcal\n"
        f"เหลืออีกประมาณ {remaining} kcal จากเป้าหมาย {target} kcal"
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
                "content": """
คุณคือ Coach Jai-dee

เป็นโค้ชคุมอาหารภาษาไทย
พูดเป็นกันเอง อบอุ่น
ไม่ดุ ไม่ตัดสินผู้ใช้

ให้ประเมินอาหารและตอบเป็น JSON เท่านั้น
ห้ามใส่ markdown
ห้ามใส่คำอธิบายอื่นนอก JSON

{
  "food": "",
  "calories": 0,
  "protein": 0,
  "carbs": 0,
  "fat": 0,
  "advice": ""
}
"""
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
