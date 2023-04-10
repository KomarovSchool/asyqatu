#!/usr/bin/env pybricks-micropython
from pybricks.hubs import EV3Brick
from pybricks.ev3devices import (Motor, TouchSensor, ColorSensor,
                                 InfraredSensor, UltrasonicSensor, GyroSensor)
from pybricks.parameters import Port, Stop, Direction, Button, Color
from pybricks.tools import wait, StopWatch, DataLog
from pybricks.robotics import DriveBase
from pybricks.media.ev3dev import SoundFile, ImageFile, Font
import sys

if sys.implementation.name == 'cpython':
    import asyncio as uasyncio
else:
    import uasyncio
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


PROPORTIONAL_GAIN = 1.2
BLACK = 9
WHITE = 85
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
        self.release_motor.run_until_stalled(-100, duty_limit=40)

    def release(self):
        self.release_motor.run_until_stalled(100, duty_limit=40)

    def set_tension(self, value):
        if self.min_tension <= value <= self.max_tension:
            self.tension = value

    def shoot(self):
        start_angle = self.tension_motor.angle()
        self.tension_motor.run_until_stalled(100, duty_limit=self.tension, then=Stop.HOLD)
        self.release()
        self.tension_motor.run_target(300, start_angle)
        self.lock()


class Display:
    delta = 1

    def __init__(self, catapult):
        self.catapult = catapult
        self.ev3 = EV3Brick()

    def startup(self):
        self.ev3.screen.set_font(Font("Lucida", 48))
        self.update()
    
    def update(self):
        self.ev3.screen.clear()
        self.ev3.screen.draw_text(60, 50, str(self.catapult.tension))

    def increase(self):
        self.catapult.set_tension(self.catapult.tension + self.delta)
        self.update()


    def decrease(self):
        self.catapult.set_tension(self.catapult.tension - self.delta)
        self.update()

    def loop(self):
        if Button.UP in self.ev3.buttons.pressed():
            self.increase()
        elif Button.DOWN in self.ev3.buttons.pressed():
            self.decrease()
        elif Button.CENTER in self.ev3.buttons.pressed():
            self.catapult.shoot()


class DummySensor:
    def color(self):
        return "Dummy"
    
    def reflection(self):
        return "Dummy"


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

        self.datalog = DataLog("mode", "left_reflection", "middle_color", "right_reflection", "gyro_angle")

    def startup(self):
        self.catapult.startup()
        self.display.startup()

    async def init_routine(self):
        while self.left_color_sensor.color() != Color.GREEN:
            await uasyncio.sleep(0)

    async def start_routine(self):
        while self.left_color_sensor.color() == Color.GREEN:
            self.drive_speed = 100
            self.turn_rate = 0
            await uasyncio.sleep(0)

    def update_speed_turn_rate(self, backwards=False):
        deviation = self.right_color_sensor.reflection() - BW_THRESHOLD
        k = -1 if backwards else 1
        self.turn_rate = PROPORTIONAL_GAIN * deviation * k

    async def walk_along_line_forward(self):
        while self.left_color_sensor.color() == Color.WHITE:
            self.update_speed_turn_rate()
            await uasyncio.sleep(0)

    async def throw_routine(self):
        self.drive_speed = 0
        self.turn_rate = 0
        await uasyncio.sleep(0.2)
        self.catapult.set_tension(70)
        self.catapult.shoot()

    async def walk_along_line_backwards(self):
        while self.left_color_sensor.color() == Color.WHITE:
            self.update_speed_turn_rate(backwards=True)
        self.drive_speed = 0
        self.turn_rate = 0

    async def manage_drive(self):
        while True:
            if self.drive_speed == 0:
                self.drivebase.stop()
            else:
                self.drivebase.drive(self.drive_speed, self.turn_rate)
            await uasyncio.sleep(0.01)

    async def run(self):
        await self.init_routine()
        await self.start_routine()
        await self.walk_along_line_forward()
        await self.throw_routine()
        await self.walk_along_line_backwards()



    def log(self):
        self.datalog.log((
            self.mode,
            self.left_color_sensor.color(),
            self.right_color_sensor.reflection(),
            self.gyro_sensor.angle()
        ))
        await uasyncio.sleep(0.1)


player = Player()
player.startup()
tasks = [
    player.manage_drive(),
    player.log(),
    player.run()
]


loop = uasyncio.get_event_loop()
loop.create_task(player.manage_drive())
loop.create_task(player.log())
loop.run_until_complete(player.run())