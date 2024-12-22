import os
import io
from PIL import Image
import requests
import logging
import gc
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from rembg import remove
from google.cloud import vision
import random

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

def generate_product_details(image_content):
    """Analysiert das Bild und generiert Produktdetails."""
    try:
        # Google Cloud Vision Client
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_content)
        
        # Bild analysieren
        response = client.label_detection(image=image)
        labels = response.label_annotations
        
        # Hauptthema des Bildes ermitteln
        main_themes = [label.description for label in labels[:3]]
        
        # Produktdetails generieren
        design_title = f"{main_themes[0]} Design"
        brand = f"{main_themes[0]} Art"
        
        # Feature Bullets generieren
        feature_1 = f"Unique {main_themes[0]} artwork featuring {main_themes[1]} elements"
        feature_2 = f"Perfect gift for {main_themes[2]} enthusiasts and fans"
        
        # Beschreibung generieren
        description = f"""
Discover this unique {main_themes[0]} design that combines {main_themes[1]} with artistic flair. 
This artwork features high-quality printing and vivid colors that won't fade. 
Perfect as a gift for anyone who loves {main_themes[2]} or as a special treat for yourself.
The design is carefully crafted to ensure both style and comfort.
Made with love and attention to detail, this design is perfect for those who appreciate {main_themes[0]}.
Whether you're a fan of {main_themes[1]} or simply love unique artwork, this piece is sure to make a statement.
Show your passion for {main_themes[2]} with this eye-catching design that stands out from the crowd.
        """.strip()
        
        return {
            "design_title": design_title[:58],
            "brand": brand[:48],
            "feature_1": feature_1[:254],
            "feature_2": feature_2[:254],
            "description": description[:1998]
        }
    except Exception as e:
        logger.error(f"Fehler bei der Bilderkennung: {str(e)}")
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
        product_details = generate_product_details(input_data)
        
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
