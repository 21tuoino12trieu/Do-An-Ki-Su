# from typing import List, Dict, Any, Optional, Tuple

# import psycopg2
# from neo4j import GraphDatabase

# from beeportal.bot_bee_fraud.config.settings import Settings


# class PostgresDB:
#     """
#     A class to handle the Postgres database connections and operations.
#     Provides methods for executing queries and fetching data without modification capabilities.
#     The connection is established with read-only permissions to ensure data integrity.
#     """

#     def __init__(self, dbname: str = None, user: str = None,
#                  password: str = None, host: str = None, port: str = None):
#         """
#         Initialize Postgres connection parameters.
#         If parameters are not provided, it will try to use environment variables from Config.

#         Args:
#             dbname: Database name
#             user: Database user
#             password: Database password
#             host: Database host
#             port: Database port
#         """
#         self.dbname = dbname or Settings.DB_NAME
#         self.user = user or Settings.DB_USER
#         self.password = password or Settings.DB_PASSWORD
#         self.host = host or Settings.DB_HOST
#         self.port = port or Settings.DB_PORT
#         self.conn = None
#         self.cur = None

#     def connect(self) -> None:
#         """Establish a connection to the Postgres database."""
#         try:
#             self.conn = psycopg2.connect(
#                 dbname=self.dbname,
#                 user=self.user,
#                 password=self.password,
#                 host=self.host,
#                 port=self.port
#             )
#             self.cur = self.conn.cursor()
#             print("Postgres database connection established successfully")
#         except Exception as e:
#             print(f"Error connecting to Postgres database: {e}", exc_info=True)
#             raise

#     def disconnect(self) -> None:
#         """Close the cursor and connection."""
#         if self.cur:
#             self.cur.close()
#         if self.conn:
#             self.conn.close()
#         print("Postgres database connection closed.")

#     def execute_query(self, query: str, params: Tuple[Any] = None) -> None:
#         """
#         Execute a SQL query with optional parameters.

#         Args:
#             query: SQL query string
#             params: Optional parameters for the query
#         """
#         try:
#             if params:
#                 self.cur.execute(query, params)
#             else:
#                 self.cur.execute(query)
#         except Exception as e:
#             print(f"Error executing query: {e}", exc_info=True)
#             raise

#     def fetch_all(self) -> List[Any]:
#         """Fetch all rows from the last executed query."""
#         return self.cur.fetchall()

#     def fetch_one(self) -> tuple:
#         """Fetch a single row from the last executed query."""
#         return self.cur.fetchone()

#     def commit(self) -> None:
#         """Commit the current transaction."""
#         if self.conn:
#             self.conn.commit()

#     def rollback(self) -> None:
#         """Roll back the current transaction if needed."""
#         if self.conn:
#             self.conn.rollback()

#     def execute_and_fetch(self, query: str, params: tuple = None) -> List[Any]:
#         """
#         Execute a query and fetch all results in one operation.

#         Args:
#             query: SQL query string
#             params: Optional parameters for the query

#         Returns:
#             List of result rows
#         """
#         self.execute_query(query, params)
#         return self.fetch_all()

#     def get_fraud_transactions(self, account_id: str = None, limit: int = None) -> List[tuple]:
#         """
#         Get fraud transactions from the database.

#         Args:
#             account_id: Optional account ID to filter by
#             limit: Optional limit for number of records

#         Returns:
#             List of transaction tuples
#         """
#         base_query = """
#                      SELECT account, fraud_account, transdate, amount, trans_details
#                      FROM fraud_detection.fraud_txn_202505 \
#                      """

#         params = []
#         if account_id:
#             base_query += " WHERE fraud_account = %s"
#             params.append(account_id)

#         base_query += " ORDER BY transdate"

#         if limit:
#             base_query += " LIMIT %s"
#             params.append(limit)

#         return self.execute_and_fetch(base_query, tuple(params) if params else None)

#     def __enter__(self):
#         """Context manager entry - establishes connection."""
#         self.connect()
#         return self

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         """Context manager exit - ensures proper cleanup."""
#         # In read-only mode, no need to worry about committing changes
#         if exc_type:
#             self.rollback()  # Rollback in case of exception to clean up properly
#         self.disconnect()


