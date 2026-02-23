from google import genai
from openai import AsyncOpenAI

from ..config import settings
from . import ai

for vendor_name, api_tiers in list(settings.llm_config.items()):
    for api_tier, llm_config in list(api_tiers.items()):
        if vendor_name.upper() == "GEMINI":
            ai.geminiClients[api_tier.upper()] = genai.Client(api_key=llm_config.api_key)
        if vendor_name.upper() == "AZURE_OPENAI":
            ai.azureOpenAIClients[api_tier.upper()] = AsyncOpenAI(
                api_key=llm_config.api_key, base_url=llm_config.endpoint
            )
        if vendor_name.upper() == "OPENAI":
            ai.openAIClients[api_tier.upper()] = AsyncOpenAI(api_key=llm_config.api_key)
