# Rain gauge: getting real local rainfall into the controller

Research notes on adding a tipping-bucket rain gauge to this project. These notes build on [Option B in `docs/extensions.md`](../extensions.md), which already covers the basic idea (Misol WH-SP-RG on a GPIO, count pulses, multiply by mm/tip) and the ESPHome reference builds. This file covers what that section leaves open: how to get the signal back from outdoors, which printable designs exist, and how to power an outdoor node.

Research date: 2026-10-30. Where a claim could not be verified against a primary source, it says so.

## TL;DR

- **Wire it if you can.** The garage ESP32 is always on and powered from the controller, so a two-wire cable to a reed-switch gauge needs no battery, no radio and no sleep logic. Reed-switch gauges commonly run on long cables. Davis allows up to 900 ft (270 m) on its rain collector ([Davis cable sheet](https://cdn.shopify.com/s/files/1/0515/5992/3873/files/7876_4_Conductor_Cable_Rev_F_web_0ede7862-494b-4353-bd6b-4bad2f440c07.pdf)). Rain Bird ships its own wired rain sensor with 25 ft of UV-resistant 2-conductor wire ([Rain Bird store](https://store.rainbird.com/timers/rain-moisture-sensors/rsdbex-rain-sensor-with-bracket.html)).
- **Counting in MicroPython is easy.** Use `Pin.irq` with a time-based lockout in software. `machine.Counter` / `esp32.PCNT` exist (added in v1.26), but their hardware filter tops out at 1023 ticks of 80 MHz (about 12.8 µs). That is far too short to reject reed bounce, which lasts up to about 1 ms. Don't rely on PCNT for debounce.
- **Protect the long run.** Use an external pull-up of 4.7–10 kΩ (the internal one is about 45 kΩ), a series resistor plus RC filter, a TVS/ESD diode at the board entry, and shielded outdoor or direct-burial cable with the shield grounded at the controller end only. Nothing makes a GPIO immune to a nearby strike. Campbell Scientific says its own lightning protection "is not infallible".
- **If you go wireless, use ESP-NOW, not WiFi.** On the outdoor node, measured energy for wake + boot + send is about 7.7 mC with ESP-NOW against 109–204 mC for WiFi + MQTT, roughly 14–27× less ([practitioner measurements by the `espnow` module author](https://github.com/glenn20/upy-esp32-experiments)). `espnow` has shipped in official MicroPython since v1.21.
- **ESP-NOW and the receiver's WiFi share one radio.** A garage ESP32 connected to the router can receive ESP-NOW only on the router's current channel, and only with WiFi power-save off. If the router changes channel, the outdoor node must find it again ([MicroPython `espnow` docs](https://docs.micropython.org/en/latest/library/espnow.html)).
- **Board choice matters more than chip current.** The ESP32 chip draws 10 µA in deep sleep (datasheet), but a DevKitC-style board measured 3.8 mA because of its AMS1117 regulator and LED ([practitioner measurement](https://lucidar.me/en/esp32/power-consumption-of-esp32-devkitc-v4/)). At that draw an 18650 lasts about a month. With a bare module and a low-Iq regulator the same battery lasts years.
- **Battery for central-plains weather.** Lithium primary (Energizer L91, rated −40 to 60 °C) or LiFePO4 are better fits than Li-ion or alkaline. Li-ion must not be charged below 0 °C (Panasonic NCR18650B: charge 0 to +45 °C). Alkaline is rated only down to −18 °C.
- **Send a running total, not deltas.** Have the node report a monotonically increasing tip count plus a boot ID. Then a lost packet loses nothing, and a battery swap that resets RTC memory is easy to detect on the receiver.

**Recommendation:** Wire the gauge (Misol WH-SP-RG or a printed PETG/ASA bucket) to the existing garage ESP32. Use shielded outdoor or direct-burial 2-conductor cable, external pull-up + RC + TVS at the enclosure entry, and `Pin.irq` with a 200–500 ms software lockout. Build a battery ESP-NOW node only if the only good open-sky mounting spot can't be reached by cable. In that case use a bare ESP32 module (not a dev board), ext0/ext1 wake per tip, LiFePO4 or 3× L91, and send a cumulative count.

---

## 1. Getting the data back from outdoors

### 1a. Wired run to the existing garage ESP32

#### What the signal looks like

- The Misol WH-SP-RG is a reed relay contact, a "REED relay clean contact (max 24V 0.5A)", giving "1 pulse (contact closure for hundreds of milliseconds) at each rocker movement, corresponding to 0.3mm of rain" ([Mectronica listing](https://store.mectronica.it/en/rain/1326-rain-gauge-sensor-measures-pulse-rain-volume-for-weather-stations-and-arduino-5051151024334.html), retailer page, no official Misol datasheet found). The closure duration is unverified. Measure it on the real unit with a scope or a logging sketch.
- The SparkFun weather meter kit uses a near-identical gauge with one closure per 0.011" (0.279 mm) ([Core Electronics listing](https://core-electronics.com.au/weather-meter-kit.html.md)). Units in this family are typically 0.28–0.30 mm per tip.
- **Reed bounce** is short. Datasheets give 0.3 ms max (Standex-Meder ORD2220, [datasheet](https://static.datasheets.com/doc/25715103-standex-meder-electronics-ord-2220-20-30-ds.pdf)), 0.5 ms max (Comus GC1513, [datasheet](https://www.farnell.com/datasheets/1807497.pdf)), and 1.0 ms max for NO contacts (Oki ORT551-1, [datasheet](https://www.mouser.lt/datasheet/3/466/1/4502900000e.pdf)). The Misol's exact reed part is unknown. In practice a bucket swinging past the magnet can also give more than one closure, so software lockout matters more than contact bounce.
- **Maximum real tip rate:** at 0.3 mm/tip, 100 mm/h (extreme convective rain) is about 333 tips/h, or one tip every 11 s. At 200 mm/h it is one every 5.4 s. A 200–500 ms lockout after each counted edge therefore can't drop real tips. Tipping buckets already under-catch above roughly 50 mm/h because water is lost during the tip itself (Duchon and Biddle, summarized in [Lanza et al., WMO TECO](https://old.wmo.int/extranet/pages/prog/www/IMOP/publications/IOM-94-TECO2006/P3(15)_Lanza_Italy.pdf)).

#### Practical cable length

| Evidence | Length | Source |
|---|---|---|
| Davis rain collector (reed switch), max total cable to console | 900 ft (270 m) | [Davis 7876 cable sheet](https://cdn.shopify.com/s/files/1/0515/5992/3873/files/7876_4_Conductor_Cable_Rev_F_web_0ede7862-494b-4353-bd6b-4bad2f440c07.pdf), [Davis manual](https://www.manualslib.com/manual/227021/Davis-Instruments-Rain-Collector.html) |
| Hach tipping rain gauge, reed switch | 100 ft cable as sold | [USABlueBook listing](https://usabluebook.com/flow-metering/open-channel-flow-meters/hach-tipping-rain-gauge-with-reed-switch-18-7-l-x-14103) |
| Rain Bird RSD-BEx (switches 24VAC valve common, not a logic signal) | 25 ft, extension "not recommended" | [Rain Bird store](https://store.rainbird.com/timers/rain-moisture-sensors/rsdbex-rain-sensor-with-bracket.html), [Rain Bird guide](https://rainbird.com/media/4720) |

A dry contact at a low data rate (a few edges per minute at most) is tolerant of length. The limits in practice are noise pickup and surges, not signal integrity. For a run from a garage-mounted controller to a fence post or roofline (tens of feet), length is not a concern if the protection below is in place.

#### Pull-up, RC filter and software debounce

- The ESP32's internal pull-up is "45 kΩ" typical ([ESP32 datasheet, DC characteristics](https://documentation.espressif.com/esp32_datasheet_en.pdf), [ESP32-WROOM-32E/UE datasheet](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)). One forum user measured about 23 kΩ on a real part ([esp32.com](https://esp32.com/viewtopic.php?p=22096)). That is weak for a long cable. Use an **external 4.7–10 kΩ pull-up to 3.3 V** at the board. Reed contacts are sealed, so wetting current is not critical, but a stiffer pull-up lowers the impedance that noise couples into. The power cost doesn't matter on a mains-powered node.
- **RC filter at the pin:** a series resistor (1–10 kΩ) from the cable to the GPIO with a capacitor to ground gives tens of µs to a few ms time constant. Practitioner builds use e.g. 10 kΩ + 1 µF ([atmoCatcher BOM](https://github.com/aldotapia/atmoCatcher)) or 1 nF across the reed ([BoSL rain gauge v3](https://boslwiki.com.au/wiki/Rain_gauge), which fixed duplicate counts that way).
- **Software lockout:** count the falling edge, then ignore further edges for 200–500 ms. A common ESPHome-world default is a ~30 ms filter ([esp32.co.uk guide](https://esp32.co.uk/tipping-bucket-rain-gauge-esp32-esphome-home-assistant/), practitioner). For this gauge a longer lockout is safe given the max tip rate above.

#### Surge, ESD and lightning protection on an outdoor run

Primary guidance is thin for hobby GPIO. The best-documented practice comes from datalogger vendors and silicon vendors' ESD notes.

| Measure | What it does | Source |
|---|---|---|
| **Series resistor first, then TVS/ESD diode, then a second resistor to the pin** | The first resistor limits surge current into the TVS. The TVS clamps. The second resistor limits current into the ESP32's internal clamp diodes. A TI engineer notes "the series resistor helps reduce the effects of a surge event". | [TI E2E thread](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/1288521/tsd05c-gpio-protection-of-mcu-with-5-5v-amr), [TI SLVAFQ4 GPIO ESD brief](https://ti.com/lit/pdf/slvafq4), Silicon Labs AN376 as quoted by [mbedded.ninja](https://5f7b802fd56539458d03e297--blog-mbedded-ninja.netlify.app/electronics/circuit-design/esd-protection) (secondary) |
| **Low-voltage TVS at the enclosure entry** | Clamps surges where the cable enters, before they reach the PCB. Pick a standoff voltage just above 3.3 V. | [DigiKey: protecting MCU I/O lines](https://www.digikey.at/en/articles/protecting-mcu-io-lines-from-esd-and-other-transients) |
| **Shielded cable, shield bonded to ground at the controller end** | Campbell's spark-gap junction box manual says to connect sensor lead shields to the ground terminals. | [Campbell 036/038 manual](https://s.campbellsci.com/documents/es/manuals/036-038.pdf) |
| **A real earth ground** | Campbell says transient protection "is meaningless without a good system earth ground". | [Campbell CR10 manual excerpt](https://www.manualowl.com/m/Campbell%20Scientific/CR10/Manual/421452?page=198) |
| **Optical isolation** | Breaks the galvanic path. Campbell's SunSentry note recommends isolating devices from each other and from their mounting structures. A reed-switch loop through an optocoupler LED needs its own *isolated* supply (e.g. a small isolated DC-DC), or the isolation is bypassed. | [Campbell SunSentry surge note](https://s.campbellsci.com/documents/us/technical-papers/sunsentry-surge-protection.pdf) |
| **Outdoor-rated cable** | UV-resistant jacket above ground, direct-burial rated (or in conduit) below ground. The controller's own valve field wiring is already this class of cable. | Rain Bird RSD-BEx ships UV-resistant wire ([Rain Bird store](https://store.rainbird.com/timers/rain-moisture-sensors/rsdbex-rain-sensor-with-bracket.html)) |

Caveats specific to this install:

- The ESP32 ground is tied to the controller's 24VAC secondary through the LM2596 buck, which is not isolated. A surge on the gauge cable can therefore reach the controller's electronics as well as the ESP32. That argues for clamping at the enclosure entry, and for optical isolation if the run is long or exposed.
- No protection survives a direct or very close strike. Campbell's lightning-rod guidance says the system "is not infallible" ([Campbell CR350 help](https://help.campbellsci.com/CR350/shared/installation/lightning.htm)).

#### Counting pulses in MicroPython

| Method | Available | Debounce | Notes |
|---|---|---|---|
| `machine.Pin.irq(handler, trigger=Pin.IRQ_FALLING)` | All ESP32 builds | In software (lockout using `time.ticks_ms()`) | "Hard interrupt handlers may not allocate memory" ([Pin docs](https://docs.micropython.org/en/latest/library/machine.Pin.html)). Default soft IRQs are fine at this tip rate. Share the count via a pre-allocated `array`/`bytearray` or an int, and beware read-modify-write races in main code ([ISR rules](https://docs.micropython.org/en/latest/reference/isr_rules.html)). Call `micropython.alloc_emergency_exception_buf(100)`. |
| `machine.Counter(id, src=pin, edge=Counter.FALLING, filter_ns=...)` | ESP32 (and MIMXRT), since **v1.26** | `filter_ns` uses "the longest hardware-supported filter that does not exceed the requested value" ([Counter docs](https://docs.micropython.org/en/latest/library/machine.Counter.html)) | Thin shim over `esp32.PCNT`. Counts in hardware with no ISR. |
| `esp32.PCNT` | ESP32, since v1.26 ([v1.26 release notes via Debian mirror](https://salsa.debian.org/yangfl-guest/micropython/-/tags), [v1.26 Counter docs](https://docs.micropython.org/en/v1.26.0/library/machine.Counter.html)) | Filter "1..1023, in ticks of the 80MHz clock" ([esp32 docs](https://docs.micropython.org/en/latest/library/esp32.html)), so **12.8 µs max** | Too short to reject ms-scale reed bounce or bucket chatter on its own. It would need the external RC filter plus a check in software. PCNT also does not run in deep sleep: it lives in the digital domain ([esp32.com thread](https://esp32.com/viewtopic.php?p=5931)). |

Recommendation for the wired case: `Pin.irq` on falling edge, with a lockout of a few hundred ms in the handler. Keep a running total in a module-level int, and read it on each 15-minute cycle. Check what MicroPython version the device runs before relying on `machine.Counter`.

### 1b. Standalone battery-powered outdoor node

#### Deep sleep with reed-switch wake

- **RTC-capable pins:** "Some ESP32 pins (0, 2, 4, 12-15, 25-27, 32-39) are connected to the RTC during deep-sleep" and can wake the chip. "Pins 34-39 are input only, and also do not have internal pull-up resistors." Avoid strapping pins 0, 2, 12 and 15 for the reed input. Good choices are GPIO 25–27, 32 or 33 ([MicroPython ESP32 quickref](https://docs.micropython.org/en/latest/esp32/quickref.html)).
- **Pull retention:** "The output-capable RTC pins (all except 34-39) will also retain their pull-up or pull-down resistor configuration when entering deep-sleep" ([quickref](https://docs.micropython.org/en/latest/esp32/quickref.html)).
- **ext0 vs ext1** ([ESP-IDF sleep modes](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/sleep_modes.html)):
  - ext0: one RTC pin, wake on a level. "RTC peripherals will be kept powered on during Deep-sleep if this wakeup source is requested". That costs some extra sleep current compared with the 10 µA "RTC timer + RTC memory" figure. The exact delta was not found in a primary source.
  - ext1: one or more pins, and "supports wakeup even when the RTC peripheral is powered down". However, "internal resistors do not work when RTC peripherals are shut down, so external resistors may be needed". On the ESP32 the modes are ALL_LOW or ANY_HIGH.
  - MicroPython exposes these as `esp32.wake_on_ext0(pin, level)` and `esp32.wake_on_ext1(pins, level)` ([esp32 docs](https://docs.micropython.org/en/latest/library/esp32.html)).
  - With a reed to GND and an external pull-up (e.g. 100 kΩ–1 MΩ), current flows only during the brief closure.
- **Stuck-closed trap:** wake is level-triggered. If the bucket can come to rest with the magnet over the reed, the chip re-wakes immediately in a loop and drains the battery. Some printed designs do exactly this on purpose. The [DN110 hall-sensor design](https://www.printables.com/model/184037) gives "a steady signal while the seesaw is in position A, and no signal if the seesaw is in position B". With such designs, flip the wake level on every wake, or use ext1 ANY_HIGH and ALL_LOW alternately.
- **Counting in RTC memory:** `machine.RTC().memory()` holds "2048 bytes by default on esp32" and "is persistent across restarts, including Soft Reset and machine.deepsleep()". The docs say nothing about power loss. RTC SRAM is not battery-backed, so treat it as lost on a battery swap ([RTC docs](https://docs.micropython.org/en/latest/library/machine.RTC.html)).
- **Cost of a wake per tip:** a stock MicroPython wake that boots to `main.py`, increments a counter and sleeps again took 635 ms and 41.9 mC (about 11.6 µAh) in practitioner measurements. A frozen `_boot.py` cut that to 48.8 ms and 1.8 mC ([upy-esp32-experiments](https://github.com/glenn20/upy-esp32-experiments), measured on the USB line, which "will over-estimate power consumed"). A tip that arrives during the boot window has to be caught by a `Pin.irq` while awake.
- **ULP counting** avoids full wakes. ESP-IDF's `ulp_fsm` pulse-counting example debounces in the ULP and wakes the CPU after N edges. Its README reports "average current consumption in deep sleep mode on ESP32 is 16uA" with a 20 ms ULP period ([ESP-IDF example](https://github.com/espressif/esp-idf/tree/master/examples/system/ulp/ulp_fsm/ulp)). MicroPython offers `esp32.ULP` (load and run a binary) and the MIT-licensed [micropython-esp32-ulp](https://github.com/micropython/micropython-esp32-ulp) assembler, which includes a `counter.py` example. **Is it worth it?** At about 2,500 tips per year (worked estimate below), per-tip wakes cost roughly 30 mAh/year. The ULP saves little of that and adds ULP assembly to maintain. Skip the ULP unless measurements show per-tip wakes dominate.

#### WiFi association time and energy from deep sleep

Practitioner measurements made by the `espnow` module's author, total wake → send → sleep, MicroPython on ESP32/ESP32-S3 ([upy-esp32-experiments](https://github.com/glenn20/upy-esp32-experiments)):

| Scenario | Time (ms) | Charge (mC) | ≈ µAh |
|---|---|---|---|
| Optimised boot only (frozen `_boot.py`) | 48.8 | 1.8 | 0.5 |
| Unoptimised boot to `main.py` | 635.1 | 41.9 | 11.6 |
| Optimised boot + ESP-NOW send | 119.0 | 7.7 | 2.1 |
| Optimised boot + MQTT over WiFi, static IP | 774.3 | 108.6 | 0.030 |
| Optimised boot + MQTT over WiFi, DHCP | 1626.0 | 204.3 | 0.057 |

- Static IP and cached BSSID/channel in RTC memory are the usual WiFi speed-ups. Reported savings vary, and one forum poster "did not notice any difference" (practitioner, summarised from search; unverified).
- The radio's current is large and bursty: 802.11b TX at 19.5 dBm averages 239 mA with a **379 mA peak**, and RX is 112 mA ([WROOM-32E/UE datasheet, Table 16](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)). The battery and regulator must handle that peak, especially when cold.

#### ESP-NOW from the outdoor node to the garage ESP32

- **Supported:** the `espnow` module is part of MicroPython for ESP32 and ESP8266 ([espnow docs](https://docs.micropython.org/en/latest/library/espnow.html)). "ESPNow support has been available in production micropython images since the v1.21.0 release" ([micropython-espnow-images](https://github.com/glenn20/micropython-espnow-images)). Payload is up to 250 bytes on v1, or 1470 bytes on ESP-NOW v2 with ESP-IDF 5.4+. Check `espnow.MAX_DATA_LEN`.
- **Coexistence with STA on the receiver** (all from the [espnow docs](https://docs.micropython.org/en/latest/library/espnow.html)):
  - STA_IF and AP_IF share one radio and always use the same channel.
  - Peers "MUST use the same channel" as a device connected to an access point.
  - Connecting to an AP enables power save, which makes the receiver "unreliable in receiving ESPNow messages". Fix with `sta.config(pm=sta.PM_NONE)`. On a mains-powered garage node, the extra current doesn't matter.
  - If the router changes channel, "other ESPNow-only devices will remain on the previous channel and communication will be lost". Also, "ESPNow messages will be lost while scanning for the AP".
- **Handling this in practice:**
  - Pin the router's 2.4 GHz channel if possible.
  - Have the outdoor node keep its last-good channel in RTC memory. ESP-NOW unicast is MAC-acknowledged and `send()` reports success, so on failure the node walks channels 1–13 and stores the new one.
  - Alternatively, the receiver can report its channel in a reply. The ESP-IDF docs note that peer channel 0 means "use the current channel" ([ESP-IDF ESP-NOW](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html)).
  - Practitioners report the same channel-tracking need ([MicroPython forum](https://forum.micropython.org/viewtopic.php?p=58187), [dev.to channel-hopping writeup](https://dev.to/gtanyware/channel-hopping-on-the-esp32-c3-with-esp-now-2led)).
- **Before sleeping:** "applications must disable the WLAN peripheral" before deep or light sleep ([espnow docs](https://docs.micropython.org/en/latest/library/espnow.html)). ESP-IDF also requires WiFi/BT to be stopped ([sleep modes](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/sleep_modes.html)).
- **Security:** ESP-NOW supports per-peer LMK encryption (CCMP, 16-byte keys), with up to 17 encrypted peers ([ESP-IDF ESP-NOW](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html)). Given the project's no-backdoor requirement, the receiver should accept only one known peer MAC with a key set, and treat the payload as data (bounds-check it).

#### Range and antenna in a plastic enclosure

- Espressif-hosted partner tests (ESP32-C6, PCB antenna) found ESP-NOW success near 100% to 150 m and about 60% at 300 m in open field. ESP-NOW-LR was near 100% to 450 m. In forest, success dropped below 50% at 125 m. Espressif notes it "has not independently verified" the content ([Espressif blog](https://developer.espressif.com/blog/esp-now-for-outdoor-applications/)). Backyard-to-garage distances are well within this, but walls, a metal garage door, and the controller's own enclosure are the real losses.
- LR mode needs both ends to be ESP32. Results are mixed in practice, and a MicroPython issue reported no change after enabling it (summarised from [esp32.com](https://esp32.com/viewtopic.php?p=127565); unverified).
- Espressif's layout guide: "A clearance of at least 15 mm is recommended in all directions" between antenna and housing, and the finished product should be range-tested ([Espressif hardware design guidelines](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html)). Plastic is largely RF-transparent. Keep batteries, screws and wiring out of that zone.
- The garage unit is already a WROOM-32U with a U.FL external antenna, which helps the receive side. Route that antenna outside the metal parts of the controller, or at least away from them. A U-variant module with a short external dipole on the outdoor node is the low-risk choice.

### 1c. Other options people use (brief)

| Option | How | Fit for this project |
|---|---|---|
| **433/868/915 MHz commercial gauge + SDR/transceiver decode** | Buy an Ecowitt WH40-class wireless gauge (0.1 mm/tip per [Ecowitt support](https://ecowitt-subgqs9hhsx.gorgias.help/en-US/ws69wh40-rain-gauge-accuracy-issue-check-listing-564827)). rtl_433 decodes it as protocol **[113] "EcoWitt WH40/WN20 rain gauge"** ([rtl_433 README](https://github.com/merbanan/rtl_433)). On an ESP32 this means a CC1101/SX127x radio and [rtl_433_ESP](https://github.com/NorthernMan54/rtl_433_ESP), which is an **Arduino C++ library, not MicroPython**. | Buys a finished, sealed, battery gauge, but needs a second firmware stack or porting a decoder. The US frequency for the WH40 was not verified (915 MHz is confirmed only for the WH40BH sibling, [manual](https://manuals.plus/asin/B0DT5ZP2ZQ)). |
| **LoRa** | SX126x/SX127x modules. MicroPython drivers exist in micropython-lib (`lora-sx126x`, `lora-sx127x`) and work on any port with `machine.SPI` ([micropython-lib lora](https://github.com/micropython/micropython-lib/tree/master/micropython/lora)). | Overkill for backyard range. Adds a radio module at both ends. |
| **Zigbee via a door sensor** | Replace the gauge's reed board with a Sonoff SNZB-04 contact sensor. The original poster reports "over four years on one battery" ([HA forum thread](https://community.home-assistant.io/t/diy-zigbee-rain-gauge/255379/1), [Printables remix](https://www.printables.com/model/224326)). | Needs a Zigbee coordinator and Home Assistant. Not compatible with this bare-MicroPython, no-hub design. |
| **HC-12 433 MHz serial link** | Used by the [Weather Station One](https://www.printables.com/model/61720) build ("up to 1 kilometer distance", author claim). | UART bridge. Simple, but adds modules at both ends and has no encryption. |

### Recommendation for question 1

**Wired (1a)**, because:

1. The garage ESP32 already has power, network and the decision logic. A wired gauge adds one GPIO and an ISR, with no battery maintenance, no second firmware image, and no channel-tracking problem.
2. Dry-contact reed gauges are routinely run hundreds of feet (Davis: 900 ft), so cable length is not a real constraint at residential distances.
3. The main risk, surge on an outdoor cable, is manageable with cheap parts: series R + TVS + RC, shielded cable, and optionally an optocoupler with an isolated supply.

Go wireless (1b) only if the best open-sky location (away from eaves, trees and splash) can't practically be reached by cable. In that case use ESP-NOW on a fixed router channel, send a cumulative count, and use a bare module with a low-Iq regulator.

---

## 2. Free 3D-printable rain gauge designs

Licences below come from each platform's own model data. Thingiverse and MakerWorld pages refused automated fetches, so licences there are marked as unverified. Designer names are left out (public repo), and the links identify each design.

| Design | Licence (exact) | Mechanism | Funnel / tip volume | Calibration / accuracy | Hardware |
|---|---|---|---|---|---|
| [Printables 130513 "Rain gauge"](https://www.printables.com/model/130513) | "Creative Commons — Attribution" (CC-BY) | Tipping bucket, reed switch + "round magnet 5x2mm" | "One impuls from reed switch equals 0.2 mm"; funnel size not stated | Adjusting screws under the bucket; no accuracy figure | M3x6/M3x8 screws, magnet, reed switch, strainer "to avoid jamming the small hole with leaves or insect". Printed in PETG, then painted with UV-resistant paint |
| [Printables 61720 "Weather Station One Part 4 – the Rain Gauge"](https://www.printables.com/model/61720) | "Creative Commons — Attribution" (CC-BY) | Tipping bucket, reed + magnet | Not stated in description | "Measure the amount of water you can drop into the gauge before the bucket flips. Using a small syringe is convenient"; adjust reed distance with axle screws | PETG body, TPE/TPU seals, stainless hardware, M3x20 screws; v2 widened the gutter and gap "to work around surface tension" |
| [Printables 386114 "Rain gauge – Pluviometer"](https://www.printables.com/model/386114) | "Creative Commons — Attribution — Noncommercial — Share Alike" (CC-BY-NC-SA) | Tipping bucket, reed 1.8x7 mm + magnet 4x2 mm | "funnel area is 0.01m2"; "1.5mL an impulse" → "0.15mm of rain" | "375mL of water generate 250 impulses" (dynamic pour) | 3 mm x 30 mm rod, M3x6 bolts |
| [Printables 1199963 "Solar powered rain gauge – Pluviometer V2"](https://www.printables.com/model/1199963) | "Creative Commons — Attribution — Noncommercial — Share Alike" (CC-BY-NC-SA) | Tipping bucket, reed 1.8x7 mm + magnet 4x2 mm; solar + supercapacitor wireless node | "Funnel radius is 80mm"; "1.15mL" → "0.057mm" | "After calibration test" (method in linked French writeup) | Rod, magnets, silicone, TPU seals, many M2.5–M4 screws |
| [Printables 184037 "Tipping Bucket Rain Gauge for HT DN 110 pipe"](https://www.printables.com/model/184037) | "Creative Commons — Attribution" (CC-BY) | Tipping bucket, **A3144 hall switch** + 5x5x2 mm magnet; steady level per bucket position | Sits on a DN110 pipe; "approximately 2.5 cubic centimeters" per tip | None published | DN110 pipe, hall sensor, magnet, M3 or wood screws. Printed in PLA; suggests gauze against insects |
| [Printables 247135 "Tipping Bucket Rain Gauge"](https://www.printables.com/model/247135) | "Creative Commons — Attribution — Share Alike" (CC-BY-SA) | Tipping bucket, **slotted opto-switch** | Not stated | None | ESP8266 + slotted opto (always-powered sensor, poor fit for battery) |
| [Printables 557375 "Rain Gauge Project with ESP32 wireless"](https://www.printables.com/model/557375) | "Creative Commons — Public Domain" (CC0) | Tipper + hall sensor; ESP32 deep sleep, wakes on tip, **ESP-NOW** to a second ESP32 | Not stated | None | 2×1.5 V cells + MT3608 boost |
| [Printables 847431 "Rain Gauge based on Tipping bucket-teknik"](https://www.printables.com/model/847431) | "Creative Commons — Attribution — Noncommercial" (CC-BY-NC) | Tipping bucket, AH180 hall or reed; ESP32 FireBeetle deep sleep | "0.4 mm rain att each tipp" | None | FireBeetle 2, LiPo 2000–3700 mAh; author says "not 100% finished" |
| [Printables 224326 "Zigbee Rain Gauge"](https://www.printables.com/model/224326) (remix of [Thingiverse 2849562](https://www.thingiverse.com/thing:2849562)) | Printables: "Creative Commons — Attribution — Noncommercial" (CC-BY-NC). Thingiverse base: **not verified** | Tipping bucket, reed (rewired to SNZB-04) | Author measured 9.5 mL per tip; funnel per base design | Published method: pipette fill, 10 repeats, average; mm/pulse = 1 / ((area/10) / tip average) | Sonoff SNZB-04 |
| [SS4H-RG](https://smartsolutions4home.com/ss4h-rg-rain-gauge/) | **No licence stated**; described as "totally open-source", files behind an email-gated download | Tipping bucket, hall sensor + magnet; custom ESP32 PCB, ESPHome | Funnel radius 55 mm; 6 mL → 0.631 mm/tip | Pour 6 mL, turn screw until it tips, repeat for other side | AAA cells, custom PCB, PVB-varnished board |
| [atmoCatcher (GitHub)](https://github.com/aldotapia/atmoCatcher) | **No licence file found** (so legally all rights reserved) | Tipping bucket, reed + mini magnet | Fits 125 mm PVC pipe | Published intensity-dependent calibration ŷ = 2.35 + 0.05x mL (x in L/h) | Pico W (ESP32 suggested), 10 kΩ + 1 µF, PLA+ |
| [BoSL rain gauge (wiki)](https://boslwiki.com.au/wiki/Rain_gauge) | **Not stated** | Tipping bucket; moved from hall to **reed** because the hall sensor "drew too much power" | Target 2 mL/flip; measured 2.8–3.1 mL | Overnight repeat calibrations differed by −1% to 9% across six gauges; field comparison with a Campbell gauge (no numbers published) | Arduino Nano, M5 stainless rod, 1 nF across reed |
| [MakerWorld 1366151 "Rain Gauge"](https://makerworld.com/en/models/1366151-rain-gauge) | **Not verified**; a mirror ([3dgo.app](https://3dgo.app/models/makerworld/1366151)) lists "Standard Digital File License" | Tipping bucket; ESPHome code included | About 7 mL per tip (from search snippet) | Unverified | Unverified |
| [MakerWorld 1451114](https://makerworld.com/models/1451114) | **Not verified** | Tipping bucket, reed variant | "100 sq. cm" opening, "10 ml equals 1 mm"; about 0.5 mm/tip (from search snippet) | Unverified | Printed in PLA; author expects "a couple of years" outdoors |

Takeaways:

- Only CC-BY / CC0 designs (130513, 61720, 184037, 557375) can be freely remixed and redistributed without NC/SA strings. That matters if a remixed STL ever lands in this public repo.
- Reed + magnet is the battery-friendly choice. A reed switch draws nothing when open. Hall sensors need continuous power, which is why BoSL switched to reed.
- The tip volumes above span 0.057–0.63 mm per tip. Smaller tips give finer resolution but more wakes on a battery node.

### Calibration procedure

1. **Area:** A = π·(d/2)² of the funnel's *sharp-edged rim*, in mm².
2. **Static check:** drip water from a syringe into one bucket until it tips, and record mL. Repeat about 10× per side, then balance the sides with the adjusting screws. This is the method used by 61720, 224326 and SS4H-RG.
3. **Dynamic calibration (the number to actually use):** pour a known volume V (e.g. 500 mL) through the funnel *slowly*, at a realistic rain rate (a bottle with a pinhole over 30+ minutes), and count tips N. Then **mm per tip = (V/N × 1000 mm³/mL) / A**. Example: SS4H-RG has 6 mL and r = 55 mm, so A = 9,503 mm² and 6,000 / 9,503 = 0.631 mm, which matches the author's figure.
4. **Rate dependence:** tip volume grows with intensity (atmoCatcher: +0.05 mL per L/h). The WMO lab intercomparison found that only tipping buckets "that apply proper correction to account for mechanical errors comply with the WMO specifications" ([Lanza et al.](https://old.wmo.int/extranet/pages/prog/www/IMOP/publications/IOM-94-TECO2006/P3(15)_Lanza_Italy.pdf)). For irrigation thresholds of 0.25"/0.5", a single dynamic calibration at moderate intensity is adequate.
5. **Field check:** compare against a cheap manual cylinder gauge over a few storms.

### Filament for outdoor UV and heat

| Material | Prusa guidance | Fit |
|---|---|---|
| **PLA** | "gets soft and deforms at temperatures over 60 °C", "degrades under UV light", "not suitable for technical and outdoor use" ([Prusa PLA](https://help.prusa3d.com/article/pla_2062)) | No. A sun-baked dark part in a >100 °F summer can approach its softening point. |
| **PETG** | "suitable both for interior and most exterior use (with temperatures below 80 °C)", "Water and humidity resistant". Prusa's page says nothing about UV ([Prusa PETG](https://help.prusa3d.com/article/petg_2059)) | OK, and widely used (130513, 61720). Paint or use a light colour for UV. |
| **ASA** | "suitable for outdoor use, due to its high UV light and temperature resistance", "up to 93 °C"; "more UV resistant" than ABS ([Prusa ASA](https://help.prusa3d.com/article/asa_1809)) | Best for the funnel and housing. Needs an enclosed printer. |
| **TPU/TPE** | Used for seals in 61720 and 1199963 | Gaskets |

Water absorption also matters for calibration drift. BoSL measured about 1.26% weight gain for PLA and about 0.87% for PETG, and recommends "100% infill" for buckets ([BoSL](https://boslwiki.com.au/wiki/Rain_gauge)).

### Known failure modes

| Failure | Evidence | Mitigation |
|---|---|---|
| **Clogging (leaves, seeds, dust)** | 130513 adds a strainer; BoSL added a filter funnel | Removable mesh over the funnel outlet; inspect after storms |
| **Insects / spiders** | Davis: spider webs and insect nests "can keep the tipping spoons from moving", causing under-reporting ([Davis sensor maintenance](https://cdn.shopify.com/s/files/1/0515/5992/3873/files/Doc_Sensor-Maintenance.pdf)) | Gauze on inlet and drain (184037), periodic cleaning |
| **Bucket sticking / surface tension** | 61720 v2 widened the bucket-to-base gap; BoSL saw sticking overnight and drift from water on the base | Larger clearances, smooth pivot (metal rod), slanted bucket top |
| **Bounce / double counts** | BoSL v2/v3, HA forum reports | RC filter + lockout (section 1a) |
| **Reed positioning / breakage** | 61720: glass reeds "break very fast when bending the wires"; HA forum reports missed tips from imprecise magnet positioning ([HA thread](https://community.home-assistant.io/t/diy-zigbee-rain-gauge/255379?page=18)) | Pot the reed in epoxy; adjustable reed mount |
| **Wind undercatch** | Wind is "the largest" error component; gauges above ground lose drops to rim turbulence ([Lanza et al.](https://old.wmo.int/extranet/pages/prog/www/IMOP/publications/IOM-94-TECO2006/3(4)_Lanza_Italy.pdf)) | Mount low, level, and away from walls and eaves; a sheltered spot is better than a rooftop |
| **Freezing / snow / hail** | Not found in a primary source for these designs. A tipping bucket can't measure snow until it melts, and ice can lock the bucket. Hail can bounce out or melt in later as delayed "rain". | Irrigation is likely off in deep winter anyway. Treat counts during freezing weather as untrusted (open question). |
| **Heat** | PLA softens >60 °C (above) | PETG/ASA, light colour |
| **Mounting near magnetic objects** | Davis: the magnet-operated switch "may not operate correctly" near objects that attract a magnet ([Davis manual](https://www.manualslib.com/manual/227021/Davis-Instruments-Rain-Collector.html)) | Non-ferrous mount |

---

## 3. Power for an outdoor node

(Only relevant if the wireless option is chosen.)

### Battery chemistries

| Chemistry | Voltage | Temperature (datasheet) | Notes |
|---|---|---|---|
| **Li-ion 18650** (Panasonic NCR18650B) | 3.6 V nom, 4.2 V full | "Charge: 0 to +45°C", "Discharge: -20 to +60°C", "Storage: -20 to +50°C"; "At temperatures below 10°C, charge at a 0.25C rate" ([NCR18650B datasheet](https://files.batteryjunction.com/frontend/files/Panasonic-NCR18650B.pdf)) | 3200 mAh min. Needs a regulator for the ESP32 (3.0–3.6 V). **Must not be charged below 0 °C.** Storage limit of 50 °C is the concern in a sun-exposed box. |
| **LiFePO4** (26650/32650/18650 LFP) | 3.2 V nom, 3.6–3.65 V full | Typical sheet: charge 0–45 °C, discharge −20 to 60 °C ([Power-Sonic IFR26650PC](https://cdn.power-sonic.com/documents/PSL-FP-IFR26650PC-Data-Sheet.pdf), [Bioenno 26650](https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs)); some cells allow 0–55 °C charge | Voltage sits inside the ESP32's 3.0–3.6 V supply range for most of its discharge. Practitioners run ESP32s straight off the 3V3 pin ([HA forum](https://community.home-assistant.io/t/how-to-power-an-esp32-supermini-board-directly-from-a-lifepo4-battery/975202), [hackaday.io](https://hackaday.io/project/167245/log/167362-power-system-battery-charger)). A just-charged cell (3.65 V) slightly exceeds 3.6 V, and there's no undervoltage cutoff without added protection. **Also no charging below 0 °C.** |
| **Lithium primary AA** (Energizer L91, Li/FeS₂) | 1.5 V nom | "Recommended Lithium Operating/Storage Temperature: -40°C to 60°C"; "Shelf Life: 15 years at 21°C" (this datasheet revision; newer ones say 25); max "2.0 Amps Continuous" ([L91 datasheet](https://files.batteryjunction.com/frontend/files/L91.pdf)) | Best cold and heat tolerance, no charging problem, handles WiFi peaks. 2 cells sag below 3.0 V under load, so use 3 cells + a low-Iq LDO, or 2 cells + boost. |
| **Alkaline AA** (Energizer E91) | 1.5 V nom | "Operating Temp: -18°C to 55°C (0°F to 130°F)" ([E91 datasheet](https://courses.egr.uh.edu/ECE/ECE2100/Archive/Spring%202024%20Honors/E91.pdf)) | Fails the "below 0 °F" requirement at the cold end, has high internal resistance (150–300 mΩ fresh) against 379 mA peaks, and can leak. Not recommended. |

**Heat:** a sealed box in direct sun runs well above ambient. No primary measurement was found, so log it with a sensor. Every chemistry above has an upper limit of 50–60 °C. Mount the battery box shaded, light coloured and vented below the seal line. L91 and LFP have the most margin.

### Solar charging

| Charger | Chemistry | Low-temp cutoff | Notes |
|---|---|---|---|
| **TP4056** | Li-ion 4.2 V | Has a TEMP pin for an NTC. One datasheet copy says charging suspends if TEMP is outside 45%–80% of VIN; grounding TEMP disables it ([UMW TP4056 datasheet](https://datasheet.lcsc.com/lcsc/2311091738_UMW-Youtai-Semiconductor-Co---Ltd--TP4056_C725790.pdf), [TP4056 PDF](https://github.com/komakow/SensorsProject/files/3936079/TP4056.pdf)) | Linear, no MPPT. **Most cheap modules ground TEMP**, so they will happily charge a frozen cell. Wrong voltage for LFP. |
| **CN3791** | Li-ion 4.2 V, MPPT (constant-voltage MPPT pin regulated to about 1.205 V) | **Not verified.** Sources conflict on whether the chip has a TEMP pin ([LCSC C154992](https://www.lcsc.com/product-detail/C154992.html)) | Common "solar Li-ion" module. Check the board for an NTC before trusting it in winter. |
| **CN3801** | LiFePO4 (3.625 V CV), MPPT | Not confirmed in the sources found | LFP-specific MPPT controller ([LCSC C840499](https://www.lcsc.com/product-detail/C840499.html)) |
| **CN3058E** | LiFePO4, linear | Not confirmed | No MPPT ([electronics-lab](https://www.electronics-lab.com/news/lifepo4-charger-board-based-on-cn3058e/)) |
| **TI bq24650** | Configurable (any chemistry via feedback divider), MPPT | TS pin + NTC: "If battery temperature is outside of this range, the controller suspends charge" ([bq24650 datasheet](https://www.ti.com.cn/document-viewer/cn/BQ24650/datasheet/35-ZHCSKO6B)) | The one option here with a documented cold cutoff. Over-spec for a 1 W panel. |

Given the load estimates below (about 0.7 mAh/day for an ESP-NOW design), **solar is optional**. A primary-lithium or LFP pack sized for 1–2 years removes the below-freezing charge problem entirely. If solar is used, the charger must have a working NTC cold cutoff, or the firmware must refuse to enable charging below about 2 °C (which needs a charger with an enable pin).

### Realistic battery-life math

**Chip versus board:**
- The ESP32 datasheet gives **"RTC timer + RTC memory 10 µA"**, "Hibernation RTC timer only 5 µA", and "The ULP coprocessor is powered up. 150 µA" ([ESP32 datasheet Table 4-2](https://documentation.espressif.com/esp32_datasheet_en.pdf)). The supply range is 3.0–3.6 V ([WROOM-32E/UE datasheet](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)).
- A DevKitC V4 measured **3.8 mA** in deep sleep, blamed on the power LED and the AMS1117 regulator ([lucidar](https://lucidar.me/en/esp32/power-consumption-of-esp32-devkitc-v4/), practitioner). A forum user went from about 4 mA to about 12 µA by cutting out the regulator (from [search summary](https://hubble.com/community/guides/esp32-deep-sleep-current-what-the-datasheet-says-vs-what-you-ll-actually-measure/); unverified).
- A FireBeetle (DFR0478) measured 10 µA ([lucidar](https://lucidar.me/en/esp32/power-consumption-of-esp32-firebeetle-dfr0478/)).
- A low-Iq LDO such as the MCP1700 is 1.6 µA typical ([MCP1700 datasheet](https://www.radiolocman.com/datasheet/pdf.html?di=128895)). It is rated only 200–250 mA, though, below the 379 mA radio peak, so it needs a large bulk capacitor or a bigger low-Iq part. That trade-off is unverified and should be bench-tested.

**Per-wake cost** (from the table in 1b, stock MicroPython boot = 41.9 mC; radio increment = optimised total − 1.8 mC boot):

| Wake type | mC | µAh |
|---|---|---|
| Tip, count only (stock boot) | 41.9 | 11.6 |
| Tip or heartbeat + ESP-NOW (41.9 + 5.9) | 47.8 | 13.3 |
| Heartbeat + WiFi static IP (41.9 + 106.8) | 148.7 | 41 |
| Heartbeat + WiFi DHCP (41.9 + 202.5) | 244.4 | 68 |

These figures were measured on the USB line, so they overstate a battery build somewhat ([source](https://github.com/glenn20/upy-esp32-experiments)).

**Worked estimate.** Assumptions:
- 15 µA total sleep (10 µA chip + about 5 µA for LDO, battery divider and leakage; this is an assumption).
- 0.3 mm/tip, so a 1" rain day ≈ 85 tips and a 3" day ≈ 254 tips.
- An assumed ~30 in/yr of rain ≈ 2,540 tips/yr, spread over about 60 rain days. This is an assumed round figure for the plains, not a sourced climatology.

| Item | ESP-NOW design (hourly heartbeat, send on tip) | WiFi DHCP design (hourly heartbeat, send on tip) | Dev board, ESP-NOW |
|---|---|---|---|
| Sleep per day | 15 µA × 24 h = 0.36 mAh | 0.36 mAh | 3.8 mA × 24 h = 91 mAh |
| Heartbeats per day (24) | 24 × 13.3 µAh = 0.32 mAh | 24 × 68 µAh = 1.63 mAh | 0.32 mAh |
| 1" rain day (85 tips) | +1.13 mAh | +5.8 mAh | +1.13 mAh |
| 3" rain day (254 tips) | +3.4 mAh | +17.3 mAh | +3.4 mAh |
| **Year** (365 dry-day baseline + 2,540 tips) | 131 + 117 + 34 ≈ **280 mAh** | 131 + 595 + 173 ≈ **900 mAh** | **≈ 33,500 mAh** |
| With 1.5× margin (cold, regulator, self-discharge) | ≈ 420 mAh/yr | ≈ 1.35 Ah/yr | — |
| 3,200 mAh 18650 or ~3,000 mAh L91 pack | **multi-year** (self-discharge and cold then dominate) | **≈ 2 years** | **≈ 35 days** |

What the estimate shows:
1. The board's sleep current dominates everything, so don't use a dev board.
2. On a well-built node, heartbeats cost more than rain. Pick the heartbeat interval deliberately. A 15-minute heartbeat that matches the controller's cycle quadruples that line (about 1.3 mAh/day with ESP-NOW).
3. WiFi instead of ESP-NOW costs about 3× the annual energy.

### Swappable battery design

- **Two packs in rotation:** with a ~1–2 year life there is little need for rotation. A spare pack mainly gives a zero-downtime swap. Put the pack on a polarised, keyed connector (e.g. JST-XH/PH style) so a cold-fingered swap can't reverse polarity. The node should read pack voltage at each heartbeat, with a high-value or switched divider so the divider doesn't become the dominant sleep load.
- **Holders and doors:** a tool-free door or a screw-cap housing is easier to keep sealed than a lid with many screws. Seal with an O-ring or a printed TPU gasket (61720 and 1199963 print their seals in TPU/TPE).
- **IP rating:** IP65 = dust-tight + low-pressure water jets from any direction. IP67 = dust-tight + temporary immersion (roughly up to 1 m for 30 min). A 7 does not imply jet protection ([e-switch IP guide](https://www.e-switch.com/blog/all-about-ip-ratings-ingress-protection/), secondary; the IEC 60529 text itself was not accessible). For a gauge-side box, IP65 + a drip loop + a downward-facing cable gland is the practical target. Fully sealed boxes can pull in moist air as they cool, so a vent membrane or desiccant helps.
- **Does hot-swap matter?** No, if the protocol is designed for it. RTC memory survives deep sleep but is documented only as "persistent across restarts, including Soft Reset and machine.deepsleep()" ([RTC docs](https://docs.micropython.org/en/latest/library/machine.RTC.html)), so a power loss resets it. Tips during the few seconds of a swap are lost either way. A supercap hold-up adds complexity for little benefit.
- **Persist or report deltas?** **Report a cumulative counter plus a boot/epoch ID and a sequence number**, not deltas:
  - A dropped ESP-NOW packet then loses nothing. The next packet carries the new total.
  - The receiver sees a counter drop or an epoch change, treats it as a reset, and resumes from zero.
  - The outdoor node needs no flash writes. The receiver, which is mains powered, owns the rolling `rain_6h` window.
  - The receiver should keep its own window in RAM, optionally checkpointed to flash. WROOM flash is rated "100,000" program/erase cycles ([WROOM-32E/UE datasheet Table 17](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)), so a write every 15 minutes is fine with a wear-levelled filesystem but not to a single fixed sector.

---

## Open questions for design

1. **Mount location.** Where is the nearest spot with open sky (no eaves, trees or wall turbulence), and how far is it from the controller by a cable route? This one answer largely decides wired vs wireless.
2. **Wired vs wireless.** Is a cable run acceptable (trenching, wall penetration, crossing a driveway)? If wired, how long is it, and is it above ground or buried?
3. **Gauge choice.** Misol WH-SP-RG (cheap, proven, 0.3 mm, closure duration unverified) or a printed design (finer resolution possible; licence matters if STLs go in the repo)?
4. **Replace or supplement `rain_6h`.** Does the local gauge replace Open-Meteo's `past_hours` rain outright? Or take `max(gauge, api)`? Or override the API only when the gauge reports more than the API? How should the controller behave when the gauge is offline or stale?
5. **Trusting the gauge in winter.** Should counts be ignored below freezing (snow, ice, delayed melt), given irrigation is probably off then anyway?
6. **Persistence across reboots on the garage ESP32.** Keep the rolling window only in RAM, in RTC memory (survives soft reset, not power loss), or checkpoint to flash, and how often? What happens to a storm's total if the controller loses 24VAC mid-storm?
7. **Surge protection depth.** Is series R + TVS + shield enough, or is the run long or exposed enough to justify an optocoupler with an isolated supply? Where is the nearest real earth ground at the controller?
8. **Calibration constant.** Use the vendor's 0.3 mm/tip, or do a dynamic pour calibration on the actual unit? Where does the constant live (config file vs code)?
9. **Lockout value.** What closure duration and bounce does the real Misol unit produce? Measure before fixing the 200–500 ms lockout.
10. **If wireless: radio channel.** Can the router's 2.4 GHz channel be pinned? If not, should the node scan channels, or should the receiver advertise its channel?
11. **If wireless: heartbeat interval and stale-data rule.** How often should the node report, and after how long without a heartbeat does the controller stop trusting the gauge?
12. **If wireless: security model.** Use ESP-NOW with an LMK and a single allowed peer MAC. Where does the key live, given `secrets.py` is off-limits to tooling and the repo is public?
13. **If wireless: battery chemistry.** Primary L91 (no charging, best cold) or LFP + solar (needs a charger with a cold cutoff)? What is the acceptable swap interval?
14. **Firmware split.** Same codebase with a role flag, or a separate minimal image for the outdoor node (frozen `_boot.py` for the fast-boot numbers)?

---

## Sources

**MicroPython (primary)**
- espnow module: https://docs.micropython.org/en/latest/library/espnow.html
- esp32 module (wake_on_ext0/ext1, ULP, PCNT): https://docs.micropython.org/en/latest/library/esp32.html
- machine.Counter: https://docs.micropython.org/en/latest/library/machine.Counter.html (v1.26: https://docs.micropython.org/en/v1.26.0/library/machine.Counter.html)
- machine.Pin (irq): https://docs.micropython.org/en/latest/library/machine.Pin.html
- Writing interrupt handlers: https://docs.micropython.org/en/latest/reference/isr_rules.html
- machine.RTC (memory): https://docs.micropython.org/en/latest/library/machine.RTC.html
- ESP32 quick reference (RTC pins, deep sleep): https://docs.micropython.org/en/latest/esp32/quickref.html
- micropython-esp32-ulp: https://github.com/micropython/micropython-esp32-ulp
- micropython-lib LoRa drivers: https://github.com/micropython/micropython-lib/tree/master/micropython/lora
- v1.26 release tags (Debian mirror): https://salsa.debian.org/yangfl-guest/micropython/-/tags
- espnow images / first release v1.21.0: https://github.com/glenn20/micropython-espnow-images

**Espressif (primary)**
- ESP32 Series datasheet: https://documentation.espressif.com/esp32_datasheet_en.pdf
- ESP32-WROOM-32E/UE datasheet: https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf
- ESP-IDF sleep modes: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/sleep_modes.html
- ESP-IDF ESP-NOW: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html
- ESP-IDF ULP FSM pulse-count example: https://github.com/espressif/esp-idf/tree/master/examples/system/ulp/ulp_fsm/ulp
- Hardware design guidelines (PCB layout / antenna): https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html
- ESP-NOW outdoor range (partner content, unverified by Espressif): https://developer.espressif.com/blog/esp-now-for-outdoor-applications/

**Batteries and chargers (manufacturer datasheets)**
- Panasonic NCR18650B: https://files.batteryjunction.com/frontend/files/Panasonic-NCR18650B.pdf
- Energizer L91: https://files.batteryjunction.com/frontend/files/L91.pdf
- Energizer E91: https://courses.egr.uh.edu/ECE/ECE2100/Archive/Spring%202024%20Honors/E91.pdf
- Power-Sonic IFR26650PC (LiFePO4): https://cdn.power-sonic.com/documents/PSL-FP-IFR26650PC-Data-Sheet.pdf
- Bioenno 26650 LFP: https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs
- TP4056 (UMW): https://datasheet.lcsc.com/lcsc/2311091738_UMW-Youtai-Semiconductor-Co---Ltd--TP4056_C725790.pdf ; TP4056: https://github.com/komakow/SensorsProject/files/3936079/TP4056.pdf
- CN3791 (LCSC): https://www.lcsc.com/product-detail/C154992.html
- CN3801 (LCSC): https://www.lcsc.com/product-detail/C840499.html
- CN3058E board: https://www.electronics-lab.com/news/lifepo4-charger-board-based-on-cn3058e/
- TI bq24650: https://www.ti.com.cn/document-viewer/cn/BQ24650/datasheet/35-ZHCSKO6B
- Microchip MCP1700: https://www.radiolocman.com/datasheet/pdf.html?di=128895

**Reed switches, protection, gauges (manufacturer docs)**
- Standex-Meder ORD2220: https://static.datasheets.com/doc/25715103-standex-meder-electronics-ord-2220-20-30-ds.pdf
- Comus GC1513: https://www.farnell.com/datasheets/1807497.pdf
- Oki ORT551-1: https://www.mouser.lt/datasheet/3/466/1/4502900000e.pdf
- TI SLVAFQ4 GPIO ESD: https://ti.com/lit/pdf/slvafq4
- TI E2E GPIO surge thread: https://e2e.ti.com/support/interface-group/interface/f/interface-forum/1288521/tsd05c-gpio-protection-of-mcu-with-5-5v-amr
- DigiKey MCU I/O protection: https://www.digikey.at/en/articles/protecting-mcu-io-lines-from-esd-and-other-transients
- Campbell SunSentry surge note: https://s.campbellsci.com/documents/us/technical-papers/sunsentry-surge-protection.pdf
- Campbell 036/038 junction box: https://s.campbellsci.com/documents/es/manuals/036-038.pdf
- Campbell CR350 lightning: https://help.campbellsci.com/CR350/shared/installation/lightning.htm
- Campbell CR10 grounding: https://www.manualowl.com/m/Campbell%20Scientific/CR10/Manual/421452?page=198
- Davis cable sheet: https://cdn.shopify.com/s/files/1/0515/5992/3873/files/7876_4_Conductor_Cable_Rev_F_web_0ede7862-494b-4353-bd6b-4bad2f440c07.pdf
- Davis rain collector manual: https://www.manualslib.com/manual/227021/Davis-Instruments-Rain-Collector.html
- Davis sensor maintenance: https://cdn.shopify.com/s/files/1/0515/5992/3873/files/Doc_Sensor-Maintenance.pdf
- Rain Bird RSD-BEx: https://store.rainbird.com/timers/rain-moisture-sensors/rsdbex-rain-sensor-with-bracket.html ; guide: https://rainbird.com/media/4720
- Misol WH-SP-RG retailer listing: https://store.mectronica.it/en/rain/1326-rain-gauge-sensor-measures-pulse-rain-volume-for-weather-stations-and-arduino-5051151024334.html
- SparkFun weather meter (Core Electronics): https://core-electronics.com.au/weather-meter-kit.html.md
- Hach tipping gauge listing: https://usabluebook.com/flow-metering/open-channel-flow-meters/hach-tipping-rain-gauge-with-reed-switch-18-7-l-x-14103
- rtl_433: https://github.com/merbanan/rtl_433 ; rtl_433_ESP: https://github.com/NorthernMan54/rtl_433_ESP
- Ecowitt WH40 support article: https://ecowitt-subgqs9hhsx.gorgias.help/en-US/ws69wh40-rain-gauge-accuracy-issue-check-listing-564827 ; WH40BH manual: https://manuals.plus/asin/B0DT5ZP2ZQ

**Measurement science**
- Lanza et al., WMO TECO 2006 (TBR intensity errors): https://old.wmo.int/extranet/pages/prog/www/IMOP/publications/IOM-94-TECO2006/P3(15)_Lanza_Italy.pdf
- Lanza et al., WMO TECO 2006 (wind and other errors): https://old.wmo.int/extranet/pages/prog/www/IMOP/publications/IOM-94-TECO2006/3(4)_Lanza_Italy.pdf

**Filament (manufacturer knowledge base)**
- Prusa ASA: https://help.prusa3d.com/article/asa_1809
- Prusa PETG: https://help.prusa3d.com/article/petg_2059
- Prusa PLA: https://help.prusa3d.com/article/pla_2062

**Printable designs**
- Printables 130513: https://www.printables.com/model/130513
- Printables 61720: https://www.printables.com/model/61720
- Printables 386114: https://www.printables.com/model/386114
- Printables 1199963: https://www.printables.com/model/1199963
- Printables 184037: https://www.printables.com/model/184037
- Printables 247135: https://www.printables.com/model/247135
- Printables 557375: https://www.printables.com/model/557375
- Printables 847431: https://www.printables.com/model/847431
- Printables 224326: https://www.printables.com/model/224326 ; Thingiverse 2849562: https://www.thingiverse.com/thing:2849562
- SS4H-RG: https://smartsolutions4home.com/ss4h-rg-rain-gauge/
- atmoCatcher: https://github.com/aldotapia/atmoCatcher
- BoSL rain gauge: https://boslwiki.com.au/wiki/Rain_gauge
- MakerWorld 1366151: https://makerworld.com/en/models/1366151-rain-gauge (licence mirror: https://3dgo.app/models/makerworld/1366151)
- MakerWorld 1451114: https://makerworld.com/models/1451114

**Practitioner reports (labelled as such in text)**
- ESP32 MicroPython energy measurements: https://github.com/glenn20/upy-esp32-experiments
- DevKitC V4 deep sleep: https://lucidar.me/en/esp32/power-consumption-of-esp32-devkitc-v4/
- FireBeetle DFR0478 deep sleep: https://lucidar.me/en/esp32/power-consumption-of-esp32-firebeetle-dfr0478/
- Deep sleep datasheet vs measured (secondary): https://hubble.com/community/guides/esp32-deep-sleep-current-what-the-datasheet-says-vs-what-you-ll-actually-measure/
- ESP32 internal pull-up measured: https://esp32.com/viewtopic.php?p=22096
- PCNT in deep sleep: https://esp32.com/viewtopic.php?p=5931
- ESP32 LR mode reports: https://esp32.com/viewtopic.php?p=127565
- ESP-NOW channel mismatch (MicroPython forum): https://forum.micropython.org/viewtopic.php?p=58187
- ESP-NOW channel hopping: https://dev.to/gtanyware/channel-hopping-on-the-esp32-c3-with-esp-now-2led
- ESP32 rain gauge wiring/debounce guide: https://esp32.co.uk/tipping-bucket-rain-gauge-esp32-esphome-home-assistant/
- DIY Zigbee rain gauge thread: https://community.home-assistant.io/t/diy-zigbee-rain-gauge/255379/1
- LiFePO4 direct to ESP32: https://community.home-assistant.io/t/how-to-power-an-esp32-supermini-board-directly-from-a-lifepo4-battery/975202 ; https://hackaday.io/project/167245/log/167362-power-system-battery-charger
- ESD placement (secondary, quoting SiLabs AN376): https://5f7b802fd56539458d03e297--blog-mbedded-ninja.netlify.app/electronics/circuit-design/esd-protection
- IP code summary (secondary): https://www.e-switch.com/blog/all-about-ip-ratings-ingress-protection/
