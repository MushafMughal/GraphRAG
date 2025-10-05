from fastapi import FastAPI, HTTPException, Body
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
import json
import os
import requests
from utils.graphConnection import get_graph_connection
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def get_last_n_call_records(limit):
    """
    Retrieves the complete records for the last 'n' calls directly using an
    efficient Cypher query.

    Args:
        limit (int): The number of recent calls to retrieve. Defaults to 2.

    Returns:
        list: A list of dictionaries, where each dictionary is a detailed
              record of a call. Returns an empty list if an error occurs.
    """
    print(f"Attempting to retrieve the last {limit} call records...")
    
    try:
        # Establish the graph connection
        graph = get_graph_connection(1)

        # This Cypher query fetches all data related to the most recent calls
        query = """
        // 1. Find all CallSession nodes
        MATCH (cs:CallSession)
        
        // 2. Order them by session_id's numeric part to get the latest first
        WITH cs
        ORDER BY toInteger(split(cs.session_id, '_')[-1]) DESC
        LIMIT $limit // 3. Limit to the number of calls requested
        
        // 4. For these latest calls, find all the participants
        MATCH (p:Person)-[:PARTICIPATED_IN]->(cs)
        
        // 5. And find all the dialogue turns associated with these calls
        MATCH (turn)-[:RAISED_IN]->(cs)
        
        // 6. Collect all data into a structured format for each call
        // We collect participants and turns separately for each call session
        WITH cs, collect(DISTINCT p.name) AS participants, collect(turn) AS turns
        
        // 7. Unwind the turns again so we can order them
        UNWIND turns AS turn
        WITH cs, participants, turn
        ORDER BY turn.turn_number ASC
        
        // 8. Collect the ordered turns and return the final structure
        RETURN 
            cs.session_id AS session_id,
            cs.outcome AS outcome,
            cs.quality_score AS quality_score,
            participants,
            collect({
                turn_number: turn.turn_number, 
                speaker_name: [(turn)<-[:MADE_BY]-(s:Person) | s.name][0], // Find the speaker
                turn_type: labels(turn)[0], // e.g., 'CustomerObjection'
                text: turn.text
            }) AS dialogue_flow
        ORDER BY toInteger(split(session_id, '_')[-1]) ASC // Final sort for readability
        """

        # Execute the query
        result = graph.query(query, params={"limit": limit})
        
        if not result:
            print("No call records found in the database.")
            return []
            
        print(f"Successfully retrieved {len(result)} call record(s).")
        with open('calls.json', 'w') as f:
            json.dump(result, f, indent=4)

        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Calls Graph database: {str(e)}")


def get_last10_calls_graph():
    try:
        llm = ChatOpenAI(model="gpt-5-mini", temperature=0, openai_api_key=OPENAI_API_KEY)
        calls_graph = get_graph_connection(1)
        callschain = GraphCypherQAChain.from_llm(
            graph=calls_graph, llm=llm,
            verbose=True, allow_dangerous_requests=True
        )

        response = callschain.invoke({"query": "give me complete call records for last 10 calls"})
        result = response['result']
        print(result)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Calls Graph database: {str(e)}")



