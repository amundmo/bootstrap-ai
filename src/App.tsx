import React, { useState, useEffect } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { TaskList } from './components/TaskList';
import { AutomationStatusComponent } from './components/AutomationStatus';
import { useWebSocket } from './hooks/useWebSocket';
import { taskAPI, chatAPI, automationAPI } from './services/api';
import { Task, ChatMessage, AutomationStatus } from './types';
import { Cog6ToothIcon } from '@heroicons/react/24/outline';

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus>({
    running: false,
    loop_count: 0,
    error_count: 0
  });
  const [isProcessingMessage, setIsProcessingMessage] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const { subscribe, unsubscribe } = useWebSocket();

  useEffect(() => {
    // Load initial data
    loadTasks();
    loadChatMessages();
    loadAutomationStatus();

    // Subscribe to WebSocket events
    const handleTaskCreated = (task: Task) => {
      setTasks(prev => [...prev, task]);
    };

    const handleTaskUpdated = (task: Task) => {
      setTasks(prev => prev.map(t => t.id === task.id ? task : t));
    };

    const handleTaskDeleted = (data: { task_id: string }) => {
      setTasks(prev => prev.filter(t => t.id !== data.task_id));
    };

    const handleChatMessage = (message: ChatMessage) => {
      setChatMessages(prev => [...prev, message]);
    };

    const handleStatusUpdate = (status: AutomationStatus) => {
      setAutomationStatus(status);
    };

    const handleAutomationStarted = (status: AutomationStatus) => {
      setAutomationStatus(status);
    };

    const handleAutomationStopped = (status: AutomationStatus) => {
      setAutomationStatus(status);
    };

    subscribe('task_created', handleTaskCreated);
    subscribe('task_updated', handleTaskUpdated);
    subscribe('task_deleted', handleTaskDeleted);
    subscribe('chat_message', handleChatMessage);
    subscribe('status_update', handleStatusUpdate);
    subscribe('automation_started', handleAutomationStarted);
    subscribe('automation_stopped', handleAutomationStopped);

    return () => {
      unsubscribe('task_created', handleTaskCreated);
      unsubscribe('task_updated', handleTaskUpdated);
      unsubscribe('task_deleted', handleTaskDeleted);
      unsubscribe('chat_message', handleChatMessage);
      unsubscribe('status_update', handleStatusUpdate);
      unsubscribe('automation_started', handleAutomationStarted);
      unsubscribe('automation_stopped', handleAutomationStopped);
    };
  }, [subscribe, unsubscribe]);

  const loadTasks = async () => {
    try {
      const tasks = await taskAPI.getTasks();
      setTasks(tasks);
    } catch (error) {
      console.error('Failed to load tasks:', error);
    }
  };

  const loadChatMessages = async () => {
    try {
      const messages = await chatAPI.getMessages();
      setChatMessages(messages);
    } catch (error) {
      console.error('Failed to load chat messages:', error);
    }
  };

  const loadAutomationStatus = async () => {
    try {
      const status = await automationAPI.getStatus();
      setAutomationStatus(status);
    } catch (error) {
      console.error('Failed to load automation status:', error);
    }
  };

  const handleSendMessage = async (message: string) => {
    setIsProcessingMessage(true);
    try {
      await chatAPI.createTaskFromMessage({ message });
    } catch (error) {
      console.error('Failed to send message:', error);
    } finally {
      setIsProcessingMessage(false);
    }
  };

  const handleToggleAutomation = async () => {
    try {
      if (automationStatus.running) {
        await automationAPI.stop();
      } else {
        await automationAPI.start();
      }
    } catch (error) {
      console.error('Failed to toggle automation:', error);
    }
  };

  const handleTaskClick = (task: Task) => {
    setSelectedTask(task);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Cog6ToothIcon className="h-8 w-8 text-primary-600 mr-3" />
              <h1 className="text-xl font-semibold text-gray-900">
                Claude Code Automation
              </h1>
            </div>
            <div className="text-sm text-gray-500">
              {tasks.length} task{tasks.length !== 1 ? 's' : ''} • 
              {chatMessages.filter(m => m.type === 'user').length} conversation{chatMessages.filter(m => m.type === 'user').length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Chat Interface */}
          <div className="lg:col-span-2">
            <ChatInterface
              messages={chatMessages}
              onSendMessage={handleSendMessage}
              isProcessing={isProcessingMessage}
            />
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Automation Status */}
            <AutomationStatusComponent
              status={automationStatus}
              onToggleAutomation={handleToggleAutomation}
            />

            {/* Task List */}
            <div className="bg-white rounded-lg shadow-lg p-6">
              <TaskList
                tasks={tasks}
                onTaskClick={handleTaskClick}
              />
            </div>
          </div>
        </div>
      </main>

      {/* Task Detail Modal */}
      {selectedTask && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">
                  Task Details
                </h2>
                <button
                  onClick={() => setSelectedTask(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <h3 className="font-medium text-gray-900 mb-2">Title</h3>
                  <p className="text-gray-700">{selectedTask.title}</p>
                </div>

                <div>
                  <h3 className="font-medium text-gray-900 mb-2">Description</h3>
                  <p className="text-gray-700">{selectedTask.description}</p>
                </div>

                {selectedTask.requirements.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-900 mb-2">Requirements</h3>
                    <ul className="list-disc list-inside text-gray-700 space-y-1">
                      {selectedTask.requirements.map((req, index) => (
                        <li key={index}>{req}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {selectedTask.acceptance_criteria.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-900 mb-2">Acceptance Criteria</h3>
                    <ul className="list-disc list-inside text-gray-700 space-y-1">
                      {selectedTask.acceptance_criteria.map((criteria, index) => (
                        <li key={index}>{criteria}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex items-center space-x-4 text-sm text-gray-500">
                  <span>Status: <span className="font-medium">{selectedTask.status}</span></span>
                  <span>Priority: <span className="font-medium">{selectedTask.priority}</span></span>
                  <span>Created: {new Date(selectedTask.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;