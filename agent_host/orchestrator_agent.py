# orchestrator_agent.py
import asyncio
import sys
from openai import AsyncOpenAI
from disrup_detect_agent import DisruptionDetectionAgent
from dotenv import load_dotenv
import os 
import json 
import uuid

load_dotenv()

class OrchestratorAgent:
    def __init__(self):
        """
        Initializes the OrchestratorAgent.
        AI agent client
        """
        self.client = AsyncOpenAI(
        api_key= os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai"
        )
        self.model = "sonar"
        print(f"OrchestratorAgent initialized.")
    
        
    def generate_agent_id(self , length=6, prefix="AGENT_", suffix=""):
        import uuid
        base_id = uuid.uuid4().hex[:length]
        return f"{prefix}{base_id}{suffix}"


    async def execute_workflow(self, user_input ):
        """
        Parses user input and launches the appropriate agent workflow.
        """
        print(f"\n[Orchestrator] Starting workflow for: '{user_input}'")

        system_prompt = """
                        You are the orchestration agent for the Global Supply Chain Resilience AI multi-agent system.

                        Your task is to perform two actions:
                        1.  **Parse User Input**: Extract key supply chain details from the user's request. Key details include, but are not limited to: port codes, cities, shipment types, supplier names, involved companies, specific product SKUs, and any mentions of urgency or risk (e.g., 'critical', 'emergency', 'immediately').
                        2.  **Decide Agent Workflow**: Based on the parsed data and any indication of urgency, determine the correct sequence of agents to call.

                        **Available Agents:**
                        - `DisruptionDetectionAgent`: The primary agent for monitoring and initial detection.
                        - `ImpactAssessmentAgent`: Analyzes the financial and logistical impact of a disruption.
                        - `ResponseCoordinationAgent`: Takes action to mitigate the disruption.

                        **Decision Logic:**
                        - **Standard Workflow**: For routine checks or low-urgency queries, the sequence is: `["DisruptionDetectionAgent", "ImpactAssessmentAgent", "ResponseCoordinationAgent"]`.
                        - **Emergency Workflow**: If the user's query contains words indicating high risk or urgency (e.g., 'emergency', 'critical failure', 'port closure confirmed', 'immediate action'), you may shorten the sequence to `["DisruptionDetectionAgent", "ResponseCoordinationAgent"]` to enable a faster response.

                        **Output Format:**
                        Your entire output MUST be a single, valid JSON object with NO additional text or explanations. The JSON object must have two keys: "parsed_data" and "agent_call_sequence".

                        **Example Output:**
                        {
                        "parsed_data": {
                            "port": "Los Angeles",
                            "shipment_type": "container",
                            "suppliers": ["Supplier A", "Supplier B"],
                            "companies_involved": ["Company X"],
                            "urgency_level": "low"
                        },
                        "agent_call_sequence": ["DisruptionDetectionAgent", "ImpactAssessmentAgent", "ResponseCoordinationAgent"]
                        }

                        Now, analyze the user's request and generate the JSON output. nothing else than json not a single word out put start with : { 
                    """
        try:
            response = await self.client.chat.completions.create(
                model = self.model , 
                messages = [
                    {"role" : "system" ,  "content" : system_prompt },
                    {"role" : "user" , "content" : user_input }
                ],
                temperature = 0.1, 
                max_tokens = 500,
                # response_format={"type": "json_object"},
            )
            
            raw_content = response.choices[0].message.content
            # print raw content
            print(f"Orchestrator: Received raw LLM response: {raw_content}")
            # parse json string into python dict object
            result = json.loads(raw_content)

            # user parsed data input 
            user_input_params = result["parsed_data"]
            # agentic call seq :
            agent_seq = result["agent_call_sequence"]   # list of str

        except (json.JSONDecodeError, KeyError) as e:
                print(f"Orchestrator: Error parsing LLM response - {e}")
                return
        
        except Exception as e:
                print(f"Orchestrator: An unexpected error occurred during LLM call - {e}")
                return


        if agent_seq and agent_seq[0] == "DisruptionDetectionAgent":
            print("[Orchestrator] Instantiating DisruptionDetectionAgent...")
            disruption_agent = DisruptionDetectionAgent()

            print(f"[Orchestrator] Executing agent task with parameters: {user_input_params}")
            await disruption_agent.run_single_analysis(initial_params=user_input_params)
            
            print("[Orchestrator] Agent task complete.")
        else:
            print("[Orchestrator] No suitable agent found in the sequence to execute.")





if __name__ == "__main__":
    print("Starting Orchestrator Agent for a single run...")
    orchestrator = OrchestratorAgent()

    user_task = """I want you to check for my supply chain resilience. 
    My supply chain info: Baltimore port, electronic container shipment, my supplier is Foxconn. 
    There are reports of a major crane failure.
    """

    try:
        # The main execution block is now a simple, direct call to execute the workflow once.
        asyncio.run(orchestrator.execute_workflow(user_task))
        print("\nOrchestrator workflow finished.")
    except KeyboardInterrupt:
        print("\nOrchestrator run interrupted by user.")
    except Exception as e:
        print(f"A critical error occurred: {e}")

