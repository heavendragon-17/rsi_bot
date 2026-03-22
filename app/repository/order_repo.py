from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String

from .db_connect import Base


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    order_id = Column(String)
    side = Column(String)
    price = Column(Numeric(precision=20, scale=8))
    amount = Column(Numeric(precision=20, scale=8))
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderRepository:
    def __init__(self, db_session):
        self.db = db_session

    def add(self, order_data):
        order = Order(**order_data)
        self.db.add(order)
        self.db.commit()
        return order

    def get_open_orders(self):
        return self.db.query(Order).filter(Order.status == "OPEN").all()
