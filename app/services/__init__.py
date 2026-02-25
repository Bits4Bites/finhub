import logging

from google import genai
from openai import AsyncOpenAI

from ..config import settings
from . import ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# initialize LLM clients based on configurations
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


# load prompt templates
def read_file_as_single_string(file_path) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = [line.rstrip() for line in file]
            combined_text = "\n".join(lines)
        return combined_text
    except FileNotFoundError:
        logging.error("Error: File '%s' not found.", file_path)
    except PermissionError:
        logging.error("Error: Permission denied for file '%s'.", file_path)
    except Exception as e:
        logging.exception("An unexpected error occurred while reading file '%s': '%e'", file_path, e)
    return ""


templ_name = ai.EVENT_INCOMING_EARNINGS
templ_file = "./resources/prompts/incoming_earnings_events.md"
logging.info("Loading prompt template '%s' from file '%s'...", templ_name, templ_file)
templ_prompt = read_file_as_single_string(templ_file)
ai.prompts[templ_name] = templ_prompt.strip()

templ_name = ai.EVENT_INCOMING_DIVIDENDS
templ_file = "./resources/prompts/incoming_dividend_distribution_events.md"
logging.info("Loading prompt template '%s' from file '%s'...", templ_name, templ_file)
templ_prompt = read_file_as_single_string(templ_file)
ai.prompts[templ_name] = templ_prompt.strip()
