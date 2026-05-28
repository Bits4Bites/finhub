import logging

from .. import config
from . import ai

# initialize LLM clients based on configurations
for vendor_name, api_tiers in list(config.settings_llm_vendor.vendors.items()):
    v_name = vendor_name.upper()
    for api_tier, llm_config in list(api_tiers.items()):
        a_tier = api_tier.upper()
        if v_name == "GEMINI":
            if "GEMINI" not in config.settings_llm_vendor.client_factories:
                config.settings_llm_vendor.client_factories["GEMINI"] = {}
            config.settings_llm_vendor.client_factories["GEMINI"][a_tier] = config.GeminiClientFactory(
                api_key=llm_config.api_key,
                timeout_sec=300,
            )
        if v_name == "AZURE_OPENAI" or v_name == "AZUREOPENAI" or v_name == "AZURE OPENAI":
            if "AZURE_OPENAI" not in config.settings_llm_vendor.client_factories:
                config.settings_llm_vendor.client_factories["AZURE_OPENAI"] = {}
            config.settings_llm_vendor.client_factories["AZURE_OPENAI"][a_tier] = config.AzureOpenAIClientFactory(
                endpoint=llm_config.endpoint,
                timeout_sec=300,
            )
        if v_name == "OPENROUTER" or v_name == "OPEN_ROUTER" or v_name == "OPEN ROUTER":
            if "OPEN_ROUTER" not in config.settings_llm_vendor.client_factories:
                config.settings_llm_vendor.client_factories["OPEN_ROUTER"] = {}
            config.settings_llm_vendor.client_factories["OPEN_ROUTER"][a_tier] = config.OpenRouterClientFactory(
                api_key=llm_config.api_key,
                endpoint=llm_config.endpoint,
                timeout_sec=300,
            )
        if v_name == "OPENAI":
            if "OPENAI" not in config.settings_llm_vendor.client_factories:
                config.settings_llm_vendor.client_factories["OPENAI"] = {}
            config.settings_llm_vendor.client_factories["OPENAI"][a_tier] = config.OpenAIClientFactory(
                api_key=llm_config.api_key,
                timeout_sec=300,
            )


# load prompt templates
def read_file_as_single_string(file_path) -> str:
    try:
        with open(file_path, encoding="utf-8") as file:
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
]
template_file_list = [
    "./resources/prompts/asx_new_listings.md",
    "./resources/prompts/analyze_asx_listings.md",
    "./resources/prompts/analyze_asx_dividend.md",
    "./resources/prompts/analyze_us_dividend.md",
    "./resources/prompts/analyze_vn_dividend.md",
]

for tmpl_name, tmpl_file in zip(template_list, template_file_list):
    logging.info("Loading template '%s' from file '%s'...", tmpl_name, tmpl_file)
    tmpl_content = read_file_as_single_string(tmpl_file)
    if tmpl_content:
        ai.prompts[tmpl_name] = tmpl_content
    else:
        logging.error("Failed to load prompt template from file '%s'", tmpl_file)
