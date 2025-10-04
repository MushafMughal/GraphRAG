from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import json
import sys
import os
from utils.graphConnection import get_graph_connection


def check_threshold():
    """
    Checks if the highest session ID has reached the next analysis threshold (50, 100, 150, 200, etc.).
    Returns a simple Yes/No (boolean) and the next threshold that needs to be reached.
    """    
    try:
            calls_graph = get_graph_connection(1)

            # Get the highest session ID (similar to get_next_session_id function)
            query = """
            MATCH (cs:CallSession)
            // We extract the numeric part of the session_id
            WITH toInteger(split(cs.session_id, '_')[-1]) AS session_num
            RETURN max(session_num) AS max_id
            """
            
            result = calls_graph.query(query)
            max_session_id = result[0]['max_id'] if result and result[0]['max_id'] is not None else 0

            # Calculate what threshold we should be at based on max_session_id
            # Find the highest threshold that max_session_id has surpassed
            current_threshold_level = (max_session_id // 50) * 50
            next_threshold = current_threshold_level + 50

            # Check if we've reached a new threshold
            if max_session_id >= next_threshold:
                return {
                    "threshold_met": True,
                    "max_session_id": max_session_id,
                    "threshold_reached": next_threshold,
                    "message": f"Threshold of {next_threshold} calls reached. Current max session ID: {max_session_id}."
                }
            else:
                return {
                    "threshold_met": False,
                    "max_session_id": max_session_id,
                    "next_threshold": next_threshold,
                    "sessions_remaining": next_threshold - max_session_id,
                    "message": f"Threshold not met. Current max session ID: {max_session_id}/{next_threshold}. {next_threshold - max_session_id} more sessions needed."
                }
    except Exception as e:
            # If the database is down or the query fails, return an error
            raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
    

if __name__ == "__main__":
    response = check_threshold()
    print(json.dumps(response, indent=2))
