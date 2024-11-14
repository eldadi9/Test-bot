import os
import sqlite3
import zipfile
import asyncio
import platform
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from zipfile import ZipFile, ZIP_DEFLATED
from threading import Lock
import shutil
import tempfile

TOKEN = '7908068063:AAEoi6BHjEEk2O0t7SANwsZ1DC1Qph4x3hY'
PASSWORD = 'olam_tov'  # סיסמת ZIP

download_lock = Lock()

def create_database():
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
    keyboard = [
        [InlineKeyboardButton("📤 העלאת קובץ", callback_data='upload')],
        [InlineKeyboardButton("📥 הורדת קבצים", callback_data='download')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ברוכים הבאים! מה תרצה לעשות?", reply_markup=reply_markup)

async def upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("אנא שלח את הקובץ להעלאה.")

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    file = update.message.document
    file_name = file.file_name
    upload_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    category = 'אחר'
    app_folder = os.path.splitext(file_name)[0]
    file_path = f'uploads/{category}/{app_folder}/{file_name}'
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

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

    await update.message.reply_text("הקובץ הועלה בהצלחה!")

async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("פלייליסטים", callback_data='download_playlists')],
        [InlineKeyboardButton("אפליקציות", callback_data='download_apps')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("בחר קטגוריה להורדה:", reply_markup=reply_markup)

async def download_playlists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not download_lock.acquire(blocking=False):
        await update.callback_query.answer("ההורדה כבר מתבצעת, נסה שוב בעוד רגע.")
        return

    try:
        category = 'פלייליסטים'
        files_path = f'uploads/{category}/'
        file_paths = [os.path.join(files_path, f) for f in os.listdir(files_path) if f.endswith('.m3u') or f.endswith('.m3u8')]

        if not file_paths:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("אין קבצים להורדה.")
            return

        zip_path = f'{category}.zip'
        with ZipFile(zip_path, 'w', ZIP_DEFLATED) as zipf:
            zipf.setpassword(PASSWORD.encode('utf-8'))
            for file_path in file_paths:
                zipf.write(file_path, arcname=os.path.basename(file_path))

        await update.callback_query.answer()
        await update.callback_query.message.reply_document(
            document=open(zip_path, 'rb'),
            caption=f'הורד את כל הפלייליסטים בקובץ ZIP, השתמש בסיסמה: {PASSWORD}',
            filename=zip_path
        )
    finally:
        download_lock.release()

async def download_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    conn = sqlite3.connect('downloads.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT file_name FROM files WHERE category = 'אפליקציות'")
    apps = c.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton(app[0], callback_data=f'download_app_{app[0]}')] for app in apps]
    keyboard.append([InlineKeyboardButton("חזור", callback_data='download')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("בחר אפליקציה להורדה:", reply_markup=reply_markup)

async def download_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app_name = update.callback_query.data.split('_')[2]
    if not download_lock.acquire(blocking=False):
        await update.callback_query.answer("ההורדה כבר מתבצעת, נסה שוב בעוד רגע.")
        return

    try:
        category = 'אפליקציות'
        file_path = f'uploads/{category}/{app_name}/{app_name}.apk'  # ודא שהנתיב זהה לנתיב שמור במסד הנתונים ובעת העלאה

        if not os.path.exists(file_path):
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("הקובץ לא נמצא.")
            return

        zip_path = f"{app_name}.zip"
        with ZipFile(zip_path, 'w', ZIP_DEFLATED) as zipf:
            zipf.setpassword(PASSWORD.encode('utf-8'))
            zipf.write(file_path, arcname=os.path.basename(file_path))

        await update.callback_query.answer()
        await update.callback_query.message.reply_document(
            document=open(zip_path, 'rb'),
            caption=f'להורדת האפליקציה השתמש בסיסמה: {PASSWORD}',
            filename=zip_path
        )
    finally:
        download_lock.release()


async def main():
    create_database()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(upload_callback, pattern='^upload$'))
    app.add_handler(CallbackQueryHandler(download_callback, pattern='^download$'))
    app.add_handler(CallbackQueryHandler(download_playlists, pattern='^download_playlists$'))
    app.add_handler(CallbackQueryHandler(download_apps, pattern='^download_apps$'))
    app.add_handler(CallbackQueryHandler(download_app, pattern='^download_app_'))
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
