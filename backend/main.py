"""
上市公司股票分析 - 后端 + 前端一体化服务
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from services.stock_service import search_stocks, get_all_company_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="上市公司股票分析", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Static frontend ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "miniprogram"


@app.get("/")
async def root():
    """Serve the main web page."""
    html_path = Path(__file__).resolve().parent.parent / "index.html"
    return FileResponse(html_path, media_type="text/html")


# ---- API routes ----

@app.get("/api/search")
async def api_search(keyword: str = Query(..., min_length=1, description="公司名称关键词")):
    results = search_stocks(keyword)
    return {
        "code": 0,
        "data": results,
        "message": "success" if results else "未找到匹配的公司",
    }


@app.get("/api/company/{stock_code}")
async def api_company(stock_code: str):
    if not stock_code or len(stock_code) < 6:
        raise HTTPException(status_code=400, detail="Invalid stock code")

    data = get_all_company_data(stock_code)

    if not data.get("name"):
        return {
            "code": 1,
            "data": None,
            "message": "未查询到该公司数据，请确认股票代码是否正确",
        }

    return {
        "code": 0,
        "data": data,
        "message": "success",
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
