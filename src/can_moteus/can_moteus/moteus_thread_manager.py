import asyncio
import threading

import moteus
from moteus.moteus import Result
from rclpy.node import Node

from lib.color_codes import ColorCodes, colorStr
from lib.configs import MoteusMotorConfig

from .moteus_motor import MoteusMotor


class MoteusThreadManager:
    CONNECTION_TIMEOUT_IN_SECONDS = 0.1
    GENERAL_TIMEOUT = 0.05

    """
    This creates a new thread called "moteus_thread" to run all
    of the asyncio methods required by the Moteus library
    """

    def __init__(self, ros_node: Node):
        self._id_to_moteus_motor: dict[int, MoteusMotor] = {}
        self._id_to_moteus_controller: dict[int, moteus.Controller] = {}  # Used by the thread
        self._ros_node = ros_node
        self._moteus_thread: threading.Thread | None = None
        self._should_moteus_thread_loop = True  # No thread safety, but it works lololol
        self._should_reconnect = True  # No thread safety, but it works lololol

    def addMotor(self, config: MoteusMotorConfig) -> None:
        """
        Adds a motor to the list to attempt to connect to it.
        """
        if self._moteus_thread is not None:
            self._ros_node.get_logger().error("Attempted to add motor after thread was started!")
            return

        # Create motor
        motor = MoteusMotor(config, self._ros_node)
        self._id_to_moteus_motor[config.can_id] = motor

    def start(self) -> None:
        """
        Starts a new thread. New motors cannot be added after this is called
        """

        self._moteus_thread = threading.Thread(
            target=self.threadEntry, name="moteus_thread", daemon=True
        )
        self._moteus_thread.start()

    def reconnectMotors(self) -> None:
        self._should_reconnect = True

    def terminateAllThreads(self) -> None:
        """
        Gracefully shuts down the motors by calling set_stop().
        Terminates the thread.
        Does not clean up this class
        """
        self._should_moteus_thread_loop = False
        if self._moteus_thread is not None:
            self._moteus_thread.join()

    def threadEntry(self) -> None:
        """
        The entry of the thread that launches the asyncio loop
        """
        self._ros_node.get_logger().info(colorStr("Moteus Thread Launched", ColorCodes.BLUE_OK))
        asyncio.run(self.startLoop())

    async def tryToShutdownMotor(self, can_id: int) -> None:
        self._ros_node.get_logger().info(
            colorStr(f"Unexpectedly trying to turn off motor: {can_id}", ColorCodes.WARNING_YELLOW)
        )

        try:
            await asyncio.wait_for(
                self._id_to_moteus_controller[can_id].set_stop(),
                timeout=self.GENERAL_TIMEOUT,
            )
            self._ros_node.get_logger().info(
                colorStr(f"Stopped motor: {can_id}", ColorCodes.GREEN_OK)
            )
        except asyncio.TimeoutError:
            self._ros_node.get_logger().info(
                colorStr(f'FAILED TO "set_stop" MOTOR. TIMED OUT {can_id}', ColorCodes.FAIL_RED)
            )
            del self._id_to_moteus_controller[can_id]
            del self._id_to_moteus_motor[can_id]
        except RuntimeError as error:
            self._ros_node.get_logger().info(colorStr(str(error), ColorCodes.FAIL_RED))
            del self._id_to_moteus_controller[can_id]
            del self._id_to_moteus_motor[can_id]

    async def startLoop(self) -> None:
        """
        The main loop of the whole system.
        Reads/sends data to/from the Moteus controllers.

        This can handle the following edge cases
        ----------
        1) Motor faults
            A) set_stop() the motor or
            B) Remove the motor from the list of motors
        2) CAN Bus disconnection
            A) Remove the motor from the list of motors
        3) Reconnect to Moteus Controllers


        """
        # Connect the motor for the first time
        await self.connectToMoteusControllers()

        while self._should_moteus_thread_loop:
            if self._should_reconnect:
                await self.connectToMoteusControllers()

            # Go through each Moteus Controller to send data
            for can_id, controller in self._id_to_moteus_controller.copy().items():
                motor = self._id_to_moteus_motor[can_id]

                try:
                    # Check for faults
                    result_from_moteus: Result = await asyncio.wait_for(
                        controller.query(), self.GENERAL_TIMEOUT
                    )

                    if result_from_moteus.values[moteus.Register.FAULT] != 0:
                        self._ros_node.get_logger().info(
                            colorStr(
                                f"FAULT CODE: {result_from_moteus.values[moteus.Register.FAULT]} "
                                f"FOR {motor.config.can_id}",
                                ColorCodes.FAIL_RED,
                            )
                        )
                        await self.tryToShutdownMotor(can_id)
                        continue

                    if motor.run_settings.set_stop is True:
                        await asyncio.wait_for(controller.set_stop(), self.GENERAL_TIMEOUT)

                    else:
                        result_from_moteus = await asyncio.wait_for(
                            controller.set_position(
                                position=motor.run_settings.position,
                                velocity=motor.run_settings.velocity,
                                feedforward_torque=motor.run_settings.feedforward_torque,
                                kp_scale=motor.run_settings.kp_scale,
                                kd_scale=motor.run_settings.kd_scale,
                                maximum_torque=motor.run_settings.max_torque,
                                watchdog_timeout=motor.run_settings.watchdog_timeout,
                                velocity_limit=motor.run_settings.velocity_limit,
                                accel_limit=motor.run_settings.accel_limit,
                                fixed_voltage_override=motor.run_settings.fixed_voltage_override,
                                query=True,
                            ),
                            self.GENERAL_TIMEOUT,
                        )

                    motor.publishData(result_from_moteus)

                except asyncio.TimeoutError:
                    self._ros_node.get_logger().info(
                        colorStr(
                            f"FAILED TO SEND/READ DATA TO MOTEUS MOTOR: {can_id} "
                            + "CAN-FD bus disconnected?",
                            ColorCodes.FAIL_RED,
                        ),
                    )
                    del self._id_to_moteus_controller[can_id]
                    del self._id_to_moteus_motor[can_id]

            await asyncio.sleep(0.02)

        # When we exit the while loop, via ctrl-c, we set_stop() all the motors
        # Watch out for the arm
        for can_id, controller in self._id_to_moteus_controller.items():
            await controller.set_stop()

    async def connectToMoteusControllers(self) -> None:
        """
        Connect to the Moteus motors.
        There is a timeout until we give up trying to connect
        """
        self._id_to_moteus_controller = {}
        self._should_reconnect = False

        for can_id, motor in self._id_to_moteus_motor.items():
            qr = moteus.QueryResolution()
            qr.power = moteus.F32
            qr.q_current = moteus.F32
            qr.d_current = moteus.F32
            controller = moteus.Controller(motor.config.can_id, query_resolution=qr)

            try:
                # Reset the controller
                self._ros_node.get_logger().info("Connecting to motor with id: " + str(can_id))
                await asyncio.wait_for(
                    controller.query(), timeout=self.CONNECTION_TIMEOUT_IN_SECONDS
                )  # Try to get data, if timeout then cannot connect
                self._id_to_moteus_controller[can_id] = controller
                await controller.set_stop()
                self._ros_node.get_logger().info(
                    colorStr(
                        f"Moteus motor controller connected: {motor.config.can_id}",
                        ColorCodes.GREEN_OK,
                    )
                )

            except asyncio.TimeoutError:
                self._ros_node.get_logger().info(
                    colorStr(
                        "FAILED TO CONNECT TO MOTEUS CONTROLLER WITH CANID "
                        + str(motor.config.can_id),
                        ColorCodes.FAIL_RED,
                    )
                )
                continue
            except RuntimeError as error:
                self._ros_node.get_logger().info(
                    colorStr(
                        "ERROR WHEN set_stop() IS CALLED. MOST LIKELY CANNOT FIND CANBUS",
                        ColorCodes.FAIL_RED,
                    )
                )
                self._ros_node.get_logger().info(
                    colorStr(str(error.with_traceback(None)), ColorCodes.FAIL_RED)
                )
                continue

            stream = moteus.Stream(controller, verbose=True)
            try:
                await asyncio.wait_for(
                    stream.command("conf load".encode(encoding="utf-8")),
                    timeout=self.CONNECTION_TIMEOUT_IN_SECONDS,
                )
                for key, value in (motor.config.config or {}).items():
                    if key == "id.id":
                        continue
                    await asyncio.wait_for(
                        stream.command(f"conf set {key} {value}".encode(encoding="utf-8")),
                        timeout=self.CONNECTION_TIMEOUT_IN_SECONDS,
                    )
            except asyncio.TimeoutError:
                self._ros_node.get_logger().info(
                    colorStr(
                        "FAILED TO SET CONFIG ON MOTOR: " + str(motor.config.can_id),
                        ColorCodes.FAIL_RED,
                    )
                )
            except RuntimeError as error:
                self._ros_node.get_logger().info(
                    colorStr("ERROR WHEN SETTING CONFIG.", ColorCodes.FAIL_RED)
                )
                self._ros_node.get_logger().info(
                    colorStr(str(error.with_traceback(None)), ColorCodes.FAIL_RED)
                )
