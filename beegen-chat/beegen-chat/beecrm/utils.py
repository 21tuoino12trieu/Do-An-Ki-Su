import requests

import requests
import json
import asyncio
from typing import Iterator, Any, Dict, List
from types import SimpleNamespace
from beegenerate.configs import KeycloakConfig
from beecrm.configs.scoring_config import ScoringConfig

# Load authentication configuration
authen_config = KeycloakConfig.default()
scoring_config = ScoringConfig.default()

# Function asynchronous
def get_token() -> str:
    
    url_token = f"{authen_config.keycloak_base}realms/ms-core/protocol/openid-connect/token"

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
async def run_get_token() -> str:
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_token()
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



if __name__=='__main__':
    username = "phucph1"
    category_id = "Tín dụng"
    sub_category_id = "Vay SXKD"

    # asyncio.run(run_query_industry(
    #     username=username,
    #     query="Trồng cây mía",
    #     code="-1"
    #     # category=category_id,
    #     # sub_category=sub_category_id
    # ))

    # asyncio.run(run_calculate_score(
    #     username=username,
    #     category=category_id,
    #     sub_category=sub_category_id
    # ))

    asyncio.run(run_calculate_score_sxkd(
        username=username,
        businessIndustryName="47199-Bán lẻ trong cửa hàng kinh doanh tổng hợp khác"
    ))