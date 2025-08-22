/**
 * Python Backend Configuration
 * Configuration for connecting Next.js frontend to Python FastAPI backend
 */

export const pythonBackendConfig = {
  // Backend URL configuration
  baseUrl: process.env.PYTHON_API_URL || 'http://localhost:8000',
  
  // API endpoints mapping (same paths as Next.js API routes)
  endpoints: {
    // AI Code Generation
    generateAiCodeStream: '/api/generate-ai-code-stream',
    applyAiCodeStream: '/api/apply-ai-code-stream',
    analyzeEditIntent: '/api/analyze-edit-intent',
    
    // Sandbox Management
    createAiSandbox: '/api/create-ai-sandbox',
    getSandboxFiles: '/api/get-sandbox-files',
    sandboxStatus: '/api/sandbox-status',
    killSandbox: '/api/kill-sandbox',
    
    // Vite Operations
    checkViteErrors: '/api/check-vite-errors',
    clearViteErrorsCache: '/api/clear-vite-errors-cache',
    monitorViteLogs: '/api/monitor-vite-logs',
    reportViteError: '/api/report-vite-error',
    restartVite: '/api/restart-vite',
    
    // Package Management
    installPackages: '/api/install-packages',
    detectAndInstallPackages: '/api/detect-and-install-packages',
    
    // Conversation State
    conversationState: '/api/conversation-state',
    
    // File Operations
    createZip: '/api/create-zip',
    runCommand: '/api/run-command',
    sandboxLogs: '/api/sandbox-logs',
    
    // Web Scraping
    scrapeScreenshot: '/api/scrape-screenshot',
    scrapeUrlEnhanced: '/api/scrape-url-enhanced',
    
    // Health Check
    health: '/health'
  },
  
  // Request configuration
  defaultHeaders: {
    'Content-Type': 'application/json',
  },
  
  // Timeout settings
  timeout: {
    default: 30000,      // 30 seconds
    streaming: 300000,   // 5 minutes for streaming endpoints
    sandbox: 120000,     // 2 minutes for sandbox operations
  },
  
  // Retry configuration
  retry: {
    attempts: 3,
    delay: 1000,         // 1 second
    backoff: 1.5,        // Exponential backoff multiplier
  }
};

export default pythonBackendConfig;
