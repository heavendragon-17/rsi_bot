from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from .db_connect import Base

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    order_id = Column(String)
    side = Column(String)
    price = Column(Float)
    amount = Column(Float)
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
        return self.db.query(Order).filter(Order.status == 'OPEN').all()
