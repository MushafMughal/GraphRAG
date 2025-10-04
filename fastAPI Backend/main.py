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
from utils.callTranscriptKG import construct_graph

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
    status: bool
    message: str

@app.get("/check-threshold", response_model=ThresholdCheckResponse)
def check_icp_threshold():
    """
    Checks if any IdealTargetCustomer segment has reached the 50-call threshold.
    Returns a simple Yes/No (boolean) and a list of segments that are ready.
    """
    try:
        response = check_threshold()
        # return {
        #     "status": True,
        #     "message": response.get("message")
        # }
        return {
            "status": response.get("threshold_met"),
            "message": response.get("message")
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


# --- API Endpoint 2: Call Transcript KG Construct ---

# Input model for the POST request
class CallTranscript(BaseModel):
    transcript_text: str

# Response model for clarity and type safety
class CallTranscriptResponse(BaseModel):
    status: bool
    message: str
    additional_info: str = None  # Optional field for any extra information

@app.post("/construct-kg", response_model=CallTranscriptResponse)
def construct_kg(transcript: CallTranscript):
    """
    Takes a VAPI call transcript and constructs a knowledge graph from it.
    """
    try:

        # with open(f"/home/GraphRAG/call transcripts/call 1.txt", "r") as f:
        #     call_transcript_raw = f.read()

        response = construct_graph(transcript.transcript_text)

        if not response.get("status"):
            return {"status":response.get("status"), "message":response.get("message"), "additional_info":response.get("step_failed")}

        return {"status":response.get("status"), "message":response.get("message")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph construction failed: {str(e)}")


# --- API Endpoint 3: The GraphRAG Analyzer ---

# Input model for the POST request
class VapiScript(BaseModel):
    vapi_script: str

# Response model for the analysis results
class RAGAnalysisResponse(BaseModel):
    status: bool
    message: str
    
@app.post("/update-script", response_model=RAGAnalysisResponse)
def update_script(transcript: VapiScript):
    """
    Takes a VAPI call transcript and a user query, runs it against both the
    calls graph and the PDF graph, and returns the combined results.
    """
    try:

        # with open('/home/GraphRAG/vapi script.txt', 'r', encoding='utf-8') as f:
        #     vapi_script = f.read()

        response = script_analysis(transcript.vapi_script)
        
        if response.get("vapi_update_status") == 200:
            return {"status": True, "message": "VAPI script updated successfully."}

        if response.get("vapi_update_status") == "N/A - No improvements needed":
            return {"status": True, "message": "No improvements needed for the VAPI script."}
            
        return {"status":False, "message": "VAPI script update failed."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG analysis failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)