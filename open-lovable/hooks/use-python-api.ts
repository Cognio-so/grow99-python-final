/**
 * React Hook for Python Backend API
 * Provides easy-to-use React hooks for all Python backend operations
 */

import { useState, useCallback, useEffect } from 'react';
import { pythonApi } from '@/lib/python-api-client';

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

interface UseStreamingState {
  isStreaming: boolean;
  progress: any[];
  error: string | null;
  isComplete: boolean;
}

/**
 * Generic API hook
 */
export function useApi<T = any>() {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(async (apiCall: () => Promise<T>) => {
    setState({ data: null, loading: true, error: null });
    
    try {
      const result = await apiCall();
      setState({ data: result, loading: false, error: null });
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setState({ data: null, loading: false, error: errorMessage });
      throw error;
    }
  }, []);

  return { ...state, execute };
}

/**
 * Streaming API hook
 */
export function useStreamingApi() {
  const [state, setState] = useState<UseStreamingState>({
    isStreaming: false,
    progress: [],
    error: null,
    isComplete: false,
  });

  const execute = useCallback(async (
    apiCall: (options: any) => Promise<void>
  ) => {
    setState({
      isStreaming: true,
      progress: [],
      error: null,
      isComplete: false,
    });

    try {
      await apiCall({
        onProgress: (data: any) => {
          setState(prev => ({
            ...prev,
            progress: [...prev.progress, data],
          }));
        },
        onError: (error: string) => {
          setState(prev => ({
            ...prev,
            error,
            isStreaming: false,
          }));
        },
        onComplete: (data: any) => {
          setState(prev => ({
            ...prev,
            isStreaming: false,
            isComplete: true,
            progress: [...prev.progress, data],
          }));
        },
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setState(prev => ({
        ...prev,
        error: errorMessage,
        isStreaming: false,
      }));
    }
  }, []);

  const reset = useCallback(() => {
    setState({
      isStreaming: false,
      progress: [],
      error: null,
      isComplete: false,
    });
  }, []);

  return { ...state, execute, reset };
}

/**
 * Sandbox management hook
 */
export function useSandbox() {
  const { execute: executeApi, ...apiState } = useApi();
  
  const createSandbox = useCallback(() => {
    return executeApi(() => pythonApi.createAiSandbox());
  }, [executeApi]);

  const getSandboxStatus = useCallback(() => {
    return executeApi(() => pythonApi.getSandboxStatus());
  }, [executeApi]);

  const getSandboxFiles = useCallback(() => {
    return executeApi(() => pythonApi.getSandboxFiles());
  }, [executeApi]);

  const killSandbox = useCallback(() => {
    return executeApi(() => pythonApi.killSandbox());
  }, [executeApi]);

  const createZip = useCallback(() => {
    return executeApi(() => pythonApi.createZip());
  }, [executeApi]);

  return {
    ...apiState,
    createSandbox,
    getSandboxStatus,
    getSandboxFiles,
    killSandbox,
    createZip,
  };
}

/**
 * AI code generation hook
 */
export function useAiCodeGeneration() {
  const streamingApi = useStreamingApi();
  const { execute: executeApi } = useApi();

  const generateCode = useCallback((
    prompt: string,
    model: string,
    context: any,
    isEdit: boolean = false
  ) => {
    return streamingApi.execute(async (options) => {
      await pythonApi.generateAiCode(prompt, model, context, isEdit);
    });
  }, [streamingApi]);

  const applyCode = useCallback((
    response: string,
    isEdit: boolean = false,
    packages: string[] = [],
    sandboxId?: string
  ) => {
    return streamingApi.execute(async (options) => {
      await pythonApi.applyAiCode(response, isEdit, packages, sandboxId);
    });
  }, [streamingApi]);

  const analyzeEditIntent = useCallback((
    prompt: string,
    manifest: any,
    model: string
  ) => {
    return executeApi(() => pythonApi.analyzeEditIntent(prompt, manifest, model));
  }, [executeApi]);

  return {
    ...streamingApi,
    generateCode,
    applyCode,
    analyzeEditIntent,
  };
}

/**
 * Package management hook
 */
export function usePackages() {
  const streamingApi = useStreamingApi();

  const installPackages = useCallback((packages: string[]) => {
    return streamingApi.execute(async (options) => {
      await pythonApi.installPackages(packages, options);
    });
  }, [streamingApi]);

  const detectAndInstallPackages = useCallback((code: string) => {
    return streamingApi.execute(async (options) => {
      await pythonApi.detectAndInstallPackages(code, options);
    });
  }, [streamingApi]);

  return {
    ...streamingApi,
    installPackages,
    detectAndInstallPackages,
  };
}

/**
 * Conversation state hook
 */
export function useConversationState() {
  const { execute: executeApi, ...apiState } = useApi();

  const getState = useCallback(() => {
    return executeApi(() => pythonApi.getConversationState());
  }, [executeApi]);

  const updateState = useCallback((action: 'reset' | 'clear-old' | 'update', data?: any) => {
    return executeApi(() => pythonApi.updateConversationState(action, data));
  }, [executeApi]);

  const clearState = useCallback(() => {
    return executeApi(() => pythonApi.clearConversationState());
  }, [executeApi]);

  return {
    ...apiState,
    getState,
    updateState,
    clearState,
  };
}

/**
 * Vite operations hook
 */
export function useVite() {
  const { execute: executeApi, ...apiState } = useApi();

  const checkErrors = useCallback(() => {
    return executeApi(() => pythonApi.checkViteErrors());
  }, [executeApi]);

  const clearErrorsCache = useCallback(() => {
    return executeApi(() => pythonApi.clearViteErrorsCache());
  }, [executeApi]);

  const monitorLogs = useCallback(() => {
    return executeApi(() => pythonApi.monitorViteLogs());
  }, [executeApi]);

  const reportError = useCallback((error: string, file?: string, type?: string) => {
    return executeApi(() => pythonApi.reportViteError(error, file, type));
  }, [executeApi]);

  const restart = useCallback(() => {
    return executeApi(() => pythonApi.restartVite());
  }, [executeApi]);

  return {
    ...apiState,
    checkErrors,
    clearErrorsCache,
    monitorLogs,
    reportError,
    restart,
  };
}

/**
 * Web scraping hook
 */
export function useWebScraping() {
  const { execute: executeApi, ...apiState } = useApi();

  const scrapeScreenshot = useCallback((url: string) => {
    return executeApi(() => pythonApi.scrapeScreenshot(url));
  }, [executeApi]);

  const scrapeUrlEnhanced = useCallback((url: string) => {
    return executeApi(() => pythonApi.scrapeUrlEnhanced(url));
  }, [executeApi]);

  return {
    ...apiState,
    scrapeScreenshot,
    scrapeUrlEnhanced,
  };
}

/**
 * Backend health check hook
 */
export function useBackendHealth() {
  const [isHealthy, setIsHealthy] = useState<boolean | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      await pythonApi.healthCheck();
      setIsHealthy(true);
      setLastCheck(new Date());
    } catch (error) {
      setIsHealthy(false);
      setLastCheck(new Date());
    }
  }, []);

  // Auto-check health on mount
  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  return {
    isHealthy,
    lastCheck,
    checkHealth,
  };
}