# class Neo4jDB:
#     """
#     A class to handle Neo4j graph database connections and operations.
#     Provides methods for executing queries and fetching data from a Neo4j database.
#     """

#     def __init__(self, uri: str = None, user: str = None, password: str = None):
#         """
#         Initialize Neo4j connection parameters.
#         If parameters are not provided, it will try to use environment variables from Config.

#         Args:
#             uri: Neo4j connection URI
#             user: Neo4j username
#             password: Neo4j password
#         """
#         self.uri = uri or Settings.NEO4J_URI
#         self.user = user or Settings.NEO4J_USER
#         self.password = password or Settings.NEO4J_PASSWORD
#         self.driver = None

#     def connect(self) -> None:
#         """Establish a connection to the Neo4j database."""
#         try:
#             self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
#             print("Neo4j connection established successfully.")
#         except Exception as e:
#             print(f"Error connecting to Neo4j database: {e}", exc_info=True)
#             raise

#     def disconnect(self) -> None:
#         """Close the driver connection."""
#         if self.driver:
#             self.driver.close()
#             print("Neo4j connection closed.")

#     def get_transaction_to_account(self, to_account_number: str, from_date: str,
#                                    to_date: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
#         """
#         Get all transactions sent to a specific account within a date range.

#         Args:
#             to_account_number: Destination account number
#             from_date: Start date in format "YYYY-MM-DD"
#             to_date: End date in format "YYYY-MM-DD"
#             limit: Optional maximum number of records to return

#         Returns:
#             List of transaction dictionaries
#         """
#         try:
#             with self.driver.session() as session:
#                 result = session.execute_read(
#                     self._get_transaction_to_account_query,
#                     to_account_number=to_account_number,
#                     from_date=from_date,
#                     to_date=to_date,
#                     limit=limit
#                 )
#                 return result
#         except Exception as e:
#             print(f"Error executing Neo4j query: {e}", exc_info=True)
#             raise

#     @staticmethod
#     def _get_transaction_to_account_query(tx, to_account_number: str, from_date: str,
#                                           to_date: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
#         """
#         Internal method to execute the Neo4j query.

#         Args:
#             tx: Neo4j transaction
#             to_account_number: Destination account number
#             from_date: Start date in format "YYYY-MM-DD"
#             to_date: End date in format "YYYY-MM-DD"
#             limit: Optional maximum number of records to return

#         Returns:
#             List of transaction dictionaries
#         """
#         try:
#             query = """
#             MATCH (n:Account)-[r:HAS_TRANSFERRED_TO]->(m:Account {accountNumber: $to_account_number})
#             WHERE date(r.transDate) >= date($from_date) AND date(r.transDate) <= date($to_date)
#             RETURN n.accountNumber AS from_account,
#                    m.accountNumber AS dest_account,
#                    r.amount AS amount,
#                    r.ftId AS transaction_id,
#                    toString(r.transDate) AS trans_date,
#                    r.transDetails AS transaction_detail
#             ORDER BY n.accountNumber DESC
#             """ + ("LIMIT $limit" if limit is not None else "")

#             params = {
#                 "to_account_number": to_account_number,
#                 "from_date": from_date,
#                 "to_date": to_date
#             }
#             if limit is not None:
#                 params["limit"] = limit
#             result = tx.run(query, **params)
#             records = [record.data() for record in result]

#             # Format the datetime string to desired format
#             for record in records:
#                 if record['trans_date']:
#                     # Parse the datetime string and reformat it
#                     dt = record['trans_date']
#                     if hasattr(dt, 'strftime'):  # If it's already a datetime object
#                         record['trans_date'] = dt.strftime("%Y-%m-%dT%H:%M:%S")

#             return records
#         except Exception as e:
#             print(f"Error executing query: {e}", exc_info=True)
#             raise

#     def __enter__(self):
#         """Context manager entry - establishes connection."""
#         self.connect()
#         return self

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         """Context manager exit - ensures proper cleanup."""
#         self.disconnect()
