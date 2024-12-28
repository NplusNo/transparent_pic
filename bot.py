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
        self.color_filter = {}      # Speichert den Farbfilter pro User
        self.filter_tolerance = {}  # Speichert die Toleranz pro User
        self.mode = {}             # 'transparent' oder 'filter'
        self.last_colors = {}      # Speichert die letzten analysierten Farben
        self.image_position = {}   # Speichert Positionierungseinstellungen pro User

bot_data = BotData()

def get_color_name(rgb):
    """Bestimmt den Namen einer Farbe basierend auf RGB-Werten."""
    r, g, b = rgb
    
    # Helligkeit und Sättigung berechnen
    brightness = (r + g + b) / 3
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    saturation = (max_val - min_val) / max_val if max_val != 0 else 0
    
    # Grundfarben definieren
    if max_val < 30:
        return "Schwarz"
    elif brightness > 240:
        return "Weiß"
    elif saturation < 0.1:
        if brightness < 128:
            return "Dunkelgrau"
        else:
            return "Hellgrau"
    
    # Farbton bestimmen
    if r > max(g, b):
        if g > b:
            if saturation > 0.8:
                return "Leuchtendes Rot"
            return "Rot-Orange" if g > r/2 else "Rot"
        else:
            if saturation > 0.8:
                return "Magenta"
            return "Pink" if b > r/2 else "Dunkelrot"
    elif g > max(r, b):
        if r > b:
            return "Gelbgrün" if r > g/2 else "Hellgrün"
        else:
            return "Türkis" if b > g/2 else "Grün"
    else:
        if r > g:
            return "Violett" if r > b/2 else "Lila"
        else:
            return "Cyanblau" if g > b/2 else "Blau"

def analyze_dominant_colors(input_data, num_colors=25):
    """Analysiert die dominanten Farben im Bild."""
    # Bild laden
    img = Image.open(io.BytesIO(input_data))
    img = img.convert('RGB')
    
    # Bild verkleinern für schnellere Verarbeitung
    img.thumbnail((200, 200))
    
    # Pixel sammeln
    pixels = list(img.getdata())
    
    # Farben zählen mit verbesserter Gruppierung
    color_counts = {}
    for pixel in pixels:
        # Feinere Gruppierung für mehr Farbvariationen
        rounded = (round(pixel[0]/5)*5, 
                  round(pixel[1]/5)*5, 
                  round(pixel[2]/5)*5)
        color_counts[rounded] = color_counts.get(rounded, 0) + 1
    
    # Nach Häufigkeit sortieren
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Konvertiere zu Hex und formatiere
    dominant_colors = []
    for color, count in sorted_colors[:num_colors]:
        hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
        percentage = (count / len(pixels)) * 100
        color_name = get_color_name(color)
        dominant_colors.append((hex_color, percentage, color_name))
    
    return dominant_colors

def improved_color_filter(input_data, target_color, tolerance_percent=0):
    """
    Verbesserter Farbfilter mit einstellbarer Toleranz.
    
    Args:
        input_data: Bilddaten
        target_color: Hex-Farbcode (z.B. '#FFFFFF')
        tolerance_percent: Toleranz in Prozent (0-100)
    """
    # Zielfarbe in RGB
    target_r = int(target_color[1:3], 16)
    target_g = int(target_color[3:5], 16)
    target_b = int(target_color[5:7], 16)
    
    # Toleranz in RGB-Werte umrechnen (0-255)
    # Bei 100% Toleranz werden Unterschiede bis zu 255 akzeptiert
    max_diff = int((255 * tolerance_percent) / 100)
    
    # Originalbild laden und in RGBA konvertieren
    original = Image.open(io.BytesIO(input_data))
    original = original.convert('RGBA')
    
    # Neues Bild mit Alphakanal
    result = Image.new('RGBA', original.size)
    
    # Pixel-Arrays
    width, height = original.size
    original_pixels = original.load()
    result_pixels = result.load()
    
    def color_similarity(color1, target):
        """Berechnet die Ähnlichkeit zwischen zwei Farben."""
        r_diff = abs(color1[0] - target[0])
        g_diff = abs(color1[1] - target[1])
        b_diff = abs(color1[2] - target[2])
        
        # Gewichtete Differenz für bessere Wahrnehmung
        # Menschliches Auge ist empfindlicher für Grün
        weighted_diff = (r_diff * 0.3 + g_diff * 0.5 + b_diff * 0.2)
        return weighted_diff

    # Jeden Pixel überprüfen
    for x in range(width):
        for y in range(height):
            pixel = original_pixels[x, y]
            r, g, b, a = pixel
            
            # Berechne Farbähnlichkeit
            similarity = color_similarity((r, g, b), (target_r, target_g, target_b))
            
            if similarity <= max_diff:
                # Je ähnlicher die Farbe, desto transparenter
                alpha = int(max(0, 255 * (similarity / max_diff))) if max_diff > 0 else 0
                result_pixels[x, y] = (r, g, b, alpha)
            else:
                # Farbe liegt außerhalb der Toleranz
                result_pixels[x, y] = pixel
    
    return result

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
    
    # Bild proportional skalieren
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Neues transparentes Bild mit Zielgröße erstellen
    padded_image = Image.new('RGBA', target_size, (0, 0, 0, 0))
    
    # Skaliertes Bild in die Mitte des neuen Bildes einfügen
    x_offset = (target_size[0] - new_width) // 2
    y_offset = (target_size[1] - new_height) // 2
    padded_image.paste(resized_image, (x_offset, y_offset))
    
    return padded_image

