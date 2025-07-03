from sqlalchemy import (Column, Integer, String, Float,
                        ForeignKey, Date, Boolean, DateTime)
from sqlalchemy.orm import declarative_base, relationship
import datetime

Base = declarative_base()

class ProductCategory(Base):
    __tablename__ = 'product_categories'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    products = relationship("Product", back_populates="category", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = 'products'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    category_id = Column(String, ForeignKey('product_categories.id'), nullable=False)
    category = relationship("ProductCategory", back_populates="products")

class Promocode(Base):
    __tablename__ = 'promocodes'
    code = Column(String, primary_key=True)
    discount = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    usage_limit = Column(Integer, nullable=True)
    times_used = Column(Integer, default=0, nullable=False)

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_full_name = Column(String)
    user_username = Column(String)
    service = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    duration_hours = Column(Integer, nullable=False)
    date = Column(String, nullable=False) # Оставляем строкой для совместимости с логикой календаря
    time = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)