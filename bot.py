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

# Telegram Bot Token - Sicherheit verbessert
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    print("FEHLER: Kein Telegram Token gefunden!")
    exit(1)

class BotData:
    def __init__(self):
        self.color_filter = {}  # Speichert den Farbfilter pro User
        self.mode = {}  # 'transparent' oder 'filter'
        self.last_colors = {}  # Speichert die letzten analysierten Farben pro User

bot_data = BotData()

def resize_with_padding(image, target_size):
    """Resize image maintaining aspect ratio and pad with transparency."""
    original_width, original_height = image.size
    aspect_ratio = original_width / original_height

    if aspect_ratio > target_size[0] / target_size[1]:
        new_width = target_size[0]
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = target_size[1]
        new_width = int(new_height * aspect_ratio)

    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    padded_image = Image.new('RGBA', target_size, (0, 0, 0, 0))
    x_offset = (target_size[0] - new_width) // 2
    y_offset = (target_size[1] - new_height) // 2
    padded_image.paste(resized_image, (x_offset, y_offset))
    return padded_image

def advanced_color_filter(input_data, target_color, tolerance=50, edge_softness=10):
    """
    Fortschrittliche Farbfilterung mit weichen Bildrändern
    
    :param input_data: Bilddaten
    :param target_color: Zu filternde Grundfarbe
    :param tolerance: Farbtoleranz
    :param edge_softness: Weichheit der Bildränder (0-100)
    :return: Gefiltertes Bild
    """
    target_r, target_g, target_b = tuple(int(target_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    mask_data = remove(input_data, only_mask=True)
    mask = Image.open(io.BytesIO(mask_data))
    original = Image.open(io.BytesIO(input_data))
    original = original.convert('RGBA')
    mask = mask.convert('L')
    result = Image.new('RGBA', original.size)
    
    width, height = original.size
    original_pixels = original.load()
    mask_pixels = mask.load()
    result_pixels = result.load()

    def color_distance(color1, color2):
        return max(abs(color1[0] - color2[0]), 
                   abs(color1[1] - color2[1]), 
                   abs(color1[2] - color2[2]))

    for x in range(width):
        for y in range(height):
            if mask_pixels[x, y] > 128:
                pixel = original_pixels[x, y]
                color_diff = color_distance(pixel, (target_r, target_g, target_b))
                alpha = 255
                edge_distance = min(
                    x, y,                 
                    width - x - 1,        
                    height - y - 1        
                )
                if edge_distance < edge_softness:
                    edge_factor = edge_distance / edge_softness
                    alpha = int(255 * edge_factor)
                if color_diff < tolerance:
                    alpha_reduction = int(255 * (color_diff / tolerance))
                    alpha = min(alpha, alpha_reduction)
                result_pixels[x, y] = (
                    pixel[0], 
                    pixel[1], 
                    pixel[2], 
                    max(0, alpha)  
                )
            else:
                result_pixels[x, y] = (0, 0, 0, 0)

    return result

def process_image(update, context):
    """Verarbeitet das empfangene Bild."""
    try:
        user_id = update.effective_user.id
        mode = bot_data.mode.get(user_id, 'transparent')
        
        if mode == 'transparent':
            msg = update.message.reply_text("Erstelle transparentes Bild... (ca. 30-60 Sekunden)")
        else:
            color = bot_data.color_filter.get(user_id)
            if not color:
                update.message.reply_text("Kein Farbfilter gesetzt. Bitte erst mit /filter #FARBCODE einen Filter setzen.")
                return
            msg = update.message.reply_text(f"Filtere Farbe {color}... (ca. 30-60 Sekunden)")

        logger.info("Bild empfangen, starte Verarbeitung...")
        photo_file = update.message.photo[-1].get_file()
        response = requests.get(photo_file.file_path)
        input_data = response.content
        logger.info("Bild in Speicher geladen")
        bot_data.last_colors[user_id] = analyze_dominant_colors(input_data)
        colors = bot_data.last_colors[user_id]
        color_text = "\n".join([f"Farbe {i+1}: {color[0]} ({color[1]:.1f}%)" 
                               for i, color in enumerate(colors)])
        update.message.reply_text(
            f"Dominante Farben im Bild:\n{color_text}\n"
            "Verwende diese Farbcodes mit dem /filter Befehl."
        )
        gc.collect()
        logger.info("Starte Bildverarbeitung...")
        if mode == 'transparent':
            output_img = Image.open(io.BytesIO(remove(input_data)))
        else:
            output_img = advanced_color_filter(
                input_data, 
                bot_data.color_filter[user_id], 
                tolerance=40,  
                edge_softness=15  
            )
        logger.info("Bildverarbeitung abgeschlossen")
        resized_img = resize_with_padding(output_img, (4500, 5400))
        img_byte_arr = io.BytesIO()
        resized_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        filename = 'transparent_4500x5400.png' if mode == 'transparent' else f'filtered_{bot_data.color_filter[user_id][1:]}_4500x5400.png'
        update.message.reply_document(
            document=img_byte_arr,
            filename=filename
        )
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
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("filter", set_filter))
    dp.add_handler(CommandHandler("mode_transparent", mode_transparent))
    dp.add_handler(CommandHandler("mode_filter", mode_filter))
    dp.add_handler(CommandHandler("analyze_colors", analyze_colors))
    dp.add_handler(MessageHandler(Filters.photo, process_image))
    logger.info("Bot handlers registered")
    updater.start_polling()
    logger.info("Bot is now running")
    updater.idle()

if __name__ == '__main__':
    main()

