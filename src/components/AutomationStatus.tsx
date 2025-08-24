import React from 'react';
import { AutomationStatus } from '../types';
import { 
  PlayIcon, 
  StopIcon, 
  ClockIcon, 
  ExclamationTriangleIcon 
} from '@heroicons/react/24/outline';

interface AutomationStatusProps {
  status: AutomationStatus;
  onToggleAutomation: () => void;
}

export const AutomationStatusComponent: React.FC<AutomationStatusProps> = ({
  status,
  onToggleAutomation
}) => {
  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Automation Status
        </h2>
        <button
          onClick={onToggleAutomation}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium ${
            status.running
              ? 'bg-red-100 text-red-700 hover:bg-red-200'
              : 'bg-green-100 text-green-700 hover:bg-green-200'
          }`}
        >
          {status.running ? (
            <>
              <StopIcon className="h-4 w-4" />
              <span>Stop</span>
            </>
          ) : (
            <>
              <PlayIcon className="h-4 w-4" />
              <span>Start</span>
            </>
          )}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="flex items-center">
            <div className={`w-3 h-3 rounded-full mr-2 ${
              status.running ? 'bg-green-400 animate-pulse' : 'bg-gray-400'
            }`} />
            <span className="text-sm font-medium text-gray-900">
              {status.running ? 'Running' : 'Stopped'}
            </span>
          </div>
          <p className="text-xs text-gray-600 mt-1">
            Loop #{status.loop_count}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <div className="flex items-center">
            <ClockIcon className="h-4 w-4 text-gray-600 mr-2" />
            <span className="text-sm font-medium text-gray-900">
              Last Cycle
            </span>
          </div>
          <p className="text-xs text-gray-600 mt-1">
            {status.last_cycle_duration || 'N/A'}
          </p>
        </div>
      </div>

      {status.current_task && (
        <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
          <div className="flex items-center mb-2">
            <PlayIcon className="h-4 w-4 text-blue-600 mr-2" />
            <span className="text-sm font-medium text-blue-900">
              Current Task
            </span>
          </div>
          <p className="text-sm text-blue-800">{status.current_task.title}</p>
          <p className="text-xs text-blue-600 mt-1">
            Status: {status.current_task.status.replace('_', ' ')}
          </p>
        </div>
      )}

      {status.error_count > 0 && (
        <div className="mt-4 p-4 bg-red-50 rounded-lg border border-red-200">
          <div className="flex items-center">
            <ExclamationTriangleIcon className="h-4 w-4 text-red-600 mr-2" />
            <span className="text-sm font-medium text-red-900">
              {status.error_count} Error{status.error_count !== 1 ? 's' : ''}
            </span>
          </div>
          <p className="text-xs text-red-600 mt-1">
            Check logs for details
          </p>
        </div>
      )}
    </div>
  );
};