import axios from 'axios';
import { Task, TaskCreationRequest, ChatMessage, AutomationStatus } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8009/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const taskAPI = {
  // Get all tasks
  getTasks: async (): Promise<Task[]> => {
    const response = await api.get('/tasks');
    return response.data.tasks;
  },

  // Get specific task
  getTask: async (taskId: string): Promise<Task> => {
    const response = await api.get(`/tasks/${taskId}`);
    return response.data.task;
  },

  // Create new task
  createTask: async (taskData: Partial<Task>): Promise<Task> => {
    const response = await api.post('/tasks', taskData);
    return response.data.task;
  },

  // Update task
  updateTask: async (taskId: string, updates: Partial<Task>): Promise<Task> => {
    const response = await api.patch(`/tasks/${taskId}`, updates);
    return response.data.task;
  },

  // Delete task
  deleteTask: async (taskId: string): Promise<void> => {
    await api.delete(`/tasks/${taskId}`);
  },
};

export const chatAPI = {
  // Create task from chat message
  createTaskFromMessage: async (request: TaskCreationRequest): Promise<{
    task: Task;
    message: ChatMessage;
    explanation: string;
  }> => {
    const response = await api.post('/chat/create-task', request);
    return response.data;
  },

  // Get chat message history
  getMessages: async (): Promise<ChatMessage[]> => {
    const response = await api.get('/chat/messages');
    return response.data.messages;
  },
};

export const automationAPI = {
  // Get automation status
  getStatus: async (): Promise<AutomationStatus> => {
    const response = await api.get('/status');
    return response.data.status;
  },

  // Start automation
  start: async (): Promise<{ message: string }> => {
    const response = await api.post('/automation/start');
    return response.data;
  },

  // Stop automation
  stop: async (): Promise<{ message: string }> => {
    const response = await api.post('/automation/stop');
    return response.data;
  },
};

// WebSocket connection
export class WebSocketService {
  private ws: WebSocket | null = null;
  private listeners: { [key: string]: ((data: any) => void)[] } = {};
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  connect() {
    const wsUrl = process.env.REACT_APP_WS_URL || 'ws://localhost:8009/ws';
    
    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.emit('connected', null);
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.emit(message.type, message.data);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.emit('disconnected', null);
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.emit('error', error);
      };
    } catch (error) {
      console.error('Failed to connect to WebSocket:', error);
      this.attemptReconnect();
    }
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => {
        console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        this.connect();
      }, this.reconnectDelay * this.reconnectAttempts);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.listeners = {};
  }

  on(event: string, callback: (data: any) => void) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }

  off(event: string, callback: (data: any) => void) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }
  }

  private emit(event: string, data: any) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => callback(data));
    }
  }

  send(message: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }
}

export const webSocketService = new WebSocketService();