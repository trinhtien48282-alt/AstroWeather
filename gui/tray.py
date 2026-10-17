import threading
from pathlib import Path

import pystray
from PIL import Image


def start_tray(on_show, on_quit):
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "astroweather.ico"
    image = Image.open(icon_path).convert("RGBA")

    icon = pystray.Icon(
        "AstroWeather",
        image,
        "AstroWeather",
        menu=pystray.Menu(
            pystray.MenuItem("Open AstroWeather", lambda icon, item: on_show(), default=True),
            pystray.MenuItem("Exit", lambda icon, item: on_quit()),
        ),
    )

    threading.Thread(target=icon.run, daemon=True).start()
    return icon
