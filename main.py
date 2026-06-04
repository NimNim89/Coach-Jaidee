from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from datetime import date, datetime, timezone
import os
import json
import requests
from supabase import create_client

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

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
    user_text = event["message"]["text"].strip()
    reply_token = event["replyToken"]

    if user_text == "สรุปวันนี้":
        today_start = datetime.now(timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
         ).isoformat()


        response = supabase.table("food_logs") \
            .select("food, calories, protein, carbs, fat, created_at") \
            .eq("user_id", user_id) \
            .gte("created_at", today_start) \
            .execute()

        logs = response.data or []

        total = sum(int(item["calories"]) for item in logs)
        total_protein = sum(int(item["protein"]) for item in logs)
        total_carbs = sum(int(item["carbs"]) for item in logs)
        total_fat = sum(int(item["fat"]) for item in logs)

        target = 1500
        remaining = target - total

        food_list = "\n".join(
            [f"- {item['food']} {item['calories']} kcal" for item in logs]
        )

        if not food_list:
            food_list = "ยังไม่มีรายการอาหารวันนี้"

        reply_text = (
            f"สรุปวันนี้ 🍱\n"
            f"{food_list}\n\n"
            f"รวม {total} kcal\n"
            f"โปรตีน {total_protein} g\n"
            f"คาร์บ {total_carbs} g\n"
            f"ไขมัน {total_fat} g\n\n"
            f"เหลืออีกประมาณ {remaining} kcal\n"
            f"จากเป้าหมาย {target} kcal"
        )

        reply_line(reply_token, reply_text)
        return {"status": "ok"}

    result = analyze(FoodRequest(food=user_text))

    try:
        supabase.table("food_logs").insert({
            "user_id": user_id,
            "food": result["food"],
            "calories": result["calories"],
            "protein": result["protein"],
            "carbs": result["carbs"],
            "fat": result["fat"]
        }).execute()
        print("SUPABASE SUCCESS")
    except Exception as e:
        print("SUPABASE ERROR:", e)

    response = supabase.table("food_logs") \
        .select("calories") \
        .eq("user_id", user_id) \
        .execute()

    logs = response.data or []
    total = sum(int(item["calories"]) for item in logs)

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
    return json.loads(ai_text)
