#!/usr/bin/env pybricks-micropython
from pybricks.hubs import EV3Brick
from pybricks.ev3devices import (Motor, TouchSensor, ColorSensor,
                                 InfraredSensor, UltrasonicSensor, GyroSensor)
from pybricks.parameters import Port, Stop, Direction, Button, Color
from pybricks.tools import wait, StopWatch, DataLog
from pybricks.robotics import DriveBase
from pybricks.media.ev3dev import SoundFile, ImageFile, Font
import sys
import time

if sys.implementation.name == 'cpython':
    import asyncio as uasyncio
    from collections import namedtuple
else:
    import uasyncio
    from ucollections import namedtuple
# This program requires LEGO EV3 MicroPython v2.0 or higher.
# Click "Open user guide" on the EV3 extension tab for more information.


# Create your objects here.
ev3 = EV3Brick()

# Write your program here.
ev3.speaker.beep()

CATAPULT_DEFAULT_POWER = 70
TENSION_PORT = Port.B
RELEASE_PORT = Port.C

LEFT_WHEEL_PORT = Port.A
RIGHT_WHEEL_PORT = Port.D

LEFT_SENSOR_PORT = Port.S3
RIGHT_SENSOR_PORT = Port.S1
# MIDDLE_SENSOR_PORT = Port.S3
GYRO_SENSOR_PORT = Port.S4

AXLE_TRACK = 145
# AXLE_TRACK = 175
WHEEL_DIAMETER = 56

PROPORTIONAL_GAIN = 0.5
BLACK = 4
WHITE = 38
BW_THRESHOLD = (BLACK + WHITE) / 2


class Catapult:
    min_tension = 40
    max_tension = 100

    def __init__(self, tension_port, release_port):
        self.tension_motor = Motor(tension_port)
        self.release_motor = Motor(release_port)
        self.tension = CATAPULT_DEFAULT_POWER

    def startup(self):
        self.lock()

    def lock(self):
        self.release_motor.run_until_stalled(-500, duty_limit=40)

    def release(self):
        self.release_motor.run_until_stalled(500, duty_limit=40)

    def set_tension(self, value):
        if self.min_tension <= value <= self.max_tension:
            self.tension = value

    def shoot(self):
        start_angle = self.tension_motor.angle()
        self.tension_motor.run_until_stalled(100, duty_limit=self.tension, then=Stop.HOLD)
        self.release()
        self.tension_motor.run_target(300, start_angle)
        self.lock()


DI_BLACK_LEVEL = 0
DI_WHITE_LEVEL = 1
DI_THRESHOLD = 2

Setting = namedtuple("Setting", ("name", "min", "max"))


class MeasurementScreen:
    def __init__(self, screen, color_sensor):
        self.screen = screen
        self.color_sensor = color_sensor

    def update(self):
        reflection = self.color_sensor.reflection()
        self.screen.clear()
        self.screen.draw_text(50, 50, "{}".format(reflection))

    def process_input(self):
        while True:
            if Button.CENTER in ev3.buttons.pressed():
                break
            self.update()
            wait(150)


class SettingsPage:
    def __init__(self, screen):
        self.screen = screen
        self.current_item = 0
        self.black_level = BLACK
        self.white_level = WHITE
        self.threshold = BW_THRESHOLD
        self.settings = [
            [Setting("Black", 0, 100), BLACK,],
            [Setting("White", 0, 100), WHITE,],
            [Setting("Threshold", 0, 100), BW_THRESHOLD,],
            [Setting("Tension", 40, 100), CATAPULT_DEFAULT_POWER],
            [Setting("Asyq", 1, 5), 3],
        ]
        self.update()

    def update(self):
        self.screen.clear()
        for i, (setting, value) in enumerate(self.settings):
            if self.current_item == i:
                self.screen.draw_text(5, 20 + 20 * i, ">")
            self.screen.draw_text(20, 20 + 20 * i, "{}: {}".format(setting.name, value))

    def process_input(self):
        while True:
            if Button.UP in ev3.buttons.pressed():
                self.current_item = (self.current_item - 1) % len(self.settings)
            elif Button.DOWN in ev3.buttons.pressed():
                self.current_item = (self.current_item + 1) % len(self.settings)
            elif Button.LEFT in ev3.buttons.pressed():
                setting, value = self.settings[self.current_item]
                self.settings[self.current_item][1] = min(max(setting.min, value - 1), setting.max)
            elif Button.RIGHT in ev3.buttons.pressed():
                setting, value = self.settings[self.current_item]
                self.settings[self.current_item][1] = min(max(setting.min, value + 1), setting.max)
            elif Button.CENTER in ev3.buttons.pressed():
                break
            else:
                continue
            self.update()
            wait(150)


