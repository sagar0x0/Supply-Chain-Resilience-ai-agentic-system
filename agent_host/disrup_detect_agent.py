# disrupt_agent.py
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession 
import asyncio
import json
import os 
from openai import AsyncOpenAI
from datetime import date
from pydantic import BaseModel, Field
from typing import List, Dict, Any

tools_definition_str= [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather details, maritime info, and alerts for a specific city or port area.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city name for the weather query, e.g., 'Los Angeles'."} ,
                    "history_date": {"type": "string", "description": "history_date five days prior   e.g format: YYYY-MM-DD"} ,
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Get recent news articles based on a list of keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "news_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of topics to search for, e.g., ['Los Angeles port', 'global supply chain', 'geopolitical risk']."
                    }
                },
                "required": ["news_keywords"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_port_congestion",
            "description": "Get the current congestion level for a specific port.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port_code": {"type": "string", "description": "The official port code, e.g., 'USBAL'."},
                    "vessel_type": {"type": "string", "description": "The type of vessel to check congestion for, e.g., 'cargo', 'tanker' , 'roro'."}
                },
                "required": ["port_code", "vessel_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_vessel_detail",
            "description": "Get details for a specific vessel by its name or code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vesselNameOrCode": {"type": "string", "description": "The name or identification code of the vessel, e.g., 'cla'."}
                },
                "required": ["vesselNameOrCode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sec_filing",
            "description": "Get SEC filing links for a company using its CIK.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cik_company": {"type": "string", "description": "The CIK (Central Index Key) of the company, e.g., '0000320193'."}
                },
                "required": ["cik_company"]
            }
        }
    }
]


def pretty_print_tool_calls(raw: str) -> str:
    # 1) Find the first “{” and last “}”
    start = raw.find('{')
    end   = raw.rfind('}')
    if start == -1 or end == -1 or end < start:
        raise ValueError("No valid JSON object found in input")

    # 2) Slice out only the JSON object
    clean = raw[start:end+1]

    # 3) Parse the cleaned JSON
    data = json.loads(clean)

    # 4) Re-serialize with indentation
    return json.dumps(data, indent=2)

