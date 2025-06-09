from typing import Dict, Any , List
from mcp.server.fastmcp import FastMCP
import httpx
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

# Stateful server (maintains session state)
mcp = FastMCP("StatefulServer" , port = 8001)

async def fetch(client: httpx.AsyncClient, url: str, params: dict = None):
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

@mcp.tool()
async def get_weather(city: str , history_date: str):

    api_key = os.getenv("WEATHER_API_KEY")
    
    if not api_key:
        raise ValueError("API key not found! Check your .env file and loading.")
    
    # history_date seven days prior
    endpoints = [
        ("http://api.weatherapi.com/v1/current.json", {
            "key": api_key,
            "q": city
        }),
        ("http://api.weatherapi.com/v1/forecast.json", {
            "key": api_key,
            "q": city,
            "days": 3
        }),
        ("http://api.weatherapi.com/v1/history.json", {
            "key": api_key,
            "q": city,
            "dt": history_date
        }),
        ("http://api.weatherapi.com/v1/alerts.json", {
            "key": api_key,
            "q": city
        }),
        ("http://api.weatherapi.com/v1/marine.json", {
            "key": api_key,
            "q": city
        }),
    ]

    # call the req at once async gather
    async with httpx.AsyncClient() as client :
        tasks = [
            fetch(client, url, params)
            for url, params in endpoints
        ]
        results = await asyncio.gather(*tasks)

    # result already in parsed json
    return results



def build_search_query(keywords: list[str]) -> str:
    formatted_keywords = [k.strip() for k in keywords]
    return " OR ".join(formatted_keywords)

@mcp.tool()
async def get_news(news : List[str]):
    url = "https://newsapi.org/v2/everything"

    api_key = os.getenv("NEWS_API_KEY")
    
    if not api_key:
        raise ValueError("API key not found! Check your .env file and loading.")
    
    
    news_query = build_search_query(news)

    params = {
        "apiKey" : api_key ,
        "q" : news_query ,
        "pageSize" : 10 ,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url , params=params)
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def get_port_congestion(port_code : str , vessel_type : str):
    url = "https://api.sinay.ai/congestion/api/v1/congestion"

    api_key = os.getenv("PORT_API_KEY")

    if not api_key:
        raise ValueError("API key not found! Check your .env file and loading.")
    
    params = {
        "portCode": port_code ,
        "vesselType":vessel_type
    }

    headers = {
        "API_KEY": api_key
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url , params=params , headers=headers)
        response.raise_for_status()
        return response.json()
    
@mcp.tool()
async def get_vessel_detail(vesselNameOrCode : str):
    url = "https://api.sinay.ai/ports-vessels/api/v1/vessels"

    api_key = os.getenv("PORT_API_KEY")

    if not api_key:
        raise ValueError("API key not found! Check your .env file and loading.")
    
    params = {
        "vesselNameOrCode": vesselNameOrCode ,
        "numberOfResult": 10
    }

    headers = {
        "API_KEY": api_key
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url , params=params , headers=headers)
        response.raise_for_status()
        return response.json()
    
# response is links to all the docs in html 
@mcp.tool()
async def get_sec_filing(cik_company: str):
    url = "https://api.sec-api.io"

    api_key = os.getenv("SEC_API_KEY")

    if not api_key:
        raise ValueError("API key not found! Check your .env file and loading.")
    
    # parse cik_company remove trailing zero
    cik_company = str(int(cik_company))

    headers = {"Authorization": api_key}
    payload = {
        "query": f"cik:{cik_company} AND formType:\"10-Q\"",
        "from": "0",
        "size": "1",
        "sort": [{ "filedAt": { "order": "desc" }}]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url ,json = payload , headers=headers)
        response.raise_for_status()
        return response.json()




if __name__ == "__main__":
    print("Starting MCP server with streamable-http transport...")
    # Run server with streamable_http transport
    mcp.run(transport="streamable-http")
