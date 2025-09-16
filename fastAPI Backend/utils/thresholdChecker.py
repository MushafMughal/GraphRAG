from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import json
import sys
import os
from utils.graphConnection import get_graph_connection


def check_threshold():
    """
    Checks if any IdealTargetCustomer segment has reached the 50-call threshold.
    Returns a simple Yes/No (boolean) and a list of segments that are ready.
    """    
    try:
            calls_graph = get_graph_connection(1)

            # The Cypher query to find segments ready for analysis
            query = """
            MATCH (ic:IdealTargetCustomer)
            WHERE ic.completed_call_count >= 50
            AND (ic.last_analysis_run IS NULL OR ic.completed_call_count > ic.last_analysis_count)
            RETURN ic.segment AS segment_to_analyze
            """
            
            result = calls_graph.query(query)
            
            ready_segments = [record['segment_to_analyze'] for record in result]

            if ready_segments:
                return {
                    "threshold_met": True,
                    "ready_segments": ready_segments,
                    "message": f"Threshold of 50 calls met for segments: {', '.join(ready_segments)}."
                }
            else:
                return {
                    "threshold_met": False,
                    "ready_segments": [],
                    "message": "No customer segments have reached the analysis threshold yet."
                }
    except Exception as e:
            # If the database is down or the query fails, return an error
            raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
    

if __name__ == "__main__":
    response = check_threshold()
    print(json.dumps(response, indent=2))
