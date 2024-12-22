import os
import io
import requests
import logging
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

# Kleineres Modell verwenden
os.environ['REMBG_MODEL'] = 'u2netp'
os.environ['REMBG_CACHE_DIR'] = '/tmp'

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
        
        # Hintergrund entfernen
        logger.info("Starte Hintergrundentfernung...")
        output_data = remove(input_data)  # Verwendet das Modell aus der Umgebungsvariable
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
