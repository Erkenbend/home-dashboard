# Tablet setup (kiosk browser)

The display is a Samsung Galaxy Tab A 10.1 (2016, SM-T580) on Android 8.1, running
[Fully Kiosk Browser](https://www.fully-kiosk.com/). The free version covers everything the dashboard needs;
PLUS (one-time fee per device) adds a kiosk lock, a night-time screen-off timer and remote admin.
Menu paths are from Samsung Experience 9 (Oreo) and may differ slightly. Other tablets work the same
way: the page needs nothing beyond a browser from the last decade (server-side rendering, plain ES5,
Flexbox), and the layout adapts to any screen size.

## 1. Prepare the tablet

- **Browser engine:** on Android 7–9 Chrome is the system WebView, so Fully renders with the installed Chrome.
  Update **Chrome** from the Play Store (Chrome stopped updating on Android 8 around version 138, still far
  more than the dashboard needs). Leave *Android System WebView* disabled if it is.
- **Viewport:** the 1920×1200 screen reports about 1280×800 CSS px in landscape (pixel ratio 1.5), one of the
  layout test viewports.
- **Lock screen:** Settings → Lock screen and security → Screen lock type → **None**.
- **Developer options:** Settings → About tablet → Software information → tap *Build number* 7 times, then
  Developer options → **Stay awake** (screen stays on while charging) as a fallback.
- **Battery optimization** (Samsung kills background apps aggressively):
  - Settings → Device maintenance → Battery → **Unmonitored apps** → add Fully
  - same screen, ⋮ → Settings → turn off "Put unused apps to sleep"
  - Settings → Apps → ⋮ → Special access → **Optimize battery usage** → All apps → Fully: off
- **Display:** Settings → Display → *Adaptive brightness* off, *Screen timeout* to the maximum (fallback).
- **Distractions:** Settings → Software update → *Download updates automatically* off; notifications of
  Galaxy Store and Play Store off.

## 2. Configure Fully Kiosk Browser

Install it from the Play Store, then:

| Setting (approximate path) | Value |
|---|---|
| Web Content → **Start URL** | `http://<pi-host>:3274/` (IP address of the server) |
| Web Auto Reload → **Reload on network reconnect** | on |
| Web Auto Reload → **Reload on page error / timeout** | on, e.g. after 60 s |
| Toolbars & Appearance → **Fullscreen**, hide status and navigation bar | on |
| Device Management → **Keep screen on** | on |
| Device Management → **Launch on boot** | on |
| Device Management → screen brightness | fixed, dimmer than you'd expect |
| Web Zoom and Scaling → **Enable zoom** | off |
| Advanced Web Settings → pull to refresh, text selection | off (optional) |

The two reload settings matter most: the dashboard rides out short Wi-Fi drops by itself (HTMX retries on the
next poll, and an offline notice shows meanwhile), but if the periodic full reload (`page_reload_hours`) hits
while the tablet is offline, the browser shows an error page that only Fully's reload brings back.

**Initial scale** (Web Zoom and Scaling) changes how many CSS pixels the tablet reports, so the dashboard picks
a different size step. Use it if text is too small or too big from 2–3 m.

Without Fully (testing only): open the URL in Chrome, *Add to Home screen*, then Settings → Lock screen and
security → Other security settings → **Pin windows**. No auto start after reboot, no recovery from error pages.

## 3. Hardware

- **Battery:** Samsung's charge limit only arrived with Android 11, so a battery permanently on the charger
  ages and may swell; check the back now and then. A timer smart plug that charges a few hours a day is the
  gentler option (the 7300 mAh battery lasts the rest of the day with a dimmed screen).
- **Mounting:** keep the USB port and speakers free.

## 4. Check on the device

- Readable from 2–3 m
- Reboot the tablet: it comes back to the dashboard on its own
- Wi-Fi off for a few minutes: "Keine Verbindung seit HH:MM" replaces the date and the widgets dim;
  Wi-Fi on: the dashboard recovers by itself within one poll
