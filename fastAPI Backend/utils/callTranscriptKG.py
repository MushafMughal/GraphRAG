import json
from langchain_neo4j import Neo4jGraph
from utils.graphConnection import get_graph_connection
import json
import hashlib
from typing import List, Literal, Optional
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types
import re
import os
from dotenv import load_dotenv
load_dotenv()


# ==============================================================================
# 1. THE BULLETPROOF VALIDATOR (PYDANTIC MODELS) - UPDATED
# ==============================================================================
class CallSession(BaseModel):
    session_id: str
    outcome: Literal["Meeting Scheduled", "Rejected", "Gatekeeper Block", "Voicemail", "Follow-up Required", "Wrong Person", "Call Dropped"]
    product_focus: str
    matched_icp_segment: Optional[str] = None

class Participant(BaseModel):
    name: str
    role: Literal["Agent", "Recipient", "Gatekeeper"]
    organization: Optional[str] = None

class DialogueTurn(BaseModel):
    turn_number: int
    speaker_name: str
    text: str
    # UPDATED to match the new, specific turn types from the final prompt
    turn_type: Literal[
        "Opening", 
        "Closing", 
        "Gatekeeper_Dialogue", 
        "Agent_Question",
        "Agent_Response",
        "Rapport_Building",
        "Customer_Question", 
        "Customer_Response", 
        "Customer_Objection", 
        "Customer_Pain_Point", 
        "Customer_Buying_Signal", 
        "Technical_Issue",

    ]

class DialogueGraphData(BaseModel):
    call_session: CallSession
    participants: List[Participant]
    dialogue_turns: List[DialogueTurn]

# ==============================================================================
# 2. THE UPDATED SCORER
# ==============================================================================

def score_dialogue_extraction(validated_data: DialogueGraphData) -> dict:
    score = 0
    notes = []

    score += len(validated_data.participants) * 5
    if any(p.role == "Gatekeeper" for p in validated_data.participants):
        score += 10
        notes.append("SUCCESS: Gatekeeper correctly identified.")
    
    if validated_data.call_session.outcome == "Meeting Scheduled":
        score += 10
        notes.append("SUCCESS: Meeting outcome captured.")
        
    customer_objections = [t for t in validated_data.dialogue_turns if t.turn_type == 'Customer_Objection']
    customer_pain_points = [t for t in validated_data.dialogue_turns if t.turn_type == 'Customer_Pain_Point']
    customer_buying_signals = [t for t in validated_data.dialogue_turns if t.turn_type == 'Customer_Buying_Signal']

    score += len(customer_objections) * 5
    score += len(customer_pain_points) * 10
    score += len(customer_buying_signals) * 8

    if customer_objections:
        notes.append(f"SUCCESS: Identified {len(customer_objections)} customer objection(s).")
    if customer_pain_points:
        notes.append(f"SUCCESS: Identified {len(customer_pain_points)} customer pain point(s).")
        
    status = "High-confidence" if score > 30 else "Review Recommended"

    return {"final_score": score, "status": status, "notes": notes}

# # ==============================================================================
# # 3. THE ADVANCED INGESTION SCRIPT - UPDATED
# # ==============================================================================

# def ingest_dialogue_flow(graph: Neo4jGraph, validated_data: DialogueGraphData, quality_report: dict):
#     session_query = """
#     MERGE (cs:CallSession {session_id: $session_id})
#     SET cs += $session_details,
#         cs.quality_score = $quality_score,
#         cs.quality_status = $quality_status
    
#     MERGE (p:Product {name: $product_name})
#     MERGE (cs)-[:FOCUSES_ON]->(p)
    
#     WITH cs
#     UNWIND $participants AS participant_data
#     MERGE (person:Person {name: participant_data.name})
#     SET person.role = participant_data.role
#     MERGE (person)-[:PARTICIPATED_IN]->(cs)
#     """
#     graph.query(session_query, params={
#         'session_id': validated_data.call_session.session_id,
#         'session_details': validated_data.call_session.dict(),
#         'quality_score': quality_report['final_score'],
#         'quality_status': quality_report['status'],
#         'product_name': validated_data.call_session.product_focus,
#         'participants': [p.dict() for p in validated_data.participants]
#     })
#     print(f"Ingested CallSession {validated_data.call_session.session_id} with score {quality_report['final_score']}")

#     previous_turn_node_id = None
#     last_customer_objection_id = None