class Display:
    delta = 1

    def __init__(self, catapult):
        self.catapult = catapult
        self.ev3 = EV3Brick()
        self.settings_page = SettingsPage(self.ev3.screen)
        self.measurement_page = MeasurementScreen(self.ev3.screen, ColorSensor(RIGHT_SENSOR_PORT))

    def startup(self):
        self.ev3.screen.set_font(Font("Lucida", 18))
        #self.measurement_page.process_input()
        #self.settings_page.process_input()

    def increase(self):
        self.catapult.set_tension(self.catapult.tension + self.delta)

    def decrease(self):
        self.catapult.set_tension(self.catapult.tension - self.delta)

    def loop(self):
        if Button.UP in self.ev3.buttons.pressed():
            self.increase()
        elif Button.DOWN in self.ev3.buttons.pressed():
            self.decrease()
        elif Button.CENTER in self.ev3.buttons.pressed():
            self.catapult.shoot()


class Player:
    MODE_START = 0
    MODE_WALK_ALONG_LINE = 1
    MODE_THROW_POSITION = 2
    MODE_RETURN = 3
    MODE_FINISH = 4

    def __init__(self):
        self.catapult = Catapult(TENSION_PORT, RELEASE_PORT)
        self.display = Display(self.catapult)
        self.drivebase = DriveBase(
            Motor(LEFT_WHEEL_PORT),
            Motor(RIGHT_WHEEL_PORT),
            WHEEL_DIAMETER,
            AXLE_TRACK
        )
        self.left_color_sensor = ColorSensor(LEFT_SENSOR_PORT)
        self.right_color_sensor = ColorSensor(RIGHT_SENSOR_PORT)
        self.gyro_sensor = GyroSensor(GYRO_SENSOR_PORT)
        self.mode = self.MODE_START
        self.drive_speed = 0
        self.turn_rate = 0
        self.drive_speed_factor = 1
        self.walk_along_line_start = time.time()

        self.datalog = DataLog(
            "left_color",
            "right_reflection",
            "gyro_angle",
            "turn_rate"
        )

    def startup(self):
        self.catapult.startup()
        # self.display.startup()

    async def init_routine(self):
        print("Init start")
        while self.left_color_sensor.color() != Color.GREEN:
            await uasyncio.sleep(0)
        print("Init end")

    async def start_routine(self):
        print("Start start")
        while self.left_color_sensor.color() == Color.GREEN:
            self.drive_speed = 100
            self.turn_rate = 0
            await uasyncio.sleep(0)
        print("Start end")

    def update_speed_turn_rate(self, backwards=False):
        if time.time() - self.walk_along_line_start > 10:
            self.drive_speed_factor = 0.5
        else:
            self.drive_speed_factor = 1
        deviation = self.right_color_sensor.reflection() - BW_THRESHOLD
        k = -0.25 if backwards else 1
        self.turn_rate = PROPORTIONAL_GAIN * deviation * k

    async def walk_along_line_forward(self):
        print("WALF start")
        self.walk_along_line_start = time.time()
        while self.left_color_sensor.color() != Color.RED:
            self.update_speed_turn_rate()
            await uasyncio.sleep(0.1)
        print("WALF end")

    async def throw_routine(self):
        print("Throw start")
        self.drive_speed = 0
        self.turn_rate = 0
        await uasyncio.sleep(0.2)
        self.catapult.set_tension(70)
        self.catapult.shoot()
        print("Throw end")

    async def walk_along_line_backwards(self):
        print("WALB start")
        self.drive_speed = -100
        self.turn_rate = 0
        self.walk_along_line_start = time.time()
        await uasyncio.sleep(0.1)
        print("WALB while color")
        while self.left_color_sensor.color() != Color.GREEN:
            self.update_speed_turn_rate(backwards=True)
            await uasyncio.sleep(0.1)
        self.drive_speed = 0
        self.turn_rate = 0
        print("WALB end")

    async def manage_drive(self):
        while True:
            if self.drive_speed == 0:
                self.drivebase.stop()
            else:
                self.drivebase.drive(self.drive_speed * self.drive_speed_factor, self.turn_rate)
            await uasyncio.sleep(0.01)

    async def run(self):
        await self.init_routine()
        await self.start_routine()
        await self.walk_along_line_forward()
        await self.throw_routine()
        await self.walk_along_line_backwards()

    def log(self):
        while True:
            self.datalog.log((
                self.left_color_sensor.color(),
                self.right_color_sensor.reflection(),
                self.gyro_sensor.angle(),
                self.turn_rate
            ))
            await uasyncio.sleep(0.1)

while Button.CENTER not in ev3.buttons.pressed():
    wait(50)
player = Player()
player.startup()
tasks = [
    player.manage_drive(),
    player.log(),
    player.run()
]

loop = uasyncio.get_event_loop()
loop.create_task(player.manage_drive())
#loop.create_task(player.log())
loop.run_until_complete(player.run())
