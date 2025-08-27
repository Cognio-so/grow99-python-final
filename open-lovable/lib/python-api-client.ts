/**
 * Enhanced Python Backend API Client
 * Handles all communication between Next.js frontend and Python FastAPI backend
 * Enhanced with better error handling, streaming, and connection management
 */

import { pythonBackendConfig } from '@/config/python-backend';

// Helper function to create the full API URL
const getApiUrl = (path: string) => {
  return `${pythonBackendConfig.baseUrl}${path}`;
};

// Enhanced error handling for API responses
// Enhanced error handling with auto-recreation
const handleApiError = async (response: Response, endpoint: string) => {
  console.error(`[PythonAPI] Error in ${endpoint}:`, response.status, response.statusText);
  
  try {
    const errorData = await response.json();
    console.error(`[PythonAPI] Error details:`, errorData);
    
    return {
      ok: false,
      error: errorData.error || errorData.detail || `HTTP ${response.status}`,
      status: response.status,
      ...errorData
    };
  } catch {
    return {
      ok: false,
      error: `HTTP ${response.status}: ${response.statusText}`,
      status: response.status
    };
  }
};
// Enhanced request wrapper with retry logic
const makeRequest = async (url: string, options: RequestInit = {}, retries = 2): Promise<Response> => {
  const requestOptions: RequestInit = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  };

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      console.log(`[PythonAPI] ${options.method || 'GET'} ${url} (attempt ${attempt + 1})`);
      
      const response = await fetch(url, requestOptions);
      
      if (response.ok) {
        return response;
      }
      
      // If it's a client error (4xx), don't retry
      if (response.status >= 400 && response.status < 500) {
        return response;
      }
      
      // For server errors (5xx), retry
      if (attempt < retries) {
        console.warn(`[PythonAPI] Retrying after error: ${response.status}`);
        await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
        continue;
      }
      
      return response;
    } catch (error) {
      console.error(`[PythonAPI] Network error on attempt ${attempt + 1}:`, error);
      
      if (attempt < retries) {
        await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
        continue;
      }
      
      throw error;
    }
  }
  
  throw new Error('Max retries exceeded');
};

// Enhanced streaming response handler
const handleStreamingResponse = async (
  response: Response,
  onProgress: (data: any) => void,
  onError: (error: string) => void
) => {
  if (!response.body) {
    onError('No response body available for streaming');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      
      // Process complete lines
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the incomplete line in buffer

      for (const line of lines) {
        if (line.trim() === '') continue;
        
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            onProgress(data);
          } catch {
            console.warn('[PythonAPI] Failed to parse SSE data:', line);
          }
        }
      }
    }
  } catch (error) {
    console.error('[PythonAPI] Streaming error:', error);
    onError(error instanceof Error ? error.message : 'Streaming failed');
  } finally {
    reader.releaseLock();
  }
};

// --- Enhanced API Methods ---

const getSandboxStatus = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/sandbox-status'));
    
    if (!response.ok) {
      return await handleApiError(response, 'getSandboxStatus');
    }
    
    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] getSandboxStatus error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Network error',
      active: false,
      healthy: false
    };
  }
};

const createAiSandbox = async () => {
  try {
    console.log('[PythonAPI] Creating AI sandbox...');
    const response = await makeRequest(getApiUrl('/api/create-ai-sandbox'), {
      method: 'POST',
    });

    if (!response.ok) {
      return await handleApiError(response, 'createAiSandbox');
    }

    const data = await response.json();
    console.log('[PythonAPI] Sandbox created successfully:', data);
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] createAiSandbox error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to create sandbox'
    };
  }
};

const generateAiCode = async (
  prompt: string,
  model: string,
  context: any,
  isEdit: boolean
): Promise<Response> => {
  console.log('[PythonAPI] Generating AI code...', { 
    promptLength: prompt.length, 
    model, 
    isEdit,
    contextKeys: Object.keys(context || {})
  });

  const makeGenerateRequest = async () => {
    return await makeRequest(getApiUrl('/api/generate-ai-code-stream'), {
      method: 'POST',
      body: JSON.stringify({ 
        prompt, 
        model, 
        context: context || {}, 
        isEdit: Boolean(isEdit)
      }),
    });
  };

  try {
    const response = await makeGenerateRequest();
    
   if (!response.ok) {
    // The backend now handles recreation, so we just return the stream or error directly.
    return response; 
}
    
    return response;
  } catch (error) {
    console.error('[PythonAPI] generateAiCode error:', error);
    throw error;
  }
};