def call_script_analysis(call_records, vapi_script):
    """
    Analyzes call records against the VAPI script using OpenAI GPT-4o-mini.
    Returns insights on what improvements can be made to the specific sections.
    
    Args:
        call_records (list): List of call records from the database
        vapi_script (str): The complete VAPI script content
        
    Returns:
        str: Analysis and improvement insights from OpenAI
    """
    try:
        # Initialize the LLM
        llm = ChatOpenAI(model="gpt-5-mini", temperature=0, openai_api_key=OPENAI_API_KEY)

        # Define the 12 sections to analyze
        sections_to_analyze = [
            "SECTION 1; type='hook' id='hook_1' target='general-business'",
            "SECTION 2; type='objection' id='obj_1' category='email-privacy-concern'",
            "SECTION 3; type='objection' id='obj_2' category='phone-privacy-concern'",
            "SECTION 4; type='objection' id='obj_3' category='phone-privacy-concern'",
            "SECTION 5; type='objection' id='obj_4' category='phone-privacy-concern'",
            "SECTION 6; type='objection' id='obj_5' category='information-privacy-concern'",
            "SECTION 7; type='hook' id='hook_2' target='general-business'",
            "SECTION 8; type='objection' id='obj_6' category='we-have-a-solution'",
            "SECTION 9; type='objection' id='obj_7' category='we-have-a-solution'",
            "SECTION 10; type='objection' id='obj_8' category='send-information'",
            "SECTION 11; type='closing' id='close_1' style='meeting-request'",
            "SECTION 12; type='commitment-check' id='close_1' style='meeting-request'"
        ]
        
        # Create the analysis prompt
        analysis_prompt = f"""
        You are an expert sales script analyst specializing in cold calling optimization and conversion rate improvement.
        
        CRITICAL INSTRUCTION: Only recommend improvements for sections that show clear evidence of poor performance or missed opportunities in the actual call data. If a section is performing well or not being used, explicitly state "NO IMPROVEMENT NEEDED" and explain why.
        
        **CALL RECORDS DATA:**
        Here are the last 10 call records from our database:
        {json.dumps(call_records, indent=2)}
        
        **CURRENT VAPI SCRIPT:**
        {vapi_script}
        
        **SECTIONS TO ANALYZE (Priority Focus Areas):**
        Please specifically analyze these 12 sections and provide targeted improvement recommendations ONLY WHERE NEEDED:
        
        1. {sections_to_analyze[0]}
        2. {sections_to_analyze[1]} 
        3. {sections_to_analyze[2]}
        4. {sections_to_analyze[3]}
        5. {sections_to_analyze[4]}
        6. {sections_to_analyze[5]}
        7. {sections_to_analyze[6]}
        8. {sections_to_analyze[7]}
        9. {sections_to_analyze[8]}
        10. {sections_to_analyze[9]}
        11. {sections_to_analyze[10]}
        12. {sections_to_analyze[11]}
        
        **ANALYSIS REQUIREMENTS:**
        
        1. **Evidence-Based Performance Analysis**: 
           - Analyze actual call outcomes, quality scores, and dialogue patterns from the data
           - Don't rely too much on the quality scores alone; focus on real dialogue and outcomes
           - Look for sections that were actually used vs. those that weren't needed
           - Identify patterns where specific sections led to positive or negative outcomes
           - Note if customers objected, hung up, or showed resistance after certain sections
        
        2. **Section-Specific Recommendations**: 
           For each of the 12 sections above, provide ONE OF THESE RESPONSES:
           
           **Option A - If section needs improvement:**
           - Evidence from call data showing poor performance
           - Specific improvement recommendations based on actual issues observed
           - Suggested alternative approaches or language
           
           **Option B - If section is performing well:**
           - State "NO IMPROVEMENT NEEDED"
           - Cite evidence from call data showing good performance
           - Explain why this section is working effectively
           
           **Option C - If section wasn't used/tested:**
           - State "NOT EVALUATED - No data available"
           - Explain that this section didn't occur in the analyzed calls
           - Note if this is normal (e.g., objection handling when no objections occurred)
        
        3. **Performance Context**:
           - Call success rate (meetings scheduled vs. total calls)
           - Average quality scores and what they indicate
           - Overall script effectiveness based on actual outcomes
        
        4. **Structured Output Format**:
           
           ## OVERALL PERFORMANCE SUMMARY
           **Call Success Rate**: X out of Y calls resulted in [outcome]
           **Average Quality Score**: X/100
           **Overall Assessment**: [Brief assessment of whether the script is working well or needs major changes]
           
           ## SECTION-BY-SECTION ANALYSIS
           
           ### Section 1: Hook 1 (hook_1)
           **Status**: [NEEDS IMPROVEMENT / NO IMPROVEMENT NEEDED / NOT EVALUATED]
           **Evidence**: [Specific evidence from call data]
           **Action**: [Specific recommendations OR explanation why no action needed]
           
           [Continue for all 12 sections...]
           
           ## IMPROVEMENT SECTIONS
           If at least one section requires improvement:
           Improvement Needed: Yes
           Sections: [List only section names that actually need improvement]

           If no section requires improvement:
           Improvement Needed: No
           Sections: None

           
        Note: Strictly follow the output format in point 4. No extra explanations or anything outside the specified structure.
        """
        
        # Get analysis from OpenAI
        analysis_response = llm.invoke(analysis_prompt)
        
        return analysis_response.content
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Call script analysis failed: {str(e)}")


