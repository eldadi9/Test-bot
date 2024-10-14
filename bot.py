import os
import sqlite3
import zipfile
import asyncio
import platform
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = '7908068063:AAEoi6BHjEEk2O0t7SANwsZ1DC1Qph4x3hY'
PASSWORD = 'olam_tov'  # סיסמת ZIP

def create_database():
    """יוצר את בסיס הנתונים והטבלאות הדרושות אם הן לא קיימות."""
    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            file_name TEXT,
            uploader_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            category TEXT,
            upload_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """תפריט ראשי."""
    keyboard = [
        [InlineKeyboardButton("📤 העלאת קובץ", callback_data='upload')],
        [InlineKeyboardButton("📥 הורדת קבצים", callback_data='download')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ברוכים הבאים! מה תרצה לעשות?", reply_markup=reply_markup)

async def upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מבקש מהמשתמש לשלוח קובץ להעלאה."""
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("אנא שלח את הקובץ להעלאה.")

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בהעלאת קובץ ושמירתו בתיקייה הנכונה ובבסיס הנתונים."""
    user = update.message.from_user
    file = update.message.document
    file_name = file.file_name
    upload_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # קביעת הקטגוריה לפי הסיומת
    category = 'פלייליסטים' if file_name.endswith(('.m3u', '.m3u8')) else 'אפליקציות' if file_name.endswith('.apk') else 'אחר'

    # יצירת תיקייה לפי הקטגוריה ושמירת הקובץ שם
    os.makedirs(f'uploads/{category}', exist_ok=True)
    file_path = f'uploads/{category}/{file_name}'
    new_file = await context.bot.get_file(file.file_id)
    await new_file.download_to_drive(file_path)

    # שמירת פרטי הקובץ בבסיס הנתונים
    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO files (file_id, file_name, uploader_id, username, first_name, last_name, category, upload_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (file.file_id, file_name, user.id, user.username or "לא זמין", user.first_name, user.last_name or "לא זמין", category, upload_time))
    conn.commit()
    conn.close()

    # חזרה עם תשובה למשתמש
    await update.message.reply_text("תודה רבה! אחלה יום.")

async def uploaded_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מציג את כל הקבצים שהועלו ומי העלה אותם."""
    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute('SELECT file_name, username, uploader_id, category, upload_time FROM files')
    files = c.fetchall()
    conn.close()

    if files:
        response = "רשימת הקבצים שהועלו:\n" + "\n".join(
            [f"📄 {file[0]} - הועלה ע\"י {file[1]} (ID: {file[2]})\nקטגוריה: {file[3]}, זמן העלאה: {file[4]}" for file in files]
        )
    else:
        response = "לא נמצאו קבצים במערכת."

    await update.message.reply_text(response)

async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """תפריט הורדות עם קטגוריות."""
    await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("🎵 פלייליסטים חינם", callback_data='category_playlists')],
        [InlineKeyboardButton("📲 אפליקציות", callback_data='category_apps')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("בחר קטגוריה:", reply_markup=reply_markup)

async def download_zip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """יצירת ZIP עם סיסמה ושליחתו למשתמש."""
    zip_path = f'{category}.zip'

    # יצירת קובץ ZIP עם כל הקבצים בקטגוריה
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(f'uploads/{category}'):
            for file in files:
                zipf.write(os.path.join(root, file), arcname=file)

    # שליחת ה-ZIP עם הודעה על הסיסמה
    await update.callback_query.message.reply_document(
        document=open(zip_path, 'rb'),
        caption=f'סיסמה לקובץ ZIP: {PASSWORD}'
    )

async def main():
    create_database()

    app = Application.builder().token(TOKEN).build()

    # הגדרת Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("uploaded_files", uploaded_files))
    app.add_handler(CallbackQueryHandler(upload_callback, pattern='upload'))
    app.add_handler(CallbackQueryHandler(download_callback, pattern='download'))
    app.add_handler(CallbackQueryHandler(lambda u, c: download_zip_callback(u, c, 'פלייליסטים'), pattern='category_playlists'))
    app.add_handler(CallbackQueryHandler(lambda u, c: download_zip_callback(u, c, 'אפליקציות'), pattern='category_apps'))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))

    # טיפול בלולאת האירועים
    if platform.system() == "Windows":
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Future()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
