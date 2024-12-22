import os
import io
import requests
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from rembg import remove

# Kleineres Modell verwenden
os.environ['REMBG_MODEL'] = 'u2netp'

# Telegram Bot Token
TOKEN = os.getenv('TELEGRAM_TOKEN', 'IHR_TOKEN_HIER')

def start(update, context):
    """Sendet eine Nachricht wenn der Befehl /start ausgegeben wird."""
    update.message.reply_text('Hallo! Sende mir ein Bild und ich werde den Hintergrund entfernen.')

def process_image(update, context):
    """Verarbeitet das empfangene Bild."""
    try:
        print("Bild empfangen, starte Verarbeitung...")  # Debug
        
        # Progress Nachricht
        msg = update.message.reply_text("Verarbeite Bild... (ca. 30-60 Sekunden)")
        
        # Bild vom Benutzer herunterladen
        photo_file = update.message.photo[-1].get_file()
        print("Bild heruntergeladen")  # Debug
        
        # Direkt im Speicher verarbeiten
        response = requests.get(photo_file.file_path)
        input_data = response.content
        print("Bild in Speicher geladen")  # Debug
        
        # Hintergrund entfernen
        print("Starte Hintergrundentfernung...")  # Debug
        output_data = remove(input_data, model_name='u2netp')
        print("Hintergrund entfernt")  # Debug
        
        # Ergebnis senden
        update.message.reply_document(
            document=io.BytesIO(output_data),
            filename='ohne_hintergrund.png'
        )
        print("Bild erfolgreich gesendet")  # Debug
        
        # Progress Nachricht löschen
        msg.delete()
        
    except Exception as e:
        print(f"Fehler aufgetreten: {str(e)}")  # Debug
        update.message.reply_text(f'Ein Fehler ist aufgetreten: {str(e)}')

def main():
    """Startet den Bot."""
    print("Bot starting...")  # Debug
    
    # Bot starten
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.photo, process_image))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
