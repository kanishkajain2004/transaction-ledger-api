from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.errors import register_exception_handlers
from app.routers import accounts, transactions, transfers

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Transaction Ledger API",
    description="Accounts, credit/debit transactions, balances, history and transfers.",
    version="1.0.0",
)

register_exception_handlers(app)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)


@app.get("/", include_in_schema=False)
def test_console() -> FileResponse:
    """Simple browser page for trying out the API by hand."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
