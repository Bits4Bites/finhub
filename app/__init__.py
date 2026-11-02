import logging

from . import config


class CustomLoggerConfig(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, logging.WARNING if name.startswith("azure.") else level)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s: %(message)s")
logging.setLoggerClass(CustomLoggerConfig)

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
for vendor_name, api_tiers in list(config.settings_llm_vendor.vendors.items()):
    config.settings_llm_vendor.vendors[vendor_name.upper()] = api_tiers.copy()
    for api_tier, llm_cfg in list(api_tiers.items()):
        # remove any entries that have empty api_key and empty endpoint
        # or empty models list
        if (not llm_cfg.api_key and not llm_cfg.endpoint) or llm_cfg.models is None or not llm_cfg.models:
            logging.warning(
                f"Removing LLM config for vendor '{vendor_name}', tier '{api_tier}' due to missing API key, endpoint, or models."
            )
            del api_tiers[api_tier]
        else:
            config.settings_llm_vendor.vendors[vendor_name.upper()][api_tier.upper()] = llm_cfg.model_copy()
            config.settings_llm_vendor.vendors[vendor_name.upper()][api_tier.upper()].vendor_name = vendor_name.upper()
            config.settings_llm_vendor.vendors[vendor_name.upper()][api_tier.upper()].api_tier = api_tier.upper()

for vendor_name, api_tiers in list(config.settings_llm_vendor.vendors.items()):
    # final cleanup
    for api_tier, llm_cfg in list(api_tiers.items()):
        if not llm_cfg.vendor_name or not llm_cfg.api_tier:
            logging.warning(
                f"Removing LLM config for vendor '{vendor_name}', tier '{api_tier}' due to missing vendor name or API tier."
            )
            del api_tiers[api_tier]

    # delete the whole vendor if it has no api_tiers left
    if not api_tiers:
        logging.warning(f"Removing vendor '{vendor_name}' as it has no valid API tiers left.")
        del config.settings_llm_vendor.vendors[vendor_name]

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
for task_name, llm_task_config in list(config.settings_llm_task.tasks.items()):
    config.settings_llm_task.tasks[task_name.upper()] = llm_task_config.model_copy()
    config.settings_llm_task.tasks[task_name.upper()].task_name = task_name.upper()

for task_name, llm_cfg in list(config.settings_llm_task.tasks.items()):
    # remove any entries that have empty vendor or empty tier or empty model
    if not llm_cfg.task_name or not llm_cfg.vendor or not llm_cfg.tier or not llm_cfg.model:
        logging.warning(
            f"Removing LLM task config for task '{task_name}' due to missing task name, vendor, tier, or model."
        )
        del config.settings_llm_task.tasks[task_name]
