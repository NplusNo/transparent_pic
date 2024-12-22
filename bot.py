import os
import io
from PIL import Image
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

def resize_with_padding(image, target_size):
   """Resize image maintaining aspect ratio and pad with transparency."""
   original_width, original_height = image.size
   aspect_ratio = original_width / original_height
   
   if aspect_ratio > target_size[0] / target_size[1]:
       # Bild ist verhältnismäßig breiter
       new_width = target_size[0]
       new_height = int(new_width / aspect_ratio)
   else:
       # Bild ist verhältnismäßig höher
       new_height = target_size[1]
       new_width = int(new_height * aspect_ratio)
   
   # Bild proportional skalieren
   resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
   
   # Neues transparentes Bild mit Zielgröße erstellen
   padded_image = Image.new('RGBA', target_size, (0, 0, 0, 0))
   
   # Skaliertes Bild in die Mitte des neuen Bildes einfügen
   x_offset = (target_size[0] - new_width) // 2
   y_offset = (target_size[1] - new_height) // 2
   padded_image.paste(resized_image, (x_offset, y_offset))
   
   return padded_image

def start(update, context):
   """Sendet eine Nachricht wenn der Befehl /start ausgegeben wird."""
   logger.info("Received /start command")
   update.message.reply_text('Hallo! Sende mir ein Bild und ich werde den Hintergrund entfernen.')

def process_image(update, context):
   """Verarbeitet das empfangene Bild."""
   try:
       logger.info("Bild empfangen, starte Verarbeitung...")
       msg = update.message.reply_text("Verarbeite Bild... (ca. 30-60 Sekunden)")
       
       photo_file = update.message.photo[-1].get_file()
       logger.info("Bild heruntergeladen")
       
       response = requests.get(photo_file.file_path)
       input_data = response.content
       logger.info("Bild in Speicher geladen")
       
       gc.collect()
       
       logger.info("Starte Hintergrundentfernung...")
       output_data = remove(
           input_data,
           alpha_matting=False,
           only_mask=False,
           post_process_mask=False
       )
       logger.info("Hintergrund entfernt")
       
       # Bild in Pillow laden
       img = Image.open(io.BytesIO(output_data))
       
       # Verschiedene Größen erstellen
       sizes = [(4500, 5400), (4500, 5400)]
       for width, height in sizes:
           resized_img = resize_with_padding(img, (width, height))
           
           # In Bytes umwandeln
           img_byte_arr = io.BytesIO()
           resized_img.save(img_byte_arr, format='PNG')
           img_byte_arr.seek(0)
           
           # Senden
           update.message.reply_document(
               document=img_byte_arr,
               filename=f'transparent_{width}x{height}.png'
           )
           
       logger.info("Bilder erfolgreich gesendet")
       msg.delete()
       
   except Exception as e:
       error_msg = f"Fehler aufgetreten: {str(e)}"
       logger.error(error_msg)
       update.message.reply_text(error_msg)
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
