import json
from langchain_neo4j import Neo4jGraph
import json
import hashlib
from typing import List, Literal, Optional
from openai import OpenAI
from pydantic import BaseModel, ValidationError
import re

# --- Connection Details ---
NEO4J_URL = "bolt://127.0.0.1:7687" # Default URL for local Neo4j
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "12345678" # The password you set in Step 1
NEO4J_DATABASE = "callsanalytics" # The database name you created
api_key = "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"


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
        "Customer_Question", 
        "Customer_Objection", 
        "Customer_Pain_Point", 
        "Customer_Buying_Signal", 
        "Agent_Response"
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

# ==============================================================================
# 3. THE ADVANCED INGESTION SCRIPT - UPDATED
# ==============================================================================

def ingest_dialogue_flow(graph: Neo4jGraph, validated_data: DialogueGraphData, quality_report: dict):
    session_query = """
    MERGE (cs:CallSession {session_id: $session_id})
    SET cs += $session_details,
        cs.quality_score = $quality_score,
        cs.quality_status = $quality_status
    
    MERGE (p:Product {name: $product_name})
    MERGE (cs)-[:FOCUSES_ON]->(p)
    
    WITH cs
    UNWIND $participants AS participant_data
    MERGE (person:Person {name: participant_data.name})
    SET person.role = participant_data.role
    MERGE (person)-[:PARTICIPATED_IN]->(cs)
    """
    graph.query(session_query, params={
        'session_id': validated_data.call_session.session_id,
        'session_details': validated_data.call_session.dict(),
        'quality_score': quality_report['final_score'],
        'quality_status': quality_report['status'],
        'product_name': validated_data.call_session.product_focus,
        'participants': [p.dict() for p in validated_data.participants]
    })
    print(f"Ingested CallSession {validated_data.call_session.session_id} with score {quality_report['final_score']}")

    previous_turn_node_id = None
    last_customer_objection_id = None

    for turn in sorted(validated_data.dialogue_turns, key=lambda x: x.turn_number):
        turn_type_label = "".join(filter(str.isalnum, turn.turn_type))
        turn_query = f"""
        MATCH (cs:CallSession {{session_id: $session_id}})
        MATCH (speaker:Person {{name: $speaker_name}})
        CREATE (turn_node:{turn_type_label} {{text: $text, turn_number: $turn_number}})
        CREATE (speaker)-[:MADE_BY]->(turn_node)
        CREATE (turn_node)-[:RAISED_IN]->(cs)
        WITH turn_node
        RETURN id(turn_node) AS current_turn_id
        """
        result = graph.query(turn_query, params={
            'session_id': validated_data.call_session.session_id,
            'speaker_name': turn.speaker_name, 'text': turn.text,
            'turn_number': turn.turn_number
        })
        current_turn_node_id = result[0]['current_turn_id']

        if previous_turn_node_id is not None:
            graph.query(
                "MATCH (p) WHERE id(p) = $prev_id MATCH (c) WHERE id(c) = $curr_id CREATE (p)-[:NEXT]->(c)",
                {'prev_id': previous_turn_node_id, 'curr_id': current_turn_node_id}
            )
        
        # **UPDATED LOGIC** to link Agent_Response to Customer_Objection
        if turn.turn_type == "Agent_Response" and last_customer_objection_id is not None:
            graph.query(
                "MATCH (r) WHERE id(r) = $resp_id MATCH (o) WHERE id(o) = $obj_id CREATE (r)-[:RESPONDS_TO]->(o)",
                {'resp_id': current_turn_node_id, 'obj_id': last_customer_objection_id}
            )
            last_customer_objection_id = None # Reset after a response is linked

        previous_turn_node_id = current_turn_node_id
        # **UPDATED LOGIC** to track the last objection
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

    ner_system_prompt = f"""You are a master data architect. Your task is to convert a call transcript into a structured JSON object representing the dialogue flow. Follow the schema and definitions with extreme precision.

### CRITICAL RULES:
1.  **MODEL THE DIALOGUE FLOW:** The `dialogue_turns` array MUST be a chronological sequence of the entire conversation.
2.  **USE THE PROVIDED DEFINITIONS:** You MUST use the exact `turn_type` definitions provided below. Do not deviate.

---

### JSON SCHEMA:

1.  **`call_session` (Object):**
    *   `session_id`: A unique ID for the call (e.g., "call_transcript_1").
    *   `outcome`: MUST be one of: `["Meeting Scheduled", "Rejected", "Gatekeeper Block"]`.
    *   `product_focus`: The main product discussed.

2.  **`participants` (Array of Objects):**
    *   `name`: Full name of the participant (e.g., "Arison", "Dale Spear", "Unnamed Gatekeeper").
    *   `role`: MUST be one of: `["Agent", "Recipient", "Gatekeeper"]`.
    *   `organization`: The organization they belong to.

3.  **`dialogue_turns` (Array of Chronological Objects):**
    *   Each object represents one speaking turn and must have:
        *   `turn_number`: A sequential integer starting from 1.
        *   `speaker_name`: The name of the speaker.
        *   `text`: The EXACT quote.
        *   `turn_type`: **You MUST choose EXACTLY one value from this list based on these PLAIN ENGLISH definitions:**
            *   **`Opening`**: The agent's first few lines to the decision-maker.
            *   **`Closing`**: The agent's final few lines to wrap up the call.
            *   **`Gatekeeper_Dialogue`**: ANY turn, from either speaker, that happens before the decision-maker is on the line.
            *   **`Agent_Question`**: Any turn where the AGENT asks a question to gather information or move the conversation forward.
            *   **`Customer_Question`**: Any turn where the CUSTOMER asks a question for clarification.
            *   **`Customer_Objection`**: Any turn where the CUSTOMER shows resistance, says no, or expresses a lack of awareness. (e.g., "We're not interested," "No, we haven't heard of that.").
            *   **`Customer_Pain_Point`**: Any turn where the CUSTOMER explicitly mentions a business problem or risk. (e.g., "That would probably result in a lawsuit.").
            *   **`Customer_Buying_Signal`**: Any turn where the CUSTOMER shows clear agreement or interest. (e.g., "Yes, that sounds relevant," "Yes, I am available," "That's correct.").
            *   **`Agent_Response`**: Any turn where the AGENT is directly answering a customer's question or responding to their objection/pain point/buying signal.

---
Example of a Perfect Output Structure:
```json
{{
  "dialogue_turns": [
    {{
      "turn_number": 1,
      "speaker_name": "Arison",
      "text": "Hi. Is compliance available?",
      "turn_type": "Gatekeeper_Dialogue"
    }},
    {{
      "turn_number": 2,
      "speaker_name": "Unnamed Gatekeeper",
      "text": "Is not available.",
      "turn_type": "Gatekeeper_Dialogue"
    }},
    {{
      "turn_number": 14,
      "speaker_name": "Dale",
      "text": "Yes. I'd definitely sounds relevant to my organization.",
      "turn_type": "Customer_Buying_Signal"
    }},
    {{
      "turn_number": 15,
      "speaker_name": "Arison",
      "text": "I'm glad to hear that, Dale. For your privacy...",
      "turn_type": "Agent_Response"
    }}
  ]
}}
"""

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
1. Property-Managers
   - Typical job titles: Property Manager, VP Procurement, Chief Security Officer, Facilities Director
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

