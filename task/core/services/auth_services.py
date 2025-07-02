import requests
from django.conf import settings
from requests.exceptions import RequestException

def get_user(user_id):
    try:
        response = requests.get(
            f"{settings.AUTH_SERVICE_URL}/api/user/{user_id}/", 
            headers={"Authorization": f"Bearer {settings.SERVICE_TO_SERVICE_TOKEN}"},
            timeout=3
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur Auth Service: {str(e)}")
        return None
    

# def get_userSerializer():
#     try:
#         response = requests.get(
#             f"{settings.AUTH_SERVICE_URL}/auth/serializers/UserSerializer", 
#             headers={"Authorization": f"Bearer {settings.SERVICE_TO_SERVICE_TOKEN}"},
#             timeout=3
#         )
#         response.raise_for_status()
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         print(f"Erreur Auth Service: {str(e)}")
#         return None