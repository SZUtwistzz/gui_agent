import os
from volcenginesdkarkruntime import Ark

client = Ark(
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    api_key=os.getenv('ARK_API_KEY'),  # Ensure ARK_API_KEY is set in your environment
)

response = client.responses.create(
    model="doubao-seed-1-6-251015",
    input="hello"
)
print(response)