import json

from . import config
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# config.settings.llm_config is in the following format:
# {
#     "vendor_name": {
#         "api_tier": LLMConfig(
#             vendor_name="vendor_name",
#             api_tier="api_tier",
#             api_key="api_key",
#             endpoint="endpoint",
#             models={"model1", "model2"}
#         )
#     }
# }
# vendor_name and api_tier are initially empty, we want to populate their values from the keys
for vendor_name, api_tiers in list(config.settings_llm.llm_config.items()):
    config.settings_llm.llm_config[vendor_name.upper()] = api_tiers.copy()
    for api_tier, llm_cfg in list(api_tiers.items()):
        # remove any entries that have empty api_key and empty endpoint
        # or empty models list
        if (not llm_cfg.api_key and not llm_cfg.endpoint) or llm_cfg.models is None or not llm_cfg.models:
            del api_tiers[api_tier]
        else:
            config.settings_llm.llm_config[vendor_name.upper()][api_tier.upper()] = llm_cfg.copy()
            config.settings_llm.llm_config[vendor_name.upper()][api_tier.upper()].vendor_name = vendor_name.upper()
            config.settings_llm.llm_config[vendor_name.upper()][api_tier.upper()].api_tier = api_tier.upper()

for vendor_name, api_tiers in list(config.settings_llm.llm_config.items()):
    # final cleanup
    for api_tier, llm_cfg in list(api_tiers.items()):
        if not llm_cfg.vendor_name or not llm_cfg.api_tier:
            del api_tiers[api_tier]

    # delete the whole vendor if it has no api_tiers left
    if not api_tiers:
        del config.settings_llm.llm_config[vendor_name]

# config.settings.llm_task_config is in the following format:
# {
#     "task_name": LLMTaskConfig(
#         task_name="task_name",
#         vendor="vendor_name",
#         tier="api_tier",
#         model="model_name"
#     )
# }
# task_name is initially empty, we want to populate its value from the keys
for task_name, llm_task_config in list(config.settings_llm.llm_task_config.items()):
    config.settings_llm.llm_task_config[task_name.upper()] = llm_task_config.copy()
    config.settings_llm.llm_task_config[task_name.upper()].task_name = task_name.upper()

for task_name, llm_cfg in list(config.settings_llm.llm_task_config.items()):
    # remove any entries that have empty vendor or empty tier or empty model
    if not llm_cfg.task_name or not llm_cfg.vendor or not llm_cfg.tier or not llm_cfg.model:
        del config.settings_llm.llm_task_config[task_name]


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


# populate config.market_indices
indices_files = [
    ("ASX20", "./resources/indices/asx20.json"),
    ("ASX50", "./resources/indices/asx50.json"),
    ("ASX100", "./resources/indices/asx100.json"),
    ("ASX200", "./resources/indices/asx200.json"),
    ("ASX300", "./resources/indices/asx300.json"),
    ("NASDAQ100", "./resources/indices/nasdaq100.json"),
    ("SP500", "./resources/indices/sp500.json"),
    ("SP400", "./resources/indices/spmidcap400.json"),
    ("SP600", "./resources/indices/spsmallcap600.json"),
    ("HNX30", "./resources/indices/hnx30.json"),
    ("VN30", "./resources/indices/vn30.json"),
    ("VN100", "./resources/indices/vn100.json"),
]
for index, from_file in indices_files:
    logging.info("Loading index '%s' data from file '%s'...", index, from_file)
    json_content = read_file_as_single_string(from_file)
    if json_content:
        config.market_indices.indices[index.upper()] = {}
        # parse json data as a list of objects
        index_data = json.loads(json_content)
        for entry in index_data["data"]:
            symbol = entry["symbol"].upper()
            company_info = config.CompanyBriefInfo(
                symbol=symbol,
                name=entry.get("company", symbol),
                sector=entry.get("sector", symbol),
                market_cap=int(entry.get("market_cap", 0)),
            )
            config.market_indices.indices[index.upper()][symbol.upper()] = company_info
    else:
        logging.error("Failed to load prompt template from file '%s'", from_file)
