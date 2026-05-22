import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routes import router
from mcps.lighting.server import server as lighting_mcp_server
from mcps.screens.server import server as screens_mcp_server


app = FastAPI()
# Mount a static folder (optional)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# add routes from routes.py
app.include_router(router)

# MCP servers — in-process, mounted under /mcp/<domain>.
# Each one wraps the corresponding domain's Python module APIs and is
# usable by any MCP client (Claude Code, our own agents in later phases).
app.mount("/mcp/lighting", lighting_mcp_server.sse_app())
app.mount("/mcp/screens", screens_mcp_server.sse_app())

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
#        ssl_keyfile="key.pem",
#        ssl_certfile="cert.pem",
    )
