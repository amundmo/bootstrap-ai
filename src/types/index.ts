export interface Task {
  id: string;
  title: string;
  description: string;
  requirements: string[];
  acceptance_criteria: string[];
  priority: 'low' | 'medium' | 'high' | 'critical';
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  duration?: string;
  iterations?: number;
}

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  task_id?: string;
}

export interface AutomationStatus {
  running: boolean;
  current_task?: Task;
  loop_count: number;
  last_cycle_duration?: string;
  error_count: number;
}

export interface TaskCreationRequest {
  message: string;
  context?: string;
}

export interface TaskCreationResponse {
  task: Task;
  explanation: string;
}