# CreateScaleSetParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**disable_update** | **bool** |  | [optional] 
**enable_shell** | **bool** |  | [optional] 
**enabled** | **bool** |  | [optional] 
**extra_specs** | **object** |  | [optional] 
**flavor** | **str** |  | [optional] 
**github_runner_group** | **str** | GithubRunnerGroup is the github runner group in which the runners of this pool will be added to. The runner group must be created by someone with access to the enterprise. | [optional] 
**image** | **str** |  | [optional] 
**labels** | **List[str]** |  | [optional] 
**max_runners** | **int** |  | [optional] 
**min_idle_runners** | **int** |  | [optional] 
**name** | **str** |  | [optional] 
**os_arch** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**provider_name** | **str** |  | [optional] 
**runner_bootstrap_timeout** | **int** |  | [optional] 
**runner_prefix** | **str** |  | [optional] 
**scale_set_id** | **int** |  | [optional] 
**template_id** | **int** |  | [optional] 

## Example

```python
from garm_client.models.create_scale_set_params import CreateScaleSetParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateScaleSetParams from a JSON string
create_scale_set_params_instance = CreateScaleSetParams.from_json(json)
# print the JSON string representation of the object
print(CreateScaleSetParams.to_json())

# convert the object into a dict
create_scale_set_params_dict = create_scale_set_params_instance.to_dict()
# create an instance of CreateScaleSetParams from a dict
create_scale_set_params_from_dict = CreateScaleSetParams.from_dict(create_scale_set_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


