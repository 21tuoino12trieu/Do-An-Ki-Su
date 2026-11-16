import requests
from typing import Dict, Any, Optional
import uuid
import json


def get_access_token():
    url = "https://beegen-admin.tanzu-dev.mbbank.com.vn/beegen-admin-be/public/login"

    payload = json.dumps({
        "username": "dev_aicenter_1",
        "password": "REPLACE_WITH_LOCAL_SECRET"
    })
    headers = {
        'accept': '*/*',
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload, verify=False)

    return response.json()['accessToken']


def send_request(
    url: str,
    method: str,
    bot_id: str = "711bd760-5824-4772-addd-e038633c7847",
    payload: Optional[Dict[str, Any]] = None
) -> Dict:
    """
    Send HTTP request with specified type (POST/GET/DELETE).
    
    Args:
        url: API endpoint URL
        request_type: Type of request ('post', 'get', or 'delete')
        bot_id: Bot identifier for query parameter
        payload: Optional dictionary containing request body data (required for POST, optional for DELETE)
    
    Returns:
        Dictionary containing response data
    """
    try:
        method = method.lower()
        if method not in ['post', 'get', 'delete']:
            raise ValueError(f"Invalid method: {method}")
        
        headers = {
            'Content-Type': 'application/json',
            'clientMessageId': str(uuid.uuid4()),
            'Authorization': f'Bearer {get_access_token()}'
        }

        kwargs = {
            'url': url,
            'params': {'botId': bot_id},
            'headers': headers,
            'verify': False
        }
        
        # Add payload for POST and DELETE (if provided)
        if payload is not None and method in ['post', 'delete']:
            kwargs['json'] = payload
            
        # Send request using the appropriate method
        request_method = getattr(requests, method)
        response = request_method(**kwargs)
        
        return response.json()
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    

def run_command(
    command: str
) -> Dict:
    import random
    
    if command == "category/create":
        response = send_request(
            method="post",
            url=f"https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-portal-be/{command}",
            payload={
                "name": "default",
                "description": "topic mặc định zui zui"
            }
        )
        return response.json()['data']['id']
    elif command == "category/all":
        response = send_request(
            method="get",
            url=f"https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-portal-be/{command}"
        )
        
        return [r['id'] for r in response['data']['content']]
    elif command == "dialogues/create":
        random_number = random.uniform(1.0, 10.0)
        response = send_request(
            method="post",
            url=f"https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-portal-be/{command}",
            payload={
                "questions": [
                    f"question number: {random_number}"
                ],
                "answers": [
                    f"question number: {random_number}"
                ]
            }
        )
        return response['data']['id']
    elif command == 'dialogues/delete':
        response = send_request(
            method="delete",
            url=f"https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-portal-be/{command}",
            payload={
                "dialogueIds": ["ec3d8328-cca9-4e1d-8b8b-17d989e17aea"],
                "excludeIds": []
            }
        )
        
        return response
    

def main():
    print(run_command(command="dialogues/delete"))

       
if __name__ == "__main__":
    main()