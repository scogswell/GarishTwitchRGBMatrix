# THE Garish Twitch RGBMatrix Status Display
# Like to follow your favourite twitch streamers and want to really show it,
# to the point of buying hardware dedicated to it?
#
# "Features":
# - Scrolling list of live twitch streamers you've selected
# - "Now Live" exuberant display when someone goes live
# - Scrolling twitch logo with "LIVE" in case it isn't obvious
# - catJAM
#
# This uses the Adafruit Matrix Portal M4 + 64x32 RGBMatrix which you can buy
# as one convenient kit  https://www.adafruit.com/product/4812
#
# Animations are done with the tile grid groups
# https://learn.adafruit.com/circuitpython-display-support-using-displayio/tilegrid-and-group
# Graphics have been "gamma adjusted" to be nice on the rgbmatrix
# https://learn.adafruit.com/image-correction-for-rgb-led-matrices
#
# Wifi secrets and twitch secrets are in secrets.py
# Streamers to monitor are in streamer.py
# The Neopixel LED on the M4 board shows network status.
#
# Tested with Circuitpython 7.3.3
#
# To use, on a Matrix Portal M4 running Circuitpython copy all files to CIRCUITPY
# (except README.md and readme-images) along with the libraries:
# Place required libraries and probably some ones you don't need for circuitpython
# in /lib: https://circuitpython.org/libraries
# adafruit_bitmap_font, adafruit_bus_device, adafruit_display_text, adafruit_esp32spi,
# adafruit_imageload, adafruit_io, adafruit_matrixportal, adafruit_minimqtt,
# adafruit_portabase, adafruit_fakerequests.mpy, adafruit_miniqr.mpy,
# adafruit_requests.mpy, neopixel.mpy, simpleio.py
#
# This "works for me" but if you need to debug connect to the serial console for debug messages
#
# If the watchdog timer is enabled in streamer.py the program will likely reboot in the event
# of any runtime exceptions like twitch tokens expiring.  If it keeps rebooting over and
# over check your settings.
#
# You will need to generate a set of twitch oAuth secrets to access the twitch
# API.
# To get and generate the twitch_client_id and twitch_client_secret:
# https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow
# https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow
# Register a new app with:
#  https://dev.twitch.tv/docs/authentication/register-app/
# Logging into your twitch dev console https://dev.twitch.tv/console
# Register your app as category "other", and use "http://localhost" for the oauth callback.
# Yes this procedure is complicated, I didn't come up with it, complain to twitch dev.
#
# Steven Cogswell February 2023
import time
import board
import terminalio
from adafruit_matrixportal.matrixportal import MatrixPortal
import displayio
from adafruit_matrixportal.matrix import Matrix
import adafruit_display_text.scrolling_label
import adafruit_display_text.bitmap_label
import adafruit_imageload
from adafruit_bitmap_font import bitmap_font
from digitalio import DigitalInOut
import busio
import adafruit_requests as requests
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import neopixel
import rtc
import microcontroller
import watchdog

#pylint: disable=invalid-name

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_STREAM_URL = "https://api.twitch.tv/helix/streams"

UPDATE_DELAY = 63
NOWLIVE_DELAY = 15
SCROLL_DELAY = 0.03
DEBUG = True
DEBUG = False

# --- Display setup ---
matrix = Matrix(bit_depth=4)
display = matrix.display
group = displayio.Group()

# A black screen
blank_group = displayio.Group()

# For info messages
message_group = displayio.Group()
message_text = adafruit_display_text.bitmap_label.Label(font=terminalio.FONT,
                        text="Starting!      ",
                        color=(0,0,255))
message_group.append(message_text)    # Item 0
message_group[0].x=0
message_group[0].y = display.height // 2
display.show(message_group)

# A garishly complicated "now live" display featuring:
# - "LIVE" flashing
# - Twitch logo prowling back and forth
# - catJAM, what more can I say
# - list of streamers currently live
streamer_font = bitmap_font.load_font("fonts/Roboto-Condensed.pcf")
streamer_font.load_glyphs(b'abcdefghjiklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890- ()')

twitchlogo, twitchpalette = adafruit_imageload.load("/twitchlogo.bmp",
                        bitmap=displayio.Bitmap,
                        palette=displayio.Palette)
twitchpalette.make_transparent(5)  # make the black in the logo transparent
logo_grid = displayio.TileGrid(twitchlogo, pixel_shader=twitchpalette)
catjam, catpalette = adafruit_imageload.load("/catjamtiles.bmp",
                        bitmap=displayio.Bitmap,
                        palette=displayio.Palette)
catjam_grid = displayio.TileGrid(catjam, pixel_shader=catpalette,
                        width=1,
                        height=1,
                        tile_width=16,
                        tile_height=16)
