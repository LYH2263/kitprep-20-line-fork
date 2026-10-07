import json

from sqlalchemy import func, select

from app.models.models import Ingredient, KitchenOrder, OrderLine, PrepRun


def _line_count(db, order_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(OrderLine).where(OrderLine.order_id == order_id)
    )


def _prep_run_count(db) -> int:
    return db.scalar(select(func.count()).select_from(PrepRun))


def _prep_runs(db):
    return [(r.id, json.loads(r.result_json))
            for r in db.scalars(select(PrepRun).order_by(PrepRun.id)).all()]


def _stock_map(db) -> dict:
    return dict(db.execute(select(Ingredient.code, Ingredient.stock_qty)).all())


def _line_by_code(result: dict, code: str) -> dict:
    return next(l for l in result["prep_lines"] if l["ingredient_code"] == code)


def _add_lines(client, order_id=1, lines=None):
    lines = lines if lines is not None else [
        {"dish_id": 2, "portions": 5},   # 鱼香茄子 +5
        {"dish_id": 3, "portions": 2},   # 鸡汤面 +2
    ]
    return client.post(f"/api/orders/{order_id}/lines", json={"lines": lines})


def test_add_lines_success_returns_all_rows(client, db_session):
    resp = _add_lines(client)
    assert resp.status_code == 201
    rows = resp.json()
    assert len(rows) == 3 + 2
    assert all({"id", "dish_id", "dish_name", "portions"} <= set(r) for r in rows)
    assert [r for r in rows if r["dish_id"] == 2 and r["portions"] == 5]
    assert [r for r in rows if r["dish_id"] == 3 and r["portions"] == 2]

    got = client.get("/api/orders/1/lines").json()
    assert got == rows


def test_add_lines_does_not_touch_existing_snapshot(client, db_session):
    snap = client.post("/api/prep/run?order_id=1", json={}).json()
    assert _prep_run_count(db_session) == 1
    before_runs = _prep_runs(db_session)
    before_stock = _stock_map(db_session)

    assert _add_lines(client).status_code == 201

    # 备料单不新增、旧快照逐字段冻结
    assert _prep_run_count(db_session) == 1
    assert _prep_runs(db_session) == before_runs
    latest = client.get("/api/prep/latest?order_id=1").json()
    assert latest["id"] == snap["id"]
    assert latest["stats"] == snap["stats"]
    # 库存不被扣减
    assert _stock_map(db_session) == before_stock


def test_add_lines_never_creates_snapshot(client, db_session):
    assert _prep_run_count(db_session) == 0
    assert _add_lines(client).status_code == 201
    assert _prep_run_count(db_session) == 0
    # 连调只读接口也不得补算落库
    client.get("/api/prep/latest?order_id=1")
    client.get("/api/prep/shortages?order_id=1")
    client.get("/api/prep/latest?order_id=1")
    assert _prep_run_count(db_session) == 0


def test_add_lines_keeps_stock_unchanged(client, db_session):
    before = _stock_map(db_session)
    assert _add_lines(client).status_code == 201
    after = _stock_map(db_session)
    assert after == before
    assert len(after) == 7


def test_invalid_dish_rolls_back_whole_batch(client, db_session):
    lines_before = _line_count(db_session, 1)
    runs_before = _prep_run_count(db_session)
    resp = _add_lines(client, lines=[{"dish_id": 1, "portions": 3}, {"dish_id": 999999, "portions": 1}])
    assert resp.status_code == 400
    # 合法那条也不得入库
    assert _line_count(db_session, 1) == lines_before
    assert _prep_run_count(db_session) == runs_before


def test_invalid_portions_422_no_write(client, db_session):
    lines_before = _line_count(db_session, 1)
    for bad in (0, -1, 1.5):
        resp = client.post("/api/orders/1/lines", json={"lines": [{"dish_id": 1, "portions": bad}]})
        assert resp.status_code == 422, bad
    assert _line_count(db_session, 1) == lines_before
    assert _prep_run_count(db_session) == 0


def test_empty_or_malformed_batch_422(client, db_session):
    lines_before = _line_count(db_session, 1)
    assert client.post("/api/orders/1/lines", json={"lines": []}).status_code == 422
    assert client.post("/api/orders/1/lines", json={"lines": [{"dish_id": "x"}]}).status_code == 422
    assert client.post("/api/orders/1/lines", json={}).status_code == 422
    assert client.post("/api/orders/1/lines").status_code == 422
    assert _line_count(db_session, 1) == lines_before
    assert _prep_run_count(db_session) == 0


def test_order_not_found_404_no_write(client, db_session):
    resp = _add_lines(client, order_id=999999, lines=[{"dish_id": 1, "portions": 1}])
    assert resp.status_code == 404
    assert _line_count(db_session, 1) == 3
    assert _prep_run_count(db_session) == 0


def test_regenerate_recomputes_and_keeps_old_snapshot(client, db_session):
    a = client.post("/api/prep/run?order_id=1").json()
    assert _line_by_code(a, "I-EG")["need_qty"] == 9.0          # 30 × 0.3

    assert _add_lines(client).status_code == 201                 # 鱼香茄子 +5

    # 未再生成前，latest 仍是旧单
    frozen = client.get("/api/prep/latest?order_id=1").json()
    assert frozen["id"] == a["id"]
    assert _line_by_code(frozen, "I-EG")["need_qty"] == 9.0

    # 显式再生成才现算
    b = client.post("/api/prep/run?order_id=1").json()
    assert b["id"] > a["id"]
    assert _line_by_code(b, "I-EG")["need_qty"] == 10.5         # 35 × 0.3
    assert b["stats"] != a["stats"]

    # 两张快照都在，旧快照数字未被改写
    runs = _prep_runs(db_session)
    assert len(runs) == 2
    old = next(parsed for rid, parsed in runs if rid == a["id"])
    assert _line_by_code(old, "I-EG")["need_qty"] == 9.0
    latest = client.get("/api/prep/latest?order_id=1").json()
    assert latest["id"] == b["id"]


def test_empty_state_contract_when_no_snapshot(client, db_session):
    assert _prep_run_count(db_session) == 0
    latest = client.get("/api/prep/latest?order_id=1").json()
    assert latest["id"] is None
    assert latest["prep_lines"] == []
    assert latest["shortages"] == []
    assert latest["stats"] == {
        "ingredient_count": 0, "shortage_count": 0, "total_shortage_qty": 0,
    }
    assert latest["order"]["id"] == 1

    sh = client.get("/api/prep/shortages?order_id=1").json()
    assert sh["shortages"] == []
    assert sh["stats"]["shortage_count"] == 0
    # 只读不得落库
    assert _prep_run_count(db_session) == 0


def test_two_batches_accumulate(client, db_session):
    r1 = _add_lines(client, lines=[{"dish_id": 1, "portions": 1}])
    r2 = _add_lines(client, lines=[{"dish_id": 2, "portions": 2}])
    assert r1.status_code == 201 and r2.status_code == 201
    assert _line_count(db_session, 1) == 3 + 1 + 1
    assert _prep_run_count(db_session) == 0
