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
    
    # Bild proportional skalieren
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Neues transparentes Bild mit Zielgröße erstellen
    padded_image = Image.new('RGBA', target_size, (0, 0, 0, 0))
    
    # Skaliertes Bild in die Mitte des neuen Bildes einfügen
    x_offset = (target_size[0] - new_width) // 2
    y_offset = (target_size[1] - new_height) // 2
    padded_image.paste(resized_image, (x_offset, y_offset))
    
    return padded_image

def analyze_dominant_colors(input_data, num_colors=3):
    """Analysiert die dominanten Farben im Bild."""
    # Bild laden
    img = Image.open(io.BytesIO(input_data))
    img = img.convert('RGB')
    
    # Bild verkleinern für schnellere Verarbeitung
    img.thumbnail((150, 150))
    
    # Pixel sammeln
    pixels = list(img.getdata())
    
    # Farben zählen
    color_counts = {}
    for pixel in pixels:
        # Gruppiere ähnliche Farben
        rounded = (round(pixel[0]/10)*10, 
                  round(pixel[1]/10)*10, 
                  round(pixel[2]/10)*10)
        color_counts[rounded] = color_counts.get(rounded, 0) + 1
    
    # Nach Häufigkeit sortieren
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Konvertiere zu Hex und formatiere
    dominant_colors = []
    for color, count in sorted_colors[:num_colors]:
        hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
        percentage = (count / len(pixels)) * 100
        dominant_colors.append((hex_color, percentage))
    
    return dominant_colors

