import os
from pathlib import Path
 
import pandas as pd
import pymysql
from dotenv import load_dotenv
 
load_dotenv(override=True)
 
BASE_DIR = Path(__file__).resolve().parent.parent
 
EXCEL_FILE = BASE_DIR / "data" / "SuperStoreOrders.xlsx"
 
 
def get_connection():
 
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )
 
 
def load_sheet(sheet_name):
 
    df = pd.read_excel(
        EXCEL_FILE,
        sheet_name=sheet_name
    )
 
    df.columns = [
        column.strip().lower()
        for column in df.columns
    ]
 
    return df
 
 
def create_tables(connection):
 
    cursor = connection.cursor()
 
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
 
    cursor.execute("DROP TABLE IF EXISTS order_items;")
    cursor.execute("DROP TABLE IF EXISTS orders;")
    cursor.execute("DROP TABLE IF EXISTS products;")
    cursor.execute("DROP TABLE IF EXISTS customers;")
 
    cursor.execute("""
        CREATE TABLE customers (
            customer_id VARCHAR(20) PRIMARY KEY,
            customer_name VARCHAR(255),
            segment VARCHAR(50),
            country VARCHAR(100),
            state VARCHAR(100),
            market VARCHAR(50),
            region VARCHAR(50)
        );
    """)
 
    cursor.execute("""
        CREATE TABLE products (
            product_id VARCHAR(20) PRIMARY KEY,
            product_name VARCHAR(255),
            category VARCHAR(100),
            sub_category VARCHAR(100),
            product_cost NUMERIC(15, 2),
            selling_price NUMERIC(15, 2)
        );
    """)
 
    cursor.execute("""
        CREATE TABLE orders (
            order_id VARCHAR(20) PRIMARY KEY,
            customer_id VARCHAR(20),
            order_date DATE,
            ship_date DATE,
            ship_mode VARCHAR(50),
            order_priority VARCHAR(20),
            year INTEGER,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
    """)
 
    cursor.execute("""
        CREATE TABLE order_items (
            order_item_id VARCHAR(20) PRIMARY KEY,
            order_id VARCHAR(20),
            product_id VARCHAR(20),
            quantity INTEGER,
            discount NUMERIC(10, 4),
            shipping_cost NUMERIC(15, 2),
            profit NUMERIC(15, 2),
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
    """)
 
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
 
    connection.commit()
 
    print("Tables created successfully.")
 
    cursor.close()
 
 
def insert_customers(connection, df):
 
    cursor = connection.cursor()
 
    sql = """
    INSERT INTO customers(
        customer_id,
        customer_name,
        segment,
        country,
        state,
        market,
        region
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
 
    records = []
 
    for row in df.itertuples(index=False):
 
        records.append(
            (
                str(row.customer_id).strip(),
                str(row.customer_name).strip(),
                str(row.segment).strip() if pd.notna(row.segment) else None,
                str(row.country).strip() if pd.notna(row.country) else None,
                str(row.state).strip() if pd.notna(row.state) else None,
                str(row.market).strip() if pd.notna(row.market) else None,
                str(row.region).strip() if pd.notna(row.region) else None,
            )
        )
 
    cursor.executemany(sql, records)
 
    connection.commit()
 
    print(
        f"{len(records)} customers inserted."
    )
 
    cursor.close()
 
 
def insert_products(connection, df):
 
    cursor = connection.cursor()
 
    sql = """
    INSERT INTO products(
        product_id,
        product_name,
        category,
        sub_category,
        product_cost,
        selling_price
    )
    VALUES (%s, %s, %s, %s, %s, %s)
    """
 
    records = []
 
    for row in df.itertuples(index=False):
 
        records.append(
            (
                str(row.product_id).strip(),
                str(row.product_name).strip(),
                str(row.category).strip() if pd.notna(row.category) else None,
                str(row.sub_category).strip() if pd.notna(row.sub_category) else None,
                float(row.product_cost),
                float(row.selling_price),
            )
        )
 
    cursor.executemany(sql, records)
 
    connection.commit()
 
    print(
        f"{len(records)} products inserted."
    )
 
    cursor.close()
 
 
def insert_orders(connection, df):
 
    cursor = connection.cursor()
 
    sql = """
    INSERT INTO orders(
        order_id,
        customer_id,
        order_date,
        ship_date,
        ship_mode,
        order_priority,
        year
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
 
    records = []
 
    for row in df.itertuples(index=False):
 
        records.append(
            (
                str(row.order_id).strip(),
                str(row.customer_id).strip(),
                pd.to_datetime(row.order_date, dayfirst=True).date(),
                pd.to_datetime(row.ship_date, dayfirst=True).date(),
                str(row.ship_mode).strip() if pd.notna(row.ship_mode) else None,
                str(row.order_priority).strip() if pd.notna(row.order_priority) else None,
                int(row.year) if pd.notna(row.year) else None,
            )
        )
 
    cursor.executemany(sql, records)
 
    connection.commit()
 
    print(
        f"{len(records)} orders inserted."
    )
 
    cursor.close()
 
 
def insert_order_items(connection, df):
 
    cursor = connection.cursor()
 
    sql = """
    INSERT INTO order_items(
        order_item_id,
        order_id,
        product_id,
        quantity,
        discount,
        shipping_cost,
        profit
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
 
    records = []
 
    for row in df.itertuples(index=False):
 
        records.append(
            (
                str(row.order_item_id).strip(),
 
                str(row.order_id).strip(),
 
                str(row.product_id).strip(),
 
                int(row.quantity),
 
                float(row.discount),
 
                float(row.shipping_cost),
 
                float(row.profit)
            )
        )
 
    cursor.executemany(sql, records)
 
    connection.commit()
 
    print(
        f"{len(records)} order items inserted."
    )
 
    cursor.close()
 
 
def main():
 
    customers = load_sheet("Customers")
    products = load_sheet("Products")
    orders = load_sheet("Orders")
    order_items = load_sheet("Order Items")
 
    print(f"Customers loaded: {len(customers)}")
    print(f"Products loaded: {len(products)}")
    print(f"Orders loaded: {len(orders)}")
    print(f"Order items loaded: {len(order_items)}")
 
    connection = get_connection()
 
    try:
 
        create_tables(connection)
 
        insert_customers(connection, customers)
        insert_products(connection, products)
        insert_orders(connection, orders)
        insert_order_items(connection, order_items)
 
    finally:
        connection.close()
 
 
if __name__ == "__main__":
    main()
 
 