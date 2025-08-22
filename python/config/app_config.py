# config/app_config.py - Python Backend Configuration

from types import SimpleNamespace

appConfig = SimpleNamespace(
    e2b=SimpleNamespace(
        timeoutMinutes=15,
        timeoutMs=15 * 60 * 1000,  # 15 minutes in milliseconds
        vitePort=5173,
        viteStartupDelay=8000,  # 8 seconds - reduced from 10s
    ),
    
    api=SimpleNamespace(
        timeout=30000,  # 30 seconds
        retries=3,
        retryDelay=1000,  # 1 second
    ),
    
    sandbox=SimpleNamespace(
        defaultModel='moonshotai/kimi-k2-instruct',
        maxConcurrentSandboxes=5,
        cleanupIntervalMs=60000,  # 1 minute
    ),
    
    # URL patterns for E2B (matching working frontend)
    urlPatterns=SimpleNamespace(
        primary='https://5173-{sandboxId}.e2b.app',  # WORKING PATTERN
        fallbacks=[
            'https://{sandboxId}-5173.e2b.dev',
            'https://{sandboxId}.e2b.dev:5173',
            'https://{sandboxId}.e2b.dev',
        ]
    )
)