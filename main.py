#!/usr/bin/env python3
"""
Entry point for Invoice Processing Agent API
Runs the FastAPI server from the organized source structure
"""

import os

if __name__ == "__main__":
    # Import and run the agent API
    from src.agent_api import app
    import uvicorn
    
    print("\n" + "="*70)
    print("🤖 INVOICE PROCESSING AGENT API")
    print("="*70)
    print("\n📋 Agent Endpoints:")
    print("  POST   /api/agent/invoke          - Invoke agent (upload image/data)")
    print("  GET    /api/agent/status/{id}     - Get agent status")
    print("  GET    /human-review/pending      - List pending reviews")
    print("  POST   /human-review/decision     - Submit decision & RE-INVOKE")
    print("  GET    /api/agent/logs/{id}       - View execution logs")
    print("\n🔧 LangGraph Features:")
    print("  ✅ Built-in checkpoint table")
    print("  ✅ Automatic state management")
    print("  ✅ Agent resumes from interrupt")
    print("\n📖 Docs: http://localhost:8000/docs")
    print("="*70 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)