const applyAiCode = async (
  code: string,
  isEdit: boolean,
  packages: string[],
  sandboxId: string | null | undefined
): Promise<Response> => {
  console.log('[PythonAPI] Applying AI code...');

  try {
    const response = await makeRequest(getApiUrl('/api/apply-ai-code-stream'), {
      method: 'POST',
      body: JSON.stringify({
        response: code,
        isEdit: Boolean(isEdit),
        packages: Array.isArray(packages) ? packages : [],
        sandboxId: sandboxId || null
      }),
    });
    
    // No more 404 handling needed here!
    return response;
  } catch (error) {
    console.error('[PythonAPI] applyAiCode error:', error);
    throw error;
  }
};
const installPackages = async (
  packages: string[],
  options?: { 
    onProgress?: (data: any) => void; 
    onError?: (error: string) => void;
    sandboxId?: string;
  }
): Promise<Response> => {
  console.log('[PythonAPI] Installing packages:', packages);

  try {
    const response = await makeRequest(getApiUrl('/api/install-packages'), {
      method: 'POST',
      body: JSON.stringify({ 
        packages,
        sandboxId: options?.sandboxId 
      }),
    });

    // Handle streaming response if callbacks provided
    if (options?.onProgress && response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
      handleStreamingResponse(
        response,
        options.onProgress,
        options.onError || ((error) => console.error('[PythonAPI] Install error:', error))
      );
    }

    return response;
  } catch (error) {
    console.error('[PythonAPI] installPackages error:', error);
    if (options?.onError) {
      options.onError(error instanceof Error ? error.message : 'Installation failed');
    }
    throw error;
  }
};

const updateConversationState = async (
  action: 'reset' | 'clear-old' | 'update',
  data?: any
) => {
  try {
    const response = await makeRequest(getApiUrl('/api/conversation-state'), {
      method: 'POST',
      body: JSON.stringify({ action, data }),
    });

    if (!response.ok) {
      return await handleApiError(response, 'updateConversationState');
    }

    const result = await response.json();
    return { ok: true, ...result };
  } catch (error) {
    console.error('[PythonAPI] updateConversationState error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to update conversation state'
    };
  }
};

const getSandboxFiles = async () => {
  const makeFilesRequest = async () => {
    return await makeRequest(getApiUrl('/api/get-sandbox-files'));
  };

  try {
    const response = await makeFilesRequest();

    if (!response.ok) {
      if (!response.ok) {
    // The backend handles the 404, so we just process the final error response.
    return await handleApiError(response, 'getSandboxFiles');
}
      return await handleApiError(response, 'getSandboxFiles');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] getSandboxFiles error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to get sandbox files'
    };
  }
};

const restartVite = async () => {
  const makeRestartRequest = async () => {
    return await makeRequest(getApiUrl('/api/restart-vite'), {
      method: 'POST',
    });
  };

  try {
    const response = await makeRestartRequest();

    if (!response.ok) {
      if (response.status === 404) {
        const errorResult = await handleApiError(response, 'restartVite');
        if (errorResult instanceof Response) {
          const data = await errorResult.json();
          return { ok: true, ...data };
        }
      }
      return await handleApiError(response, 'restartVite');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] restartVite error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to restart Vite'
    };
  }
};

const createZip = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/create-zip'), {
      method: 'POST',
    });

    if (!response.ok) {
      return await handleApiError(response, 'createZip');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] createZip error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to create zip'
    };
  }
};

const scrapeScreenshot = async (url: string) => {
  const makeScreenshotRequest = async () => {
    return await makeRequest(getApiUrl('/api/scrape-screenshot'), {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  };

  try {
    const response = await makeScreenshotRequest();

    if (!response.ok) {
      if (response.status === 404) {
        const errorResult = await handleApiError(response, 'scrapeScreenshot');
        if (errorResult instanceof Response) {
          const data = await errorResult.json();
          return { ok: true, ...data };
        }
      }
      return await handleApiError(response, 'scrapeScreenshot');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] scrapeScreenshot error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to capture screenshot'
    };
  }
};

const scrapeUrlEnhanced = async (url: string) => {
  const makeScrapeRequest = async () => {
    return await makeRequest(getApiUrl('/api/scrape-url-enhanced'), {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  };

  try {
    const response = await makeScrapeRequest();
    
    if (!response.ok && response.status === 404) {
      const errorResult = await handleApiError(response, 'scrapeUrlEnhanced');
      if (errorResult instanceof Response) {
        return errorResult;
      }
    }
    
    return response;
  } catch (error) {
    console.error('[PythonAPI] scrapeUrlEnhanced error:', error);
    throw error;
  }
};
const killSandbox = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/kill-sandbox'), {
      method: 'POST',
    });

    if (!response.ok) {
      return await handleApiError(response, 'killSandbox');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] killSandbox error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to kill sandbox'
    };
  }
};

const healthCheck = async () => {
  try {
    const response = await makeRequest(getApiUrl('/health'));

    if (!response.ok) {
      return await handleApiError(response, 'healthCheck');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] healthCheck error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Health check failed',
      status: 'unhealthy'
    };
  }
};

const getConversationState = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/conversation-state'));

    if (!response.ok) {
      return await handleApiError(response, 'getConversationState');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] getConversationState error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to get conversation state'
    };
  }
};