def resize_with_positioning(image, target_size, x_percent=50, y_percent=50):
    """
    Resize image maintaining aspect ratio and position it precisely within target size.
    
    Args:
        image (PIL.Image): Input image
        target_size (tuple): Desired output size (width, height)
        x_percent (float): Horizontal positioning (0-100)
        y_percent (float): Vertical positioning (0-100)
    
    Returns:
        PIL.Image: Positioned and resized image
    """
    original_width, original_height = image.size
    aspect_ratio = original_width / original_height
    
    # Calculate new dimensions maintaining aspect ratio
    if aspect_ratio > target_size[0] / target_size[1]:
        new_width = target_size[0]
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = target_size[1]
        new_width = int(new_height * aspect_ratio)
    
    # Resize image with high-quality resampling
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Create new transparent image with target size
    padded_image = Image.new('RGBA', target_size, (0, 0, 0, 0))
    
    # Calculate positioning based on percentages
    x_offset = int((target_size[0] - new_width) * (x_percent / 100))
    y_offset = int((target_size[1] - new_height) * (y_percent / 100))
    
    # Paste resized image onto padded image
    padded_image.paste(resized_image, (x_offset, y_offset))
    
    return padded_image

def set_positioning(update, context):
    """
    Set image positioning for the next image processing
    
    Usage: /position X_PERCENT Y_PERCENT
    Example: /position 50 30  # Position slightly above center
    """
    try:
        x_percent = int(context.args[0])
        y_percent = int(context.args[1])
        
        if not (0 <= x_percent <= 100 and 0 <= y_percent <= 100):
            raise ValueError("Percentages must be between 0 and 100")
        
        user_id = update.effective_user.id
        bot_data.image_position[user_id] = {
            'x_percent': x_percent,
            'y_percent': y_percent
        }
        
        update.message.reply_text(
            f"🖼️ Bildpositionierung festgelegt:\n"
            f"Horizontal: {x_percent}%\n"
            f"Vertikal: {y_percent}%\n\n"
            "Beispiele:\n"
            "- 50/50: Zentriert\n"
            "- 0/0: Oben links\n"
            "- 100/100: Unten rechts\n"
            "- 50/30: Leicht nach oben verschoben"
        )
    
    except (IndexError, ValueError):
        update.message.reply_text(
            "Verwendung: /position X_PROZENT Y_PROZENT\n"
            "Beispiel: /position 50 30  # Leicht über der Mitte\n"
            "X und Y müssen Zahlen zwischen 0 und 100 sein\n\n"
            "Positionierungshilfe:\n"
            "- 50/50: Zentriert (Standard)\n"
            "- 0/0: Oben links\n"
            "- 100/100: Unten rechts\n"
            "- 50/30: Leicht nach oben verschoben"
        )

# [Rest of the existing functions remain the same]

def main():
    """Startet den Bot."""
    logger.info("Bot starting...")
    
    # Bot starten
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Handler registrieren
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("filter", set_filter))
    dp.add_handler(CommandHandler("mode_transparent", mode_transparent))
    dp.add_handler(CommandHandler("mode_filter", mode_filter))
    dp.add_handler(CommandHandler("analyze_colors", analyze_colors))
    dp.add_handler(CommandHandler("position", set_positioning))
    dp.add_handler(MessageHandler(Filters.photo, process_image))
    
    logger.info("Bot handlers registered")
    
    updater.start_polling()
    logger.info("Bot is now running")
    updater.idle()

if __name__ == '__main__':
    main()