def get_pdf_context(llm_insights):
    """
    Extracts relevant reference data from the reference file based on LLM insights.
    Only extracts material that directly supports the specific improvements identified.
    
    IMPORTANT: Reference material only contains these 4 sections:
    - objection-response: tell-them-why-you-are-asking
    - objection-response: i-have-to-think-about-it  
    - close-enhancement: guarantee-close
    - writing-structure: why_what_how_structure
    
    Args:
        llm_insights (str): The analysis insights from OpenAI containing specific improvement recommendations
        
    Returns:
        str: Relevant reference material extracted based on the insights, or indication if no relevant material found
    """
    try:
        # Read the reference file
        reference_file_path = '/home/GraphRAG/reference.txt'
        
        try:
            with open(reference_file_path, 'r', encoding='utf-8') as f:
                reference_content = f.read()
        except FileNotFoundError:
            return "Reference file not found. Cannot extract contextual information."
        except Exception as e:
            return f"Error reading reference file: {str(e)}"
        
        # Initialize the LLM for context extraction
        llm = ChatOpenAI(model="gpt-5-mini", temperature=0, openai_api_key=OPENAI_API_KEY)
        
        # Create prompt to extract relevant reference material
        context_extraction_prompt = f"""
        You are a reference material extraction specialist. Your task is to extract relevant sections from the available reference material that can help with the improvements identified in the VAPI script analysis.
        
        INSTRUCTIONS:
        1. The reference material contains 4 sections:
           - objection-response: tell-them-why-you-are-asking (helps with explaining why you ask questions)
           - objection-response: i-have-to-think-about-it (handles thinking/hesitation objections)
           - close-enhancement: guarantee-close (techniques for stronger closes)
           - writing-structure: why_what_how_structure (framework for hooks, messaging structure)
        
        2. Extract any sections that could be helpful for the identified improvements, even if not a perfect match
        
        3. Look for general principles, techniques, or approaches that could be adapted to address the issues
        
        **VAPI SCRIPT ANALYSIS INSIGHTS:**
        {llm_insights}
        
        **AVAILABLE REFERENCE MATERIAL (ONLY 4 SECTIONS):**
        {reference_content}
        
        **EXTRACTION APPROACH:**
        
        1. **Review the Step 2 analysis** to understand:
           - Which sections need improvement
           - What specific issues were identified
           - What kind of improvements are needed
        
        2. **Extract helpful reference material**:
           - Look for direct matches between issues and reference sections
           - Also consider general principles that could be adapted
           - Extract techniques that could inspire improvements even if not exact matches
        
        3. **Be inclusive in extraction**:
           - Extract any content that could provide helpful guidance
           - Include principles, techniques, and approaches that could be adapted
           - Don't worry about perfect matches - focus on potential value
        
        **OUTPUT FORMAT:**
        
        ## EXTRACTION SUMMARY
        **Sections Needing Improvement**: [List from Step 2 analysis]
        **Available Reference Sections**: 4 sections (objection-response x2, close-enhancement x1, writing-structure x1)
        
        ## EXTRACTED REFERENCE MATERIAL
        
        ### [Reference Section Name]: [Section Topic]
        **Relevant for**: [Which improvement issues this could help with]
        **Content**: 
        [Extract the relevant content]
        
        **How this helps**: [Brief explanation of how this content could be applied to the identified issues]
        
        [Repeat for each relevant reference section found]
        
        ## SUMMARY
        [Brief summary of what was extracted and how it can help with the improvements needed]
        
        Note: Focus on extracting helpful content rather than finding perfect matches. The goal is to provide Claude with useful reference material for making improvements.
        """
        
        # Get context extraction from OpenAI
        context_response = llm.invoke(context_extraction_prompt)
        
        return context_response.content
        
    except Exception as e:
        return f"Error extracting PDF context: {str(e)}"