#     for turn in sorted(validated_data.dialogue_turns, key=lambda x: x.turn_number):
#         turn_type_label = "".join(filter(str.isalnum, turn.turn_type))
#         turn_query = f"""
#         MATCH (cs:CallSession {{session_id: $session_id}})
#         MATCH (speaker:Person {{name: $speaker_name}})
#         CREATE (turn_node:{turn_type_label} {{text: $text, turn_number: $turn_number}})
#         CREATE (speaker)-[:MADE_BY]->(turn_node)
#         CREATE (turn_node)-[:RAISED_IN]->(cs)
#         WITH turn_node
#         RETURN id(turn_node) AS current_turn_id
#         """
#         result = graph.query(turn_query, params={
#             'session_id': validated_data.call_session.session_id,
#             'speaker_name': turn.speaker_name, 'text': turn.text,
#             'turn_number': turn.turn_number
#         })
#         current_turn_node_id = result[0]['current_turn_id']

#         if previous_turn_node_id is not None:
#             graph.query(
#                 "MATCH (p) WHERE id(p) = $prev_id MATCH (c) WHERE id(c) = $curr_id CREATE (p)-[:NEXT]->(c)",
#                 {'prev_id': previous_turn_node_id, 'curr_id': current_turn_node_id}
#             )
        
#         # **UPDATED LOGIC** to link Agent_Response to Customer_Objection
#         if turn.turn_type == "Agent_Response" and last_customer_objection_id is not None:
#             graph.query(
#                 "MATCH (r) WHERE id(r) = $resp_id MATCH (o) WHERE id(o) = $obj_id CREATE (r)-[:RESPONDS_TO]->(o)",
#                 {'resp_id': current_turn_node_id, 'obj_id': last_customer_objection_id}
#             )
#             last_customer_objection_id = None # Reset after a response is linked

#         previous_turn_node_id = current_turn_node_id
#         # **UPDATED LOGIC** to track the last objection
#         if turn.turn_type == "Customer_Objection":
#             last_customer_objection_id = current_turn_node_id

#     print(f"Built dialogue chain for CallSession {validated_data.call_session.session_id}")

# ==============================================================================
# 3. THE ADVANCED INGESTION SCRIPT - FINAL, ROBUST VERSION
# ==============================================================================
def ingest_dialogue_flow(graph: Neo4jGraph, validated_data: DialogueGraphData, quality_report: dict):
    # 1. Create/Merge the CallSession and link it to a Product
    session_query = """
    MERGE (cs:CallSession {session_id: $session_id})
    SET cs += $session_details,
        cs.quality_score = $quality_score,
        cs.quality_status = $quality_status
    MERGE (p:Product {name: $product_name})
    MERGE (cs)-[:FOCUSES_ON]->(p)
    """
    graph.query(session_query, params={
        'session_id': validated_data.call_session.session_id,
        'session_details': validated_data.call_session.dict(),
        'quality_score': quality_report['final_score'],
        'quality_status': quality_report['status'],
        'product_name': validated_data.call_session.product_focus
    })
    print(f"Ingested CallSession {validated_data.call_session.session_id} with score {quality_report['final_score']}")

    # 2. Ensure all participants from the list exist as nodes and are linked to the call
    # This step is a good "pre-creation" step to set their roles correctly.
    participants_query = """
    MATCH (cs:CallSession {session_id: $session_id})
    UNWIND $participants AS participant_data
    MERGE (p:Person {name: participant_data.name})
    SET p.role = participant_data.role
    MERGE (p)-[:PARTICIPATED_IN]->(cs)
    """
    graph.query(participants_query, params={
        'session_id': validated_data.call_session.session_id,
        'participants': [p.dict() for p in validated_data.participants]
    })

    # 3. Build the conversation chain
    previous_turn_node_id = None
    last_customer_objection_id = None

    for turn in sorted(validated_data.dialogue_turns, key=lambda x: x.turn_number):
        turn_type_label = "".join(filter(str.isalnum, turn.turn_type))
        
        # **THIS IS THE CRITICAL FIX**
        # We use MERGE for the speaker. This finds the speaker if they exist
        # OR creates them if the LLM hallucinated a speaker name not in the
        # original participants list. This prevents the MATCH from failing.
        turn_query = f"""
        MATCH (cs:CallSession {{session_id: $session_id}})
        MERGE (speaker:Person {{name: $speaker_name}})
        
        CREATE (turn_node:{turn_type_label} {{
            text: $text, 
            turn_number: $turn_number
        }})
        
        CREATE (speaker)-[:MADE_BY]->(turn_node)
        CREATE (turn_node)-[:RAISED_IN]->(cs)
        
        WITH turn_node
        RETURN id(turn_node) AS current_turn_id
        """
        
        result = graph.query(turn_query, params={
            'session_id': validated_data.call_session.session_id,
            'speaker_name': turn.speaker_name,
            'text': turn.text,
            'turn_number': turn.turn_number
        })

        # This check prevents the IndexError
        if not result or 'current_turn_id' not in result[0]:
            print(f"WARNING: Turn creation failed for turn number {turn.turn_number}. Skipping relationship creation for this turn.")
            continue # Skip to the next turn

        current_turn_node_id = result[0]['current_turn_id']

        if previous_turn_node_id is not None:
            graph.query(
                "MATCH (p) WHERE id(p) = $prev_id MATCH (c) WHERE id(c) = $curr_id CREATE (p)-[:NEXT]->(c)",
                {'prev_id': previous_turn_node_id, 'curr_id': current_turn_node_id}
            )
        
        # Updated logic to use the specific turn types
        if turn.turn_type == "Agent_Response" and last_customer_objection_id is not None:
            graph.query(
                "MATCH (r) WHERE id(r) = $resp_id MATCH (o) WHERE id(o) = $obj_id CREATE (r)-[:RESPONDS_TO]->(o)",
                {'resp_id': current_turn_node_id, 'obj_id': last_customer_objection_id}
            )
            last_customer_objection_id = None

        previous_turn_node_id = current_turn_node_id
        if turn.turn_type == "Customer_Objection":
            last_customer_objection_id = current_turn_node_id

    print(f"Built dialogue chain for CallSession {validated_data.call_session.session_id}")


