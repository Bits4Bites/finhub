import logging

from .ai_helper import GeminiClientFactory, AzureOpenAIClientFactory, OpenRouterClientFactory, OpenAIClientFactory
from ..config import settings_llm
from . import ai, ai_helper

# initialize LLM clients based on configurations
for vendor_name, api_tiers in list(settings_llm.llm_config.items()):
    for api_tier, llm_config in list(api_tiers.items()):
        if vendor_name.upper() == "GEMINI":
            ai_helper.geminiClients[api_tier.upper()] = GeminiClientFactory(api_key=llm_config.api_key, timeout_sec=300)
        if vendor_name.upper() == "AZURE_OPENAI" or vendor_name.upper() == "AZUREOPENAI":
            ai_helper.azureOpenAIClients[api_tier.upper()] = AzureOpenAIClientFactory(
                endpoint=llm_config.endpoint,
                timeout_sec=300,
            )
        if vendor_name.upper() == "OPENROUTER" or vendor_name.upper() == "OPEN_ROUTER":
            ai_helper.openRouterClients[api_tier.upper()] = OpenRouterClientFactory(
                api_key=llm_config.api_key,
                endpoint=llm_config.endpoint,
                timeout_sec=300,
            )
        if vendor_name.upper() == "OPENAI":
            ai_helper.openAIClients[api_tier.upper()] = OpenAIClientFactory(api_key=llm_config.api_key, timeout_sec=300)


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


template_list = [
    ai.EVENT_ASX_NEW_LISTINGS,
    ai.ANALYZE_ASX_LISTINGS,
    ai.ANALYZE_ASX_DIVIDEND,
    ai.ANALYZE_US_DIVIDEND,
    ai.ANALYZE_VN_DIVIDEND,
    ai.ANALYZE_PORTFOLIO_ALLOCATION,
    ai.ANALYZE_PORTFOLIO_SWING,
    ai.ANALYZE_PORTFOLIO_HYBRID,
    ai.BUILD_PORTFOLIO_ALLOCATION,
    ai.BUILD_PORTFOLIO_SWING,
    ai.BUILD_PORTFOLIO_HYBRID,
]
template_file_list = [
    "./resources/prompts/asx_new_listings.md",
    "./resources/prompts/analyze_asx_listings.md",
    "./resources/prompts/analyze_asx_dividend.md",
    "./resources/prompts/analyze_us_dividend.md",
    "./resources/prompts/analyze_vn_dividend.md",
    "./resources/prompts/analyze_portfolio_allocation.md",
    "./resources/prompts/analyze_portfolio_swing.md",
    "./resources/prompts/analyze_portfolio_hybrid.md",
    "./resources/prompts/build_portfolio_allocation.md",
    "./resources/prompts/build_portfolio_swing.md",
    "./resources/prompts/build_portfolio_hybrid.md",
]

for tmpl_name, tmpl_file in zip(template_list, template_file_list):
    logging.info("Loading template '%s' from file '%s'...", tmpl_name, tmpl_file)
    tmpl_content = read_file_as_single_string(tmpl_file)
    if tmpl_content:
        ai.prompts[tmpl_name] = tmpl_content
    else:
        logging.error("Failed to load prompt template from file '%s'", tmpl_file)