class DisruptionDetectionAgent:
    """
    An agent that continuously monitors various data sources for potential
    supply chain disruptions, analyzes the data, and reports findings.
    """
    def __init__(self, monitor_interval_seconds=3600):
        """
        Initializes the DisruptionDetectionAgent.

        """
        self.client = AsyncOpenAI(
        api_key= os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai"
        )
        self.model = "sonar"
        self.mcp_url = "http://127.0.0.1:8001/mcp"
        self.monitor_interval_seconds = monitor_interval_seconds
        self.session = None  # MCP session, initialized upon connection



    async def _fetch_data(self, params):
        """
            Dynamically fetches data from various sources by letting an LLM choose
            and parameterize the appropriate tools based on the input.

            Args:
                params (dict): A dictionary containing supply chain details from the orchestrator.
            
            Returns:
                dict: A dictionary containing the results from each data source called.
        """
        
        system_prompt = f"""
        You are a data-fetching AI component. Based on the user's input, your sole purpose is to generate a single, valid JSON object that specifies which tools to call.

        The JSON object must have a single root key: "tool_calls".
        The value of "tool_calls" must be an array of objects, where each object represents one tool call.
        Each tool call object must contain a "function" key with "name" (string) and "arguments" (object).

        Do not output any text, explanations, or markdown formatting other than the final JSON object.

        Available Tools:
        {tools_definition_str}

        Example of the required JSON output:
        {{
        "tool_calls": [
            {{
            "function": {{
                "name": "get_weather",
                "arguments": {{
                "city": "Los Angeles"
                }}
            }}
            }},
            {{
            "function": {{
                "name": "get_news",
                "arguments": {{
                "news_keywords": ["geopolitical", "maritime security"]
                }}
            }}
            }},
            {{
            "function": {{
                "name": "get_port_congestion",
                "arguments": {{
                    "port_code": "USBAL",
                    "vessel_type": "cargo"
                }}
            }}
            }}
        ]
        }}

        Now, analyze the user's input and generate the corresponding tool calls in the specified JSON format.
        dont start with ```json 
            
        """


        user_input_str = json.dumps(params, indent=2)

        try:
            print("[Agent]   - Step 1: Asking LLM for a structured JSON of tool calls...")
            
            # This is the key: using response_format with our custom Pydantic model.
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input_str}
                ],

                max_tokens=500,
            )
            
            # Parse the guaranteed JSON response using our Pydantic model.
            # This is much safer than a raw json.loads().
            
            raw_output = response.choices[0].message.content
            print(f"[Agent]   - Raw LLM Output:\n{raw_output}")


            # The output is expected to be a dictionary with a 'tool_calls' key.
            clean_json = pretty_print_tool_calls(raw_output)

            llm_response = json.loads(clean_json)

            llm_tool_decisions = llm_response.get('tool_calls', [])

            if not llm_tool_decisions:
                print("[Agent]   - LLM decided no tools were necessary for the given input.")
                return {}
        except json.JSONDecodeError as e:
            print(f"An error occurred while parsing the LLM JSON response: {e}")
            print(f"Invalid JSON received: {raw_output}")
            return {}
        except Exception as e:
            print(f"An unexpected error occurred during the LLM response handling: {e}")
            return {}
                

        fetched_data = {}
        print(f"[Agent]   - Step 2: Connecting to MCP to execute {len(llm_tool_decisions)} tool(s)...")
        try:
            async with streamablehttp_client(self.mcp_url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    for tool_call in llm_tool_decisions:
                        function_details = tool_call.get('function', {})
                        tool_name = function_details.get('name')
                        tool_args = function_details.get('arguments', {})

                        if not tool_name:
                            print("[Agent]     - Skipping a tool call with no name.")
                            continue
                        
                        print(f"[Agent]     - Calling tool: {tool_name}({tool_args})")
                        try:
                            # Simple assignment, just like your working code
                            result = await session.call_tool(tool_name, tool_args)
                            serial = result.model_dump()
                            fetched_data[tool_name] =  serial
                            print(f"[Agent]     - Successfully completed: {tool_name}")

                        except Exception as e:
                            print(f"[Agent]     - A critical error occurred calling tool '{tool_name}': {e}")
                            fetched_data[tool_name] = {"error": f"Protocol-level failure for '{tool_name}'", "details": str(e)}

            # Don't try to JSON serialize here - let the downstream code handle it
            print(f"[Agent]   - Successfully fetched data from {len(fetched_data)} tools")
            return fetched_data

        except Exception as e:
            print(f"[Agent]   - Critical error during MCP connection setup: {e}")
            return {"error": f"Failed to execute tools via MCP: {e}"}


    async def _analyze_disruptions(self, data):
        """
        Analyzes the collected data to detect potential disruptions using an LLM
        and ensures the output is a structured, machine-readable JSON object.

        Args:
            data (dict): The data fetched from various sources by the _fetch_data method.

        Returns:
            dict or None: A structured dictionary containing the analysis if a disruption
                        is detected, otherwise None.
        """
        if not data:
            print("No data provided to analyze.")
            return None

        # Convert the fetched data into a clean string for the LLM prompt
        # The LLM will analyze this content.
        data_str = json.dumps(data, indent=2)

        system_prompt ="""
            **Your Persona**: You are "Horus," a world-class supply chain risk analyst. You are logical, data-driven, and concise. Your sole purpose is to synthesize disparate, real-time intelligence into a clear, structured risk assessment for an automated system. You do not hedge or provide conversational filler; you deliver analysis.

            **Your Task**:
            1.  **Analyze**: You will be given a JSON object containing multi-source intelligence (weather, news, port congestion, SEC filings) can also search web.
            2.  **Assess**: Identify correlations and emergent risks. A weather alert combined with high port congestion is a higher risk than either alone.
            3.  **Report**: Your entire output must be a single, valid JSON object conforming to the schema below.

            **Required JSON Report Schema:**
            {
            "is_disruption_detected": <boolean>,
            "risk_score": <number | 0.0-10.0>,
            "confidence": <number | 0.0-1.0>,
            "summary": "<A concise, one-sentence summary of the situation for high-level alerts.>",
            "key_findings": [
                "<A list of the most critical individual findings that support your conclusion.>"
            ],
            "data_for_impact_agent": {
                "affected_port_codes": ["<List of affected port codes, e.g., 'USLAX'>"],
                "expected_duration_days": <integer>,
                "triggering_event_type": "<The main cause, from ['weather', 'geopolitical', 'congestion', 'supplier_financial', 'other']>"
            },
            "data_for_response_agent": {
                "immediate_actions_recommended": ["<List of suggested immediate actions, e.g., 'Reroute vessels from port USLAX'>"],
                "critical_skus_at_risk": ["<List of any identified SKUs or product types at immediate risk>"]
            }
            }

            Begin analysis. your output should start with {
            """


        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": data_str}
                ],
                # This is the key to ensuring reliable JSON output
                #response_format={"type": "json_object"},
                temperature=0.1 ,
                max_tokens = 650
            )

            raw_output = response.choices[0].message.content
            print(raw_output)

            clean_json = pretty_print_tool_calls(raw_output)

            # The response_format guarantees the content is a valid JSON string
            analysis_result = json.loads(clean_json)
            
            # Validate the result to ensure it's usable
            if analysis_result.get("is_disruption_detected"):
                print(f"Potential disruption detected with risk score: {analysis_result.get('risk_score')}")
                return analysis_result
            else:
                print("No significant disruptions detected in this cycle.")
                return None

        except json.JSONDecodeError as e:
            print(f"CRITICAL ERROR: Failed to decode JSON from LLM response despite using response_format. Response: {response.choices[0].message.content}. Error: {e}")
            return None
        except KeyError as e:
            print(f"CRITICAL ERROR: LLM response was valid JSON but missed a required key: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during disruption analysis: {e}")
            return None
        

    async def run_single_analysis(self, initial_params: dict):
        """
        Runs one complete analysis cycle: fetch, analyze, and report.
        """
        print("[Agent] Starting analysis...")

        data_to_analyze = None
        

        # 1. Fetch Data
        data_to_analyze = await self._fetch_data(initial_params)
        
        # 2. Analyze Data
        analysis_result = await self._analyze_disruptions(data_to_analyze)
        
        # 3. Report to MCP if a disruption was found
        if analysis_result:
            print("[Agent] Disruption detectection report .")
            print(analysis_result)
        else:
            print("[Agent] No significant disruption detected.")
            
        print("[Agent] Analysis finished.")



























