import os
import logging
import httpx
from dotenv import load_dotenv
load_dotenv()
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
)
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

client = Groq(api_key=os.environ["GROQ_API_KEY"])
chat_histories = {}
MAX_HISTORY = 20

SYSTEM_PROMPT = """Siz foydali, do'stona va aqlli AI yordamchisiz.

MUHIM QOIDALAR:
1. Har doim o'zbek tilida javob bering (agar savol boshqa tilda bo'lsa, o'sha tilda javob bering)
2. Javoblaringizga tegishli emojilar qo'shing — bu javobni chiroyliroq qiladi
3. Qisqa va aniq javob bering
4. Agar foydalanuvchi rasm so'rasa, faqat: [RASM: <inglizcha tavsif>] formatida yozing

Misol javoblar:
- Salom desa: "Salom! 👋 Qanday yordam bera olaman? 😊"
- Havo haqida: "Bugun havo juda yaxshi! ☀️ Sayr qilish uchun zo'r kun 🌿"
- Kod so'rasa: "Albatta! 💻 Mana kod: ..."
- Rasm so'rasa: [RASM: beautiful sunset over mountains]"""


def get_ai_response(user_id: int, user_message: str) -> str:
    if user_id not in chat_histories:
        chat_histories[user_id] = []

    chat_histories[user_id].append({"role": "user", "content": user_message})

    if len(chat_histories[user_id]) > MAX_HISTORY:
        chat_histories[user_id] = chat_histories[user_id][-MAX_HISTORY:]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *chat_histories[user_id]
        ],
        max_tokens=1024,
        temperature=0.7,
    )

    ai_reply = response.choices[0].message.content
    chat_histories[user_id].append({"role": "assistant", "content": ai_reply})
    return ai_reply


async def generate_image(prompt: str) -> bytes:
    import urllib.parse, random
    safe_prompt = urllib.parse.quote(prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=flux&enhance=true"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url)
        return r.content


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}! 👋\n\n"
        "Men aqlli AI yordamchiman ⚡\n\n"
        "🗣️ Istalgan savolingizni yozing\n"
        "🎨 Rasm yaratish uchun: 'rasm: tog' manzarasi' yozing\n\n"
        "📌 Buyruqlar:\n"
        "/start — Qayta boshlash 🔄\n"
        "/clear — Tarixni tozalash 🗑️\n"
        "/help — Yordam ℹ️"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *AI Yordamchi Bot*\n\n"
        "💡 *Nima qila olaman?*\n"
        "• Savollarga javob berish 💬\n"
        "• Tarjima qilish 🌍\n"
        "• Kod yozish 💻\n"
        "• Maslahat berish 🎯\n"
        "• Rasm yaratish 🎨\n\n"
        "🎨 *Rasm yaratish:*\n"
        "Shunchaki yozing: `rasm: <tavsif>`\n"
        "Masalan: `rasm: kechki shahar manzarasi`\n\n"
        "📌 /clear — tarixni tozalash 🗑️",
        parse_mode="Markdown"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chat_histories:
        chat_histories[user_id] = []
    await update.message.reply_text("✅ Suhbat tarixi tozalandi! Yangi suhbat boshlashingiz mumkin 😊")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Foydalanuvchi "rasm:" deb boshlasa — to'g'ridan rasm yaratish
        msg_lower = user_message.lower().strip()
        if msg_lower.startswith("rasm:") or msg_lower.startswith("rasm "):
            prompt = user_message[5:].strip()
            await update.message.reply_text(f"🎨 Rasm yaratilmoqda: *{prompt}*\nBir oz kuting... ⏳", parse_mode="Markdown")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

            # Inglizcha tarjima uchun Groq ishlatamiz
            translate_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": f"Translate this to English for image generation (only return the translation, nothing else): {prompt}"
                }],
                max_tokens=100,
            )
            english_prompt = translate_response.choices[0].message.content.strip()

            image_bytes = await generate_image(english_prompt)
            await update.message.reply_photo(photo=image_bytes, caption=f"🎨 {prompt} ✨")
            return

        # Oddiy AI javob
        ai_response = get_ai_response(user_id, user_message)

        # AI [RASM: ...] formatida javob bergan bo'lsa
        if "[RASM:" in ai_response:
            parts = ai_response.split("[RASM:")
            text_part = parts[0].strip()
            image_prompt = parts[1].split("]")[0].strip()
            after_text = parts[1].split("]")[1].strip() if "]" in parts[1] else ""

            if text_part:
                await update.message.reply_text(text_part)

            await update.message.reply_text(f"🎨 Rasm yaratilmoqda... ⏳")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            image_bytes = await generate_image(image_prompt)
            await update.message.reply_photo(photo=image_bytes, caption=f"🎨 {image_prompt} ✨")

            if after_text:
                await update.message.reply_text(after_text)
        else:
            await update.message.reply_text(ai_response)

    except Exception as e:
        logger.error(f"Xato: {e}")
        await update.message.reply_text("⚠️ Xato yuz berdi. Qayta urinib ko'ring 🙏")


async def error_handler(update, context):
    logger.error(f"Xato: {context.error}")


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot ishga tushdi! Emoji + Rasm generatsiya tayyor!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
