import React from 'react';
import { Task } from '../types';
import { 
  ClockIcon, 
  CheckCircleIcon, 
  ExclamationTriangleIcon, 
  PlayIcon,
  XCircleIcon 
} from '@heroicons/react/24/outline';

interface TaskListProps {
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
}

export const TaskList: React.FC<TaskListProps> = ({ tasks, onTaskClick }) => {
  const getStatusIcon = (status: Task['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'in_progress':
        return <PlayIcon className="h-5 w-5 text-blue-500" />;
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />;
      default:
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusBadge = (status: Task['status']) => {
    const baseClasses = "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium";
    switch (status) {
      case 'completed':
        return `${baseClasses} bg-green-100 text-green-800`;
      case 'in_progress':
        return `${baseClasses} bg-blue-100 text-blue-800`;
      case 'failed':
        return `${baseClasses} bg-red-100 text-red-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  const getPriorityColor = (priority: Task['priority']) => {
    switch (priority) {
      case 'critical':
        return 'border-l-red-500';
      case 'high':
        return 'border-l-orange-500';
      case 'medium':
        return 'border-l-blue-500';
      default:
        return 'border-l-gray-300';
    }
  };

  if (tasks.length === 0) {
    return (
      <div className="text-center py-12">
        <ClockIcon className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          No tasks yet
        </h3>
        <p className="text-gray-600">
          Start a conversation to create your first automation task.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">
          Automation Tasks ({tasks.length})
        </h2>
      </div>

      <div className="space-y-3">
        {tasks.map((task) => (
          <div
            key={task.id}
            onClick={() => onTaskClick?.(task)}
            className={`bg-white border-l-4 ${getPriorityColor(task.priority)} rounded-lg shadow-sm p-4 hover:shadow-md transition-shadow cursor-pointer`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start space-x-3 flex-1">
                {getStatusIcon(task.status)}
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-medium text-gray-900 truncate">
                    {task.title}
                  </h3>
                  <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                    {task.description}
                  </p>
                  
                  {task.requirements.length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs text-gray-500 mb-1">Requirements:</p>
                      <ul className="text-xs text-gray-600 space-y-1">
                        {task.requirements.slice(0, 2).map((req, index) => (
                          <li key={index}>• {req}</li>
                        ))}
                        {task.requirements.length > 2 && (
                          <li className="text-gray-500">
                            + {task.requirements.length - 2} more
                          </li>
                        )}
                      </ul>
                    </div>
                  )}

                  <div className="flex items-center space-x-4 mt-3 text-xs text-gray-500">
                    <span>
                      Created {new Date(task.created_at).toLocaleDateString()}
                    </span>
                    {task.duration && (
                      <span>Duration: {task.duration}</span>
                    )}
                    {task.iterations && (
                      <span>Iterations: {task.iterations}</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex flex-col items-end space-y-2">
                <span className={getStatusBadge(task.status)}>
                  {task.status.replace('_', ' ')}
                </span>
                <span className="text-xs text-gray-500 capitalize">
                  {task.priority} priority
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};