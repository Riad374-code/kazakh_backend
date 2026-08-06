import os
import uvicorn

if __name__ == "__main__":
    # Safely get the PORT from Railway, or default to 8000 locally
    port = int(os.environ.get("PORT", 8000))
    
    # Run the FastAPI instance
    uvicorn.run("api.app:app", host="0.0.0.0", port=port)
