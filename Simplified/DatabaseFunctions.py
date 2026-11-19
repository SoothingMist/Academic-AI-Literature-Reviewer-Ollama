
# Access to SQLite as the database management system (dbms).
# Statements developed here map readily to MySQL.
import sqlite3
from sqlite3 import Error


# *** Connect to an SQLite database.
# Create the database if it does not exist at the end of the path.
# https://www.sqlitetutorial.net/sqlite-python/creating-database
def create_connection(db_file):
  conn = None
  try:
    conn = sqlite3.connect(db_file)
    print("SQLite3 Version: " + sqlite3.version)
  except Error as e:
    print("\n")
    print(e)
    print("create_connection: Path does not exist to file (" + db_file + ")\n")

  return conn
#########################################

# Add a table to the database
# https://www.sqlitetutorial.net/sqlite-python/create-tables
def create_table(conn, create_table_sql):
  try: conn.cursor().execute(create_table_sql)
  except Error as e: print(e)
#########################################

# Insert record into database
# https://www.sqlitetutorial.net/sqlite-python/insert
# https://www.w3resource.com/sqlite/sqlite-insert-into.php
def insert_record(conn, tableName, record):
  if len(record) == 3:
    insertion_command = \
      f"INSERT OR REPLACE INTO {tableName} (Title, Abstract, URL) VALUES(?,?,?)"
  elif len(record) == 1:
    insertion_command = \
      f"INSERT OR REPLACE INTO {tableName} (Query) VALUES(?)"
  else: insertion_command = None
  if insertion_command:
    conn.cursor().execute(insertion_command, record)
    conn.commit()
    return conn.cursor().lastrowid
  else: return None
#########################################

# Display all records
# https://www.sqlitetutorial.net/sqlite-python/sqlite-python-select
def get_all_records(conn, table, element):
  cur = conn.cursor()
  cur.execute(f"SELECT * FROM {table} ORDER BY {element} ASC")
  rows = cur.fetchall()
  return rows
#########################################

# Display all records with similar titles
# https://www.sqlitetutorial.net/sqlite-python/sqlite-python-select
def query_database(conn, table, element, search_term):
  cur = conn.cursor()
  query = f"SELECT * FROM {table} WHERE {element} = ?;"
  cur.execute(query, (search_term,))
  rows = cur.fetchall()
  return rows
#########################################

# Close the database
def close_connection(conn):
  if conn:
    conn.close()
    conn = None
  return conn
#########################################
