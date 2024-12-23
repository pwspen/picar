import asyncio
import json
import struct
import io
import logging
import traceback
import time
from threading import Condition, Lock
from gpiozero import DistanceSensor
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from picamera2.encoders import Quality
import websockets
from Motor import Motor

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('robot_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()
        self.last_write_time = 0
        self.write_count = 0
        self.lock = Lock()

    def write(self, buf):
        try:
            with self.lock:
                self.write_count += 1
                current_time = time.time()  # Use time.time() instead of asyncio.get_event_loop().time()
                
                if self.last_write_time:
                    time_diff = current_time - self.last_write_time
                    if time_diff > 1.0:
                        logger.warning(f"Long frame interval: {time_diff:.2f}s")
                
                self.last_write_time = current_time

            with self.condition:
                self.frame = buf
                self.condition.notify_all()
                
            if self.write_count % 100 == 0:
                logger.debug(f"Frames written: {self.write_count}")
                
        except Exception as e:
            logger.error(f"Error in StreamingOutput.write: {e}")
            logger.error(traceback.format_exc())

class RobotServer:
    def __init__(self):
        try:
            logger.info("Initializing RobotServer...")
            
            # Initialize ultrasonic sensor with error handling
            try:
                self.sensor = DistanceSensor(echo=22, trigger=27, max_distance=3)
                logger.info("Ultrasonic sensor initialized")
            except Exception as e:
                logger.error(f"Failed to initialize ultrasonic sensor: {e}")
                raise
            
            # Initialize camera with error handling
            try:
                self.camera = Picamera2()
                self.camera.configure(self.camera.create_video_configuration(main={"size": (400, 300)}))
                self.output = StreamingOutput()
                self.encoder = JpegEncoder(q=90)
                logger.info("Camera initialized")
            except Exception as e:
                logger.error(f"Failed to initialize camera: {e}")
                raise
            
            # Control flags
            self.is_running = True
            self.connected_clients = set()
            self.motor = Motor()
            logger.info("RobotServer initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize RobotServer: {e}")
            logger.error(traceback.format_exc())
            raise

    async def forward(self):
        try:
            logger.debug("Moving forward")
            self.motor.setMotorModel(2000,2000,2000,2000)
            await self.finish(dur=1)
        except Exception as e:
            logger.error(f"Error in forward movement: {e}")

    async def reverse(self):
        try:
            logger.debug("Moving reverse")
            self.motor.setMotorModel(-2000, -2000, -2000, -2000)
            await self.finish(dur=1)
        except Exception as e:
            logger.error(f"Error in reverse movement: {e}")

    async def rot_right(self):
        try:
            logger.debug("Rotating right")
            self.motor.setMotorModel(2000, 2000, -2000, -2000)
            await self.finish(dur=0.4)
        except Exception as e:
            logger.error(f"Error in right rotation: {e}")

    async def rot_left(self):
        try:
            logger.debug("Rotating left")
            self.motor.setMotorModel(-2000, -2000, 2000, 2000)
            await self.finish(dur=0.4)
        except Exception as e:
            logger.error(f"Error in left rotation: {e}")

    async def finish(self, dur):
        try:
            await asyncio.sleep(dur)
            self.motor.setMotorModel(0,0,0,0)
        except Exception as e:
            logger.error(f"Error in finish movement: {e}")

    async def send_sensor_data(self, websocket):
        """Send ultrasonic sensor readings periodically"""
        logger.info(f"Starting sensor data stream for {websocket.remote_address}")
        readings_count = 0
        
        while self.is_running and websocket in self.connected_clients:
            try:
                distance_cm = self.sensor.distance * 100
                await websocket.send(json.dumps({
                    "type": "sensor",
                    "distance": distance_cm
                }))
                
                readings_count += 1
                if readings_count % 100 == 0:  # Log every 100 readings
                    logger.debug(f"Sent {readings_count} sensor readings")
                    
                await asyncio.sleep(0.1)
                
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Sensor data connection closed for {websocket.remote_address}")
                break
            except Exception as e:
                logger.error(f"Error sending sensor data: {e}")
                logger.error(traceback.format_exc())
                break
                
        logger.info(f"Sensor data stream ended for {websocket.remote_address}")
            
    async def send_video_feed(self, websocket):
        """Stream video feed over websocket"""
        logger.info(f"Starting video stream for {websocket.remote_address}")
        frames_sent = 0
        
        try:
            self.camera.start_recording(self.encoder, FileOutput(self.output), quality=Quality.VERY_HIGH)
            logger.info("Camera recording started")
            
            frame_wait = 1/2 # 2 fps

            while self.is_running and websocket in self.connected_clients:
                try:
                    with self.output.condition:
                        # Add timeout to prevent indefinite waiting
                        if not self.output.condition.wait(timeout=5.0):
                            logger.warning("Timeout waiting for frame")
                            continue
                        
                        frame = self.output.frame
                    
                    if frame is None:
                        logger.warning("Received null frame")
                        continue
                        
                    # Send frame size followed by frame data
                    frame_data = {
                        "type": "video",
                        "size": len(frame),
                        "data": frame.hex()  # Convert bytes to hex string for JSON
                    }
                    await websocket.send(json.dumps(frame_data))
                    
                    await asyncio.sleep(frame_wait)

                    frames_sent += 1
                    if frames_sent % 100 == 0:  # Log every 100 frames
                        logger.debug(f"Sent {frames_sent} frames")
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"Video connection closed for {websocket.remote_address}")
                    break
                except Exception as e:
                    logger.error(f"Error in video streaming: {e}")
                    logger.error(traceback.format_exc())
                    # Don't break here - try to continue streaming
                    await asyncio.sleep(1)  # Add delay before retry
                    
        except Exception as e:
            logger.error(f"Fatal error in video feed: {e}")
            logger.error(traceback.format_exc())
        finally:
            try:
                self.camera.stop_recording()
                logger.info("Camera recording stopped")
            except Exception as e:
                logger.error(f"Error stopping camera: {e}")
    
    def handle_command(self, command):
        """Process movement commands"""
        try:
            logger.debug(f"Received command: {command}")
            
            if command == "forward":
                asyncio.create_task(self.forward())
            elif command == "reverse":
                asyncio.create_task(self.reverse())
            elif command == "rot_right":
                asyncio.create_task(self.rot_right())
            elif command == "rot_left":
                asyncio.create_task(self.rot_left())
            else:
                logger.warning(f"Unknown command received: {command}")
                
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
    
    async def handle_client(self, websocket):
        """Handle individual client connection"""
        client_address = websocket.remote_address
        logger.info(f"Client connected from {client_address}")
        
        self.connected_clients.add(websocket)
        
        try:
            # Start sensor and video feed tasks
            sensor_task = asyncio.create_task(self.send_sensor_data(websocket))
            video_task = asyncio.create_task(self.send_video_feed(websocket))
            
            # Handle incoming commands
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "command":
                        self.handle_command(data.get("command"))
                except json.JSONDecodeError:
                    logger.error(f"Invalid message format: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_address} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
            logger.error(traceback.format_exc())
        finally:
            self.connected_clients.remove(websocket)
            # Clean up tasks
            sensor_task.cancel()
            video_task.cancel()
            try:
                await asyncio.gather(sensor_task, video_task, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            logger.info(f"Cleaned up connection for {client_address}")

    async def start_server(self, host="0.0.0.0", port=8765):
        """Start the WebSocket server"""
        try:
            logger.info(f"Starting server on ws://{host}:{port}")
            async with websockets.serve(self.handle_client, host, port):
                logger.info("Server started successfully")
                await asyncio.Future()  # Run forever
        except Exception as e:
            logger.error(f"Fatal error starting server: {e}")
            logger.error(traceback.format_exc())
            raise

def cleanup_gpio():
    """Clean up all GPIO resources"""
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
        logger.info("GPIO cleanup completed")
    except Exception as e:
        logger.error(f"Error during GPIO cleanup: {e}")

if __name__ == "__main__":
    try:
        # Cleanup any existing GPIO connections first
        cleanup_gpio()
        
        server = RobotServer()
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Always cleanup on exit
        cleanup_gpio()