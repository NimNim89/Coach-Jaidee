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

def calculate_target_calories(weight, height, sex, age, activity_level, goal):
    if sex == "ชาย":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    activity_map = {
        "เบา": 1.2,
        "กลาง": 1.375,
        "หนัก": 1.55,
        "มาก": 1.725
    }

    tdee = bmr * activity_map.get(activity_level, 1.2)

    if goal == "ลด":
         if age < 18:
             target = int(tdee)
         elif age >= 65:
             target = int(tdee - 100)
         else:
             target = int(tdee - 300)

    elif goal == "เพิ่ม":
         target = int(tdee + 300)

    else:  # คง
         target = int(tdee)

    if sex == "ชาย" and target < 1500:
         target = 1500
    elif sex != "ชาย" and target < 1200:
         target = 1200

    return target


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
   
    if user_text == "เป้าหมายวันนี้":
                  
            today_start = datetime.now(timezone.utc).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            ).isoformat()
                
            response = supabase.table("food_logs") \
                .select("calories") \
                .eq("user_id", user_id) \
                .gte("created_at", today_start) \
                .execute()
            
            logs = response.data or []
            
            total = sum(int(item["calories"]) for item in logs)
            profile = (
                supabase.table("user_profiles") 
                .select("target_calories")
                .eq("user_id", user_id)    
                .single() 
                .execute()
            ) 
                
            target = profile.data["target_calories"]
            
            remaining = target - total
            
            reply_text = (
                f"🎯 เป้าหมายรายวัน\n\n"
                f"🔥 เป้าหมาย: {target} kcal\n"
                f"🍽️ กินแล้ว: {total} kcal\n"
                f"📉 เหลืออีก: {remaining} kcal"
            )
             
            reply_line(reply_token, reply_text)
            return {"status": "ok"}
   
    if user_text == "เป้าหมายน้ำหนัก":

        profile = supabase.table("user_profiles") \
            .select("weight,height") \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not profile.data:
            reply_line(
                reply_token,
                "กรุณาตั้งโปรไฟล์ก่อน\nตัวอย่าง:\n60,160,หญิง,30,กลาง,ลด"
            )
            return {"status": "ok"}

        weight = float(profile.data["weight"])
        height = float(profile.data["height"])

        height_m = height / 100

        bmi = weight / (height_m ** 2)

        healthy_min = round(18.5 * (height_m ** 2), 1)
        healthy_max = round(22.9 * (height_m ** 2), 1)

        recommended = round(20 * (height_m ** 2), 1)

        remaining = max(0, round(weight - recommended, 1))

        weeks = round(remaining / 0.5)

        reply_text = (
            f"🎯 เป้าหมายน้ำหนัก\n\n"
            f"น้ำหนักปัจจุบัน: {weight:.1f} kg\n\n"
            f"BMI ปัจจุบัน: {bmi:.1f}\n\n"
            f"ช่วงน้ำหนักสุขภาพดี:\n"
            f"{healthy_min:.1f} - {healthy_max:.1f} kg\n\n"
            f"น้ำหนักที่แนะนำ:\n"
            f"{recommended:.1f} kg\n\n"
            f"เหลืออีก:\n"
            f"{remaining:.1f} kg\n\n"
            f"หากลด 0.5 kg/สัปดาห์\n"
            f"คาดว่าใช้เวลา {weeks} สัปดาห์"
        )

        reply_line(reply_token, reply_text)
        return {"status": "ok"}

    if user_text == "สรุปรายสัปดาห์":
        weights = supabase.table("weight_logs") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(2) \
            .execute()

        logs = weights.data or []

        if len(logs) < 2:
            reply_line(
                reply_token,
                "ยังมีข้อมูลน้ำหนักไม่พอ\nกรุณาชั่งน้ำหนักอย่างน้อย 2 ครั้ง"
            )
            return {"status": "ok"}
        latest_weight = float(logs[0]["weight_kg"])
        previous_weight = float(logs[1]["weight_kg"])

        change = latest_weight - previous_weight

        if change < 0:
            trend = f"ลดลง {abs(change):.1f} kg 🎉"
        elif change > 0:
            trend = f"เพิ่มขึ้น {change:.1f} kg"
        else:
            trend = "ไม่เปลี่ยนแปลง"           

        height = float(
            supabase.table("user_profiles")
            .select("height")
            .eq("user_id", user_id)
            .single()
            .execute()
            .data["height"]
        )

        height_m = height / 100
        target_weight = round(20 * (height_m ** 2), 1)
        remaining = max(0, round(latest_weight - target_weight, 1))
        total_to_lose = max(0.1, previous_weight - target_weight)
        lost_so_far = max(0, previous_weight - latest_weight)
        progress = min(100, round((lost_so_far / total_to_lose) * 100))
        weeks_left = round(remaining / 0.5)

        reply_text = (
            f"📊 สรุปรายสัปดาห์\n\n"
            f"น้ำหนักก่อนหน้า: {previous_weight:.1f} kg\n"
            f"น้ำหนักล่าสุด: {latest_weight:.1f} kg\n\n"
            f"ผลลัพธ์:\n"
            f"{trend}\n\n"
            f"🎯 น้ำหนักเป้าหมาย: {target_weight:.1f} kg\n\n"
            f"เหลืออีก:\n"
            f"{remaining:.1f} kg\n\n"
            f"ความคืบหน้า:\n"
            f"{progress}%\n\n"
            f"คาดว่าใช้เวลาอีก:\n"
            f"{weeks_left} สัปดาห์"
        )
        reply_line(reply_token, reply_text)
        return {"status": "ok"}

    if user_text == "ลบล่าสุด":

        latest = supabase.table("food_logs") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("id", desc=True) \
            .limit(1) \
            .execute()

        logs = latest.data or []

        if not logs:
            reply_line(
                reply_token,
                "ยังไม่มีรายการอาหารให้ลบนะ 😊"
            )
            return {"status": "ok"}

        food = logs[0]

        supabase.table("food_logs") \
            .delete() \
            .eq("id", food["id"]) \
            .execute()

        reply_line(
            reply_token,
            f"🗑 ลบรายการล่าสุดแล้ว\n\n"
            f"{food['food']}\n"
            f"{food['calories']} kcal"
        )

        return {"status": "ok"}

    if user_text == "ล้างวันนี้":

        today_start = datetime.now(timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        ).isoformat()

        supabase.table("food_logs") \
            .delete() \
            .eq("user_id", user_id) \
            .gte("created_at", today_start) \
            .execute()

        reply_line(
            reply_token,
            "🗑️ ล้างข้อมูลอาหารวันนี้เรียบร้อยแล้ว"
        )
        return {"status": "ok"}

    if user_text == "โปรไฟล์":
        profile = supabase.table("user_profiles") \
            .select("*") \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        data = profile.data

        reply_line(
            reply_token,
            f"👤 โปรไฟล์ของคุณ\n\n"
            f"น้ำหนัก: {data['weight']} kg\n"
            f"ส่วนสูง: {data['height']} cm\n"
            f"เพศ: {data['sex']}\n"
            f"อายุ: {data['age']} ปี\n"
            f"กิจกรรม: {data['activity_level']}\n"
            f"เป้าหมายน้ำหนัก: {data['goal']}\n\n"
            f"🔥 พลังงานเป้าหมาย: {data['target_calories']} kcal/วัน"
        )

        return {"status": "ok"}

    if user_text == "ตั้งโปรไฟล์":
        reply_line(
            reply_token,
            "กรุณาส่งข้อมูลในรูปแบบ 😊\n\n"
            "น้ำหนัก,ส่วนสูง,เพศตามใบเกิด,อายุ,ระดับกิจกรรม,เป้าหมายน้ำหนัก:\n"
            "ระดับกิจกรรม:\n"
            "- เบา (นั่งทำงานเป็นส่วนใหญ่)\n"
            "- กลาง (ออกกำลังกาย 1-3 วัน/สัปดาห์)\n"
            "- หนัก (ออกกำลังกาย 4-6 วัน/สัปดาห์)\n"
            "- มาก (ใช้แรงงานหรือซ้อมหนักทุกวัน)\n\n"
            "เป้าหมายน้ำหนัก:\n"
            "- ลด\n"
            "- คง\n"
            "- เพิ่ม\n\n"
            "ตัวอย่าง:\n"
            "65,160,หญิง,35,เบา,ลด"
           )
        return {"status": "ok"}

    parts = user_text.split(",")

    if len(parts) == 6:
        try:
            weight = float(parts[0].strip())
            height = float(parts[1].strip())
            sex = parts[2].strip()
            age = int(parts[3].strip())
            activity_level = parts[4].strip()
            goal = parts[5].strip()

            target_calories = calculate_target_calories(weight, height, sex, age, activity_level, goal)
            bmi = round(weight / ((height / 100) ** 2), 1)

            if bmi < 18.5:
                bmi_text = "น้ำหนักน้อย"
            elif bmi < 23:
                bmi_text = "ปกติ"
            elif bmi < 25:
                bmi_text = "น้ำหนักเกิน"
            elif bmi < 30:
                bmi_text = "อ้วนระดับ 1"
            else:
                bmi_text = "อ้วนระดับ 2"

            supabase.table("user_profiles").upsert(
                {
                    "user_id": user_id,
                    "weight": weight,
                    "height": height,
                    "sex": sex,
                    "age": age,
                    "activity_level": activity_level,
                    "goal": goal,
                    "target_calories": target_calories
                },
                on_conflict="user_id"
             ).execute()

            reply_line(
                reply_token,
                f"ตั้งโปรไฟล์เรียบร้อยแล้ว 🎯\n\n"
                f"เป้าหมายน้ำหนัก: {goal}\n"
                f"🔥 พลังงานเป้าหมาย: {target_calories} kcal/วัน\n"
                f"📊 BMI: {bmi} ({bmi_text})"
            )
            return {"status": "ok"}

        except Exception as e:
            print("PROFILE ERROR:", repr(e))
            
            reply_line(
                reply_token,
                f"ERROR:\n{e}"
            )

            return {"status": "ok"}

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

        profile = supabase.table("user_profiles") \
            .select("target_calories") \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        target = profile.data["target_calories"]
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
    
    if user_text.startswith("ชั่งน้ำหนัก"):

        try:
            weight_text = user_text.replace("ชั่งน้ำหนัก", "").strip()
            weight_kg = float(weight_text)

            supabase.table("weight_logs").insert({
                "user_id": user_id,
                "weight_kg": weight_kg
            }).execute()

            supabase.table("user_profiles").update({
                "weight": weight_kg
            }).eq("user_id", user_id).execute()
            reply_line(
                reply_token,
                f"✅ บันทึกน้ำหนักเรียบร้อย\n\nน้ำหนัก: {weight_kg:.1f} kg"
            )
            return {"status": "ok"}

        except Exception as e:
            print("WEIGHT LOG ERROR:", repr(e))
            reply_line(
                reply_token,
                "กรุณาส่งแบบนี้นะ\nชั่งน้ำหนัก 53.5"
            )
            return {"status": "ok"} 

    result = analyze(FoodRequest(food=user_text))

    try:
        supabase.table("food_logs").insert({
            "user_id": user_id,
            "food": result["food"],
            "calories": result["calories"],
            "protein": float(result["protein"]),
            "carbs": float(result["carbs"]),
            "fat": float(result["fat"])
        }).execute()
        print("SUPABASE SUCCESS")
    except Exception as e:
        print("SUPABASE ERROR:", e)

    today_start = datetime.now(timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
         ).isoformat()
            

    response = supabase.table("food_logs") \
        .select("calories") \
        .eq("user_id", user_id) \
        .gte("created_at", today_start) \
        .execute()

    logs = response.data or []
    total = sum(int(item["calories"]) for item in logs)
    
    profile = supabase.table("user_profiles") \
        .select("target_calories") \
        .eq("user_id", user_id) \
        .single() \
        .execute()

    target = profile.data["target_calories"]
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
