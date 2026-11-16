from asyncio.log import logger
import ssl
import time
import aiohttp
import requests

import requests
import json
import asyncio
from typing import Iterator, Any, Dict, List, Optional
from types import SimpleNamespace
from beegenerate.configs import KeycloakConfig
from beecrm.configs.scoring_config import ScoringConfig

# Load authentication configuration
authen_config = KeycloakConfig.default()
scoring_config = ScoringConfig.default()


# Function asynchronous
def get_token(
    url_token: str
) -> str:
    payload = f'client_id={authen_config.client_id}&client_secret={authen_config.client_secret_key}&grant_type=client_credentials'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }

    response = requests.request("POST", url_token, headers=headers, data=payload)

    access_token = response.json().get("access_token", "")

    if not access_token:
        raise ValueError("Không lấy được access token!")

    return access_token

# Function asynchronous
async def run_get_token(
    url_token: str = f"{authen_config.keycloak_base}realms/ms-core/protocol/openid-connect/token"
) -> str:
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_token(url_token)
    )

# Function synchronous
def calculate_score(
    username: str,
    category: str,
    sub_category: str,
    token: str,
    url: str
) -> Dict:
    payload = json.dumps({
        "username": username,
        "category": category,
        "sub_category": sub_category
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    scenarios = response.get("scenarios", [])

    return scenarios
    
# Function ansynchronous
async def run_calculate_score(
    username: str,
    category: str,
    sub_category: str,
) -> Iterator[Any]:
    token = await run_get_token()
    
    url = f"{scoring_config.domain}/api/v1/calculate-score"

    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: calculate_score(
            username=username,
            category=category,
            sub_category=sub_category,
            token=token,
            url=url
        )
    )

# Function synchronous
def calculate_score_sxkd(
    username: str,
    businessIndustryName: str,
    businessIndustryId: str,
    token: str,
    url: str
) -> List[Dict]:

    payload = json.dumps({
        "username": username,
        "businessIndustryName": businessIndustryName,
        "businessIndustryId": businessIndustryId
    })

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    scenarios = response.get("scenarios", [])

    print(scenarios)

    return scenarios

# Function asynchronous
async def run_calculate_score_sxkd(
    username: str,
    businessIndustryName: str,
    businessIndustryId: str = None,
) -> Iterator[Any]:
    token = await run_get_token()

    url = f"{scoring_config.domain}/api/v1/sxkd/calculate-score"

    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: calculate_score_sxkd(
            username=username,
            businessIndustryId=businessIndustryId,
            businessIndustryName=businessIndustryName,
            token=token,
            url=url
        )
    )


# Function synchronous
def suggest_business_industries(
    username: str,
    token: str,
    url: str,
) -> List[Dict]:
        
    payload = json.dumps({
        "username": username,
    })

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    crmBusinessIndustries = response.get("crmBusinessIndustries", [])

    print("crmBusinessIndustries: ", crmBusinessIndustries)

    return crmBusinessIndustries

# Function asynchronous
async def run_suggest_business_industries(
    username: str,
) -> List[Dict]:
    token = await run_get_token()

    url = f"{scoring_config.domain}/api/v1/sxkd/suggest-business-industries"

    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: suggest_business_industries(
            username=username,
            token=token,
            url=url
        )
    )

# Function synchronous
def query_industry(
    query: str,
    username: str,
    code: str,
    token: str,
    url: str
) -> Dict:
    payload = json.dumps({
        "username": username,
        "query": query,
        "code": code
    })

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    print("Response: ", response)

    return response

# Function Asynchronous
async def run_query_industry(
    query: str,
    username: str,
    code: str,
) -> List[Dict]:
    token = await run_get_token()

    url = f"{scoring_config.domain}/api/v1/sxkd/query-industry"

    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: query_industry(
            query=query,
            username=username,
            code=code,
            token=token,
            url=url
        )
    )



# Get RM info

def get_user_info(
    username: str,
    token: str,
    url: str
) -> Dict:
    payload = json.dumps({
        "username": username
    })

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    return response

# Function Asynchronous
async def run_get_user_info(
    username: str,
) -> List[Dict]:
    token = await run_get_token()
    
    url = f"{scoring_config.domain}/api/v1/user-info"
    
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_user_info(
            username=username,
            token=token,
            url=url
        )
    )

# Function synchronous
def rcm_scenario_id(
    username: str,
    scenario_id: str,
    token: str,
    url: str
) -> List[Dict]:

    payload = json.dumps({
        "username": username,
        "scenario_id": scenario_id,
    })

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()
    print(response)
    scenarios = response.get("scenarios", [])

    print(scenarios)

    return scenarios

# Function asynchronous
async def run_rcm_scenario_id(
    username: str,
    scenario_id: str,
) -> Iterator[Any]:
    token = await run_get_token()
    
    url = f"{scoring_config.domain}/api/v1/sxkd/recommend-scenario"
    
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: rcm_scenario_id(
            username=username,
            scenario_id= scenario_id,
            token=token,
            url=url
        )
    )

# Function synchronous
def count_scenarios(
    token: str,
    url: str,
    filter_values: Dict[str, Any],
) -> Dict[str, Any]:

    payload = json.dumps({
        "values": filter_values
    })

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    return response

# Function asynchronous
async def run_count_scenarios(
    filter_values: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Args:
        filter_values: Dict có dạng {
            "L1": "Tín dụng",
            "L2": "SXKD",
            "L3": "01110-Trồng lúa"
        }
    
    Returns:
        Dict với count_scenario và success flag
    """
    token = await run_get_token()
    
    url = f"{scoring_config.domain}/api/v1/count-scenarios"
    
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: count_scenarios(
            filter_values=filter_values,
            token=token,
            url=url
        )
    )

if __name__=='__main__':
    username = "dungdd2"
    category_id = "Tín dụng"
    sub_category_id = "Nhà đất"
    scenario_id = "f38bf60e-2b56-45b4-828b-737ea0e23ea3"

    rs = asyncio.run(run_count_scenarios(
        filter_values={
            "L1": "Thẻ",
            "L2": "",
            "L3": ""
        }
    ))

    print(rs)