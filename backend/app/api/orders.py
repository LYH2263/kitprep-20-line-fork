from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Dish, KitchenOrder, OrderLine
router = APIRouter(prefix="/orders", tags=["orders"])

class LineIn(BaseModel):
    dish_id: int
    portions: int = Field(gt=0)

class LinesIn(BaseModel):
    lines: list[LineIn] = Field(min_length=1)

def _serialize_lines(db: Session, order_id: int) -> list[dict]:
    dishes = {d.id: d for d in db.scalars(select(Dish)).all()}
    rows = db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    return [{"id": r.id, "dish_id": r.dish_id, "dish_name": dishes[r.dish_id].name, "portions": r.portions}
            for r in rows]

@router.get("")
def list_orders(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "outlet": r.outlet, "status": r.status}
            for r in db.scalars(select(KitchenOrder).order_by(KitchenOrder.id)).all()]

@router.get("/{order_id}/lines")
def order_lines(order_id: int, db: Session = Depends(get_db)):
    return _serialize_lines(db, order_id)

@router.post("/{order_id}/lines", status_code=201)
def add_order_lines(order_id: int, payload: LinesIn, db: Session = Depends(get_db)):
    """整批追加订单行：先全部校验，再一次 commit；任一行非法整批退回。
    纯订单写操作——不生成备料单、不扣库存。"""
    order = db.get(KitchenOrder, order_id)
    if order is None:
        raise HTTPException(404, "订单不存在")
    valid_dish_ids = set(db.scalars(select(Dish.id)).all())
    for ln in payload.lines:
        if ln.dish_id not in valid_dish_ids:
            raise HTTPException(400, f"菜品不存在: {ln.dish_id}")
    try:
        db.add_all([OrderLine(order_id=order_id, dish_id=ln.dish_id, portions=ln.portions)
                    for ln in payload.lines])
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "保存失败，整批已回滚")
    return _serialize_lines(db, order_id)
