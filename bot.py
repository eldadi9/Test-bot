import os
import sqlite3
import zipfile
import asyncio
import platform
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from zipfile import ZipFile, ZIP_DEFLATED
from threading import Lock  # מנעול למניעת כפילות בהורדה
import shutil
import tempfile

TOKEN = '7908068063:AAEoi6BHjEEk2O0t7SANwsZ1DC1Qph4x3hY'
PASSWORD = 'olam_tov'  # סיסמת ZIP

# מנעול למניעת הורדות כפולות בו-זמנית
download_lock = Lock()

def create_database():
    """יוצר את בסיס הנתונים והטבלאות הדרושות אם הן לא קיימות."""
    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()

    # טבלת קבצים שהועלו
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

    # טבלת לוג הורדות
    c.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            download_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT,
            downloader_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            download_time TEXT
        )
    ''')

    conn.commit()
    conn.close()

def create_secure_zip(file_paths, output_zip_path, password):
    """יוצר קובץ ZIP מוגן בסיסמה."""
    try:
        with ZipFile(output_zip_path, 'w', ZIP_DEFLATED) as zipf:
            zipf.setpassword(password.encode('utf-8'))
            for file_path in file_paths:
                zipf.write(file_path, os.path.basename(file_path))
        print(f"קובץ ZIP נוצר בהצלחה: {output_zip_path}")
    except Exception as e:
        print(f"שגיאה ביצירת קובץ ה-ZIP: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """תפריט ראשי."""
    print(update.message.from_user.id)  # הדפסת מזהה המשתמש למסוף
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
    """מטפל בהעלאת קובץ ושומר את הנתונים בבסיס הנתונים."""
    user = update.message.from_user
    file = update.message.document
    file_name = file.file_name
    upload_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    category = 'פלייליסטים' if file_name.endswith(('.m3u', '.m3u8')) else 'אפליקציות' if file_name.endswith('.apk') else 'אחר'
    os.makedirs(f'uploads/{category}', exist_ok=True)
    file_path = f'uploads/{category}/{file_name}'
    new_file = await context.bot.get_file(file.file_id)
    await new_file.download_to_drive(file_path)

    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO files (file_id, file_name, uploader_id, username, first_name, last_name, category, upload_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (file.file_id, file_name, user.id, user.username or "לא זמין", user.first_name, user.last_name or "לא זמין", category, upload_time))
    conn.commit()
    conn.close()

    await update.message.reply_text("תודה רבה! הקובץ הועלה בהצלחה.")

async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """תפריט הורדות עם קטגוריות."""
    await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("🎵 פלייליסטים", callback_data='category_playlists')],
        [InlineKeyboardButton("📲 אפליקציות", callback_data='category_apps')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("בחר קטגוריה להורדה:", reply_markup=reply_markup)

async def download_zip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """יוצר ZIP מוגן בסיסמה ושולח למשתמש."""
    if not download_lock.acquire(blocking=False):
        await update.callback_query.answer("ההורדה כבר מתבצעת, נסה שוב בעוד רגע.")
        return

    try:
        zip_path = f'{category}.zip'
        user = update.callback_query.from_user
        download_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        file_paths = [
            os.path.join(root, file)
            for root, _, files in os.walk(f'uploads/{category}')
            for file in files
        ]

        if not file_paths:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("אין קבצים בקטגוריה שנבחרה.")
            return

        temp_dir = tempfile.mkdtemp()
        temp_zip_path = os.path.join(temp_dir, f"{category}.zip")

        with ZipFile(temp_zip_path, 'w', ZIP_DEFLATED) as zipf:
            zipf.setpassword(PASSWORD.encode('utf-8'))
            for file_path in file_paths:
                zipf.write(file_path, os.path.basename(file_path))

        shutil.move(temp_zip_path, zip_path)
        shutil.rmtree(temp_dir)

        conn = sqlite3.connect('downloads.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO downloads (file_name, downloader_id, username, first_name, last_name, download_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (f"{category}.zip", user.id, user.username or "לא זמין", user.first_name, user.last_name or "לא זמין", download_time))
        conn.commit()
        conn.close()

        await update.callback_query.answer()
        await update.callback_query.message.reply_document(
            document=open(zip_path, 'rb'),
            caption=f'להורדת הקובץ השתמש בסיסמה: {PASSWORD}',
            filename=f"{category}.zip"
        )

    finally:
        download_lock.release()

async def uploaded_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != 504019926:
        await update.message.reply_text("אין לך הרשאה לצפות במידע זה.")
        return

    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute('SELECT file_name, username, uploader_id, category, upload_time FROM files')
    files = c.fetchall()
    conn.close()

    response = "\n".join([f"📄 {file[0]} - הועלה ע\"י {file[1]} (ID: {file[2]})\nקטגוריה: {file[3]}, תאריך: {file[4]}" for file in files]) or "לא נמצאו קבצים."
    await update.message.reply_text(response)

async def download_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != 504019926:
        await update.message.reply_text("אין לך הרשאה לצפות במידע זה.")
        return

    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute('SELECT file_name, username, downloader_id, download_time FROM downloads')
    downloads = c.fetchall()
    conn.close()

    response = "\n".join([f"📥 {log[0]} - הורד ע\"י {log[1]} (ID: {log[2]}) בתאריך {log[3]}" for log in downloads]) or "לא נמצאו הורדות."
    await update.message.reply_text(response)

async def main():
    create_database()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("uploaded_files", uploaded_files))
    app.add_handler(CommandHandler("download_logs", download_logs))
    app.add_handler(CallbackQueryHandler(upload_callback, pattern='upload'))
    app.add_handler(CallbackQueryHandler(download_callback, pattern='download'))
    app.add_handler(CallbackQueryHandler(lambda u, c: download_zip_callback(u, c, 'פלייליסטים'), pattern='category_playlists'))
    app.add_handler(CallbackQueryHandler(lambda u, c: download_zip_callback(u, c, 'אפליקציות'), pattern='category_apps'))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))

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
