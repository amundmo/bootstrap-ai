import { useEffect, useRef, useCallback } from 'react';
import { webSocketService } from '../services/api';

export const useWebSocket = () => {
  const isConnected = useRef(false);
  const eventListeners = useRef<{ [key: string]: ((data: any) => void)[] }>({});

  useEffect(() => {
    // Connect to WebSocket
    webSocketService.connect();

    const handleConnect = () => {
      isConnected.current = true;
      console.log('WebSocket connected');
    };

    const handleDisconnect = () => {
      isConnected.current = false;
      console.log('WebSocket disconnected');
    };

    webSocketService.on('connected', handleConnect);
    webSocketService.on('disconnected', handleDisconnect);

    return () => {
      webSocketService.off('connected', handleConnect);
      webSocketService.off('disconnected', handleDisconnect);
      webSocketService.disconnect();
    };
  }, []);

  const subscribe = useCallback((event: string, callback: (data: any) => void) => {
    webSocketService.on(event, callback);
    
    // Keep track of listeners for cleanup
    if (!eventListeners.current[event]) {
      eventListeners.current[event] = [];
    }
    eventListeners.current[event].push(callback);
  }, []);

  const unsubscribe = useCallback((event: string, callback: (data: any) => void) => {
    webSocketService.off(event, callback);
    
    // Remove from tracked listeners
    if (eventListeners.current[event]) {
      eventListeners.current[event] = eventListeners.current[event].filter(cb => cb !== callback);
    }
  }, []);

  const send = useCallback((message: any) => {
    webSocketService.send(message);
  }, []);

  return {
    subscribe,
    unsubscribe,
    send,
    isConnected: isConnected.current
  };
};