from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
import json
import os
from utils.graphConnection import get_graph_connection
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-5-mini", temperature=0)


def get_last10_calls_graph():

    try:
        calls_graph = get_graph_connection(1)
        callschain = GraphCypherQAChain.from_llm(
            graph=calls_graph, llm=llm,
            verbose=True, allow_dangerous_requests=True
        )

        response = callschain.invoke({"query": "give me complete call records for last 2 calls"})
        result = response['result']
        print(result)

        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Calls Graph database: {str(e)}")

def call_script_analysis(transcript, callHistory):
    pass

def get_pdf_context(LLMPrompt):
    pass

def generate_vapi_script(LLMPrompt, callHistory, pdfContext):
        
        # Final LLM call to generate updated VAPI Script 
        summary_prompt = f"""
        You are an AI analyst. You have received two pieces of information to answer a user's query.
        
        User's Query: "{transcript.query}"
        
        Context from Call History Graph: "{llm_insights}"

        Context from Document (PDF) Graph: "{pdf_result}"
        
        Synthesize these two pieces of information into a single, concise answer.
        """
        
        summary_response = llm.invoke(summary_prompt)

        return summary_response.content


def script_analysis(transcript):
    """
    Main function to perform Graph RAG analysis on the given transcript.
    """
    try:
        # Initialize the LLM
        llm = ChatOpenAI(model="gpt-5-mini", temperature=0, openai_api_key=OPENAI_API_KEY)

        # --- Part 1: Get last 10 Calls ---
        recent_calls = get_last10_calls_graph()

        # --- Part 2: Analyze against the PDF Graph ---
        llm_insights = call_script_analysis(transcript, recent_calls)

        # --- Part 3: Get Context/References from PDF ---
        pdf_context = get_pdf_context(transcript)

        # --- Part 4: Combine and Summarize ---
        final_result = generate_vapi_script(llm_insights, recent_calls, pdf_context)

        return {
            "vapi_script": final_result,
            "ICP": "ICP 1"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph RAG analysis failed: {str(e)}")