const clearConversationState = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/conversation-state'), {
      method: 'DELETE',
    });

    if (!response.ok) {
      return await handleApiError(response, 'clearConversationState');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] clearConversationState error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to clear conversation state'
    };
  }
};

const checkViteErrors = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/check-vite-errors'));

    if (!response.ok) {
      return await handleApiError(response, 'checkViteErrors');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] checkViteErrors error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to check Vite errors'
    };
  }
};

const clearViteErrorsCache = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/clear-vite-errors-cache'), {
      method: 'POST',
    });

    if (!response.ok) {
      return await handleApiError(response, 'clearViteErrorsCache');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] clearViteErrorsCache error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to clear Vite errors cache'
    };
  }
};

const monitorViteLogs = async () => {
  try {
    const response = await makeRequest(getApiUrl('/api/monitor-vite-logs'));
    return response; // Return response for streaming
  } catch (error) {
    console.error('[PythonAPI] monitorViteLogs error:', error);
    throw error;
  }
};

const reportViteError = async (error: string, file?: string, type?: string) => {
  try {
    const response = await makeRequest(getApiUrl('/api/report-vite-error'), {
      method: 'POST',
      body: JSON.stringify({ error, file, type }),
    });

    if (!response.ok) {
      return await handleApiError(response, 'reportViteError');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] reportViteError error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to report Vite error'
    };
  }
};

const analyzeEditIntent = async (prompt: string, manifest: any, model: string) => {
  try {
    const response = await makeRequest(getApiUrl('/api/analyze-edit-intent'), {
      method: 'POST',
      body: JSON.stringify({ prompt, manifest, model }),
    });

    if (!response.ok) {
      return await handleApiError(response, 'analyzeEditIntent');
    }

    const data = await response.json();
    return { ok: true, ...data };
  } catch (error) {
    console.error('[PythonAPI] analyzeEditIntent error:', error);
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to analyze edit intent'
    };
  }
};

const detectAndInstallPackages = async (
  code: string,
  options?: { 
    onProgress?: (data: any) => void; 
    onError?: (error: string) => void 
  }
) => {
  try {
    const response = await makeRequest(getApiUrl('/api/detect-and-install-packages'), {
      method: 'POST',
      body: JSON.stringify({ code }),
    });

    // Handle streaming if callbacks provided
    if (options?.onProgress && response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
      handleStreamingResponse(
        response,
        options.onProgress,
        options.onError || ((error) => console.error('[PythonAPI] Detect/install error:', error))
      );
    }

    return response;
  } catch (error) {
    console.error('[PythonAPI] detectAndInstallPackages error:', error);
    if (options?.onError) {
      options.onError(error instanceof Error ? error.message : 'Package detection failed');
    }
    throw error;
  }
};

// New function to run commands

// const runCommand = async (command: string, sandboxId?: string) => {
//   try {
//     const response = await makeRequest(getApiUrl('/api/run-command'), {
//       method: 'POST',
//       body: JSON.stringify({ command, sandboxId }),
//     });

//     if (!response.ok) {
//       return await handleApiError(response, 'runCommand');
//     }

//     const data = await response.json();
//     return { ok: true, ...data };
//   } catch (error) {
//     console.error('[PythonAPI] runCommand error:', error);
//     return {
//       ok: false,
//       error: error instanceof Error ? error.message : 'Failed to run command'
//     };
//   }
// };

// Enhanced connection test function
const testConnection = async (): Promise<boolean> => {
  try {
    const result = await healthCheck();
    return result.ok && result.status === 'healthy';
  } catch {
    return false;
  }
};

// Enhanced debugging helper
const debugConnection = async () => {
  console.group('[PythonAPI] Connection Debug');
  
  try {
    console.log('Backend URL:', pythonBackendConfig.baseUrl);
    
    const health = await healthCheck();
    console.log('Health check:', health);
    
    const status = await getSandboxStatus();
    console.log('Sandbox status:', status);
    
    const conversation = await getConversationState();
    console.log('Conversation state:', conversation);
    
  } catch (error) {
    console.error('Debug error:', error);
  } finally {
    console.groupEnd();
  }
};

export const pythonApi = {
  // Core sandbox operations
  getSandboxStatus,
  createAiSandbox,
  killSandbox,
  getSandboxFiles,
  restartVite,
  createZip,

  // AI operations
  generateAiCode,
  applyAiCode,
  analyzeEditIntent,

  // Package management
  installPackages,
  detectAndInstallPackages,

  // Conversation management
  updateConversationState,
  getConversationState,
  clearConversationState,

  // Vite error management
  checkViteErrors,
  clearViteErrorsCache,
  monitorViteLogs,
  reportViteError,

  // Web scraping
  scrapeScreenshot,
  scrapeUrlEnhanced,

  // Utilities
  healthCheck,
  testConnection,
  debugConnection,

  // Enhanced streaming helper
  handleStreamingResponse,
};

export default pythonApi;