# ==============================================================================
# 4. FUNCTION TO GET THE NEXT AVAILABLE SESSION ID FROM NEO4J
# ==============================================================================
def get_next_session_id(graph: Neo4jGraph) -> int:
    """
    Queries the graph to find the highest existing session_id and returns the next number.
    """
    query = """
    MATCH (cs:CallSession)
    // We extract the numeric part of the session_id
    WITH toInteger(split(cs.session_id, '_')[-1]) AS session_num
    RETURN max(session_num) AS max_id
    """
    try:
        result = graph.query(query)
        if result and result[0]['max_id'] is not None:
            # If there are existing calls, return the max ID + 1
            return result[0]['max_id'] + 1
        else:
            # If the graph is empty, start at 1
            return 1
    except Exception as e:
        print(f"Could not query for max session ID. Defaulting to 1. Error: {e}")
        return 1
    


# ==============================================================================
# 5. FUNCTION TO BUILD THE DIALOGUE FLOW JSON USING THE NER PROMPT
# ==============================================================================
def dialogue_flow_ner(apiClient_key, transcript_text):
    """
    Create the dialogue flow of the raw transcript text into the graph.
    """

    ner_system_prompt = """You are a master data architect. Your task is to convert a call transcript into a structured JSON object representing the dialogue flow. Follow the schema and definitions with extreme precision.

### CRITICAL RULES:
1.  **MODEL THE DIALOGUE FLOW:** The `dialogue_turns` array MUST be a chronological sequence of the entire conversation.
2.  **USE THE PROVIDED DEFINITIONS:** You MUST use the exact `turn_type` definitions provided below. Do not deviate.

---

### JSON SCHEMA:

1.  **`call_session` (Object):**
    *   `session_id`: A unique ID for the call (e.g., "call_transcript_1").
    *   `outcome`: You MUST choose EXACTLY one value from this list: `["Meeting Scheduled", "Rejected", "Gatekeeper Block", "Voicemail", "Follow-up Required", "Wrong Person", "Call Dropped"]`.
    *   `product_focus`: The main product discussed (e.g., "NLA Security Solution").

2.  **`participants` (Array of Objects):**
    *   `name`: Full name of the participant (e.g., "Arison Josh", "Dale Spear", "Unnamed Gatekeeper").
    *   `role`: MUST be one of: `["Agent", "Recipient", "Gatekeeper"]`.
    *   `organization`: The organization they belong to.

3.  **`dialogue_turns` (Array of Chronological Objects):**
    *   Each object represents one speaking turn and must have:
        *   `turn_number`: A sequential integer starting from 1.
        *   `speaker_name`: The name of the speaker.
        *   `text`: The EXACT quote.
        *   `turn_type`: **You MUST choose EXACTLY one value from this list based on these PLAIN ENGLISH definitions:**
            ### Agent-Centric Labels
            - **Opening**: The agent's very first lines to the decision-maker. (e.g., "Hi Sarah, this is James from Acme Corp. Thanks for taking the time.")
            - **Closing**: The agent's last few lines before the call ends. (e.g., "Thankyou for the time, I'll send over the info by email.")
            - **Gatekeeper_Dialogue**: Any exchange that happens `before` the decision-maker is on the line (includes both agent + gatekeeper). (e.g., "Can I speak with Mr. Davis?", "He's not available right now")
            - **Agent_Question**: When the agent asks a question to gather information or move the conversation forward. (e.g., "Are you currently using outside counsel for compliance?")
            - **Agent_Response**: When the agent directly answers a customer's question, objection, pain point, or buying signal. (e.g., "We already have a vendor. → Agent: Totally understand. Many of our clients started in the same place.")
            - **Rapport_Building**: Non-business, relationship-focused statements or light humor. (e.g., "Hope you had a good weekend.", "I'm a pancake person too.")

            ### Customer-Centric Labels
            - **Customer_Question**: Customer asks for clarity, detail, or next steps. (e.g., "Can you explain how that works", "What's the cost?")
            - **Customer_Response**: Neutral or factual statements that do not qualify as a question, objection, pain point, or buying signal. (e.g., "No, I'm not the right person.", "I work in finance, not compliance.", "Okay.")
              ⚠️ **Note:** A simple "No" or "Not really" → goes here **unless** it explicitly conveys resistance to the product/meeting (in which case it is a `Customer_Objection`).
            - **Customer_Objection**: Customer resists, refuses, or dismisses the agent's proposal. (e.g., "We're not interested.", "We already have a provider.")
              ⚠️ **Important:** A normal "No" or short denial **does not count as an objection** unless it is clearly rejecting the agent's pitch or request.
            - **Customer_Pain_Point**: Customer explicitly mentions a business problem, risk, or dissatisfaction. (e.g., "We've had compliance gaps in the past.", "That would probably result in a lawsuit.")
            - **Customer_Buying_Signal**: Customer shows agreement, alignment, or willingness to continue. (e.g., "Yes, that sounds relevant," "Yes, I am available," "That's correct.").

            ### System / Meta Labels
            - **Technical_Issue**: Mentions of call quality problems, pauses, or audio glitches. (e.g., "Are you there?", "There's a long pause.")

---

Example of a Perfect Output Structure:
```json
{
  "call_session": {
    "session_id": "call_transcript_1",
    "outcome": "Meeting Scheduled",
    "product_focus": "Georgia Senate Bill 68 compliance solution"
  },
  "participants": [
    {
      "name": "Arison",
      "role": "Agent",
      "organization": "NLA Investigative Division"
    },
    {
      "name": "Unnamed Gatekeeper",
      "role": "Gatekeeper",
      "organization": "Not Provided"
    },
    {
      "name": "Dale Spear",
      "role": "Recipient",
      "organization": "Not Provided"
    }
  ],
  "dialogue_turns": [
    {
      "speaker": "Agent",
      "text": "Hi Sarah, this is James from Acme Corp. Thanks for taking the time.",
      "labels": "Opening"
    },
    {
      "speaker": "Customer",
      "text": "What does your company do exactly?",
      "labels": "Customer_Question"
    },
    {
      "speaker": "Agent",
      "text": "Great question — we help firms reduce compliance risk by automating workflows.",
      "labels": "Agent_Response"
    },
    {
      "speaker": "Customer",
      "text": "We've had issues in the past with missed filings.",
      "labels": "Customer_Pain_Point"
    },
    {
      "speaker": "Agent",
      "text": "That's exactly where we can help — most clients see a 40% reduction in errors.",
      "labels": "Agent_Response"
    },
    {
      "speaker": "Customer",
      "text": "Yes, that sounds relevant. Can you send me more info?",
      "labels": "Customer_Buying_Signal"
    },
    {
      "speaker": "Agent",
      "text": "Absolutely, I'll follow up with details this afternoon.",
      "labels": "Closing"
    }
  ]
}```"""

    user_prompt = f"""Transcript:
    {transcript_text}
"""

    
    client = OpenAI(api_key=apiClient_key)
    response = client.responses.create(
        model="gpt-5-mini",
        instructions=ner_system_prompt,
        input=user_prompt,
    )
    output = response.output_text
    clean_text = re.sub(r"^```json\s*|\s*```$", "", output.strip())
    
    
    return clean_text
    # return json.loads(clean_text)


