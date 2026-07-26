from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request

from ..services.reports import ReportsService

router = APIRouter(prefix="/reports", tags=["reports"])


def _service(request: Request) -> ReportsService:
    return ReportsService(request.app.state.conn)


@router.get("/sales")
def sales_report(request: Request, date_from: date, date_to: date):
    return _service(request).sales_summary(date_from, date_to)


@router.get("/caja")
def caja_report(request: Request, date_from: date, date_to: date):
    return _service(request).caja_summary(date_from, date_to)


@router.get("/stock")
def stock_report(request: Request, low_stock_threshold: Decimal = Decimal("0")):
    return _service(request).stock_summary(low_stock_threshold=low_stock_threshold)
