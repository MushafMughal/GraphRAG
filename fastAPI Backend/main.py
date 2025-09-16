from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
import json
import os
from dotenv import load_dotenv
from utils.thresholdChecker import check_threshold
from utils.graphRAG import script_analysis

# Load environment variables
load_dotenv()

# --- Application Setup ---
app = FastAPI(
    title="N8N Cold Calling AI Analysis API",
    description="Provides endpoints to check call thresholds and run GraphRAG analysis.",
    version="1.0.0"
)

# --- API Endpoint 1: The Threshold Checker ---

# Response model for clarity and type safety
class ThresholdCheckResponse(BaseModel):
    threshold_met: bool
    ready_segments: list[str]
    message: str

@app.get("/check-threshold", response_model=ThresholdCheckResponse)
def check_icp_threshold():
    """
    Checks if any IdealTargetCustomer segment has reached the 50-call threshold.
    Returns a simple Yes/No (boolean) and a list of segments that are ready.
    """
    try:
        response = check_threshold()
        return response
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


# --- API Endpoint 2: The GraphRAG Analyzer ---

# Input model for the POST request
class VapiTranscript(BaseModel):
    transcript_text: str
    query: str

# Response model for the analysis results
class RAGAnalysisResponse(BaseModel):
    updatedScript: str
    ICP: str
    
@app.post("/update-script", response_model=RAGAnalysisResponse)
def update_script(transcript: VapiTranscript):
    """
    Takes a VAPI call transcript and a user query, runs it against both the
    calls graph and the PDF graph, and returns the combined results.
    """
    try:

        # response = script_analysis(transcript)
        response = {"vapi_script": "This is a dummy updated script.", "ICP": "ICP 1"}

        return {
            "updatedScript": response.get("vapi_script", ""),
            "ICP": response.get("ICP", "")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG analysis failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)