# ==============================================================================
# 6. **NEW**: THE ICP CLASSIFIER AND LINKER
# ==============================================================================
def classify_and_link_icp(graph, api_key, transcript_text, recipient_name):
    """
    Classifies a transcript against existing ICPs in the graph and links the recipient.
    """

    # Step A: Classify the transcript using the LLM
    system_classification_prompt = f"""You are an expert sales analyst. 
Classify the call transcript into one of these ICP segments. 

Available Segments:
1. Retail-Enterprise
   - Typical job titles: VP Procurement, Chief Security Officer, Property Manager
   - Key pain points: cost, vendor lock-in, integration, compliance
   - Industries: retail chains, consumer goods, property management

2. Healthcare-Enterprise
   - Typical job titles: CIO, CTO, Director IT Security, CCSFP
   - Key pain points: HIPAA compliance, patient data security, interoperability
   - Industries: hospitals, healthcare systems

3. Manufacturing-Enterprise
   - Typical job titles: COO, VP Safety, Head of Logistics
   - Key pain points: downtime, workforce compliance, legacy system upgrades
   - Industries: factories, industrial facilities

4. Financial-SME
   - Typical job titles: Head of Security, Executive Protection Leader, Lawyer, Attorney, Partner (Law Firm)
   - Key pain points: integration, vendor support, budget
   - Industries: finance, small firms, family offices, law firms / legal practices

5. Film-Entertainment
   - Typical job titles: Studio Exec, Producer, Head of Distribution
   - Key pain points: IP leakage, production delays, talent management
   - Industries: studios, entertainment, media

Rules:
- Look for **industry keywords** and **job titles** first (highest priority).
- Use **pain points only if industry clues are missing**.
- If no match is clear, output "General".

**Response format:** Output only the segment name (e.g., Retail-Enterprise).
"""

    user_prompt = f"""Call Transcript:
    {transcript_text}
    """

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model="gpt-5-mini",
        instructions=system_classification_prompt,
        input=user_prompt,
    )
    matched_segment = response.output_text
    
    print(f"LLM classified recipient profile as: {matched_segment}")

    # Step B: Create the relationship in the graph and increment the counter
    if matched_segment != "General":
        link_query = """
        MATCH (p:Person {name: $recipient_name})
        MATCH (ic:IdealTargetCustomer {segment: $segment})
        MERGE (p)-[:MATCHES_PROFILE]->(ic)
        SET ic.completed_call_count = coalesce(ic.completed_call_count, 0) + 1
        """
        graph.query(link_query, params={'recipient_name': recipient_name, 'segment': matched_segment})
        print(f"Linked '{recipient_name}' to '{matched_segment}' and incremented counter.")
        
    return matched_segment