group.append(logo_grid)    # Item 0
group.append(catjam_grid)  # Item 1

live_text = adafruit_display_text.bitmap_label.Label(font=terminalio.FONT,
                                        text="LIVE",color=(0,0,255))
group.append(live_text)  # Item 2

streamer_text = adafruit_display_text.bitmap_label.Label(font=streamer_font,
                        text=" "*50)
group.append(streamer_text) # Item 3

# twitch logo
group[0].x = 0
group[0].y = 0

# catJAM
group[1].x = 43
group[1].y = 0

# "LIVE" text
group[2].x = 5
group[2].y = 7
livetext_colors = [(0,255,0),(0,255,255),(0,0,255),(255,255,0)]

# Streamer names
group[3].x = 0
group[3].y = 22
#streamer_text.text=" "*20
streamertext_colors = [(255,255,255),(200,200,200),(180,180,180),
                        (150,150,150),(180,180,180),(200,200,200)]

# Splash screen for when a streamer goes live
nowlive_group = displayio.Group()
nowlive_background, nowlive_palette = adafruit_imageload.load("/wow.bmp",
                        bitmap=displayio.Bitmap,
                        palette=displayio.Palette)
nowlive_grid = displayio.TileGrid(nowlive_background, pixel_shader=nowlive_palette,
                        width=1,
                        height=1,
                        tile_width=64,
                        tile_height=32)
nowlive1_text = adafruit_display_text.bitmap_label.Label(font=terminalio.FONT,
                text="LIVE NOW",
                color=(0,255,0),anchored_position=(display.width // 2, display.height // 2),
                anchor_point=(0.5, 1))
nowlive2_text = adafruit_display_text.bitmap_label.Label(font=streamer_font,
                text=" "*20,
                color=(0,255,0),anchored_position=(display.width // 2, display.height),
                anchor_point=(0.5,1.2))
nowlive_logo = displayio.TileGrid(twitchlogo, pixel_shader=twitchpalette)
nowlive_group.append(nowlive_grid)   # 0
nowlive_group.append(nowlive_logo)   # 1
nowlive_group.append(nowlive1_text)  # 2
nowlive_group.append(nowlive2_text)  # 3

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

# Get list of streamers to monitor from streamer.py
try:
    from streamer import STREAMER_NAMES
    print("Monitoring status for",STREAMER_NAMES)
except ImportError:
    print("Set twitch stream to monitor as STREAMER_NAME in streamer.py")
    raise

# If there's a TIMEZONE_OFFSET in streamer.py, use it for offsetting the clock time
# otherwise it'll default to UTC.
try:
    from streamer import TIMEZONE_OFFSET
except ImportError:
    print("Using UTC for time, set TIMEZONE_OFFSET in streamer.py for different time zone")
    TIMEZONE_OFFSET = 0

def get_twitch_multi_status(twitch_token, streamers):
    """
    Retrieve twitch live status for a list of names, uses only one api call
    to get all statuses
    :param str twitch_token: oauth token from get_twitch_token()
    :param streamers: list of streamers to get live status for
    """
    if not streamers:
        return []
    headers = {
        'Client-ID': secrets['twitch_client_id'],
        'Authorization': 'Bearer ' + twitch_token
    }
    if DEBUG:
        print("Twitch Multi-Status: Headers are",headers)
    streamer_request = "?"
    for s in streamers:
        streamer_request += "&user_login="+s
    stream_data = None
    if DEBUG:
        print("Twitch Multi-Status: URL is",TWITCH_STREAM_URL + streamer_request)
    try:
        stream = wifi.get(TWITCH_STREAM_URL + streamer_request, headers=headers)
        stream_data = stream.json()
    except Exception as error:  # pylint: disable=broad-except
        print("Exception during status request: ",error)
        print("query was",TWITCH_STREAM_URL + streamer_request)
        print("stream data was",stream_data)
        print("headers were",headers)
        return False
    live_now = []
    if stream_data['data'] is not None:
        for streams in stream_data['data']:
            if DEBUG:
                print("Twitch Multi-Status: Data is",streams)
                print("Twitch Multi-Status: user_name is",streams['user_name'])
            live_now.append(streams['user_name'])
    live_now.sort(key=lambda s: s.lower())   # sort list case-insensitive
    if DEBUG:
        print("live_now is",live_now)
    return live_now

def get_twitch_token():
    """
    Get a twitch oAuth token.  Note you must have twitch_client_id and
    twitch_client_secret defined in secrets.py.  Get those by registering
    an app with "client credentials grant flow"
    https://dev.twitch.tv/docs/authentication/register-app
    https://dev.twitch.tv/docs/authentication/getting-tokens-oauth#client-credentials-grant-flow
    """
    body = {
        'client_id': secrets['twitch_client_id'],
        'client_secret': secrets['twitch_client_secret'],
        "grant_type": 'client_credentials'
    }
    if DEBUG:
        print("Twitch Token: Body is",body)
    try:
        r = wifi.post(TWITCH_AUTH_URL, data=body)
        keys = r.json()
        if DEBUG:
            print(keys)
    except Exception as error:  # pylint: disable=broad-except
        print("Exception getting twitch token:",error)
        return None
    if not "access_token" in keys:
        print("Didn't get proper access token from twitch")
        return None
    if DEBUG:
        print("Twitch Token: Access token is",keys['access_token'])
    return keys['access_token']

def format_datetime(datetime):
    """
    Simple pretty-print for a datetime object
    :param datetime: a datetime object
    """
    # pylint: disable=consider-using-f-string
    return "{:02}/{:02}/{} {:02}:{:02}:{:02}".format(
        datetime.tm_mon,
        datetime.tm_mday,
        datetime.tm_year,
        datetime.tm_hour,
        datetime.tm_min,
        datetime.tm_sec,
    )

def show_gone_live(name):
    """
    Show a splash screen when a streamer goes live
    :param str name: The name to display (not verified with twitch)
    """
    print(name,"has gone live")
    nowlive2_text.text = name
    nowlive_group[1].x = 24
    nowlive_group[1].y = 0

    # If the name is too wide to fit on the screen,
    # prepare for continuous wrap-around scrolling
    if nowlive2_text.width > display.width:
        reset_scroll = nowlive2_text.bounding_box[2]
        nowlive2_text.text += " " + name
        nowlive2_text.x = 0

    display.show(nowlive_group)

    live_color = 0
    live_t = time.monotonic()
    while time.monotonic() - live_t < NOWLIVE_DELAY:
        if USE_WATCHDOG:
            microcontroller.watchdog.feed()
        nowlive_grid[0]=live_color  # animate background
        live_color += 1
        nowlive1_text.color = livetext_colors[live_color]  # animate live now colours
        if live_color > 2:
            live_color = 0
        # If the streamer name is wider than the display, scroll
        if nowlive2_text.width > display.width:
            if nowlive2_text.x <= - reset_scroll - 3:
                nowlive2_text.x = 0
            else:
                nowlive2_text.x += -1
        time.sleep(0.1)
    nowlive2_text.text=" "

# -- Network startup
# If you are using a board with pre-defined ESP32 Pins:
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

# Setup the wifi on the ESP32 co-processor
# Note we are using "full esp32spi" mode because we want access to
# wifi.post() which is not in the MatrixPortal Network library
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
status_light = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)

# setup sockets for requests library
requests.set_socket(socket, esp)

if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    print("ESP32 found and in idle mode")
print("Firmware vers.", esp.firmware_version)
print("MAC addr:", [hex(i) for i in esp.MAC_address])
message_text.text="Connecting"
wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets, status_light, debug=DEBUG)
wifi.connect()
while not esp.is_connected:
    try:
        time.sleep(2)
    except OSError as e:
        print("could not connect to AP, retrying: ", e)
        continue
