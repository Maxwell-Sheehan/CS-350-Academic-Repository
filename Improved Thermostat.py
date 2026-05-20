from time import sleep
from datetime import datetime
from statemachine import StateMachine, State
import board
import adafruit_ahtx0
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd
import serial
from gpiozero import Button, PWMLED
from threading import Thread
from math import floor

DEBUG = True

# -----------------------------
# Hardware Setup
# -----------------------------
i2c = board.I2C()
thSensor = adafruit_ahtx0.AHTx0(i2c)

ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

redLight = PWMLED(18)
blueLight = PWMLED(23)


# -----------------------------
# LCD Display Manager
# -----------------------------
class ManagedDisplay:

    def __init__(self):
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs,
            self.lcd_en,
            self.lcd_d4,
            self.lcd_d5,
            self.lcd_d6,
            self.lcd_d7,
            16,
            2
        )

        self.lcd.clear()

        # cache previous display output
        self.prev_line1 = ""
        self.prev_line2 = ""

    def updateScreen(self, line1, line2):

        # only update LCD if text changed
        if line1 != self.prev_line1 or line2 != self.prev_line2:
            self.lcd.home()
            self.lcd.message = f"{line1[:16]:<16}\n{line2[:16]:<16}"

            self.prev_line1 = line1
            self.prev_line2 = line2

    def cleanupDisplay(self):
        self.lcd.clear()

        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()


screen = ManagedDisplay()


# -----------------------------
# Thermostat State Machine
# -----------------------------
class TemperatureMachine(StateMachine):

    off = State(initial=True)
    heat = State()
    cool = State()

    setPoint = 72

    cycle = off.to(heat) | heat.to(cool) | cool.to(off)

    endDisplay = False

    def __init__(self):
        super().__init__()

        # cached temp value
        self.currentTemp = 0

        # dictionary state lookup (O(1))
        self.stateHandlers = {
            "heat": self.handleHeat,
            "cool": self.handleCool,
            "off": self.handleOff
        }

    # -----------------------------
    # Temperature Reading
    # -----------------------------
    def updateTemperature(self):
        self.currentTemp = ((9 / 5) * thSensor.temperature) + 32

    # -----------------------------
    # State Handlers
    # -----------------------------
    def handleHeat(self):

        redLight.off()
        blueLight.off()

        if self.currentTemp < self.setPoint:
            redLight.pulse()
        else:
            redLight.on()

    def handleCool(self):

        redLight.off()
        blueLight.off()

        if self.currentTemp > self.setPoint:
            blueLight.pulse()
        else:
            blueLight.on()

    def handleOff(self):
        redLight.off()
        blueLight.off()

    # -----------------------------
    # LED State Update
    # -----------------------------
    def updateLights(self):

        # dictionary lookup instead of if/elif chain
        handler = self.stateHandlers[self.current_state.id]
        handler()

    # -----------------------------
    # State Transitions
    # -----------------------------
    def on_enter_heat(self):
        self.updateLights()

        if DEBUG:
            print("* Changed state to HEAT")

    def on_enter_cool(self):
        self.updateLights()

        if DEBUG:
            print("* Changed state to COOL")

    def on_enter_off(self):
        self.updateLights()

        if DEBUG:
            print("* Changed state to OFF")

    # -----------------------------
    # Button Actions
    # -----------------------------
    def processTempStateButton(self):

        self.cycle()
        self.updateLights()

        if DEBUG:
            print("Cycling thermostat mode")

    def processTempIncButton(self):

        self.setPoint += 1
        self.updateLights()

        if DEBUG:
            print(f"Setpoint increased -> {self.setPoint}")

    def processTempDecButton(self):

        self.setPoint -= 1
        self.updateLights()

        if DEBUG:
            print(f"Setpoint decreased -> {self.setPoint}")

    # -----------------------------
    # Serial Output
    # -----------------------------
    def setupSerialOutput(self):

        state = self.current_state.id
        temp = round(self.currentTemp, 1)

        return f"{state},{temp},{self.setPoint}\n"

    # -----------------------------
    # Main Display Thread
    # -----------------------------
    def manageMyDisplay(self):

        counter = 0
        altCounter = 0

        while not self.endDisplay:

            # ONE sensor read per loop
            self.updateTemperature()

            now = datetime.now()

            line1 = now.strftime("%m/%d %H:%M")

            # alternate display content
            if altCounter < 5:
                line2 = f"Temp: {round(self.currentTemp,1)}F"
            else:
                line2 = f"{self.current_state.id.upper()} {self.setPoint}F"

            altCounter += 1

            if altCounter >= 10:
                altCounter = 0

            # only updates LCD if changed
            screen.updateScreen(line1, line2)

            # serial output every 30 seconds
            counter += 1

            if counter >= 30:
                ser.write(self.setupSerialOutput().encode())
                counter = 0

            sleep(1)

        screen.cleanupDisplay()

    # -----------------------------
    # Start Background Thread
    # -----------------------------
    def run(self):
        Thread(target=self.manageMyDisplay).start()


# -----------------------------
# Start Thermostat
# -----------------------------
tsm = TemperatureMachine()
tsm.run()

# -----------------------------
# Button Setup
# -----------------------------
greenButton = Button(24)
greenButton.when_pressed = tsm.processTempStateButton

redButton = Button(25)
redButton.when_pressed = tsm.processTempIncButton

blueButton = Button(12)
blueButton.when_pressed = tsm.processTempDecButton


# -----------------------------
# Main Program Loop
# -----------------------------
running = True

while running:

    try:
        sleep(30)

    except KeyboardInterrupt:

        print("Cleaning up and exiting...")

        running = False
        tsm.endDisplay = True

        sleep(1)
