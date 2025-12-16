# Revised Thermostat Code – All TODOs Completed to Meet Requirements
# ---------------------------------------------------------------
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

# I2C + Sensor
i2c = board.I2C()
thSensor = adafruit_ahtx0.AHTx0(i2c)

# UART
ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# LEDs
redLight = PWMLED(18)
blueLight = PWMLED(23)


class ManagedDisplay():

    ## manages the 16x2 LED display using GPIO pins, handles cleaned up / initilization / update
    def __init__(self):
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)
        self.lcd_columns = 16
        self.lcd_rows = 2
        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs, self.lcd_en,
            self.lcd_d4, self.lcd_d5,
            self.lcd_d6, self.lcd_d7,
            self.lcd_columns, self.lcd_rows
        )
        self.lcd.clear()

    def cleanupDisplay(self):
        #clear the dispplay and release GPIO Resources
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()

    def updateScreen(self, line1, line2):
        #add text two the screen
        self.lcd.home()
        self.lcd.message = f"{line1[:16]:<16}\n{line2[:16]:<16}"


screen = ManagedDisplay() #create LCD instacnce


class TemperatureMachine(StateMachine):
    #stat machine controlling off / heat / cool

    #define states
    off = State(initial=True)
    heat = State()
    cool = State()

    #default setpoint value
    setPoint = 72

    cycle = off.to(heat) | heat.to(cool) | cool.to(off)

    def on_enter_heat(self):
        self.updateLights()
        if DEBUG:
            print('* Changing state to heat')

    def on_exit_heat(self):
        redLight.off()

    def on_enter_cool(self):
        self.updateLights()
        if DEBUG:
            print('* Changing state to cool')

    def on_exit_cool(self):
        blueLight.off()

    def on_enter_off(self):
        redLight.off()
        blueLight.off()
        if DEBUG:
            print('* Changing state to off')

    def processTempStateButton(self):
        if DEBUG:
            print('Cycling Temperature State')
        self.cycle()
        self.updateLights()

    def processTempIncButton(self):
        self.setPoint += 1
        if DEBUG:
            print(f'Increasing Set Point -> {self.setPoint}')
        self.updateLights()

    def processTempDecButton(self):
        self.setPoint -= 1
        if DEBUG:
            print(f'Decreasing Set Point -> {self.setPoint}')
        self.updateLights()

    #updated LED behavior based on state and temp
    def updateLights(self):
        temp = floor(self.getFahrenheit())
        redLight.off()
        blueLight.off()

        if self.current_state == self.heat:
            if temp < self.setPoint:
                redLight.pulse()
            else:
                redLight.on()

        elif self.current_state == self.cool:
            if temp > self.setPoint:
                blueLight.pulse()
            else:
                blueLight.on()

    def run(self):
        Thread(target=self.manageMyDisplay).start()

    def getFahrenheit(self):
        return ((9 / 5) * thSensor.temperature) + 32

    def setupSerialOutput(self):
        state = self.current_state.id
        temp = round(self.getFahrenheit(), 1)
        output = f"{state},{temp},{self.setPoint}\n"
        return output

    endDisplay = False

    def manageMyDisplay(self):
        counter = 1
        altCounter = 1
        while not self.endDisplay:
            now = datetime.now()
            lcd_line_1 = now.strftime('%m/%d %H:%M') + '\n'

            if altCounter < 6:
                temp = round(self.getFahrenheit(), 1)
                lcd_line_2 = f"Temp: {temp}F"
                altCounter += 1
            else:
                lcd_line_2 = f"{self.current_state.id.upper()} {self.setPoint}F"
                altCounter += 1
                if altCounter >= 11:
                    self.updateLights()
                    altCounter = 1

            screen.updateScreen(lcd_line_1, lcd_line_2)


            if counter % 30 == 0:
                ser.write(self.setupSerialOutput().encode())
                counter = 1
            else:
                counter += 1

            sleep(1)

        screen.cleanupDisplay()


# State machine
tsm = TemperatureMachine()
tsm.run()

# Buttons
greenButton = Button(24)
greenButton.when_pressed = tsm.processTempStateButton

redButton = Button(25)
redButton.when_pressed = tsm.processTempIncButton

blueButton = Button(12)
blueButton.when_pressed = tsm.processTempDecButton


repeat = True
while repeat:
    try:
        sleep(30)
    except KeyboardInterrupt:
        print('Cleaning up. Exiting...')
        repeat = False
        tsm.endDisplay = True
        sleep(1)