# Main execution block
async def main_agent_loop():
    # Configuration for the agent
    mcp_server_url = "http://127.0.0.1:8001/mcp"
    # For testing, use a short interval. In production, this would be longer (e.g., 1 hour = 3600s).
    monitoring_interval_sec = 60 
    
    # Define initial parameters for data fetching. These could be loaded from a config file/service.
    initial_monitoring_params = {
        "weather_city": "New York",
        "news_keywords": ["port congestion", "supply chain disruption", "geopolitical tensions affecting trade", "industrial action logistics"],
        "port_code": "USNYC", # Example: Port of New York and New Jersey
        "vessel_identifier": "EVERGREEN", # Example: Search for vessels with "EVERGREEN" in name
        "cik_company": "0000320193" # Apple Inc. CIK, for financial health monitoring
    }

    # Create and start the agent
    disruption_agent = DisruptionDetectionAgent(
        monitor_interval_seconds=monitoring_interval_sec
    )
    await disruption_agent.run_single_analysis(initial_params=initial_monitoring_params)


if __name__ == "__main__":
    print("Starting Disruption Detection Agent...")
    try:
        asyncio.run(main_agent_loop())
    except KeyboardInterrupt:
        print("\nDisruption Detection Agent stopped by user.")
    except Exception as e:
        print(f"\nCritical error in main agent loop: {e}")

