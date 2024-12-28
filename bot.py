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

def start(update, context):
    """Sendet eine Nachricht wenn der Befehl /start ausgegeben wird."""
    logger.info("Received /start command")
    user_id = update.effective_user.id
    bot_data.mode[user_id] = 'transparent'  # Standard: Transparenz
    update.message.reply_text(
        'Hallo! Sende mir ein Bild und ich werde den Hintergrund transparent machen.\n'
        'Nutze /help um alle verfügbaren Befehle zu sehen.'
    )

def help_command(update, context):
    """Zeigt Hilfe-Text mit allen verfügbaren Commands."""
    help_text = """
<b>Verfügbare Befehle:</b>

/start - Startet den Bot und zeigt die Willkommensnachricht
/help - Zeigt diese Hilfe-Nachricht
/mode_transparent - Aktiviert den Transparenz-Modus (Standard)
/mode_filter - Aktiviert den Farbfilter-Modus
/filter #FARBCODE [TOLERANZ] - Setzt einen Farbfilter mit optionaler Toleranz
/filter - Ohne Parameter entfernt den aktiven Filter
/analyze_colors - Zeigt die dominanten Farben des letzten Bildes
/position X Y - Positioniert das Bild im 4500x5400 Format
""".strip()
    
    update.message.reply_text(help_text, parse_mode='HTML')

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

def analyze_colors(update, context):
    """Analysiert die dominanten Farben im letzten Bild."""
    user_id = update.effective_user.id
    if user_id not in bot_data.last_colors:
        update.message.reply_text("Bitte sende erst ein Bild, bevor du die Farben analysierst.")
        return
    
    colors = bot_data.last_colors[user_id]
    color_text = "\n".join([f"Farbe {i+1}: {color[0]} ({color[1]:.1f}%) - {color[2]}" 
                           for i, color in enumerate(colors)])
    
    update.message.reply_text(
        f"Dominante Farben im Bild:\n{color_text}\n\n"
        "Verwende /filter #FARBCODE [TOLERANZ] um eine dieser Farben zu filtern.\n"
        "Die Toleranz ist optional (0-100) und bestimmt, wie großzügig gefiltert wird."
    )

def mode_transparent(update, context):
    """Setzt den Modus auf Transparenz."""
    user_id = update.effective_user.id
    bot_data.mode[user_id] = 'transparent'
    update.message.reply_text("Modus auf 'Transparent' gesetzt! 🌟\nBilder werden jetzt mit transparentem Hintergrund erstellt.")

def mode_filter(update, context):
    """Setzt den Modus auf Farbfilter."""
    user_id = update.effective_user.id
    if user_id not in bot_data.color_filter:
        update.message.reply_text("Bitte setze zuerst einen Farbfilter mit /filter #FARBCODE [TOLERANZ]")
        return
    bot_data.mode[user_id] = 'filter'
    tolerance = bot_data.filter_tolerance.get(user_id, 0)
    update.message.reply_text(
        f"Modus auf 'Farbfilter' gesetzt! 🎨\n"
        f"Aktiver Filter: {bot_data.color_filter[user_id]} mit Toleranz {tolerance}%"
    )

def set_filter(update, context):
    """Setzt den Farbfilter und optional die Toleranz."""
    user_id = update.effective_user.id
    
    if not context.args:
        if user_id in bot_data.color_filter:
            del bot_data.color_filter[user_id]
            del bot_data.filter_tolerance[user_id]
            bot_data.mode[user_id] = 'transparent'
            update.message.reply_text("Farbfilter wurde entfernt! ⚪️\nModus auf 'Transparent' zurückgesetzt.")
        else:
            update.message.reply_text(
                "Bitte gib einen Farbcode und optional die Toleranz (0-100) an.\n"
                "Beispiele:\n"
                "/filter #FFFFFF    (exakte Farbe)\n"
                "/filter #FFFFFF 50 (mittlere Toleranz)\n"
                "/filter #FFFFFF 100 (maximale Toleranz)\n"
                "/filter           (Filter entfernen)"
            )
        return
    
    # Farbcode verarbeiten
    color = context.args[0].upper()
    if not color.startswith('#'):
        color = f"#{color}"
    
    if len(color) != 7 or not all(c in '0123456789ABCDEF#' for c in color):
        update.message.reply_text("Ungültiger Farbcode. Bitte nutze das Format #FFFFFF")
        return
    
    # Toleranz verarbeiten
    tolerance = 0  # Standardwert
    if len(context.args) > 1:
        try:
            tolerance = int(context.args[1])
            if tolerance < 0 or tolerance > 100:
                update.message.reply_text("Toleranz muss zwischen 0 und 100 liegen.")
                return
        except ValueError:
            update.message.reply_text("Ungültige Toleranz. Bitte gib eine Zahl zwischen 0 und 100 an.")
            return
    
    # Werte speichern
    bot_data.color_filter[user_id] = color
    bot_data.filter_tolerance[user_id] = tolerance
    
    update.message.reply_text(
        f"Farbfilter auf {color} gesetzt mit Toleranz {tolerance}%! 🎨\n"
        "Nutze /mode_filter um den Filtermodus zu aktivieren."
    )

