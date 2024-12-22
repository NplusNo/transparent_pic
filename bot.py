import os
import io
from PIL import Image
import requests
import logging
import gc
import random
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

def analyze_image(image_data):
   """Simple local image analysis"""
   try:
       # Liste möglicher Kategorien
       categories = [
           ["Fashion", "Style", "Design"],
           ["Animal", "Wildlife", "Nature"],
           ["Art", "Abstract", "Creative"],
           ["Vintage", "Retro", "Classic"],
           ["Fun", "Humor", "Joy"],
           ["Love", "Heart", "Romance"],
           ["Sport", "Active", "Fitness"],
           ["Music", "Sound", "Rhythm"],
           ["Food", "Cuisine", "Delicious"],
           ["Travel", "Adventure", "Explore"],
           ["Cute", "Adorable", "Sweet"],
           ["Fantasy", "Magic", "Dream"],
           ["Space", "Galaxy", "Universe"],
           ["Gothic", "Dark", "Mysterious"],
           ["Anime", "Manga", "Japanese"]
       ]
       
       # Zufällige Kategorie wählen
       chosen = random.choice(categories)
       
       # Produktdetails generieren
       design_title = f"{chosen[0]} {chosen[1]} Art"
       brand = f"{chosen[0]} Art Collection"
       
       feature_1 = f"Unique {chosen[0]} design featuring {chosen[1]} elements"
       feature_2 = f"Perfect gift for {chosen[2]} enthusiasts and fans"
       
       description = f"""
Experience this unique {chosen[0]} design that beautifully combines {chosen[1]} elements with artistic expression.
Our high-quality printing process ensures vibrant colors that won't fade, making this piece a lasting addition to your collection.
Perfect as a thoughtful gift for {chosen[2]} enthusiasts or as a special treat for yourself.
This design is carefully crafted with attention to detail, ensuring both style and quality.
Show your passion for {chosen[0]} with this eye-catching design that stands out from the crowd.
Whether you're a fan of {chosen[1]} or simply appreciate unique artwork, this piece makes a bold statement.
Each design is created with care and printed using premium techniques to ensure lasting quality.
The perfect blend of style and creativity makes this design a must-have for any {chosen[2]} lover.
       """.strip()
       
       return {
           "design_title": design_title[:58],
           "brand": brand[:48],
           "feature_1": feature_1[:254],
           "feature_2": feature_2[:254],
           "description": description[:1998]
       }
       
   except Exception as e:
       logger.error(f"Fehler bei der Bildanalyse: {str(e)}")
       return None

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
       
       # Produktdetails generieren
       product_details = analyze_image(input_data)
       
       gc.collect()
       
       logger.info("Starte Hintergrundentfernung...")
       output_data = remove(
           input_data,
           alpha_matting=False,
           only_mask=False,
           post_process_mask=False
       )
       logger.info("Hintergrund entfernt")
       
       # Bild in Pillow laden und resize
       img = Image.open(io.BytesIO(output_data))
       resized_img = resize_with_padding(img, (4500, 5400))
       
       # In Bytes umwandeln
       img_byte_arr = io.BytesIO()
       resized_img.save(img_byte_arr, format='PNG')
       img_byte_arr.seek(0)
       
       # Bild senden
       update.message.reply_document(
           document=img_byte_arr,
           filename='transparent_4500x5400.png'
       )
       
       # Produktdetails senden
       if product_details:
           details_text = f"""
🎨 *Product Details*
*Design Title:* {product_details['design_title']}
*Brand:* {product_details['brand']}

📋 *Product Features*
- {product_details['feature_1']}
- {product_details['feature_2']}

📝 *Description*
{product_details['description']}
           """.strip()
           
           update.message.reply_text(details_text, parse_mode='Markdown')
       
       logger.info("Verarbeitung abgeschlossen")
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
