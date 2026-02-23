from . import config

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
for vendor_name, api_tiers in list(config.settings.llm_config.items()):
    config.settings.llm_config[vendor_name.upper()] = api_tiers.copy()
    for api_tier, llm_cfg in list(api_tiers.items()):
        # remove any entries that have empty api_key and empty endpoint
        # or empty models list
        if (not llm_cfg.api_key and not llm_cfg.endpoint) or llm_cfg.models is None or not llm_cfg.models:
            del api_tiers[api_tier]
        else:
            config.settings.llm_config[vendor_name.upper()][api_tier.upper()] = llm_cfg.copy()
            config.settings.llm_config[vendor_name.upper()][api_tier.upper()].vendor_name = vendor_name.upper()
            config.settings.llm_config[vendor_name.upper()][api_tier.upper()].api_tier = api_tier.upper()

    # # delete the whole vendor if it has no api_tiers left
    # if not api_tiers:
    #     del config.settings.llm_config[vendor_name]

for vendor_name, api_tiers in list(config.settings.llm_config.items()):
    # final cleanup
    for api_tier, llm_cfg in list(api_tiers.items()):
        if not llm_cfg.vendor_name or not llm_cfg.api_tier:
            del api_tiers[api_tier]

    # delete the whole vendor if it has no api_tiers left
    if not api_tiers:
        del config.settings.llm_config[vendor_name]

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
for task_name, llm_task_config in list(config.settings.llm_task_config.items()):
    config.settings.llm_task_config[task_name.upper()] = llm_task_config.copy()
    config.settings.llm_task_config[task_name.upper()].task_name = task_name.upper()

for task_name, llm_cfg in list(config.settings.llm_task_config.items()):
    # remove any entries that have empty vendor or empty tier or empty model
    if not llm_cfg.task_name or not llm_cfg.vendor or not llm_cfg.tier or not llm_cfg.model:
        del config.settings.llm_task_config[task_name]
