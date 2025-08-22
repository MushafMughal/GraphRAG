import json
# from langchain_community.graphs import Neo4jGraph
from langchain_neo4j import Neo4jGraph

# --- Connection Details ---
# Replace with your Neo4j database details
NEO4J_URL = "bolt://127.0.0.1:7687" # Default URL for local Neo4j
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "12345678" # The password you set in Step 1
NEO4J_DATABASE = "callsanalytics" # The database name you created

# Initialize the connection to Neo4j
try:
    graph = Neo4jGraph(
        url=NEO4J_URL,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE
    )
    print("Successfully connected to Neo4j.")
except Exception as e:
    print(f"Failed to connect to Neo4j: {e}")
    exit()