# LinkGuard Backend

FastAPI backend server for LinkGuard application.

## Setup

1. Create virtual environment:
   ```bash
   py -m venv venv
   ```

2. Activate virtual environment:
   - PowerShell: `.\venv\Scripts\Activate.ps1`
   - CMD: `venv\Scripts\activate.bat`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the server:
   ```bash
   python main.py
   ```

Or use the provided scripts:
- `start.bat` (Windows CMD)
- `start.ps1` (PowerShell)

## API Endpoints

- `GET /` - API status
- `GET /health` - Health check
- `POST /api/check-link` - Check if a link is healthy

## Configuration

The server runs on port 8000 by default. You can change this by setting the `PORT` environment variable.