# ==============================================================================
# FINAL MAIN WORKFLOW FUNCTION - UPDATED WITH YOUR IDEA
# ==============================================================================
def process_single_transcript(graph, api_key, raw_transcript_text, session_id, path):
    
    # STEP 1: EXTRACT (LLM Call 1 - The Heavy Lifter)
    try:
        llm_output = dialogue_flow_ner(api_key, raw_transcript_text)
    except Exception as e:
        error_message = f"[call_transcript_{session_id}] STEP 1 FAILED: Could not extract dialogue flow from transcript. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "extraction"}
    
    # Inject the correct sequential ID
    try:
        data = json.loads(llm_output)
        data['call_session']['session_id'] = f"call_transcript_{session_id}"
        llm_output_json_with_id = json.dumps(data)
    except Exception as e:
        error_message = f"[call_transcript_{session_id}] STEP 1 FAILED: Could not parse LLM output as JSON. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "json_parsing"}

    # Save raw LLM output to a file for auditing
    try:
        with open(f"{path}/call_transcript_{session_id}_raw.json", "w") as f:
            f.write(llm_output_json_with_id)
        print(f"[call_transcript_{session_id}] Raw LLM output saved.")
    except Exception as e:
        error_message = f"[call_transcript_{session_id}] WARNING: Could not save raw output file. Error: {str(e)}"
        print(error_message)
        # Continue processing even if file save fails

    # STEP 2(A): VALIDATE the initial structure
    try:
        validated_data = DialogueGraphData.parse_raw(llm_output_json_with_id)
        print(f"[{validated_data.call_session.session_id}] Initial Pydantic Validation SUCCESSFUL.")
    except ValidationError as e:
        error_message = f"[call_transcript_{session_id}] STEP 2 FAILED: Pydantic validation failed. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "validation"}
    except Exception as e:
        error_message = f"[call_transcript_{session_id}] STEP 2 FAILED: Unexpected error during validation. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "validation"}
    
    # STEP 2(B): NORMALIZE SPEAKER NAMES
    try:
        participant_names = {p.name.lower().strip(): p.name for p in validated_data.participants}
        for turn in validated_data.dialogue_turns:
            norm = turn.speaker_name.lower().strip()
            if norm in participant_names:
                turn.speaker_name = participant_names[norm]
            else:
                print(f"WARNING: Speaker '{turn.speaker_name}' not found in participants "
                      f"for session '{validated_data.call_session.session_id}' "
                      f"(turn {turn.turn_number})")
    except Exception as e:
        error_message = f"[{validated_data.call_session.session_id}] STEP 2 FAILED: Speaker name normalization failed. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "speaker_normalization"}

    # STEP 3: **NEW** - CLASSIFY and ENRICH the validated data object
    try:
        recipient = next((p for p in validated_data.participants if p.role == "Recipient"), None)
        if recipient:
            # This function returns the name of the matched segment (e.g., "Healthcare-Enterprise")
            matched_segment = classify_and_link_icp(graph, api_key, raw_transcript_text, recipient.name)
            
            # We add the result directly to our data object.
            validated_data.call_session.matched_icp_segment = matched_segment
            print(f"[{validated_data.call_session.session_id}] Data enriched with ICP segment: '{matched_segment}'")
    except Exception as e:
        error_message = f"[{validated_data.call_session.session_id}] STEP 3 FAILED: ICP classification and enrichment failed. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "icp_enrichment"}

    # Save enriched data to a file for auditing
    try:
        with open(f"{path}/call_transcript_{session_id}_enriched.json", "w") as f:
            f.write(validated_data.model_dump_json(indent=2))
        print(f"[{validated_data.call_session.session_id}] Enriched data saved.")
    except Exception as e:
        error_message = f"[{validated_data.call_session.session_id}] WARNING: Could not save enriched data file. Error: {str(e)}"
        print(error_message)
        # Continue processing even if file save fails

    # STEP 4: SCORE the now-enriched, clean data
    try:
        quality_report = score_dialogue_extraction(validated_data)
        print(f"[{validated_data.call_session.session_id}] Quality Score Calculated: {quality_report['final_score']}")
    except Exception as e:
        error_message = f"[{validated_data.call_session.session_id}] STEP 4 FAILED: Quality scoring failed. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "quality_scoring"}

    # Save quality report to a file for auditing
    try:
        with open(f"{path}/call_transcript_{session_id}_quality_report.json", "w") as f:
            json.dump(quality_report, f, indent=2)
        print(f"[{validated_data.call_session.session_id}] Quality report saved.")
    except Exception as e:
        error_message = f"[{validated_data.call_session.session_id}] WARNING: Could not save quality report file. Error: {str(e)}"
        print(error_message)
        # Continue processing even if file save fails

    # STEP 5: INGEST the final, enriched data
    try:
        ingest_dialogue_flow(graph, validated_data, quality_report)
    except Exception as e:
        error_message = f"[{validated_data.call_session.session_id}] STEP 5 FAILED: Graph ingestion failed. Error: {str(e)}"
        print(error_message)
        return {"status": False, "message": error_message, "step_failed": "graph_ingestion"}

    message = f"[{validated_data.call_session.session_id}] Full processing complete successfully."
    print(message)
    
    result = {
        "status": True, 
        "message": message,
        "session_id": validated_data.call_session.session_id,
        "quality_score": quality_report['final_score']
    }
    return result


# ==============================================================================
# MAIN EXECUTION BLOCK
# ==============================================================================

def construct_graph(call_transcript):

    try:
        graph = get_graph_connection(1)
        print("Successfully connected to Neo4j.")
    except Exception as e:
        print(f"Failed to connect to Neo4j: {e}")
        exit()

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Get the starting ID for this batch
    current_session_id = get_next_session_id(graph) 

    print(f"\n--- Processing Transcript # {current_session_id} ---")

    # create seprate path to save outputs
    path = f"/home/GraphRAG/call outputs/call_{current_session_id}"
    if not os.path.exists(path):
        os.makedirs(path)

    result = process_single_transcript(graph, OPENAI_API_KEY, call_transcript, current_session_id, path)
    print(f"Result: {result}")

    return result

if __name__ == "__main__":
        
        with open(f"/home/GraphRAG/call transcripts/call 4.txt", "r") as f:
            transcript_text = f.read()
        
        construct_graph(transcript_text)
