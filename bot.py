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

# Bot Data Class für User-Einstellungen
class BotData:
    def __init__(self):
        self.description_enabled = {}  # Speichert den Status pro User

bot_data = BotData()

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
    """Generiert Produktdetails mit lokaler Logik"""
    try:
        # Liste möglicher Kategorien
        categories = [
            ["Fashion", "Style", "Trendy", "Modern fashion that makes a statement"],
            ["Animal", "Wildlife", "Nature", "Beautiful wildlife artwork"],
            ["Art", "Abstract", "Creative", "Unique artistic expression"],
            ["Vintage", "Retro", "Classic", "Timeless retro charm"],
            ["Fun", "Humor", "Joy", "Bringing smiles and laughter"],
            ["Love", "Heart", "Romance", "Spreading love and joy"],
            ["Sport", "Active", "Fitness", "For the active lifestyle"],
            ["Music", "Sound", "Rhythm", "For music lovers"],
            ["Food", "Cuisine", "Delicious", "Foodie favorites"],
            ["Travel", "Adventure", "Explore", "Adventure awaits"],
            ["Cute", "Adorable", "Sweet", "Irresistibly cute"],
            ["Fantasy", "Magic", "Dream", "Magical and mystical"],
            ["Space", "Galaxy", "Universe", "Out of this world"],
            ["Gothic", "Dark", "Mysterious", "Dark and mysterious"],
            ["Anime", "Manga", "Japanese", "Anime inspired art"]
        ]
        
        # Zufällige Kategorie wählen
        chosen = random.choice(categories)
        
        # Produktdetails generieren
        design_title = f"{chosen[0]} {chosen[1]} Design Collection"
        brand = f"{chosen[0]} Art Studio"
        
        feature_1 = f"Premium {chosen[0]} artwork featuring unique {chosen[1]} elements - {chosen[3]}"
        feature_2 = f"Perfect gift for {chosen[2]} enthusiasts - High-quality design that stands out"
        
        description = f"""
Welcome to our exclusive {chosen[0]} collection! This unique design combines the beauty of {chosen[1]} with the spirit of {chosen[2]}.

{chosen[3]}! Our high-quality printing process ensures vibrant colors that won't fade, making this piece a lasting addition to your collection.

Key Features:
- Premium quality materials
- Vibrant, long-lasting colors
- Professional {chosen[0]} design
- Perfect for {chosen[2]} lovers
- Makes a great gift

Whether you're a fan of {chosen[1]} or simply appreciate unique artwork, this piece makes a bold statement. Each design is carefully crafted to ensure both style and quality.

Ideal for:
- {chosen[2]} enthusiasts
- {chosen[0]} lovers
- Unique gift-giving
- Personal style expression
- Collection addition

Care Instructions:
Machine washable, inside out with cold water. The design is made to last through multiple washes while maintaining its vibrant appearance.
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
    user_id = update.effective_user.id
    bot_data.description_enabled[user_id] = False  # Standard: Beschreibung aus
    update.message.reply_text(
        'Hallo! Sende mir ein Bild und ich werde den Hintergrund entfernen.\n'
        'Nutze /help um alle verfügbaren Befehle zu sehen.'
    )

def help_command(update, context):
    """Zeigt Hilfe-Text mit allen verfügbaren Commands."""
    help_text = """
*Verfügbare Befehle:*

/start - Startet den Bot und zeigt die Willkommensnachricht
/help - Zeigt diese Hilfe-Nachricht
/description_on - Aktiviert automatische Produktbeschreibungen
/description_off - Deaktiviert automatische Produktbeschreibungen

*Verwendung:*
1. Sende ein Bild an den Bot
2. Der Bot entfernt den Hintergrund
3. Das Bild wird auf 4500x5400px skaliert
4. Wenn Produktbeschreibungen aktiviert sind, werden diese automatisch generiert

*Hinweise:*
- Produktbeschreibungen sind standardmäßig deaktiviert
- Die Bildverarbeitung kann 30-60 Sekunden dauern
- Bilder werden proportional skaliert und mit Transparenz aufgefüllt
""".strip()
    
    update.message.reply_text(help_text, parse_mode='Markdown')

def description_on(update, context):
    """Aktiviert Produktbeschreibungen für den User."""
    user_id = update.effective_user.id
    bot_data.description_enabled[user_id] = True
    update.message.reply_text("Produktbeschreibungen sind jetzt aktiviert! 🟢")

def description_off(update, context):
    """Deaktiviert Produktbeschreibungen für den User."""
    user_id = update.effective_user.id
    bot_data.description_enabled[user_id] = False
    update.message.reply_text("Produktbeschreibungen sind jetzt deaktiviert! 🔴")

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
        
        # Produktdetails nur generieren wenn aktiviert
        user_id = update.effective_user.id
        product_details = None
        if bot_data.description_enabled.get(user_id, False):
            product_details = analyze_image(input_data)
        
        gc.collect()
        
        logger.info("Starte Hintergrundentfernung...")
        output_data = remove(
            input_data,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,  # Höherer Wert für bessere Weißerkennung
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=5,
            post_process_mask=True
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
        
        # Produktdetails senden wenn aktiviert
        if bot_data.description_enabled.get(user_id, False) and product_details:
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
    
    # Handler registrieren
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("description_on", description_on))
    dp.add_handler(CommandHandler("description_off", description_off))
    dp.add_handler(MessageHandler(Filters.photo, process_image))
    
    logger.info("Bot handlers registered")
    
    updater.start_polling()
    logger.info("Bot is now running")
    updater.idle()

if __name__ == '__main__':
    main()