def generate_vapi_script(vapi_script, call_records, llm_insights, reference_material):
    """
    STEP 4: Uses Claude to generate improved VAPI script sections.
    
    Claude will use Step 2 insights as the definitive guide and apply reference material
    techniques to improve only the specific sections identified, while preserving
    the client's original tone, style, and important elements.
    
    Args:
        vapi_script (str): The original VAPI script (primary reference)
        call_records (list): Call records from the database (for context)
        llm_insights (str): Step 2 analysis insights (definitive improvement guide)
        reference_material (str): Reference material from PDF (improvement techniques)
        
    Returns:
        str: Side-by-side comparison of original vs improved sections
    """
    try:
        # Initialize Claude
        llm_claude = ChatAnthropic(model='claude-sonnet-4-20250514', temperature=0, max_tokens=8192, anthropic_api_key=ANTHROPIC_API_KEY)

        # Create focused prompt for Claude
        claude_prompt = f"""
        You are a VAPI script improvement specialist. Your job is to make surgical improvements to specific sections identified in the analysis, while respecting and preserving the client's original work.
        
        **PRIMARY REFERENCES:**
        
        **1. THE SCRIPT (study this carefully to understand the client's style):**
        {vapi_script}
        
        **2. THE REFERENCE MATERIAL (techniques to apply):**
        {reference_material}
        
        **3. IMPROVEMENT GUIDE (what needs fixing):**
        {llm_insights}
        
        **CRITICAL INSTRUCTIONS:**
        
        1. **USE POINT 3 INSIGHTS AS YOUR DEFINITIVE GUIDE**: Only improve sections explicitly marked as "NEEDS IMPROVEMENT" in the analysis.
        
        2. **PRESERVE THE CLIENT'S STYLE**: Maintain the original script's humor, energy, personality, and tone that makes it effective.
        
        3. **APPLY REFERENCE TECHNIQUES INTELLIGENTLY**: Use reference material techniques to address the specific issues while maintaining the original style and approach. If not found in reference material, analyze how the current script is written, maintain that tone/style, and apply general principles inspired by the reference material to make improvements.
        
        4. **KEEP SECTION STRUCTURE**: Preserve all SECTION tags, attributes, and formatting exactly as they are.
        
        **OUTPUT FORMAT (EXACT FORMAT REQUIRED):**
        
        IMPROVED SECTIONS:
        
        Section X:
        
        Before:
        <SECTION X; [exact section tag and content from original script]>
        [exact original content]
        </SECTION X>
        
        After:
        <SECTION X; [exact same section tag]>
        [your improved content - preserving tone while fixing the specific issue]
        </SECTION X>
        
        [Repeat only for sections that Step 2 identified as needing improvement]
        
        **REQUIREMENTS:**
        - Only output sections that need improvement (ignore "NO IMPROVEMENT NEEDED" sections)
        - Keep exact SECTION tags and numbers from original script
        - Preserve the client's humor, energy, and personality
        - Fix only the specific issues mentioned in Step 2 analysis
        - No extra explanations or commentary
        - Use the exact format shown above"""
        
        # Get improved script from Claude
        claude_response = llm_claude.invoke(claude_prompt)
        
        return claude_response.content
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VAPI script generation with Claude failed: {str(e)}")


