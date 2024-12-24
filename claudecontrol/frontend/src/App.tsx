import React, { useEffect, useState, useRef } from 'react';
import { ChevronUp, ChevronDown, RotateCcw, RotateCw } from 'lucide-react';

interface SensorData {
  type: 'sensor';
  distance: number;
}

interface VideoData {
  type: 'video';
  size: number;
  data: string;
}

type WebSocketData = SensorData | VideoData;

const RobotControl = () => {
  const [distance, setDistance] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    wsRef.current = new WebSocket('ws://192.168.137.70:8765');

    wsRef.current.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    wsRef.current.onclose = () => {
      setIsConnected(false);
      setError('Connection lost. Please refresh to reconnect.');
    };

    wsRef.current.onerror = () => {
      setError('Failed to connect to robot. Please check if the server is running.');
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data: WebSocketData = JSON.parse(event.data);
        
        if (data.type === 'sensor') {
          setDistance(Math.round(data.distance * 10) / 10);
        } else if (data.type === 'video') {
          if (videoRef.current) {
            const bytes = new Uint8Array(
              data.data.match(/.{1,2}/g)?.map(byte => parseInt(byte, 16)) || []
            );
            const blob = new Blob([bytes], { type: 'image/jpeg' });
            videoRef.current.src = URL.createObjectURL(blob);
          }
        }
      } catch (e) {
        console.error('Error processing message:', e);
      }
    };

    return () => {
      wsRef.current?.close();
    };
  }, []);

  const sendCommand = (command: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'command',
        command: command
      }));
    }
  };

  return (
    <div className="h-screen w-screen bg-gray-100 flex flex-col">
      {/* Status Bar */}
      <div className="bg-white shadow-sm py-2 px-4 flex items-center space-x-4">
        <div className="flex items-center">
          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="ml-2 text-sm text-gray-600">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {error && (
          <div className="text-red-500 text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex">
        {/* Video Feed */}
        <div className="w-2/3 p-4 bg-gray-900">
          <div className="h-full flex items-center justify-center">
            <img
              ref={videoRef}
              alt="Robot camera feed"
              className="max-h-full max-w-full object-contain"
            />
          </div>
        </div>

        {/* Controls Section */}
        <div className="w-1/3 p-6 flex flex-col">
          {/* Control Pad */}
          <div className="flex-1 flex items-center justify-center">
                          <div className="w-96">
              <div className="grid grid-cols-3 gap-4">
                {/* Forward */}
                <div className="col-start-2">
                  <button
                    onClick={() => sendCommand('forward')}
                    className="w-full aspect-square bg-blue-500 hover:bg-blue-600 text-white rounded-lg flex items-center justify-center shadow-lg"
                  >
                    <ChevronUp size={48} />
                  </button>
                </div>

                {/* Left */}
                <div className="col-start-1 row-start-2">
                  <button
                    onClick={() => sendCommand('rot_left')}
                    className="w-full aspect-square bg-blue-500 hover:bg-blue-600 text-white rounded-lg flex items-center justify-center shadow-lg"
                  >
                    <RotateCcw size={48} />
                  </button>
                </div>

                {/* Right */}
                <div className="col-start-3 row-start-2">
                  <button
                    onClick={() => sendCommand('rot_right')}
                    className="w-full aspect-square bg-blue-500 hover:bg-blue-600 text-white rounded-lg flex items-center justify-center shadow-lg"
                  >
                    <RotateCw size={48} />
                  </button>
                </div>

                {/* Reverse */}
                <div className="col-start-2 row-start-3">
                  <button
                    onClick={() => sendCommand('reverse')}
                    className="w-full aspect-square bg-blue-500 hover:bg-blue-600 text-white rounded-lg flex items-center justify-center shadow-lg"
                  >
                    <ChevronDown size={48} />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Sensor Reading */}
          <div className="mt-8 bg-white rounded-lg shadow-lg p-6 text-center">
            <h2 className="text-lg font-semibold text-gray-700 mb-2">Distance</h2>
            <div className="text-4xl font-bold text-blue-600">
              {distance !== null ? `${distance} cm` : '--'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RobotControl;