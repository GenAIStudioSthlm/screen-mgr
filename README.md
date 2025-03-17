# Multi-Screen Content Manager

This FastAPI project manages display content across multiple screens. Use the admin panel to update unique URLs for each screen, and your screens will automatically refresh via WebSockets.

## Setup

1. **Create and activate a virtual environment:**

   ```bash
   python -m venv venv
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```


2. **Install dependencies:**

pip install -r requirements.txt

3. **Run the server:**


uvicorn main:app --reload