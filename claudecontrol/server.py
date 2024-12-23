import asyncio
import json
import struct
from gpiozero import DistanceSensor
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from picamera2.outputs import StreamingOutput
from picamera2.encoders import Quality
import websockets

class RobotServer:
    def __init__(self):
        # Initialize ultrasonic sensor
        self.sensor = DistanceSensor(echo=22, trigger=27, max_distance=3)
        
        # Initialize camera
        self.camera = Picamera2()
        self.camera.configure(self.camera.create_video_configuration(main={"size": (400, 300)}))
        self.output = StreamingOutput()
        self.encoder = JpegEncoder(q=90)
        
        # Control flags
        self.is_running = True
        
    async def send_sensor_data(self, websocket):
        """Send ultrasonic sensor readings periodically"""
        while self.is_running:
            try:
                distance_cm = self.sensor.distance * 100
                await websocket.send(json.dumps({
                    "type": "sensor",
                    "distance": distance_cm
                }))
                await asyncio.sleep(0.1)  # Send sensor data every 100ms
            except websockets.exceptions.ConnectionClosed:
                break
            
    async def send_video_feed(self, websocket):
        """Stream video feed over websocket"""
        self.camera.start_recording(self.encoder, FileOutput(self.output), quality=Quality.VERY_HIGH)
        
        while self.is_running:
            try:
                with self.output.condition:
                    self.output.condition.wait()
                    frame = self.output.frame
                
                # Send frame size followed by frame data
                frame_data = {
                    "type": "video",
                    "size": len(frame),
                    "data": frame.hex()  # Convert bytes to hex string for JSON
                }
                await websocket.send(json.dumps(frame_data))
                
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                print(f"Video streaming error: {e}")
                break
                
        self.camera.stop_recording()
    
    def handle_command(self, command):
        """Process movement commands"""
        if command == "forward":
            # INSERT FORWARD MOVEMENT CODE HERE
            pass
        
        elif command == "reverse":
            # INSERT REVERSE MOVEMENT CODE HERE
            pass
        
        elif command == "rot_right":
            # INSERT ROTATION RIGHT CODE HERE
            pass
        
        elif command == "rot_left":
            # INSERT ROTATION LEFT CODE HERE
            pass
    
    async def handle_client(self, websocket, path):
        """Handle individual client connection"""
        print(f"Client connected from {websocket.remote_address}")
        
        # Start sensor and video feed tasks
        sensor_task = asyncio.create_task(self.send_sensor_data(websocket))
        video_task = asyncio.create_task(self.send_video_feed(websocket))
        
        try:
            # Handle incoming commands
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "command":
                        self.handle_command(data.get("command"))
                except json.JSONDecodeError:
                    print(f"Invalid message format: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected")
        finally:
            # Clean up tasks
            sensor_task.cancel()
            video_task.cancel()
            try:
                await sensor_task
                await video_task
            except asyncio.CancelledError:
                pass

    async def start_server(self, host="0.0.0.0", port=8765):
        """Start the WebSocket server"""
        async with websockets.serve(self.handle_client, host, port):
            print(f"Server started on ws://{host}:{port}")
            await asyncio.Future()  # Run forever

if __name__ == "__main__":
    server = RobotServer()
    asyncio.run(server.start_server())