def filter_color(input_data, target_color, tolerance=50):
    """Filtert eine bestimmte Farbe aus dem Bild mit verbesserter Nachbearbeitung."""
    # Farbe in RGB umwandeln
    r, g, b = tuple(int(target_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    
    # Maske erstellen
    mask_data = remove(input_data, only_mask=True)
    mask = Image.open(io.BytesIO(mask_data))
    
    # Originalbild laden
    original = Image.open(io.BytesIO(input_data))
    
    # Neues Bild mit Alphakanal erstellen
    result = Image.new('RGBA', original.size)
    
    # Bilder in RGBA konvertieren
    original = original.convert('RGBA')
    mask = mask.convert('L')  # Graustufenmaske
    
    # Arrays für schnellere Verarbeitung
    width, height = original.size
    original_pixels = original.load()
    mask_pixels = mask.load()
    result_pixels = result.load()

    # Erste Phase: Pixel verarbeiten
    for x in range(width):
        for y in range(height):
            if mask_pixels[x, y] > 128:  # Vordergrund
                r1, g1, b1, a1 = original_pixels[x, y]
                # Erweiterte Farbprüfung
                color_diff = max(abs(r1 - r), abs(g1 - g), abs(b1 - b))
                brightness = (r1 + g1 + b1) / 3
                
                if color_diff < tolerance or brightness > 235:
                    result_pixels[x, y] = (0, 0, 0, 0)  # Transparent
                else:
                    result_pixels[x, y] = original_pixels[x, y]
            else:
                result_pixels[x, y] = (0, 0, 0, 0)  # Transparent

    # Zweite Phase: Rauschentfernung
    cleaned = Image.new('RGBA', original.size)
    cleaned_pixels = cleaned.load()

    for x in range(2, width-2):
        for y in range(2, height-2):
            if result_pixels[x, y][3] > 0:  # Wenn Pixel nicht transparent
                # Zähle transparente Nachbarn in 5x5 Umgebung
                transparent_count = 0
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        if result_pixels[x+dx, y+dy][3] == 0:
                            transparent_count += 1
                
                if transparent_count > 15:  # Schwellwert angepasst
                    cleaned_pixels[x, y] = (0, 0, 0, 0)
                else:
                    cleaned_pixels[x, y] = result_pixels[x, y]
            else:
                cleaned_pixels[x, y] = (0, 0, 0, 0)

    return cleaned

def analyze_colors(update, context):
    """Analysiert die dominanten Farben im letzten Bild."""
    user_id = update.effective_user.id
    if user_id not in bot_data.last_colors:
        update.message.reply_text("Bitte sende erst ein Bild, bevor du die Farben analysierst.")
        return
    
    colors = bot_data.last_colors[user_id]
    color_text = "\n".join([f"Farbe {i+1}: {color[0]} ({color[1]:.1f}%)" 
                           for i, color in enumerate(colors)])
    
    update.message.reply_text(
        f"Dominante Farben im Bild:\n{color_text}\n\n"
        "Verwende /filter #FARBCODE um eine dieser Farben zu behalten und den Rest zu entfernen."
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
        update.message.reply_text("Bitte setze zuerst einen Farbfilter mit /filter #FARBCODE")
        return
    bot_data.mode[user_id] = 'filter'
    update.message.reply_text(f"Modus auf 'Farbfilter' gesetzt! 🎨\nAktiver Filter: {bot_data.color_filter[user_id]}")

def set_filter(update, context):
    """Setzt den Farbfilter."""
    user_id = update.effective_user.id
    
    if not context.args:
        if user_id in bot_data.color_filter:
            del bot_data.color_filter[user_id]
            bot_data.mode[user_id] = 'transparent'
            update.message.reply_text("Farbfilter wurde entfernt! ⚪️\nModus auf 'Transparent' zurückgesetzt.")
        else:
            update.message.reply_text("Bitte gib einen Farbcode an, z.B. /filter #FFFFFF oder /filter zum Entfernen des Filters")
        return
    
    color = context.args[0].upper()
    if not color.startswith('#'):
        color = f"#{color}"
    
    if len(color) != 7 or not all(c in '0123456789ABCDEF#' for c in color):
        update.message.reply_text("Ungültiger Farbcode. Bitte nutze das Format #FFFFFF")
        return
    
    bot_data.color_filter[user_id] = color
    update.message.reply_text(f"Farbfilter auf {color} gesetzt! 🎨\nNutze /mode_filter um den Filtermodus zu aktivieren.")

def process_image(update, context):
    """Verarbeitet das empfangene Bild."""
    try:
        user_id = update.effective_user.id
        mode = bot_data.mode.get(user_id, 'transparent')
        
        if mode == 'transparent':
            msg = update.message.reply_text("Erstelle transparentes Bild... (ca. 30-60 Sekunden)")
        else:  # mode == 'filter'
            color = bot_data.color_filter.get(user_id)
            if not color:
                update.message.reply_text("Kein Farbfilter gesetzt. Bitte erst mit /filter #FARBCODE einen Filter setzen.")
                return
            msg = update.message.reply_text(f"Filtere Farbe {color}... (ca. 30-60 Sekunden)")
        
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
            output_img = filter_color(input_data, bot_data.color_filter[user_id])
        
        logger.info("Bildverarbeitung abgeschlossen")
        
        # Resize
        resized_img = resize_with_padding(output_img, (4500, 5400))
        
        # In Bytes umwandeln
        img_byte_arr = io.BytesIO()
        resized_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        # Bild senden
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

def help_command(update, context):
    """Zeigt Hilfe-Text mit allen verfügbaren Commands."""
    help_text = """
<b>Verfügbare Befehle:</b>

/start - Startet den Bot und zeigt die Willkommensnachricht
/help - Zeigt diese Hilfe-Nachricht
/mode_transparent - Aktiviert den Transparenz-Modus (Standard)
/mode_filter - Aktiviert den Farbfilter-Modus
/filter #FARBCODE - Setzt einen spezifischen Farbfilter (z.B. /filter #FFFFFF für Weiß)
/filter - Ohne Farbcode entfernt den aktiven Filter
/analyze_colors - Zeigt die dominanten Farben des letzten Bildes

<b>Häufige Farben und ihre Codes:</b>
⚪️ Weiß: #FFFFFF
⚫️ Schwarz: #000000
🔴 Rot: #FF0000
🟢 Grün: #00FF00
🔵 Blau: #0000FF
🟡 Gelb: #FFFF00
🟣 Lila: #800080
🟤 Braun: #A52A2A
🟠 Orange: #FFA500
💗 Pink: #FFC0CB
💚 Hellgrün: #90EE90
💙 Hellblau: #87CEEB
🤎 Beige: #F5F5DC
🩶 Grau: #808080
🔴 Dunkelrot: #8B0000
🟢 Dunkelgrün: #006400
🔵 Dunkelblau: #00008B
🟣 Violett: #8A2BE2
🤍 Cremeweiß: #FFFDD0
⚫️ Anthrazit: #293133

<b>Modi:</b>
1. <b>Transparent-Modus (Standard):</b>
   • Entfernt den Hintergrund komplett
   • Ersetzt ihn durch Transparenz
   • Aktivierung mit /mode_transparent

2. <b>Filter-Modus:</b>
   • Filtert bestimmte Farben
   • Zeigt dominante Farben im Bild
   • Aktivierung mit /mode_filter

<b>Beispiele:</b>
1. Transparenter Hintergrund:
   • /mode_transparent
   • Bild senden

2. Bestimmte Farbe filtern:
   • Bild senden (zeigt dominante Farben)
   • /filter #FARBCODE
   • /mode_filter
   • Bild erneut senden

<b>Hinweise:</b>
- Die Bildverarbeitung kann 30-60 Sekunden dauern
- Bilder werden auf 4500x5400px skaliert
- Farbanalyse erfolgt automatisch bei jedem Bild
""".strip()
    
    update.message.reply_text(help_text, parse_mode='HTML')

def start(update, context):
    """Sendet eine Nachricht wenn der Befehl /start ausgegeben wird."""
    logger.info("Received /start command")
    user_id = update.effective_user.id
    bot_data.mode[user_id] = 'transparent'  # Standard: Transparenz
    update.message.reply_text(
        'Hallo! Sende mir ein Bild und ich werde den Hintergrund transparent machen.\n'
        'Nutze /help um alle verfügbaren Befehle zu sehen.'
    )

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
    dp.add_handler(MessageHandler(Filters.photo, process_image))
    
    logger.info("Bot handlers registered")
    
    updater.start_polling()
    logger.info("Bot is now running")
    updater.idle()

if __name__ == '__main__':
    main()
