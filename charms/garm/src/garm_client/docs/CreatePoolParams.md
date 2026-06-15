# CreatePoolParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**enable_shell** | **bool** |  | [optional] 
**enabled** | **bool** |  | [optional] 
**extra_specs** | **object** |  | [optional] 
**flavor** | **str** |  | [optional] 
**github_runner_group** | **str** | GithubRunnerGroup is the github runner group in which the runners of this pool will be added to. The runner group must be created by someone with access to the enterprise. | [optional] 
**image** | **str** |  | [optional] 
**max_runners** | **int** |  | [optional] 
**min_idle_runners** | **int** |  | [optional] 
**os_arch** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**priority** | **int** |  | [optional] 
**provider_name** | **str** |  | [optional] 
**runner_bootstrap_timeout** | **int** |  | [optional] 
**runner_prefix** | **str** |  | [optional] 
**tags** | **List[str]** |  | [optional] 
**template_id** | **int** |  | [optional] 

## Example

```python
from garm_client.models.create_pool_params import CreatePoolParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreatePoolParams from a JSON string
create_pool_params_instance = CreatePoolParams.from_json(json)
# print the JSON string representation of the object
print(CreatePoolParams.to_json())

# convert the object into a dict
create_pool_params_dict = create_pool_params_instance.to_dict()
# create an instance of CreatePoolParams from a dict
create_pool_params_from_dict = CreatePoolParams.from_dict(create_pool_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


