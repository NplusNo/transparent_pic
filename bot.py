import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import telegram
from PIL import Image
import requests
import torch
from torchvision import transforms
from rembg import remove
import numpy as np
import io

# Telegram Bot Token aus Umgebungsvariable
TOKEN = os.getenv('TELEGRAM_TOKEN')

def start(update, context):
    """Sendet eine Nachricht wenn der Befehl /start ausgegeben wird."""
    update.message.reply_text('Hallo! Sende mir ein Bild und ich werde das Hauptobjekt erkennen und den Hintergrund entfernen.')

def process_image(update, context):
    """Verarbeitet das empfangene Bild."""
    try:
        # Bild vom Benutzer herunterladen
        photo_file = update.message.photo[-1].get_file()
        
        # Temporärer Dateiname für das Originalbild
        input_path = f"temp_{update.message.chat_id}.jpg"
        output_path = f"output_{update.message.chat_id}.png"
        
        # Bild speichern
        photo_file.download(input_path)
        
        # Hintergrund mit rembg entfernen
        with open(input_path, 'rb') as i:
            input_data = i.read()
            output_data = remove(input_data)
            
            # Ergebnis speichern
            with open(output_path, 'wb') as o:
                o.write(output_data)
        
        # Verarbeitetes Bild zurücksenden
        with open(output_path, 'rb') as photo:
            update.message.reply_photo(photo)
        
        # Temporäre Dateien löschen
        os.remove(input_path)
        os.remove(output_path)
        
    except Exception as e:
        update.message.reply_text(f'Ein Fehler ist aufgetreten: {str(e)}')

def main():
    """Startet den Bot."""
    # Updater für den Bot erstellen
    updater = Updater(TOKEN, use_context=True)

    # Dispatcher für die Behandlung von Befehlen registrieren
    dp = updater.dispatcher

    # Befehlshandler hinzufügen
    dp.add_handler(CommandHandler("start", start))
    
    # Bildhandler hinzufügen
    dp.add_handler(MessageHandler(Filters.photo, process_image))

    # Bot starten
    updater.start_polling()
    
    # Bot am Laufen halten bis Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()
