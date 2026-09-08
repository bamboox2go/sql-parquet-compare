from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

CUSTOMERS = [
    {
        "customer_id": 1,
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "created_at": datetime(2024, 1, 15, 9, 30, 0),
        "is_active": True,
    },
    {
        "customer_id": 2,
        "name": "Alan Turing",
        "email": None,
        "created_at": datetime(2024, 2, 1, 12, 0, 0),
        "is_active": True,
    },
    {
        "customer_id": 3,
        "name": "Grace Hopper",
        "email": "grace@example.com",
        "created_at": datetime(2023, 12, 25, 18, 45, 10),
        "is_active": False,
    },
]

ORDERS = [
    {
        "order_id": 100,
        "customer_id": 1,
        "amount": Decimal("19.9900"),
        "order_date": date(2024, 3, 1),
        "notes": None,
    },
    {
        "order_id": 101,
        "customer_id": 1,
        "amount": Decimal("120.5000"),
        "order_date": date(2024, 3, 2),
        "notes": "  rush  ",
    },
    {
        "order_id": 102,
        "customer_id": 2,
        "amount": Decimal("0.0100"),
        "order_date": date(2024, 3, 3),
        "notes": "exact",
    },
]

ORDER_LINES = [
    {
        "order_id": 100,
        "line_no": 1,
        "sku": "BOOK-1",
        "qty": 2,
        "unit_price": Decimal("9.9950"),
    },
    {
        "order_id": 100,
        "line_no": 2,
        "sku": "PEN-9",
        "qty": 1,
        "unit_price": Decimal("0.0000"),
    },
    {
        "order_id": 101,
        "line_no": 1,
        "sku": "LAMP-3",
        "qty": 1,
        "unit_price": Decimal("120.5000"),
    },
]

DDL = [
    """
    IF OBJECT_ID('dbo.order_lines', 'U') IS NOT NULL DROP TABLE dbo.order_lines;
    IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
    IF OBJECT_ID('dbo.customers', 'U') IS NOT NULL DROP TABLE dbo.customers;
    """,
    """
    CREATE TABLE dbo.customers (
        customer_id INT NOT NULL PRIMARY KEY,
        name NVARCHAR(100) NOT NULL,
        email NVARCHAR(200) NULL,
        created_at DATETIME2(6) NOT NULL,
        is_active BIT NOT NULL
    );
    """,
    """
    CREATE TABLE dbo.orders (
        order_id INT NOT NULL PRIMARY KEY,
        customer_id INT NOT NULL,
        amount DECIMAL(18, 4) NOT NULL,
        order_date DATE NOT NULL,
        notes NVARCHAR(MAX) NULL
    );
    """,
    """
    CREATE TABLE dbo.order_lines (
        order_id INT NOT NULL,
        line_no INT NOT NULL,
        sku NVARCHAR(40) NOT NULL,
        qty INT NOT NULL,
        unit_price DECIMAL(18, 4) NOT NULL,
        CONSTRAINT PK_order_lines PRIMARY KEY (order_id, line_no)
    );
    """,
]