def rebuild_vapi_script(original_script, improved_sections_output):
    """
    STEP 5: Rebuilds the complete VAPI script with improved sections using OpenAI.
    
    Takes the original script and Claude's improved sections output, then creates
    a complete new script with the improvements integrated.
    
    Args:
        original_script (str): The complete original VAPI script
        improved_sections_output (str): Claude's output with improved sections in Before/After format
        
    Returns:
        str: Complete rebuilt VAPI script with improvements integrated
    """
    try:
        # Initialize OpenAI for script rebuilding
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=OPENAI_API_KEY)
        
        rebuild_prompt = f"""
        You are a VAPI script rebuilder. Your task is to take the original complete script and replace specific sections with their improved versions.
        
        **ORIGINAL COMPLETE VAPI SCRIPT:**
        {original_script}
        
        **IMPROVED SECTIONS TO INTEGRATE:**
        {improved_sections_output}
        
        **INSTRUCTIONS:**
        
        1. **Preserve the complete script structure** - Keep everything exactly as it is in the original script
        
        2. **Replace only improved sections** - Look for sections in the improved sections output that have "After:" versions and replace those specific sections in the original script
        
        3. **Maintain exact formatting** - Keep all indentation, spacing, JSON structure, and formatting exactly as in the original
        
        4. **Keep section tags intact** - Preserve all SECTION attributes and numbering exactly as they appear
        
        5. **Leave everything else unchanged** - All other content, comments, role definitions, context, etc. should remain identical to the original
        
        **EXAMPLE OF WHAT TO DO:**
        If improved sections shows:
        ```
        Section 2:
        Before: <SECTION 2; ...>original content</SECTION 2>
        After: <SECTION 2; ...>improved content</SECTION 2>
        ```
        Then replace that exact Section 2 in the original script with the "After" version.
        
        **OUTPUT REQUIREMENT:**
        Return ONLY the complete rebuilt VAPI script with no additional commentary, explanations, or formatting markers. Just the pure script content that can be directly used.
        """
        
        # Get rebuilt script from OpenAI
        rebuild_response = llm.invoke(rebuild_prompt)
        
        return rebuild_response.content
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VAPI script rebuilding failed: {str(e)}")


def update_script_in_vapi(vapi_script):
    
    try:
        url = "https://api.vapi.ai/assistant/e1229f0e-e434-4c45-8859-816f908402a6"

        headers = {
            "Authorization": "Bearer 4757bae7-59f7-45db-a8cf-39e5b423672d",
            "Content-Type": "application/json"
        }

        # with open(r"/home/GraphRAG/vapi script.txt", "r") as f:
        #     vapi_script_raw = f.read()

        payload = {
        "model": {
            "temperature": 0.3,
            "provider": "openai",
            "model": "gpt-4.1",
            "messages": [
            {
                "role": "system",
                "content": vapi_script
            }
            ]
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "4YHmZd0D1dFjavHp4NKQ"
        },
        "startSpeakingPlan": {
            "smartEndpointingEnabled": True,
            "waitSeconds": 1.5
        },
        "firstMessage": "Hi, is compliance available?"
        }

        response = requests.patch(url, headers=headers, data=json.dumps(payload))

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Failed to update script in VAPI: {response.text}")

        return {"status_code": response.status_code, "response": response.text}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Updating script in VAPI failed: {str(e)}")


