import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import BomLine, Ingredient, KitchenOrder, OrderLine, PrepRun
from app.services.bom_engine import explode_and_merge, result_to_dict
router = APIRouter(prefix="/prep", tags=["prep"])

EMPTY_STATS = {"ingredient_count": 0, "shortage_count": 0, "total_shortage_qty": 0}

@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    """唯一会生成备料单的入口：按当前订单行现算并落一条新快照。"""
    order = db.get(KitchenOrder, order_id)
    if not order: raise HTTPException(404, "订单不存在")
    ols = [{"dish_id": l.dish_id, "portions": l.portions}
           for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()]
    bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
           for b in db.scalars(select(BomLine)).all()]
    ings = {i.id: {"code": i.code, "name": i.name, "unit": i.unit, "stock_qty": i.stock_qty}
            for i in db.scalars(select(Ingredient)).all()}
    result = result_to_dict(explode_and_merge(ols, bom, ings))
    result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
    run = PrepRun(order_id=order_id, created_at=datetime.utcnow(), result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, **result}

def _latest_run(order_id: int, db: Session) -> PrepRun | None:
    return db.scalars(select(PrepRun).where(PrepRun.order_id == order_id)
                      .order_by(PrepRun.id.desc())).first()

@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    """只读已落下的快照；没有快照就 404，绝不偷偷生成。"""
    run = _latest_run(order_id, db)
    if not run:
        raise HTTPException(404, "尚未生成备料单")
    return {"id": run.id, **json.loads(run.result_json)}

@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    """缺料贴只读最新快照；没有快照时返回空，不触发重算。"""
    run = _latest_run(order_id, db)
    if not run:
        return {"order_id": order_id, "shortages": [], "stats": dict(EMPTY_STATS)}
    data = json.loads(run.result_json)
    return {"order_id": order_id, "shortages": data.get("shortages", []), "stats": data.get("stats", dict(EMPTY_STATS))}