print("Connected to", str(esp.ssid, "utf-8"), "\tRSSI:", esp.rssi)
print("IP address", esp.pretty_ip(esp.ip_address))

# Get twitch auth token
message_text.text="Get Token"
print("Getting twitch authorization token")
token = get_twitch_token()
if token is None:
    message_text.text = "Token error"
    display.show(message_group)
    time.sleep(30)
    microcontroller.reset()

# Sync time with NTP server
message_text.text="Sync Time"
print("Syncing time",end="")
time_valid = False
while not time_valid:
    time_valid = True
    try:
        current_unix_time = esp.get_time()
    except OSError:
        time_valid = False
        print(".",end="")
        time.sleep(1)
# Adjust utc to local time the easy way
now_timezone = time.localtime(esp.get_time()[0]+TIMEZONE_OFFSET*3600)
rtc.RTC().datetime = now_timezone
print("\nTime:", format_datetime(time.localtime()))

# Get initial status of streamers
message_text.text="Get status"
streamer_status = get_twitch_multi_status(token,STREAMER_NAMES)
streamer_status_prev = streamer_status  # no "now live" notifications if already live on boot

# Make the label of live streamers for the display
streamers_live = ""
for s in streamer_status:
    streamers_live += s + "  "
streamer_text.text = streamers_live

# Check if list of streamers is wider than the display
# if so add a second copy so we can do seamless
# wraparound scrolling
streamertext_bound = streamer_text.bounding_box[2]
if streamer_text.width > display.width:
    streamer_text.text += streamer_text.text

