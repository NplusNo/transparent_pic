import os
import io
import requests
import logging
import gc
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from rembg import remove

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Print für Railway Logs
print("Bot is starting up...")

# Modell Konfiguration
os.environ['U2NET_HOME'] = '/tmp/.u2net'
os.environ['REMBG_MODEL'] = 'u2net_human_seg'

# Telegram Bot Token
TOKEN = os.getenv('TELEGRAM_TOKEN', 'IHR_TOKEN_HIER')

def start(update, context):
    """Sendet eine Nachricht wenn der Befehl /start ausgegeben wird."""
    logger.info("Received /start command")
    update.message.reply_text('Hallo! Sende mir ein Bild und ich werde den Hintergrund entfernen.')

def process_image(update, context):
    """Verarbeitet das empfangene Bild."""
    try:
        logger.info("Bild empfangen, starte Verarbeitung...")
        
        # Progress Nachricht
        msg = update.message.reply_text("Verarbeite Bild... (ca. 30-60 Sekunden)")
        
        # Bild vom Benutzer herunterladen
        photo_file = update.message.photo[-1].get_file()
        logger.info("Bild heruntergeladen")
        
        # Direkt im Speicher verarbeiten
        response = requests.get(photo_file.file_path)
        input_data = response.content
        logger.info("Bild in Speicher geladen")
        
        # Speicher freigeben
        gc.collect()
        
        # Hintergrund entfernen
        logger.info("Starte Hintergrundentfernung...")
        output_data = remove(
            input_data,
            alpha_matting=False,
            only_mask=False,
            post_process_mask=False
        )
        logger.info("Hintergrund entfernt")
        
        # Ergebnis senden
        update.message.reply_document(
            document=io.BytesIO(output_data),
            filename='ohne_hintergrund.png'
        )
        logger.info("Bild erfolgreich gesendet")
        
        # Progress Nachricht löschen
        msg.delete()
        
    except Exception as e:
        error_msg = f"Fehler aufgetreten: {str(e)}"
        logger.error(error_msg)
        update.message.reply_text(error_msg)
        # Speicher freigeben bei Fehler
        gc.collect()

def main():
    """Startet den Bot."""
    logger.info("Bot starting...")
    
    # Bot starten
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.photo, process_image))
    
    logger.info("Bot handlers registered")
    
    updater.start_polling()
    logger.info("Bot is now running")
    updater.idle()

if __name__ == '__main__':
    main()
