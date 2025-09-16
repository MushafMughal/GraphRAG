
from langchain_community.graphs import Neo4jGraph
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# --- Neo4j Connection (centralized for reusability) ---
NEO4J_URL = os.getenv("NEO4J_URL")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORDD = os.getenv("NEO4J_PASSWORDD")
NEO4J_DATABASE1 = os.getenv("NEO4J_DATABASE1")
NEO4J_DATABASE2 = os.getenv("NEO4J_DATABASE2")


def get_graph_connection(databaseNo):
    """
    Returns a Neo4jGraph instance for the calls database.
    """
    if databaseNo == 1:
        NEO4J_DATABASE = NEO4J_DATABASE1
    elif databaseNo == 2:
        NEO4J_DATABASE = NEO4J_DATABASE2
    else:
        raise ValueError("Invalid database number. Use 1 or 2.")
    
    return Neo4jGraph(
        url=NEO4J_URL,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORDD,
        database=NEO4J_DATABASE
    )

if __name__ == "__main__":
    graph = get_graph_connection(1)
    print(graph)  # Print the Neo4jGraph instance details

