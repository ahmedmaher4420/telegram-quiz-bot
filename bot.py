import os
import random
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from quizzes_data import quizzes

# 📝 تسجيل الأنشطة
def log_user_action(user_id, name, action):
    log_file = "user_logs.json"
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except FileNotFoundError:
        logs = {}

    if str(user_id) not in logs:
        logs[str(user_id)] = {"name": name, "actions": []}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs[str(user_id)]["actions"].append(f"{timestamp} - {action}")

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

user_state = {}

def get_subjects():
    return [name for name in os.listdir("lectures") if os.path.isdir(f"lectures/{name}")]

def get_types(subject):
    path = f"lectures/{subject}"
    folders = [name for name in os.listdir(path) if os.path.isdir(f"{path}/{name}")]
    return folders if folders else [""]

def get_lectures(subject, type_):
    path = f"lectures/{subject}/{type_}" if type_ else f"lectures/{subject}"
    return [name for name in os.listdir(path) if name.endswith(".pdf")]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    user_state[uid] = {}
    log_user_action(uid, name, "Started bot")

    keyboard = [[s] for s in get_subjects()] + [["🔁 ابدأ من جديد"]]
    await update.message.reply_text("📚 اختر المادة:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    text = update.message.text
    state = user_state.get(uid, {})

    if text == "🔁 ابدأ من جديد":
        log_user_action(uid, name, "Restarted bot")
        return await start(update, context)

    if text in get_subjects():
        user_state[uid] = {"subject": text}
        log_user_action(uid, name, f"Selected subject: {text}")
        types = get_types(text)
        if types != [""]:
            keyboard = [[t] for t in types] + [["🔁 ابدأ من جديد"]]
            await update.message.reply_text("📘 اختر النوع (نظري / عملي):", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
        else:
            lectures = get_lectures(text, "")
            keyboard = [[l] for l in lectures] + [["🔁 ابدأ من جديد"]]
            user_state[uid]["type"] = ""
            await update.message.reply_text("📖 اختر المحاضرة:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))

    elif "subject" in state and text in get_types(state["subject"]):
        user_state[uid]["type"] = text
        log_user_action(uid, name, f"Selected type: {text}")
        lectures = get_lectures(state["subject"], text)
        keyboard = [[l] for l in lectures] + [["🔁 ابدأ من جديد"]]
        await update.message.reply_text("📖 اختر المحاضرة:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))

    elif "subject" in state and "type" in state and text in get_lectures(state["subject"], state["type"]):
        user_state[uid]["lecture"] = text.replace(".pdf", "").strip()
        log_user_action(uid, name, f"Selected lecture: {text}")
        keyboard = [["📄 View Lecture File", "📝 Take Quiz"], ["🔁 ابدأ من جديد"]]
        await update.message.reply_text(f"📘 {text}\nاختر ما تريد:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))

    elif text == "📄 View Lecture File":
        subject = state.get("subject")
        type_ = state.get("type")
        lecture = state.get("lecture") + ".pdf"
        file_path = f"lectures/{subject}/{type_}/{lecture}" if type_ else f"lectures/{subject}/{lecture}"
        if os.path.exists(file_path):
            log_user_action(uid, name, f"Viewed lecture file: {lecture}")
            with open(file_path, "rb") as f:
                await update.message.reply_document(f)
        else:
            await update.message.reply_text("❌ الملف غير موجود.")

    elif text == "📝 Take Quiz":
        lecture = state.get("lecture", "").strip()
        if not lecture or lecture not in quizzes:
            await update.message.reply_text("❗ لا يوجد كويز مضاف لهذه المحاضرة حتى الآن.")
            return

        log_user_action(uid, name, f"Started quiz: {lecture}")
        mcqs = quizzes[lecture].get("MCQs", [])
        tfs = quizzes[lecture].get("TF", [])
        random.shuffle(mcqs)
        random.shuffle(tfs)

        user_state[uid]["quiz"] = {
            "lecture": lecture,
            "current": 0,
            "score": 0,
            "mcqs": mcqs,
            "tfs": tfs
        }

        question_data = mcqs[0]
        keyboard = [[opt] for opt in question_data["options"]] + [["⛔️ إنهاء الكويز"], ["🔁 ابدأ من جديد"]]
        await update.message.reply_text(
            f"🧪 السؤال 1:\n{question_data['question']}",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )

    elif text == "⛔️ إنهاء الكويز" and "quiz" in state:
        quiz = state["quiz"]
        score = quiz["score"]
        total = len(quiz["mcqs"]) + len(quiz["tfs"])
        log_user_action(uid, name, f"Ended quiz: score {score}/{total}")
        del user_state[uid]["quiz"]
        await update.message.reply_text(f"⛔️ الكويز تم إنهاؤه يدويًا.\n✅ درجتك: {score}/{total}")
        return

    elif "quiz" in state:
        quiz = state["quiz"]
        mcqs = quiz.get("mcqs", [])
        tfs = quiz.get("tfs", [])
        total_mcq = len(mcqs)
        total_tf = len(tfs)
        total_all = total_mcq + total_tf
        current = quiz["current"]

        if current < total_mcq:
            q = mcqs[current]
            correct_answer = q["answer"]
            chosen_answer = text[0].upper()

            if chosen_answer == correct_answer:
                quiz["score"] += 1
                feedback = "✅ إجابة صحيحة!"
            else:
                correct_option_text = [opt for opt in q["options"] if opt.startswith(correct_answer)][0]
                feedback = f"❌ إجابة خاطئة.\n✅ الإجابة الصحيحة: {correct_option_text}"

        elif current < total_all:
            tf_index = current - total_mcq
            q = tfs[tf_index]
            correct_answer = q["answer"]
            chosen_answer = text.startswith("✅") or text.lower() == "true"

            if chosen_answer == correct_answer:
                quiz["score"] += 1
                feedback = "✅ إجابة صحيحة!"
            else:
                correct_text = "True" if correct_answer else "False"
                feedback = f"❌ إجابة خاطئة.\n✅ الإجابة الصحيحة: {correct_text}"

        quiz["current"] += 1
        current += 1

        if current < total_all:
            await update.message.reply_text(feedback)
            if current < total_mcq:
                next_q = mcqs[current]
                keyboard = [[opt] for opt in next_q["options"]] + [["⛔️ إنهاء الكويز"], ["🔁 ابدأ من جديد"]]
            else:
                tf_index = current - total_mcq
                next_q = tfs[tf_index]
                keyboard = [["✅ True"], ["❌ False"], ["⛔️ إنهاء الكويز"], ["🔁 ابدأ من جديد"]]

            await update.message.reply_text(
                f"🧪 {next_q['question']}",
                reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            )
        else:
            await update.message.reply_text(feedback)
            score = quiz["score"]
            log_user_action(uid, name, f"Finished quiz: score {score}/{total_all}")
            del user_state[uid]["quiz"]
            await update.message.reply_text(f"✅ انتهى الكويز!\nدرجتك: {score}/{total_all}")

    else:
        await update.message.reply_text("❗ من فضلك اختر من القوائم.", reply_markup=ReplyKeyboardMarkup([["🔁 ابدأ من جديد"]], resize_keyboard=True))

# تشغيل البوت
app = ApplicationBuilder().token("7774771769:AAHXK9PVehCzEh5d9NOksBlD4UyfqbZ5ObM").build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("🤖 Bot is running... Send /start to begin.")
app.run_polling()