# If anyone is live from the start, show the live display
# Otherwise, blank idle screen
if streamer_status:
    display.show(group)
else:
    display.show(blank_group)

refresh_time = time.monotonic()
catjam_frame=0             # frame of catJAM tilegrid to show
catjam_delay = 0           # counter interval to animate catJAM
twitchlogo_delay = 0       # counter interval to move twitch logo
livetext_delay = 0         # counter interval to change "LIVE" color
streamertext_delay = 0     # counter interval to scroll streamer names (if scrollable)
livetext_color_index = 0   # index of color in livetext_colors[] to show streamer live names in
twitch_logo_direction = 1  # direction twitch logo moves, -1/+1 alternates
streamertext_direction = -1 # list of live streamers scrolls to the left
streamertext_color_index = 0  # index of color in streamertext_colors[] to show streamer live names in
streamertext_color_delay = 0  # counter interval to update streamer name colors

# --- Watchdog timer ---
try:
    from streamer import USE_WATCHDOG
except ImportError:
    print("set USE_WATCHDOG as True or False in streamer.py for watchdog reset")
    print("assuming no watchdog")
    USE_WATCHDOG=False

if USE_WATCHDOG:
    print("Watchdog function enabled")
    microcontroller.watchdog.timeout = 16  # 16 seconds longest possible on Matrix Portal M4
    microcontroller.watchdog.mode = watchdog.WatchDogMode.RESET
else:
    print("Watchdog function disabled")

# The main loop which updates the animations and checks streamer statuses
while True:
    if USE_WATCHDOG:
        microcontroller.watchdog.feed()
    # Update list of live streamers on schedule
    if time.monotonic() - refresh_time > UPDATE_DELAY:
        print("\nTime:", format_datetime(time.localtime()))
        refresh_time = time.monotonic()

        print("Getting status for",STREAMER_NAMES)
        # Build a new label of live streamers
        streamers_live = ""
        streamer_status_prev = streamer_status
        streamer_status = get_twitch_multi_status(token,STREAMER_NAMES)
        # if the streamer is live now, but in last update was not
        # so a garish "now live" notification screen
        for s in streamer_status:
            if s not in streamer_status_prev:
                show_gone_live(s)
                streamer_text.x = 0 # text line will change, reset position
            streamers_live += s + "  "
        print("Currently live:",streamers_live)
        # If streamer is not live now, but was live in the last update
        # just give an output to the serial
        for s in streamer_status_prev:
            if s not in streamer_status:
                print(s,"has gone offline")
                streamer_text.x = 0  # text line will change, reset position
        streamer_text.text = streamers_live
        streamertext_bound = streamer_text.bounding_box[2]
        # Check if list of streamers is wider than the display
        # if so add a second copy so we can do seamless
        # wraparound scrolling
        if streamer_text.width > display.width:
            streamer_text.text += streamer_text.text

        # If anyone is live from the start, show the live display
        # Otherwise, blank idle screen
        if streamer_status:
            display.show(group)
        else:
            display.show(blank_group)
    else:
        time.sleep(SCROLL_DELAY)

    # Animate catJAM
    if catjam_delay > 3:
        catjam_frame=catjam_frame + 1
        if catjam_frame > 14:
            catjam_frame = 0
        catjam_grid[0]=catjam_frame
        catjam_delay=0
    catjam_delay += 1

    # Animate Twitch logo
    if twitchlogo_delay > 6:
        logo_grid.x = logo_grid.x + twitch_logo_direction
        if logo_grid.x > 27 or logo_grid.x < 1:
            twitch_logo_direction = -twitch_logo_direction
        twitchlogo_delay = 0
    twitchlogo_delay += 1

    # color cycle the "live" text
    if livetext_delay > 6:
        live_text.color = livetext_colors[livetext_color_index]
        livetext_color_index += 1
        if livetext_color_index > len(livetext_colors)-1:
            livetext_color_index = 0
        livetext_delay = 0
    livetext_delay += 1

    # Show the streamers who are live, if longer than the display scroll the text
    if streamertext_delay > 1:
        streamertext_delay = 0
        if streamer_text.width > display.width:
            if streamer_text.x <= - streamertext_bound:
                streamer_text.x = 0
            else:
                streamer_text.x += streamertext_direction
    streamertext_delay += 1

    # Animate the colours of the list of names of live streamers
    if streamertext_color_delay > 4:
        streamertext_color_delay=0
        streamer_text.color = streamertext_colors[streamertext_color_index]
        streamertext_color_index += 1
        if streamertext_color_index > len(streamertext_colors)-1:
            streamertext_color_index = 0
    streamertext_color_delay += 1