def process_image(update, context):
    """Verarbeitet das empfangene Bild."""
    try:
        user_id = update.effective_user.id
        mode = bot_data.mode.get(user_id, 'transparent')
        
        # Positionierung abrufen (Standard: zentriert)
        position = bot_data.image_position.get(user_id, {'x_percent': 50, 'y_percent': 50})
        
        if mode == 'transparent':
            msg = update.message.reply_text("Erstelle transparentes Bild... (ca. 30-60 Sekunden)")
        else:  # mode == 'filter'
            color = bot_data.color_filter.get(user_id)
            tolerance = bot_data.filter_tolerance.get(user_id, 0)
            if not color:
                update.message.reply_text("Kein Farbfilter gesetzt. Bitte erst mit /filter #FARBCODE [TOLERANZ] einen Filter setzen.")
                return
            msg = update.message.reply_text(
                f"Filtere Farbe {color} mit Toleranz {tolerance}%... (ca. 30-60 Sekunden)\n"
                f"Positionierung: Horizontal {position['x_percent']}%, Vertikal {position['y_percent']}%"
            )
        
        logger.info("Bild empfangen, starte Verarbeitung...")
        
        photo_file = update.message.photo[-1].get_file()
        logger.info("Bild heruntergeladen")
        
        response = requests.get(photo_file.file_path)
        input_data = response.content
        logger.info("Bild in Speicher geladen")
        
        # Dominante Farben analysieren und speichern
        bot_data.last_colors[user_id] = analyze_dominant_colors(input_data)
        
        # Info über dominante Farben senden
        colors = bot_data.last_colors[user_id]
        color_text = "\n".join([f"Farbe {i+1}: {color[0]} ({color[1]:.1f}%) - {color[2]}" 
                           for i, color in enumerate(colors)])
        update.message.reply_text(
            f"Dominante Farben im Bild:\n{color_text}\n"
            f"Aktuelle Positionierung: Horizontal {position['x_percent']}%, Vertikal {position['y_percent']}%\n"
            "Verwende /filter #FARBCODE [TOLERANZ] um eine dieser Farben zu filtern.\n"
            "Verwende /position X_PROZENT Y_PROZENT für eine andere Bildpositionierung."
        )
        
        gc.collect()
        
        logger.info("Starte Bildverarbeitung...")
        if mode == 'transparent':
            output_img = Image.open(io.BytesIO(remove(input_data)))
        else:
            output_img = improved_color_filter(
                input_data,
                bot_data.color_filter[user_id],
                tolerance_percent=bot_data.filter_tolerance.get(user_id, 0)
            )
        
        logger.info("Bildverarbeitung abgeschlossen")
        
        # Resize mit neuer Positionierungsmethode
        resized_img = resize_with_positioning(
            output_img, 
            (4500, 5400), 
            x_percent=position['x_percent'],
            y_percent=position['y_percent']
        )
        
        # In Bytes umwandeln
        img_byte_arr = io.BytesIO()
        resized_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        # Bild senden
        filename = (
            f'transparent_4500x5400_pos_{position["x_percent"]}x{position["y_percent"]}.png' 
            if mode == 'transparent' 
            else f'filtered_{bot_data.color_filter[user_id][1:]}_tolerance_{bot_data.filter_tolerance.get(user_id, 0)}_pos_{position["x_percent"]}x{position["y_percent"]}_4500x5400.png'
        )
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