def script_analysis(vapi_script):
    """
    Main function to perform complete VAPI script analysis and improvement workflow.
    This implements steps 1-5: fetch calls → analyze → extract references → improve with Claude → rebuild script
    """
    try:
        # --- Step 1: Get last 10 Calls ---
        print("Step 1: Fetching last 10 call records...")
        # recent_calls = get_last10_calls_graph()
        recent_calls = get_last_n_call_records(10)
        
        if not recent_calls:
            print("No call records found. Cannot proceed with analysis.")
            return {"error": "No call records found in database"}

        # --- Step 2: Analyze calls against VAPI script ---
        print("Step 2: Analyzing call records against VAPI script...")
        llm_insights = call_script_analysis(recent_calls, vapi_script)

        print("Analysis completed successfully!")

        if "Improvement Needed: No" in llm_insights or "Sections: None" in llm_insights or "Sections: []" in llm_insights:
            print("No improvements needed as per analysis. Exiting workflow.")
            return {
                "status": "success",
                "call_records_count": len(recent_calls),
                "step_2_analysis": llm_insights,
                "step_3_reference_material": "N/A - No improvements needed",
                "step_4_improved_script": "N/A - No improvements needed",
                "step_5_rebuilt_script": "N/A - No improvements needed",
                "vapi_update_status": "N/A - No improvements needed",
                "workflow_steps_completed": ["call_data_fetch", "script_analysis"]
            }      

        # --- Step 3: Extract relevant reference material ---
        print("Step 3: Extracting relevant reference material based on insights...")
        pdf_context = get_pdf_context(llm_insights)
        
        print("Reference extraction completed successfully!")
        
        # --- Step 4: Generate improved script with Claude ---
        print("Step 4: Generating improved VAPI script sections with Claude...")
        improved_script = generate_vapi_script(vapi_script, recent_calls, llm_insights, pdf_context)
        
        print("Claude script improvement completed successfully!")
        
        # --- Step 5: Rebuild complete VAPI script ---
        print("Step 5: Rebuilding complete VAPI script with improvements...")
        rebuilt_script = rebuild_vapi_script(vapi_script, improved_script)
        
        print("Complete script rebuilding completed successfully!")


        # Optionally, update the rebuilt script back to VAPI system
        print("Updating rebuilt script back to VAPI system...")
        update_response = update_script_in_vapi(rebuilt_script)
        status_code = update_response.get("status_code", "No status code returned")

        print(f"VAPI update response: {status_code}")

        # Return comprehensive results
        return {
            "status": "success",
            "call_records_count": len(recent_calls),
            "step_2_analysis": llm_insights,
            "step_3_reference_material": pdf_context,
            "step_4_improved_script": improved_script,
            "step_5_rebuilt_script": rebuilt_script,
            "vapi_update_status": status_code,
            "workflow_steps_completed": ["call_data_fetch", "script_analysis", "reference_extraction", "claude_improvement", "script_rebuild", "vapi_update"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Complete script analysis workflow failed: {str(e)}")

if __name__ == "__main__":
    # Test the complete workflow (Steps 1-6)
    with open('/home/GraphRAG/vapi script.txt', 'r', encoding='utf-8') as f:
        vapi_script = f.read()
    
    result = script_analysis(vapi_script)
    
    print("="*80)
    print("COMPLETE VAPI SCRIPT IMPROVEMENT WORKFLOW")
    print("="*80)
    print(f"Status: {result.get('status')}")
    print(f"Call Records Analyzed: {result.get('call_records_count')}")
    print(f"Steps Completed: {result.get('workflow_steps_completed')}")
    
    print("\n" + "="*80)
    print("STEP 2: GPT ANALYSIS")
    print("="*80)
    print(result["step_2_analysis"])

    print("\n" + "="*80)
    print("STEP 3: REFERENCE MATERIAL")
    print("="*80)
    print(result["step_3_reference_material"])
    
    print("\n" + "="*80)
    print("STEP 4: CLAUDE IMPROVED SECTIONS")
    print("="*80)
    print(result["step_4_improved_script"])
    
    print("\n" + "="*80)
    print("STEP 5: COMPLETE REBUILT VAPI SCRIPT")
    print("="*80)
    print(result["step_5_rebuilt_script"])

    print("\n" + "="*80)
    print("STEP 6: VAPI UPDATE STATUS")
    print("="*80)
    print(f"VAPI Update Status: {result.get('vapi_update_status')}")