4. Law-Firms
   - Typical job titles: Head of Security, Executive Protection Leader, Lawyer, Attorney, Partner, Managing Partner 
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

**Response format:** Output only the segment name (e.g., Property-Managers).
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
def process_single_transcript(graph, api_key, raw_transcript_text, session_id):
    
    # STEP 1: EXTRACT (LLM Call 1 - The Heavy Lifter)
    try:
        llm_output = dialogue_flow_ner(api_key, raw_transcript_text)
    except:
        print(f"ERROR: Could not generate file. Aborting...")
        return None
    
    # Inject the correct sequential ID
    data = json.loads(llm_output)
    data['call_session']['session_id'] = f"call_transcript_{session_id}"
    llm_output_json_with_id = json.dumps(data)

    # STEP 2: VALIDATE the initial structure
    try:
        validated_data = DialogueGraphData.parse_raw(llm_output_json_with_id)
        print(f"[{validated_data.call_session.session_id}] Initial Pydantic Validation SUCCESSFUL.")
    except ValidationError as e:
        print(f"[{validated_data.call_session.session_id}] VALIDATION FAILED: {e}")
        return

    # STEP 3: **NEW** - CLASSIFY and ENRICH the validated data object
    recipient = next((p for p in validated_data.participants if p.role == "Recipient"), None)
    if recipient:
        # This function returns the name of the matched segment (e.g., "Healthcare-Enterprise")
        matched_segment = classify_and_link_icp(graph, api_key, raw_transcript_text, recipient.name)
        
        # We add the result directly to our data object.
        validated_data.call_session.matched_icp_segment = matched_segment
        print(f"[{validated_data.call_session.session_id}] Data enriched with ICP segment: '{matched_segment}'")

    # STEP 4: SCORE the now-enriched, clean data
    quality_report = score_dialogue_extraction(validated_data)
    print(f"[{validated_data.call_session.session_id}] Quality Score Calculated: {quality_report['final_score']}")

    # STEP 5: INGEST the final, enriched data
    ingest_dialogue_flow(graph, validated_data, quality_report)
    
    print(f"[{validated_data.call_session.session_id}] Full processing complete.")
    
    # Return the final, complete data object for inspection
    return validated_data


# ==============================================================================
# MAIN EXECUTION BLOCK
# ==============================================================================

if __name__ == '__main__':

    # Initialize Neo4j connection
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

    # print("Clearing existing graph for a fresh start...")
    # graph.query("MATCH (n) DETACH DELETE n")

    for i in range(1, 5):

        # Get the starting ID for this batch
        current_session_id = get_next_session_id(graph) 

        print(f"\n--- Processing Transcript #{current_session_id} ---")

        with open(f"call transcripts/call {i}.txt", "r") as f:
            transcript_text = f.read()

        process_single_transcript(graph,api_key, transcript_text, current_session_id)
        print("x------------------x--------------x"*3)